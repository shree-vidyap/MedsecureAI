import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "medsecure_ai")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH_MB", "8")) * 1024 * 1024
    UPLOAD_FOLDER = os.path.join("static", "uploads")
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}


# ---- Phase 3: AI model settings ----
Config.MODEL_DIR = "trained_model"
Config.MODEL_FILE = "medicine_classifier.keras"
Config.CLASS_FILE = "class_indices.json"
Config.IMG_SIZE = (224, 224)
# "rescale" = pixel/255 ,  "mobilenet" = MobileNetV2 preprocess_input (-1 to 1). Use what you used in training.
Config.PREPROCESS_MODE = os.getenv("PREPROCESS_MODE", "rescale")
# Below this confidence the result becomes "Suspicious"
Config.CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.85"))
# Laplacian variance below this = unclear image
Config.BLUR_THRESHOLD = float(os.getenv("BLUR_THRESHOLD", "30"))


# ---- Phase 4: OCR + expiry ----
Config.TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")          # leave empty to auto-detect
Config.OCR_LANG = os.getenv("OCR_LANG", "eng")
Config.EXPIRY_SOON_DAYS = int(os.getenv("EXPIRY_SOON_DAYS", "30"))
