import os
import uuid

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError


def allowed_file(filename, allowed):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def save_upload(file_storage, user_id, upload_root):
    """Verify the image with Pillow, then save it as a safe-named file. Returns (relative_path, abs_path)."""
    try:
        img = Image.open(file_storage.stream)
        img.verify()
    except (UnidentifiedImageError, OSError):
        raise ValueError("Unsupported file format. Please upload JPG, JPEG, or PNG.")
    file_storage.stream.seek(0)
    img = Image.open(file_storage.stream).convert("RGB")
    folder = os.path.join(upload_root, user_id)
    os.makedirs(folder, exist_ok=True)
    name = f"{uuid.uuid4().hex}.jpg"
    abs_path = os.path.join(folder, name)
    img.save(abs_path, "JPEG", quality=92)
    return f"uploads/{user_id}/{name}", abs_path


def blur_score(path):
    """Higher = sharper. Uses variance of Laplacian on a resized grayscale image."""
    data = np.fromfile(path, dtype=np.uint8)          # works with Windows paths
    img = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0.0
    h, w = img.shape
    scale = 600 / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    return float(cv2.Laplacian(img, cv2.CV_64F).var())
