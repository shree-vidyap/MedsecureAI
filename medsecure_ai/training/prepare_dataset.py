"""Builds dataset/{train,validation,test}/{genuine,counterfeit} from your raw image folders.

  python training/prepare_dataset.py --genuine raw_genuine --simulate-counterfeit
  python training/prepare_dataset.py --genuine raw_genuine --counterfeit raw_counterfeit
  (add --group-by-prefix if filenames look like  paracetamol_001.jpg, paracetamol_002.jpg ...)

What it does:  quality filter -> duplicate removal -> group-aware split (no leakage) -> save.
--simulate-counterfeit creates DIGITALLY ALTERED copies of genuine images and labels them
"counterfeit". They are SIMULATED (not real counterfeits) and this is recorded in DATASET_INFO.json.
Each simulated copy stays in the SAME split as its source image (no data leakage).
"""
import argparse, io, json, os, random, shutil
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from functools import partial

import cv2
import numpy as np
from PIL import Image, ImageEnhance

EXT = {".jpg", ".jpeg", ".png"}


def list_images(folder):
    out = []
    for root, _, files in os.walk(folder):
        out += [os.path.join(root, f) for f in files if os.path.splitext(f)[1].lower() in EXT]
    return sorted(out)


def sharpness(img):
    g = np.asarray(img.convert("L"))
    h, w = g.shape
    sc = 600 / max(h, w)
    if sc < 1:
        g = cv2.resize(g, (int(w * sc), int(h * sc)))
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def dhash(img):
    a = np.asarray(img.convert("L").resize((17, 16), Image.LANCZOS), dtype=int)   # 256-bit hash: fewer false "duplicates"
    return "".join("1" if v else "0" for v in (a[:, 1:] > a[:, :-1]).flatten())


def _check(path, min_side, min_sharp):
    """Worker: returns (path, reason, hash). reason=None means the image is good."""
    try:
        img = Image.open(path).convert("RGB")
    except Exception:
        return path, "unreadable", None
    if min(img.size) < min_side:
        return path, "too_small", None
    if sharpness(img) < min_sharp:
        return path, "blurry", None
    return path, None, dhash(img)


def load_clean(paths, min_side, min_sharp, stats, workers):
    """Quality filter + duplicate removal. Returns a list of PATHS (images are NOT kept in memory)."""
    seen, out = set(), []
    fn = partial(_check, min_side=min_side, min_sharp=min_sharp)
    if workers > 1:
        with ProcessPoolExecutor(workers) as ex:
            results = ex.map(fn, paths, chunksize=64)
            for i, (p, reason, h) in enumerate(results, 1):
                _collect(p, reason, h, seen, out, stats)
                if i % 5000 == 0:
                    print(f"  checked {i}/{len(paths)}", end="\r")
    else:
        for p in paths:
            _collect(*fn(p), seen, out, stats)
    return out


def _collect(p, reason, h, seen, out, stats):
    if reason:
        stats[reason] += 1
    elif h in seen:
        stats["duplicates"] += 1
    else:
        seen.add(h); out.append(p)


def split_items(items, by_prefix, rng):
    groups = {}
    for p in items:
        name = os.path.basename(p)
        key = name.split("_")[0] if by_prefix else name
        groups.setdefault(key, []).append(p)
    keys = list(groups); rng.shuffle(keys)
    n = len(keys)
    if n < 3:
        raise SystemExit("Need at least 3 images (or 3 groups) per class to make train/validation/test.")
    n_tr = max(1, int(n * 0.70)); n_va = max(1, int(n * 0.15))
    parts = {"train": keys[:n_tr], "validation": keys[n_tr:n_tr + n_va], "test": keys[n_tr + n_va:]}
    if not parts["test"]:                       # tiny datasets
        parts["test"] = [parts["train"].pop()]
    return {s: [it for k in ks for it in groups[k]] for s, ks in parts.items()}


# ---------- simulated tampering (clearly NOT real counterfeits) ----------
def hue_shift(img, r):
    hsv = np.array(img.convert("HSV")); hsv[..., 0] = (hsv[..., 0].astype(int) + r.randint(8, 40)) % 256
    return Image.fromarray(hsv, "HSV").convert("RGB")

def misregister(img, r):                         # poor print: colour layers not aligned
    a = np.array(img); c = r.randint(0, 2)
    a[..., c] = np.roll(a[..., c], (r.randint(2, 5), r.randint(2, 5)), axis=(0, 1))
    return Image.fromarray(a)

def jpeg_degrade(img, r):
    b = io.BytesIO(); img.save(b, "JPEG", quality=r.randint(12, 30)); b.seek(0)
    return Image.open(b).convert("RGB")

def contrast_wash(img, r):
    img = ImageEnhance.Contrast(img).enhance(r.uniform(0.55, 0.8))
    return ImageEnhance.Color(img).enhance(r.uniform(0.5, 0.8))

def patch_swap(img, r):                          # copy a region to another place (fake label area)
    w, h = img.size; pw, ph = int(w * r.uniform(.15, .3)), int(h * r.uniform(.15, .3))
    sx, sy = r.randint(0, w - pw), r.randint(0, h - ph)
    patch = img.crop((sx, sy, sx + pw, sy + ph)).resize((int(pw * r.uniform(.9, 1.1)), int(ph * r.uniform(.9, 1.1))))
    out = img.copy(); out.paste(patch, (r.randint(0, max(0, w - patch.size[0])), r.randint(0, max(0, h - patch.size[1]))))
    return out

