# MedSecure AI - AI-Based Medicine Verification and Analysis System

Assistive tool: it does NOT replace professional / pharmacist verification.

## Setup (Windows, VS Code terminal)
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-ai.txt
```
1. **MongoDB** (local, "Install as Service") - https://www.mongodb.com/try/download/community
2. **Tesseract OCR** - https://github.com/UB-Mannheim/tesseract/wiki (default folder `C:\Program Files\Tesseract-OCR\`).
   If it is elsewhere, set `TESSERACT_CMD=...` in `.env`.
3. Put your trained model files in `trained_model/` (see below). The app works without them, but then it shows
   "Authenticity not assessed" (OCR, expiry, QR/barcode, history, PDF all still work).
4. Run: `python app.py`  ->  http://127.0.0.1:5000
5. Change `SECRET_KEY` in `.env` to your own long random text.

## Pages
Get Started, Register / Login, Dashboard (+ expiry reminders), Analyze (Upload / Live / QR / Barcode), Result,
History (Genuine / Suspicious / Counterfeit / Expired filters), Reports (view / PDF / delete), Profile, Nearby Pharmacy.

## Helper scripts
| Command | What it checks |
|---|---|
| `python check_model.py [image]` | model files, loading, a test prediction |
| `python check_ocr.py image.jpg` | what Tesseract reads + extracted fields |
| `python check_codes.py image.jpg` | QR / barcode detection |

## Model (trained_model/)
`medicine_classifier.keras`, `class_indices.json` (+ `model_meta.json`, `training_report.json` from training).
Training + dataset steps: `training/README.md`. Dataset report: `dataset/DATASETS.md`.
The model is BINARY (Genuine / Counterfeit). "Suspicious" is NOT a trained class: it is shown when the model confidence
is below `CONFIDENCE_THRESHOLD` (default 0.85, set in `.env`).

## Honest limitations (write these in your report)
- Counterfeit class is trained with SIMULATED altered samples unless you have real counterfeit photos.
- OCR depends on photo quality; medicine name is a "largest text" heuristic and must be checked by the user.
- QR / barcode data is shown as scanned, not verified.
- No packaging score is shown, because no packaging-analysis component exists.
