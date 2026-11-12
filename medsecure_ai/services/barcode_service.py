"""1D barcode detection. Tries OpenCV's barcode detector first, then pyzbar (optional) as a fallback.
Never raises. Returns {'data','type','available','error'}."""
import cv2

from services import code_utils


def _opencv(img):
    det = cv2.barcode.BarcodeDetector()
    if hasattr(det, "detectAndDecodeWithType"):              # newer OpenCV: (ok, infos, types, points)
        ok, infos, types, _ = det.detectAndDecodeWithType(img)
        if ok:
            for i, s in enumerate(infos):
                if s:
                    return s, (types[i] if i < len(types) else "")
        return None
    res = det.detectAndDecode(img)                           # older OpenCV
    if isinstance(res[0], str):                              # (info, points, straight_code)
        return (res[0], "") if res[0] else None
    ok, infos, types = res[0], res[1], res[2]                # (ok, infos, types, points)
    if ok:
        for i, s in enumerate(infos):
            if s:
                return s, (types[i] if i < len(types) else "")
    return None


def _pyzbar(img):
    from pyzbar import pyzbar
    for s in pyzbar.decode(img):
        if s.type != "QRCODE" and s.data:
            return s.data.decode("utf-8", "ignore"), s.type
    return None


def detect(path):
    out = {"data": None, "type": None, "available": False, "error": None}
    engines = []
    if hasattr(cv2, "barcode"):
        engines.append(_opencv)
    try:
        import pyzbar.pyzbar  # noqa: F401
        engines.append(_pyzbar)
    except Exception:
        pass
    if not engines:
        out["error"] = "Barcode decoder is not available on this computer."
        return out
    out["available"] = True
    ran_ok, last_err = False, None
    try:
        img = code_utils.load(path)
        for v in code_utils.variants(img):
            for engine in engines:
                try:
                    r = engine(v)
                    ran_ok = True
                except Exception as e:
                    r, last_err = None, e
                if r:
                    out["data"], out["type"] = r[0].strip()[:100], (r[1] or None)
                    return out
    except Exception as e:
        out["error"] = f"Barcode scan failed: {e}"
        return out
    if not ran_ok:                                  # every decoder call crashed -> do NOT pretend "not detected"
        out["available"] = False
        out["error"] = f"Barcode decoder does not work with this OpenCV version ({last_err})."
    return out