def add_noise(img, r):
    a = np.array(img).astype("float32") + np.random.default_rng(r.randint(0, 10**6)).normal(0, r.uniform(8, 18), (img.size[1], img.size[0], 3))
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8"))

OPS = [hue_shift, misregister, jpeg_degrade, contrast_wash, patch_swap, add_noise]

def make_fake(img, r):
    for op in r.sample(OPS, k=r.choice([2, 3])):
        img = op(img, r)
    return img


def save(src_path, folder, name, size, rng=None, fake=False):
    img = Image.open(src_path).convert("RGB")
    if fake:
        img = make_fake(img, rng)
    img.thumbnail((size, size))
    os.makedirs(folder, exist_ok=True)
    img.save(os.path.join(folder, name), "JPEG", quality=90)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--genuine", nargs="+", required=True, help="one or more folders with real medicine photos")
    ap.add_argument("--counterfeit", help="folder with REAL counterfeit photos (if you have them)")
    ap.add_argument("--simulate-counterfeit", action="store_true", help="create simulated (altered) counterfeit samples")
    ap.add_argument("--sim-ratio", type=float, default=1.0, help="fraction of genuine images that get a simulated twin")
    ap.add_argument("--max-genuine", type=int, default=0, help="use at most this many genuine images (0 = all)")
    ap.add_argument("--group-by-prefix", action="store_true")
    ap.add_argument("--out", default="dataset")
    ap.add_argument("--save-size", type=int, default=256, help="longest side of saved images (saves disk)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--min-side", type=int, default=100)
    ap.add_argument("--min-sharpness", type=float, default=30)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    if not a.counterfeit and not a.simulate_counterfeit:
        raise SystemExit("Give --counterfeit <folder> (real) and/or --simulate-counterfeit.")
    rng = random.Random(a.seed)
    for s_ in ("train", "validation", "test"):
        shutil.rmtree(os.path.join(a.out, s_), ignore_errors=True)

    removed = {"unreadable": 0, "too_small": 0, "blurry": 0, "duplicates": 0}
    paths = [p for f in a.genuine for p in list_images(f)]
    print(f"genuine images found: {len(paths)}  (checking quality + duplicates with {a.workers} workers...)")
    gen = load_clean(paths, a.min_side, a.min_sharpness, removed, a.workers)
    if a.max_genuine and len(gen) > a.max_genuine:
        gen = rng.sample(gen, a.max_genuine)
    print(f"\ngenuine kept: {len(gen)}  removed: {removed}")
    gsplit = split_items(gen, a.group_by_prefix, rng)
    counts = {s_: {"genuine": 0, "counterfeit_real": 0, "counterfeit_simulated": 0} for s_ in gsplit}

    done = 0
    for s_, items in gsplit.items():
        for i, p in enumerate(items):
            save(p, f"{a.out}/{s_}/genuine", f"g_{i:06d}.jpg", a.save_size); counts[s_]["genuine"] += 1
            if a.simulate_counterfeit and rng.random() < a.sim_ratio:      # twin stays in the SAME split -> no leakage
                save(p, f"{a.out}/{s_}/counterfeit", f"sim_{i:06d}.jpg", a.save_size, rng, fake=True)
                counts[s_]["counterfeit_simulated"] += 1
            done += 1
            if done % 2000 == 0:
                print(f"  saved {done}/{len(gen)}", end="\r")

    if a.counterfeit:
        rem2 = {"unreadable": 0, "too_small": 0, "blurry": 0, "duplicates": 0}
        cf = load_clean(list_images(a.counterfeit), a.min_side, a.min_sharpness, rem2, 1)
        print(f"\nreal counterfeit kept: {len(cf)}  removed: {rem2}")
        for s_, items in split_items(cf, a.group_by_prefix, rng).items():
            for i, p in enumerate(items):
                save(p, f"{a.out}/{s_}/counterfeit", f"c_{i:06d}.jpg", a.save_size); counts[s_]["counterfeit_real"] += 1

    real = any(c["counterfeit_real"] for c in counts.values()); sim = any(c["counterfeit_simulated"] for c in counts.values())
    source = "real+simulated" if real and sim else "real" if real else "simulated"
    total_g = sum(c["genuine"] for c in counts.values())
    total_c = sum(c["counterfeit_real"] + c["counterfeit_simulated"] for c in counts.values())
    info = {"created_at": datetime.now().isoformat(timespec="seconds"), "counterfeit_source": source,
            "genuine_folders": a.genuine, "removed_genuine": removed, "counts": counts,
            "total_genuine": total_g, "total_counterfeit": total_c, "total_images": total_g + total_c,
            "note": "Genuine = real medicine photos (authenticity not independently verified)."}
    json.dump(info, open(os.path.join(a.out, "DATASET_INFO.json"), "w"), indent=2)

    print("\nSplit summary:")
    for s_, c in counts.items():
        print(f"  {s_:<11} genuine={c['genuine']:<7} counterfeit={c['counterfeit_real'] + c['counterfeit_simulated']:<7}")
    print(f"TOTAL usable images in dataset/: {total_g + total_c:,}  (genuine {total_g:,} + counterfeit {total_c:,})")
    print("counterfeit source:", source.upper())
    if source != "real":
        print("WARNING: counterfeit class contains SIMULATED samples. Say this clearly in your report/viva.")


if __name__ == "__main__":
    main()
