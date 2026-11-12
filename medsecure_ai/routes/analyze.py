from flask import render_template, request, redirect, url_for, session, flash, current_app, jsonify

from routes.main import main_bp
from services import model_service, ocr_service, qr_service, barcode_service, code_verify
from utils.auth import login_required
from utils.image_utils import allowed_file, save_upload, blur_score


@main_bp.route("/analyze")
@login_required
def analyze():
    ok, err = model_service.model_status(current_app.config)
    return render_template("analyze.html", model_ok=ok, model_err=err, active="upload", mascot_msgs=[
        "Upload a clear photo of the medicine pack.",
        "Keep the label facing the camera.",
        "Good light gives better results.",
        "Make sure the text is not blurry."])


@main_bp.route("/analyze/upload", methods=["GET", "POST"])
@login_required
def analyze_upload():
    if request.method == "GET":
        return redirect(url_for("main.analyze"))
    cfg = current_app.config
    file = request.files.get("image")

    if not file or file.filename == "":
        flash("Please upload a medicine image.", "danger")
        return redirect(url_for("main.analyze"))
    if not allowed_file(file.filename, cfg["ALLOWED_EXTENSIONS"]):
        flash("Unsupported file format. Please upload JPG, JPEG, or PNG.", "danger")
        return redirect(url_for("main.analyze"))

    try:
        rel_path, abs_path = save_upload(file, session["user_id"], "static/uploads")
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("main.analyze"))

    if blur_score(abs_path) < cfg["BLUR_THRESHOLD"]:
        flash("The image is unclear. Please upload a clearer medicine image.", "warning")
        return redirect(url_for("main.analyze"))

    # 1) AI authenticity (optional: works only when a trained model is available)
    label = conf = top = None
    model_ok, model_err = model_service.model_status(cfg)
    if model_ok:
        try:
            probs = model_service.predict(abs_path, cfg)
            label, conf, top = model_service.classify(probs, cfg["CONFIDENCE_THRESHOLD"])
        except Exception as e:
            import traceback; traceback.print_exc()
            flash(f"AI analysis failed: {e}", "danger")
            return redirect(url_for("main.analyze"))

    # 2) OCR + expiry (never crashes the request)
    try:
        o = ocr_service.analyze(abs_path, cfg)
    except Exception as e:
        o = {"available": False, "error": f"OCR failed: {e}", "text": "", "confidence": None, "name": None,
             "manufacturer": None, "batch": None, "mfg": None, "exp": None, "exp_iso": None,
             "expiry_status": None, "days_left": None}

    # 3) QR + barcode from the same photo (a value saved earlier from the live scanner is used if the photo has none)
    scanned = session.pop("scanned", {}) or {}
    try:
        q = qr_service.detect(abs_path)
    except Exception:
        q = {"data": None}
    try:
        b = barcode_service.detect(abs_path)
    except Exception:
        b = {"data": None, "type": None, "available": False, "error": None}
    qr = {"data": q["data"], "source": "image"} if q.get("data") else (
        {"data": scanned["qr"], "source": "scanner"} if scanned.get("qr") else None)
    bc = {"data": b["data"], "type": b.get("type"), "source": "image"} if b.get("data") else (
        {"data": scanned["barcode"], "type": None, "source": "scanner"} if scanned.get("barcode") else None)

    meta = model_service.model_meta()
    data = {
        "poc": model_ok and "simulated" in str(meta.get("counterfeit_source", "")),
        "qr": qr, "barcode": bc, "barcode_error": None if b.get("available", True) else b.get("error"),
        "image": rel_path,
        "result": label,                                   # None when the AI model is not available
        "ai_confidence": round(conf * 100, 1) if conf is not None else None,
        "overall_confidence": round(conf * 100, 1) if conf is not None else None,
        "model_note": None if model_ok else model_err,
        "threshold": round(cfg["CONFIDENCE_THRESHOLD"] * 100),
        "name": o["name"], "manufacturer": o["manufacturer"], "batch": o["batch"],
        "mfg": o["mfg"], "exp": o["exp"], "exp_iso": o["exp_iso"],
        "expiry_status": o["expiry_status"], "days_left": o["days_left"],
        "ocr_conf": o["confidence"], "ocr_error": o["error"], "ocr_text": (o["text"] or "")[:400],
    }
    # 4) offline code checks (barcode check digit, QR vs printed batch/expiry). A hard failure stops a "Genuine" label.
    if data["result"] == "Genuine" and code_verify.verify(data)["hard_fail"]:
        data["result"] = "Suspicious"
        data["override"] = True
    session["last_analysis"] = data
    return redirect(url_for("main.result"))


@main_bp.route("/result")
@login_required
def result():
    data = session.get("last_analysis")
    if not data:
        flash("Please upload a medicine image.", "warning")
        return redirect(url_for("main.analyze"))
    meta = model_service.model_meta()
    simulated = "simulated" in str(meta.get("counterfeit_source", ""))
    a = dict(data)
    a["verify"] = code_verify.verify(a)          # recomputed on display, not kept in the cookie session
    return render_template("result.html", a=a, simulated=simulated)


SCANNERS = {
    "live": dict(title="Live Scanner", icon="bi-camera", hint="Point the camera at the medicine pack",
                 msgs=["Hold the pack steady in the frame.", "Make sure the label is readable.",
                       "Tap Capture when you are ready."]),
    "qr": dict(title="QR Scanner", icon="bi-qr-code-scan", hint="Point the camera at the QR code",
               msgs=["Show me the QR code on the pack.", "Keep it inside the frame.",
                     "Hold steady, I will detect it."]),
    "barcode": dict(title="Barcode Scanner", icon="bi-upc-scan", hint="Point the camera at the barcode",
                    msgs=["Show me the barcode on the pack.", "Keep the barcode flat and well lit.",
                          "Hold steady, I will detect it."]),
}


def _scanner_view(mode):
    cfg = SCANNERS[mode]
    return render_template("scanner.html", mode=mode, title=cfg["title"], icon=cfg["icon"],
                           hint=cfg["hint"], mascot_msgs=cfg["msgs"], active=mode)


for _m in SCANNERS:
    main_bp.add_url_rule(f"/analyze/{_m}", endpoint=f"analyze_{_m}",
                         view_func=login_required((lambda m: (lambda: _scanner_view(m)))(_m)))


@main_bp.route("/scan/save", methods=["POST"])
@login_required
def scan_save():
    """The live QR / barcode scanner page sends what it read. It is kept in the session and
    added to the NEXT analysis, so it appears in the Result page. Nothing is verified here."""
    data = request.get_json(silent=True) or {}
    kind, value = data.get("type"), data.get("value")
    if kind not in ("qr", "barcode") or not isinstance(value, str) or not value.strip():
        return jsonify(ok=False, error="Invalid scan data."), 400
    scanned = session.get("scanned", {})
    scanned[kind] = value.strip()[:200]
    session["scanned"] = scanned
    return jsonify(ok=True)
