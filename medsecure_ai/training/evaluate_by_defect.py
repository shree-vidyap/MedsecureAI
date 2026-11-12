"""Shows WHICH simulated defects the trained model catches (recall per defect), using labels.csv from the generator.

  python training/evaluate_by_defect.py --data dataset_small --labels dataset_full/labels.csv
Reads <data>/test/{genuine,counterfeit}. Needs trained_model/medicine_classifier.keras.
"""
import argparse, csv, os
from collections import defaultdict

CLASSES = ["counterfeit", "genuine"]            # same order as train_model.py (genuine = 1)


def summarize(items, probs, thr=0.5):
    """items: [(class, defects_str)], probs: P(genuine). Returns per-defect stats for counterfeit images + genuine specificity."""
    single, anyd = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    g_tot = g_ok = 0
    for (cls, defects), p in zip(items, probs):
        pred_fake = p < thr
        if cls == "genuine":
            g_tot += 1; g_ok += int(not pred_fake)
            continue
        ds = [d for d in defects.split("+") if d]
        for d in ds:
            anyd[d][0] += 1; anyd[d][1] += int(pred_fake)
        if len(ds) == 1:
            single[ds[0]][0] += 1; single[ds[0]][1] += int(pred_fake)
    return single, anyd, g_tot, g_ok


def auc_and_threshold(y_val, p_val, y_test, p_test):
    """AUC on test + the decision threshold that is best on VALIDATION, applied to TEST (so test stays unseen)."""
    import numpy as np
    def auc(y, p):
        y, p = np.asarray(y), np.asarray(p)
        pos, neg = p[y == 1], p[y == 0]
        if not len(pos) or not len(neg):
            return float("nan")
        order = np.argsort(np.concatenate([pos, neg])); ranks = np.empty(len(order)); ranks[order] = np.arange(1, len(order) + 1)
        return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))
    ths = np.linspace(0.05, 0.95, 91)
    accs = [((np.asarray(p_val) >= t).astype(int) == np.asarray(y_val)).mean() for t in ths]
    best = float(ths[int(np.argmax(accs))])
    y_test, p_test = np.asarray(y_test), np.asarray(p_test)
    return auc(y_test, p_test), best, float(((p_test >= 0.5) == y_test).mean()), float(((p_test >= best) == y_test).mean())


def metrics_at(y, p, t):
    import numpy as np
    y, pred = np.asarray(y), (np.asarray(p) >= t).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
    fp = int(((pred == 1) & (y == 0)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
    return dict(tp=tp, tn=tn, fp=fp, fn=fn, acc=(tp + tn) / max(1, len(y)),
                gen_prec=tp / max(1, tp + fp), gen_rec=tp / max(1, tp + fn),
                fake_prec=tn / max(1, tn + fn), fake_rec=tn / max(1, tn + fp))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="dataset_small"); ap.add_argument("--labels", default="dataset_full/labels.csv")
    ap.add_argument("--model", default="trained_model/medicine_classifier.keras"); ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--save-threshold", action="store_true", help="write the validation-chosen threshold into model_meta.json (the app then uses it)")
    a = ap.parse_args()
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    from tensorflow import keras
    meta = {r["file"]: r["defects"] for r in csv.DictReader(open(a.labels, encoding="utf-8"))}
    ds = keras.utils.image_dataset_from_directory(f"{a.data}/test", labels="inferred", label_mode="binary", class_names=CLASSES,
                                                  image_size=(224, 224), batch_size=a.batch, shuffle=False)
    paths = ds.file_paths
    model = keras.models.load_model(a.model)
    probs = model.predict(ds, verbose=0).ravel()
    y_test = [1 if os.path.basename(os.path.dirname(p)) == "genuine" else 0 for p in paths]
    vds = keras.utils.image_dataset_from_directory(f"{a.data}/validation", labels="inferred", label_mode="binary", class_names=CLASSES,
                                                   image_size=(224, 224), batch_size=a.batch, shuffle=False)
    y_val = [1 if os.path.basename(os.path.dirname(p)) == "genuine" else 0 for p in vds.file_paths]
    p_val = model.predict(vds, verbose=0).ravel()
    auc, best, acc05, accbest = auc_and_threshold(y_val, p_val, y_test, probs)
    print(f"\nTest AUC: {auc:.3f}   (0.5 = guessing, 1.0 = perfect)")
    print(f"Test accuracy at threshold 0.50: {acc05:.3f}")
    print(f"Best threshold on VALIDATION = {best:.2f}  ->  test accuracy there: {accbest:.3f}")
    m = metrics_at(y_test, probs, best)
    print(f"At threshold {best:.2f}: genuine precision {m['gen_prec']:.3f} recall {m['gen_rec']:.3f} | "
          f"counterfeit precision {m['fake_prec']:.3f} recall {m['fake_rec']:.3f}")
    print(f"Confusion matrix (rows=true, cols=pred)  counterfeit: [{m['tn']}, {m['fp']}]   genuine: [{m['fn']}, {m['tp']}]")
    if a.save_threshold:
        import json
        mp = os.path.join(os.path.dirname(a.model), "model_meta.json")
        meta_json = json.load(open(mp, encoding="utf-8-sig")) if os.path.exists(mp) else {}
        meta_json.update(decision_threshold=round(best, 3), test_auc=round(auc, 4), test_accuracy_at_threshold=round(accbest, 4),
                         threshold_chosen_on="validation")
        json.dump(meta_json, open(mp, "w"), indent=2)
        print(f"Saved decision_threshold={best:.2f} to {mp}")
    items = [(os.path.basename(os.path.dirname(p)), meta.get(os.path.basename(p), "")) for p in paths]
    single, anyd, g_tot, g_ok = summarize(items, probs, best)      # same threshold as the metrics above
    print(f"\n--- per-defect table at threshold {best:.2f} ---\nGenuine packs correctly kept as genuine: {g_ok}/{g_tot} ({100 * g_ok / max(1, g_tot):.1f}%)\n")
    print(f"{'defect':<18}{'only this defect':>22}{'any image with it':>24}")
    for d in sorted(anyd, key=lambda k: -anyd[k][1] / anyd[k][0]):
        s = single.get(d, [0, 0]); t = anyd[d]
        print(f"{d:<18}{(f'{s[1]}/{s[0]} = {100 * s[1] / s[0]:.0f}%' if s[0] else '-'):>22}{f'{t[1]}/{t[0]} = {100 * t[1] / t[0]:.0f}%':>24}")
    print("\nRecall = share of counterfeit images the model called Counterfeit. Low recall on bad_ean / qr_mismatch / name_typo /"
          "\ndate_format is EXPECTED: those are not visible at 224px. services/code_verify.py checks them instead.")


if __name__ == "__main__":
    main()