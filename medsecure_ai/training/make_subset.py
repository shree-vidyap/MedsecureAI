"""Makes a small, balanced training set out of the big dataset (so CPU training finishes in a sensible time).

  python training/make_subset.py --src dataset_full --dst dataset --train 6000 --val 1500 --test 1500

Numbers are TOTAL per split (half genuine, half counterfeit). Files are COPIED, the big dataset is not touched.
The split stays product-level because the source split already is.
"""
import argparse, json, os, random, shutil

ap = argparse.ArgumentParser()
ap.add_argument("--src", default="dataset_full"); ap.add_argument("--dst", default="dataset")
ap.add_argument("--train", type=int, default=6000); ap.add_argument("--val", type=int, default=1500)
ap.add_argument("--test", type=int, default=1500); ap.add_argument("--seed", type=int, default=42)
a = ap.parse_args()
rnd = random.Random(a.seed)
if os.path.exists(a.dst) and any(os.scandir(a.dst)):
    raise SystemExit(f"'{a.dst}' is not empty. Delete it first or use another --dst.")
counts = {}
for split, total in (("train", a.train), ("validation", a.val), ("test", a.test)):
    for cls in ("genuine", "counterfeit"):
        src = os.path.join(a.src, split, cls)
        files = sorted(os.listdir(src))
        pick = rnd.sample(files, min(len(files), total // 2))
        out = os.path.join(a.dst, split, cls)
        os.makedirs(out, exist_ok=True)
        for f in pick:
            shutil.copy2(os.path.join(src, f), os.path.join(out, f))
        counts[f"{split}/{cls}"] = len(pick)
info_src = os.path.join(a.src, "DATASET_INFO.json")
info = json.load(open(info_src)) if os.path.exists(info_src) else {}
info.update(subset_of=a.src, subset_counts=counts)
json.dump(info, open(os.path.join(a.dst, "DATASET_INFO.json"), "w"), indent=2)
print("Subset ready ->", a.dst); print(json.dumps(counts, indent=1))