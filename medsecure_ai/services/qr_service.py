"""QR detection with OpenCV QRCodeDetector. Never raises. Returns {'data': str|None, 'error': str|None}."""
import cv2

from services import code_utils


def detect(path):
    out = {"data": None, "error": None}
    try:
        img = code_utils.load(path)
        det = cv2.QRCodeDetector()
        for v in code_utils.variants(img):
            data, _, _ = det.detectAndDecode(v)
            if data:
                out["data"] = data.strip()[:200]
                return out
            try:
                ok, infos, _, _ = det.detectAndDecodeMulti(v)
                if ok:
                    found = [s for s in infos if s]
                    if found:
                        out["data"] = found[0].strip()[:200]
                        return out
            except Exception:
                pass
    except Exception as e:
        out["error"] = f"QR scan failed: {e}"
    return out
