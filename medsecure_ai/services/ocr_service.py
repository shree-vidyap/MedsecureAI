"""OCR with Tesseract + simple, honest field extraction. Never raises, never invents data."""
import os
import re
import shutil
from statistics import mean

import cv2
import numpy as np

from services import expiry_service as ex

METADATA_LINE = re.compile(r"\b(MFG|MFD|EXP\w*|BATCH|B\.?\s?NO|LOT|PRICE|MRP|M\.?R\.?P|MANUFACTURED|MARKETED|STORE|KEEP|WARNING|SCHEDULE|DATE)\b", re.I)
FORM_WORDS = re.compile(r"\b(TABLETS?|CAPSULES?|SYRUP|INJECTION|SUSPENSION|CREAM|OINTMENT|DROPS?|I\.?P\.?|B\.?P\.?|U\.?S\.?P\.?|MG|ML|MCG|FILM|COATED|STRIP|OF|ONLY|FOR|USE|EACH)\b", re.I)
COMPANY = re.compile(r"\b(PHARMA\w*|LABORATOR\w*|LABS?|LIMITED|LTD\.?|PVT\.?|HEALTHCARE|LIFE\s?SCIENCES?|REMEDIES|INDUSTRIES|DRUGS?|BIOTECH|FORMULATIONS?)\b", re.I)
BATCH = re.compile(r"(?:B\.?\s?NO\.?|BATCH\s*(?:NO\.?|NUMBER|#)?|LOT\s*(?:NO\.?)?)\s*[:.\-]?\s*([A-Z0-9][A-Z0-9\-/]{2,19})", re.I)


def _setup(cfg):
    try:
        import pytesseract
    except ImportError:
        return None, "pytesseract is not installed. Run: pip install pytesseract"
    cmd = cfg.get("TESSERACT_CMD") or shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if not (os.path.isfile(cmd) or shutil.which(cmd)):
        return None, ("Tesseract OCR is not installed. Install it from github.com/UB-Mannheim/tesseract/wiki "
                      "or set TESSERACT_CMD in the .env file.")
    pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        pytesseract.get_tesseract_version()
    except Exception as e:
        return None, f"Tesseract could not start: {e}"
    return pytesseract, None


def _variants(path):
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    scale = min(2.0, 1800 / max(h, w))
    if abs(scale - 1) > 0.05:
        g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(g)
    thr = cv2.adaptiveThreshold(cv2.medianBlur(g, 3), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
    return [(clahe, 6), (clahe, 11), (thr, 11)]


def _read(pt, img, psm, lang):
    d = pt.image_to_data(img, lang=lang, config=f"--oem 3 --psm {psm}", output_type=pt.Output.DICT)
    words = []
    for i, t in enumerate(d["text"]):
        t = t.strip()
        try:
            c = float(d["conf"][i])
        except ValueError:
            continue
        if t and c >= 0:
            words.append({"text": t, "conf": c, "h": d["height"][i], "left": d["left"][i],
                          "key": (d["block_num"][i], d["par_num"][i], d["line_num"][i])})
    return words, sum(w["conf"] for w in words if w["conf"] >= 50)


def _lines(words):
    groups = {}
    for w in words:
        groups.setdefault(w["key"], []).append(w)
    lines = []
    for ws in groups.values():
        ws.sort(key=lambda w: w["left"])
        lines.append({"text": " ".join(w["text"] for w in ws), "conf": mean(w["conf"] for w in ws),
                      "h": mean(w["h"] for w in ws)})
    return lines


def _clean(s):
    return re.sub(r"\s+", " ", s).strip(" :;,.-|_")


def _manufacturer(lines):
    for i, ln in enumerate(lines):
        m = re.search(r"(?:MANUFACTURED|MFD\.?|MFG\.?|MARKETED)\s*BY\s*[:\-]?\s*(.*)", ln["text"], re.I)
        if m:
            val = _clean(m.group(1))
            if len(val) < 4 and i + 1 < len(lines):
                val = _clean(lines[i + 1]["text"])
            val = re.split(r"\d{3,}|,", val)[0]
            if len(_clean(val)) >= 4 and ln["conf"] >= 50:
                return _clean(val)[:70]
    for ln in lines:
        if COMPANY.search(ln["text"]) and not METADATA_LINE.search(ln["text"]) and ln["conf"] >= 50:
            return _clean(re.split(r"\d{3,}|,", ln["text"])[0])[:70]
    return None


def _name(lines):
    best = None
    for ln in lines:
        if ln["conf"] < 55 or METADATA_LINE.search(ln["text"]) or COMPANY.search(ln["text"]):
            continue
        text = FORM_WORDS.sub(" ", ln["text"])
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text)]
        name = " ".join(words[:3])
        if len(name) >= 4 and (best is None or ln["h"] > best[0]):
            best = (ln["h"], name.title())
    return best[1] if best else None


def _batch(text):
    for m in BATCH.finditer(text.upper()):
        v = m.group(1)
        if re.search(r"\d", v) and not re.fullmatch(r"(MFG|EXP|MFD)\w*", v):
            return v
    return None


def analyze(path, cfg):
    """Always returns a dict. Fields that are not found are None."""
    out = {"available": False, "error": None, "text": "", "confidence": None, "name": None, "manufacturer": None,
           "batch": None, "mfg": None, "exp": None, "exp_iso": None, "expiry_status": None, "days_left": None}
    pt, err = _setup(cfg)
    if err:
        out["error"] = err
        return out
    out["available"] = True
    try:
        best = None
        for img, psm in _variants(path):
            words, score = _read(pt, img, psm, cfg["OCR_LANG"])
            if best is None or score > best[1]:
                best = (words, score)
        words = best[0] if best else []
    except Exception as e:
        out["error"] = f"OCR failed: {e}"
        return out

    words = [w for w in words if len(w["text"]) >= 1]
    if not words:
        out["error"] = "Medicine text could not be detected. Please upload a clearer image."
        return out
    lines = _lines(words)
    text = "\n".join(l["text"] for l in lines)
    out["text"] = text
    out["confidence"] = round(mean(w["conf"] for w in words if len(w["text"]) >= 2) if any(len(w["text"]) >= 2 for w in words) else 0.0, 1)

    out["name"] = _name(lines)
    out["manufacturer"] = _manufacturer(lines)
    out["batch"] = _batch(text)
    mfg, exp = ex.extract_dates(text)
    if mfg:
        out["mfg"] = ex.display(mfg)
    if exp:
        out["exp"] = ex.display(exp)
        out["exp_iso"] = ex.end_date(exp).isoformat()
        out["expiry_status"], out["days_left"] = ex.expiry_status(exp, soon_days=cfg["EXPIRY_SOON_DAYS"])
    return out
