"""Run:  python check_codes.py  path\\to\\medicine.jpg   -> shows if a QR code / barcode is found in the photo."""
import sys

from services import barcode_service, qr_service

if len(sys.argv) < 2:
    sys.exit("Usage: python check_codes.py image.jpg")
q = qr_service.detect(sys.argv[1]); b = barcode_service.detect(sys.argv[1])
print("QR      :", q["data"] if q["data"] else "QR Code Not Detected.", ("(" + q["error"] + ")") if q["error"] else "")
print("Barcode :", (f'{b["data"]} ({b["type"]})' if b["data"] else "Barcode Not Detected."), ("(" + b["error"] + ")") if b["error"] else "")
print("Barcode decoder available:", b["available"])
