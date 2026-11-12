"""MobileNetV2 transfer learning (binary: counterfeit=0, genuine=1).

  python training/train_model.py                      (uses dataset/, saves to trained_model/)
  python training/train_model.py --epochs 8 --fine-tune-epochs 6 --batch 32
  python training/train_model.py --no-pretrained      (offline test only: random weights)
"""
import argparse, json, os
from datetime import datetime

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

CLASSES = ["counterfeit", "genuine"]            # alphabetical -> counterfeit=0, genuine=1


def load(path, size, batch, shuffle):
    return keras.utils.image_dataset_from_directory(
        path, labels="inferred", label_mode="binary", class_names=CLASSES,
        image_size=size, batch_size=batch, shuffle=shuffle, seed=42).prefetch(tf.data.AUTOTUNE)


def build(size, alpha, pretrained):
    base = keras.applications.MobileNetV2(input_shape=size + (3,), include_top=False, alpha=alpha,
                                          weights="imagenet" if pretrained else None)
    base.trainable = False
    aug = keras.Sequential([layers.RandomRotation(0.04), layers.RandomZoom(0.1),
                            layers.RandomContrast(0.15), layers.RandomBrightness(0.15)], name="augmentation")
    inp = keras.Input(size + (3,))                           # raw pixels 0-255
    x = aug(inp)                                             # augmentation only active while training
    x = layers.Rescaling(1 / 127.5, offset=-1)(x)            # MobileNetV2 preprocessing lives INSIDE the model
    x = base(x, training=False)
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.3)(x)
    out = layers.Dense(1, activation="sigmoid")(x)
    return keras.Model(inp, out), base


def compile_(model, lr):
    model.compile(optimizer=keras.optimizers.Adam(lr), loss="binary_crossentropy",
                  metrics=["accuracy", keras.metrics.AUC(name="auc"), keras.metrics.Precision(name="precision"), keras.metrics.Recall(name="recall")])


def count(folder):
    return {c: len(os.listdir(os.path.join(folder, c))) for c in CLASSES}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="dataset"); ap.add_argument("--out", default="trained_model")
    ap.add_argument("--epochs", type=int, default=8); ap.add_argument("--fine-tune-epochs", type=int, default=6)
    ap.add_argument("--batch", type=int, default=32); ap.add_argument("--img", type=int, default=224)
    ap.add_argument("--init-from", help="continue from an earlier .keras model (stage 2 on your pack photos)")
    ap.add_argument("--alpha", type=float, default=1.0); ap.add_argument("--no-pretrained", action="store_true")
    a = ap.parse_args()
    size = (a.img, a.img)

    train = load(f"{a.data}/train", size, a.batch, True)
    val = load(f"{a.data}/validation", size, a.batch, False)
    test = load(f"{a.data}/test", size, a.batch, False)
    n = count(f"{a.data}/train"); total = sum(n.values())
    cw = {i: total / (2 * max(1, n[c])) for i, c in enumerate(CLASSES)}        # handles class imbalance
    print("train counts:", n, "| class weights:", {k: round(v, 2) for k, v in cw.items()})

    stop = keras.callbacks.EarlyStopping(monitor="val_loss", patience=3, restore_best_weights=True)
    if a.init_from:
        model = keras.models.load_model(a.init_from)
        base = next(l for l in model.layers if l.name.startswith("mobilenetv2"))
        print(f"Loaded {a.init_from}: continuing with fine-tuning only.")
    else:
        model, base = build(size, a.alpha, not a.no_pretrained)
        print("\n=== Stage 1: train the new top layer (base frozen) ===")
        compile_(model, 1e-3)
        model.fit(train, validation_data=val, epochs=a.epochs, class_weight=cw, callbacks=[stop])

    if a.fine_tune_epochs > 0:
        print("\n=== Stage 2: fine-tune the last layers ===")
        base.trainable = True
        for l in base.layers[:-30]:
            l.trainable = False
        for l in base.layers:
            if isinstance(l, layers.BatchNormalization):
                l.trainable = False
        compile_(model, 1e-5)
        model.fit(train, validation_data=val, epochs=a.fine_tune_epochs, class_weight=cw, callbacks=[stop])

    print("\n=== Evaluation on the TEST set (images the model never saw) ===")
    y_true = np.concatenate([y.numpy().ravel() for _, y in test]).astype(int)
    y_prob = model.predict(test, verbose=0).ravel()
    y_pred = (y_prob >= 0.5).astype(int)
    tp = int(((y_pred == 1) & (y_true == 1)).sum()); tn = int(((y_pred == 0) & (y_true == 0)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum()); fn = int(((y_pred == 0) & (y_true == 1)).sum())
    acc = (tp + tn) / max(1, len(y_true))
    prec_g = tp / max(1, tp + fp); rec_g = tp / max(1, tp + fn)
    prec_c = tn / max(1, tn + fn); rec_c = tn / max(1, tn + fp)
    print(f"accuracy {acc:.3f} | genuine precision {prec_g:.3f} recall {rec_g:.3f} | counterfeit precision {prec_c:.3f} recall {rec_c:.3f}")
    print(f"confusion matrix  (rows=true, cols=pred)  counterfeit: [{tn}, {fp}]   genuine: [{fn}, {tp}]")

    os.makedirs(a.out, exist_ok=True)
    model.save(os.path.join(a.out, "medicine_classifier.keras"))
    json.dump({"counterfeit": 0, "genuine": 1}, open(os.path.join(a.out, "class_indices.json"), "w"))
    info_path = os.path.join(a.data, "DATASET_INFO.json")
    source = json.load(open(info_path)).get("counterfeit_source", "unknown") if os.path.exists(info_path) else "unknown"
    meta = {"preprocess": "raw", "img_size": list(size), "trained_at": datetime.now().isoformat(timespec="seconds"),
            "counterfeit_source": source, "pretrained_imagenet": not a.no_pretrained,
            "test_accuracy": round(acc, 4), "test_images": int(len(y_true))}
    json.dump(meta, open(os.path.join(a.out, "model_meta.json"), "w"), indent=2)
    json.dump({**meta, "train_counts": n, "confusion": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
               "genuine": {"precision": round(prec_g, 4), "recall": round(rec_g, 4)},
               "counterfeit": {"precision": round(prec_c, 4), "recall": round(rec_c, 4)}},
              open(os.path.join(a.out, "training_report.json"), "w"), indent=2)
    print(f"\nSaved to {a.out}/: medicine_classifier.keras, class_indices.json, model_meta.json, training_report.json")
    if source != "real":
        print("NOTE: counterfeit class used SIMULATED samples. These test numbers do NOT measure real counterfeit detection.")


if __name__ == "__main__":
    main()
