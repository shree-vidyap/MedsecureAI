"""Run:  python check_ocr.py  path\\to\\medicine.jpg   -> shows what the OCR reads and which fields it finds."""
import sys

from config import Config
from services import ocr_service

if len(sys.argv) < 2:
    sys.exit("Usage: python check_ocr.py image.jpg")
cfg = {k: getattr(Config, k) for k in dir(Config) if k.isupper()}
r = ocr_service.analyze(sys.argv[1], cfg)
print("Tesseract available:", r["available"])
if r["error"]:
    print("MESSAGE:", r["error"])
print("OCR confidence     :", r["confidence"])
print("----- text read -----\n" + (r["text"] or "(nothing)") + "\n---------------------")
for k in ("name", "manufacturer", "batch", "mfg", "exp", "expiry_status", "days_left"):
    print(f"{k:<14}:", r[k] if r[k] is not None else "Not Detected")
