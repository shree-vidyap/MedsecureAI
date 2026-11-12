"""Run:  python check_model.py            (checks files + model)
        python check_model.py image.jpg  (also predicts on one image)
"""
import os
import sys

from config import Config
from services import model_service as ms

cfg = {k: getattr(Config, k) for k in dir(Config) if k.isupper()}
folder = cfg["MODEL_DIR"]
print("=" * 55, "\nMedSecure AI - model check\n" + "=" * 55)

# 1. files
ok = True
for name in (cfg["MODEL_FILE"], cfg["CLASS_FILE"]):
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        print(f"[FAIL] {path} NOT FOUND"); ok = False
    else:
        size = os.path.getsize(path)
        print(f"[{'OK' if size else 'FAIL'}] {path}  ({size:,} bytes)")
        if size == 0:
            ok = False
cls = os.path.join(folder, cfg["CLASS_FILE"])
if os.path.exists(cls):
    print("       class_indices.json content ->", open(cls, encoding="utf-8-sig").read()[:200] or "(EMPTY)")
if not ok:
    print("\nFix the files above first. A real model file is usually several MB (MobileNetV2 ~ 10-30 MB).")
    sys.exit(1)

# 2. load
print("\nLoading model (first time takes 10-30 seconds)...")
loaded, err = ms.model_status(cfg)
if not loaded:
    print("[FAIL]", err); sys.exit(1)
import tensorflow as tf  # noqa
m = ms._state["model"]
print("[OK] Model loaded")
print("     input shape :", m.input_shape)
print("     output shape:", m.output_shape)
print("     classes     :", ms._state["index_to_name"])
print("     image size  :", ms._state["img_size"] or cfg["IMG_SIZE"])
print("     preprocess  :", ms._state["meta"].get("preprocess") or cfg["PREPROCESS_MODE"])
print("     meta        :", ms._state["meta"] or "(no model_meta.json)")

# 3. predict
import numpy as np
from PIL import Image
path = sys.argv[1] if len(sys.argv) > 1 else None
if not path:
    path = "_check_dummy.jpg"
    Image.fromarray((np.random.rand(300, 300, 3) * 255).astype("uint8")).save(path)
    print("\nNo image given, using a random test image (result is meaningless).")
probs = ms.predict(path, cfg)
label, conf, top = ms.classify(probs, cfg["CONFIDENCE_THRESHOLD"])
print("\nProbabilities:", {k: round(v, 4) for k, v in probs.items()})
print(f"Result: {label}  (confidence {conf*100:.1f}%, threshold {cfg['CONFIDENCE_THRESHOLD']*100:.0f}%)")
if path == "_check_dummy.jpg":
    os.remove(path)
print("\n[OK] Everything works. Start the app with: python app.py")
