"""Downloads NIH NLM C3PI consumer-grade pill images (public, research/development use only).
Each image is resized while downloading (100,000 images ~ 1-2 GB).

  python training/download_nih_pills.py --out raw_nih_pills --count 100000 --size 256 --workers 8

How it finds the image list (tries in this order, --source auto):
  1) txt   : reads NIH's own file list  directory_consumer_grade_images.txt  (one request)
  2) crawl : opens PillProjectDiscN/images/ pages and follows sub-folders
If nothing is found it prints the exact reason (HTTP error / page sample) so it can be fixed.
Files are named  D<disc>_<original>.jpg  so `prepare_dataset.py --group-by-prefix` splits by disc folder.
Safe to stop (Ctrl+C) and run again: finished files are skipped.
"""
import argparse, io, math, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

from PIL import Image

BASE = "https://data.lhncbc.nlm.nih.gov/public/Pills/"
LINK = re.compile(r"""href=["']([^"'#?]+)["']""", re.I)
IMG = re.compile(r"\.(jpe?g|png)$", re.I)
LAST_ERROR = {"msg": ""}


def fetch(url, tries=4, timeout=60):
    for t in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MedSecureAI college project)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            LAST_ERROR["msg"] = f"{url} -> {type(e).__name__}: {e}"
            if t < tries - 1:
                time.sleep(2 * (t + 1))
    return None


# ---------- method 1: NIH file list ----------
def from_txt(base, discs):
    data = fetch(base + "directory_consumer_grade_images.txt", timeout=240)
    if not data:
        return {}
    text = data.decode("utf-8", "ignore").replace("\\", "/")
    found = re.findall(r"(PillProjectDisc(\d+)/images/[^\s,;\"'<>|]+?\.(?:jpe?g|png))", text, re.I)
    by_disc = {}
    for path, disc in found:
        if int(disc) <= discs:
            by_disc.setdefault(int(disc), []).append(urljoin(base, path))
    return by_disc


# ---------- method 2: crawl the folder pages ----------
def crawl(url, depth=3, cap=10**9):
    data = fetch(url)
    if not data:
        return []
    here = url[: -len("index.html")] if url.endswith("index.html") else url
    out = []
    for h in LINK.findall(data.decode("utf-8", "ignore")):
        t = urljoin(url, h)
        if IMG.search(t):
            out.append(t)
        elif depth > 0 and (t.endswith("/") or t.endswith("/index.html")):
            d = t[: -len("index.html")] if t.endswith("index.html") else t
            if d.startswith(here) and d != here:
                out += crawl(d + "index.html", depth - 1, cap - len(out))
        if len(out) >= cap:
            break
    return out


def from_crawl(base, discs, quota):
    by_disc = {}
    for d in range(1, discs + 1):
        by_disc[d] = crawl(f"{base}PillProjectDisc{d}/images/index.html", cap=quota)
        print(f"  disc {d}: {len(by_disc[d])} images listed", end="\r")
    print()
    return by_disc


def grab(url, out, size):
    name = os.path.basename(url.split("?")[0])
    m = re.search(r"PillProjectDisc(\d+)", url, re.I)
    prefix = f"D{int(m.group(1)):03d}_" if m else "D000_"        # disc number -> used for leakage-safe splitting
    dst = os.path.join(out, prefix + os.path.splitext(name)[0] + ".jpg")
    if os.path.exists(dst):
        return "skipped"
    data = fetch(url)
    if not data:
        return "failed"
    try:
        img = Image.open(io.BytesIO(data))
        img.draft("RGB", (size * 2, size * 2))                    # fast JPEG decode at reduced scale
        img = img.convert("RGB")
        img.thumbnail((size, size))
        img.save(dst, "JPEG", quality=90)
        return "ok"
    except Exception:
        return "failed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="raw_nih_pills")
    ap.add_argument("--count", type=int, default=100000)
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--discs", type=int, default=110)
    ap.add_argument("--source", choices=["auto", "txt", "crawl"], default="auto")
    ap.add_argument("--base-url", default=BASE)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    quota = math.ceil(a.count / a.discs)

    by_disc = {}
    if a.source in ("auto", "txt"):
        print("Method 1: reading NIH file list (directory_consumer_grade_images.txt)...")
        by_disc = from_txt(a.base_url, a.discs)
        print(f"  -> {sum(len(v) for v in by_disc.values())} images listed")
    if not by_disc and a.source in ("auto", "crawl"):
        print(f"Method 2: crawling {a.discs} disc folders...")
        by_disc = from_crawl(a.base_url, a.discs, quota)

    urls = []
    for d in sorted(by_disc):
        urls += by_disc[d][:quota]
    urls = urls[: a.count]
    print(f"Total to download: {len(urls)}")
    if not urls:
        print("\nNo images found. Last network problem seen:", LAST_ERROR["msg"] or "(none, the pages loaded but had no image links)")
        sample = fetch(f"{a.base_url}PillProjectDisc1/images/index.html")
        print("Sample of PillProjectDisc1/images/index.html (first 600 chars):\n",
              sample[:600].decode("utf-8", "ignore") if sample else "(could not load)")
        sys.exit("Copy this whole message and send it so the script can be fixed.")

    stats = {"ok": 0, "skipped": 0, "failed": 0}
    with ThreadPoolExecutor(a.workers) as ex:
        for i, res in enumerate(ex.map(lambda u: grab(u, a.out, a.size), urls), 1):
            stats[res] += 1
            if i % 500 == 0 or i == len(urls):
                print(f"  {i}/{len(urls)}  {stats}", end="\r")
    print(f"\nDone. {stats}  -> {a.out}")


if __name__ == "__main__":
    main()
