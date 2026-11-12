"""Loads the trained MobileNetV2 model once and predicts on an image.

The model is BINARY (genuine / counterfeit). "Suspicious" is NOT a trained class.
It is decided by classify(): if the model is not confident enough, we call it Suspicious.
"""
import json
import os

import numpy as np
from PIL import Image

_state = {"loaded": False, "model": None, "index_to_name": None, "error": None, "img_size": None, "meta": {}}


def _map_name(raw):
    r = raw.lower()
    if any(k in r for k in ("genuine", "real", "original", "authentic")):
        return "genuine"
    if any(k in r for k in ("counterfeit", "fake", "spurious", "duplicate")):
        return "counterfeit"
    return None


def _load(cfg):
    if _state["loaded"]:
        return
    _state["loaded"] = True
    model_path = os.path.join(cfg["MODEL_DIR"], cfg["MODEL_FILE"])
    class_path = os.path.join(cfg["MODEL_DIR"], cfg["CLASS_FILE"])
    if not os.path.exists(model_path) or not os.path.exists(class_path):
        _state["error"] = ("Model files not found. Put medicine_classifier.keras and "
                           "class_indices.json inside the trained_model folder.")
        return
    # 1) check class_indices.json first (cheap)
    try:
        with open(class_path, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
        mapping = {}
        for name, idx in raw.items():
            mapped = _map_name(name)
            if mapped is None:
                _state["error"] = (f'class_indices.json has an unknown class "{name}". '
                                   'Use names like "genuine" and "counterfeit".')
                return
            mapping[int(idx)] = mapped
    except (json.JSONDecodeError, AttributeError, ValueError):
        _state["error"] = ('class_indices.json is empty or not valid JSON. '
                           'It should look like: {"counterfeit": 0, "genuine": 1}')
        return
    meta_path = os.path.join(cfg["MODEL_DIR"], "model_meta.json")      # written by training/train_model.py
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8-sig") as f:
                _state["meta"] = json.load(f)
        except Exception:
            _state["meta"] = {}
    # 2) load TensorFlow + model
    try:
        import tensorflow as tf
    except ImportError:
        _state["error"] = "TensorFlow is not installed. Run: pip install tensorflow"
        return
    try:
        _state["index_to_name"] = mapping
        model = tf.keras.models.load_model(model_path)
        _state["model"] = model
        shp = model.input_shape                      # e.g. (None, 224, 224, 3)
        if isinstance(shp, (list, tuple)) and len(shp) == 4 and shp[1] and shp[2]:
            _state["img_size"] = (int(shp[2]), int(shp[1]))
    except Exception as e:  # never crash the app
        _state["error"] = f"Could not load medicine_classifier.keras: {e}"


def _shift(p_genuine, t):
    """Moves the genuine/counterfeit boundary from 0.5 to t (t was chosen on the validation set). Keeps 0..1 scale."""
    import math
    eps = 1e-6
    p, t = min(max(p_genuine, eps), 1 - eps), min(max(t, eps), 1 - eps)
    z = math.log(p / (1 - p)) - math.log(t / (1 - t))
    return 1 / (1 + math.exp(-z))


def model_meta():
    return _state["meta"]


def model_status(cfg):
    _load(cfg)
    return (_state["model"] is not None), _state["error"]


def predict(image_path, cfg):
    """Returns {'genuine': p, 'counterfeit': p}. Raises RuntimeError if model is unavailable."""
    ok, err = model_status(cfg)
    if not ok:
        raise RuntimeError(err)
    img = Image.open(image_path).convert("RGB").resize(_state["img_size"] or cfg["IMG_SIZE"])
    x = np.asarray(img, dtype="float32")
    mode = _state["meta"].get("preprocess") or cfg["PREPROCESS_MODE"]
    if mode == "raw":              # model has its own Rescaling layer inside (our trained model)
        pass
    elif mode == "mobilenet":
        x = x / 127.5 - 1.0
    else:
        x = x / 255.0
    try:
        out = _state["model"].predict(x[None, ...], verbose=0)[0]
    except Exception as e:
        raise RuntimeError(f"Model prediction failed: {e}")
    names = _state["index_to_name"]
    if out.size > 1 and out.size != len(names):
        raise RuntimeError(f"Model gives {out.size} outputs but class_indices.json has {len(names)} classes.")
    if out.size == 1:                       # sigmoid: probability of class index 1
        p1 = float(out[0])
        probs = {names[1]: p1, names[0]: 1.0 - p1}
    else:                                   # softmax
        probs = {names[i]: float(out[i]) for i in range(out.size)}
    t = _state["meta"].get("decision_threshold")          # written by training/evaluate_by_defect.py --save-threshold
    if t and "genuine" in probs and "counterfeit" in probs:
        g = _shift(probs["genuine"], float(t))
        probs = {"genuine": g, "counterfeit": 1.0 - g}
    return probs


def classify(probs, threshold):
    """Turns binary probabilities into Genuine / Suspicious / Counterfeit.

    - top class confident (>= threshold)  -> that class
    - otherwise (model unsure)            -> Suspicious
    """
    top = max(probs, key=probs.get)
    conf = probs[top]
    if conf >= threshold:
        label = top.capitalize()
    else:
        label = "Suspicious"
    return label, conf, top