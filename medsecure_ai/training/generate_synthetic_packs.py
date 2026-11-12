"""Generates a LARGE synthetic dataset of medicine PACKAGE photos that carry a QR code AND an EAN-13 barcode.

  pip install qrcode pillow numpy opencv-python
  python training/generate_synthetic_packs.py --count 120000 --workers 8        (writes into dataset/)
  python training/generate_synthetic_packs.py --count 200 --out /tmp/demo       (quick test)

Output: <out>/{train,validation,test}/{genuine,counterfeit}/*.jpg  +  <out>/labels.csv  +  <out>/DATASET_INFO.json
This matches what training/train_model.py expects, so you can train directly afterwards.

HONEST NOTES (write these in your report / viva):
  * Every pack is RENDERED by this script. Brand names are fictional. Nothing here is a real medicine photo
    and the "counterfeit" class is SIMULATED (see DEFECTS below). Report it as a proof-of-concept dataset.
  * Genuine pack  = valid EAN-13 check digit, QR payload that matches the printed batch / expiry, sharp print.
  * Every image has a pack + QR + EAN-13 barcode (unless --allow-missing-codes).
  * Counterfeit   = 1-3 random defects: bad EAN check digit, QR missing or payload mismatch, blurred / low-res print,
                    colour shift, misaligned or typo'd text, wrong date format, missing hologram strip.
  * Split is by PRODUCT (not by image), so the same product never sits in train and test (no leakage).
  * A model trained only on this learns these rendering artefacts. Fine-tune on real pack photos afterwards
    (training/README.md, stage 2) and quote the real-photo test accuracy as your honest result.
"""
import argparse, csv, hashlib, io, json, os, random, string
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta

import numpy as np
import qrcode
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

import cv2

W, H = 640, 400            # flat pack face; final photo is saved at --size
FONT_CANDIDATES = {          # first file that exists wins (Windows, Linux, macOS); else Pillow's built-in font
    "b": ["C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
    "r": ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"],
    "m": ["C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/cour.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf", "/System/Library/Fonts/Menlo.ttc"],
}
_FONT_CACHE = {}
GENERICS = ["Paracetamol", "Ibuprofen", "Amoxicillin", "Cetirizine", "Azithromycin", "Metformin", "Omeprazole",
            "Pantoprazole", "Atorvastatin", "Amlodipine", "Losartan", "Levocetirizine", "Diclofenac", "Ranitidine",
            "Montelukast", "Ciprofloxacin", "Doxycycline", "Aspirin", "Vitamin D3", "Folic Acid", "Domperidone"]
STRENGTHS = ["50 mg", "100 mg", "250 mg", "500 mg", "650 mg", "5 mg", "10 mg", "20 mg", "40 mg", "1000 mg"]
FORMS = ["Tablets I.P.", "Capsules I.P.", "Tablets", "Film Coated Tablets", "Strip of 10 Tablets"]
MAKERS = ["Aurelia Pharma Ltd.", "Nexora Lifesciences", "Veridan Labs Pvt. Ltd.", "Corvia Healthcare", "Zenthra Remedies",
          "Lumora Pharmaceuticals", "Kalyx Drugs & Chemicals", "Orvanta Biotech"]
SYL = ["zen", "ora", "vi", "lum", "cor", "ax", "dro", "myl", "tex", "pra", "nol", "gen", "ver", "sol", "kal", "fen", "dix", "rox"]
PALETTES = [((20, 90, 160), (255, 255, 255)), ((0, 130, 90), (255, 255, 255)), ((170, 30, 50), (255, 245, 240)),
            ((240, 240, 245), (20, 60, 120)), ((250, 200, 40), (60, 40, 10)), ((90, 50, 150), (255, 255, 255)),
            ((20, 20, 30), (240, 200, 90)), ((230, 120, 30), (255, 255, 255))]
VISUAL_DEFECTS = ["blur_print", "lowres_print", "color_shift", "text_misaligned", "no_hologram"]   # a CNN can SEE these at 224px
DEFECTS = ["bad_ean", "qr_missing", "qr_mismatch", "blur_print", "lowres_print", "color_shift", "text_misaligned",
           "name_typo", "date_format", "no_hologram", "ean_missing"]

# ---------------- EAN-13 ----------------
L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
G = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"]
R = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"]
PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]


def ean_check(d12):
    s = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(d12))
    return str((10 - s % 10) % 10)


def ean_bits(code13):
    first, left, right = int(code13[0]), code13[1:7], code13[7:]
    bits = "101"
    for c, p in zip(left, PARITY[first]):
        bits += (L if p == "L" else G)[int(c)]
    bits += "01010"
    bits += "".join(R[int(c)] for c in right)
    return bits + "101"


def draw_ean(code13, bar_h=90, mod=2):
    bits = ean_bits(code13)
    qz = 11 * mod
    img = Image.new("RGB", (len(bits) * mod + 2 * qz, bar_h + 26), "white")
    d = ImageDraw.Draw(img)
    for i, b in enumerate(bits):
        if b == "1":
            long = i < 3 or 45 <= i < 50 or i >= 92
            d.rectangle([qz + i * mod, 0, qz + (i + 1) * mod - 1, bar_h + (8 if long else 0)], fill="black")
    f = font("m", 15)
    d.text((2, bar_h - 2), code13[0], font=f, fill="black")
    d.text((qz + 5 * mod, bar_h + 4), code13[1:7], font=f, fill="black")
    d.text((qz + 51 * mod, bar_h + 4), code13[7:], font=f, fill="black")
    return img


# ---------------- products ----------------
def make_product(pid):
    r = random.Random(pid * 7919 + 13)
    brand = (r.choice(SYL) + r.choice(SYL) + r.choice(["", "x", "in", "ol", "ex"])).capitalize()
    prefix = "890" + "".join(r.choice(string.digits) for _ in range(9))       # 890 = GS1 India prefix, rest random
    return dict(pid=pid, brand=brand, generic=r.choice(GENERICS), strength=r.choice(STRENGTHS), form=r.choice(FORMS),
                maker=r.choice(MAKERS), pal=r.choice(PALETTES), ean12=prefix[:12], layout=r.randint(0, 2))


def split_of(pid):
    h = int(hashlib.md5(str(pid).encode()).hexdigest(), 16) % 100
    return "train" if h < 70 else ("validation" if h < 85 else "test")


# ---------------- rendering ----------------
def font(k, s):
    key = (k, s)
    if key not in _FONT_CACHE:
        f = None
        for path in FONT_CANDIDATES.get(k, FONT_CANDIDATES["r"]):
            if os.path.exists(path):
                try:
                    f = ImageFont.truetype(path, s)
                    break
                except OSError:
                    pass
        _FONT_CACHE[key] = f or ImageFont.load_default(size=s)
    return _FONT_CACHE[key]


def typo(s, r):
    if len(s) < 4:
        return s
    i = r.randrange(1, len(s) - 1)
    return s[:i] + r.choice([s[i + 1], s[i].swapcase() if s[i].isalpha() else "0", "", s[i] * 2]) + s[i + 1:]


def render(prod, genuine, r, allow_missing=False, visual_only=False, strong=False):
    """Returns (PIL image, info dict)."""
    pool = VISUAL_DEFECTS if visual_only else (DEFECTS if allow_missing else [x for x in DEFECTS if x not in ("qr_missing", "ean_missing")])
    if strong:                     # colour shift cannot be judged without knowing the product's true colours -> not a CNN target
        pool = [x for x in pool if x != "color_shift"]
    defects = [] if genuine else r.sample(pool, min(len(pool), r.choice([1, 1, 2, 3])))
    bg, fg = prod["pal"]
    img = Image.new("RGB", (W, H), (245, 245, 242))
    d = ImageDraw.Draw(img)
    mfg = datetime(2024, 1, 1) + timedelta(days=r.randint(0, 700))
    exp = mfg + timedelta(days=r.choice([730, 1095]))
    batch = r.choice(string.ascii_uppercase) + r.choice(string.ascii_uppercase) + "".join(r.choice(string.digits) for _ in range(5))
    fmt = "%m/%Y" if "date_format" not in defects else r.choice(["%d-%m-%y", "%Y.%m.%d", "%b %d %Y"])
    mfg_s, exp_s = mfg.strftime(fmt), exp.strftime(fmt)
    name = prod["brand"] if "name_typo" not in defects else typo(prod["brand"], r)
    jx = (lambda: r.randint(-32, 32) if strong else r.randint(-14, 14)) if "text_misaligned" in defects else (lambda: 0)

    # colour band + brand
    lay = prod["layout"]
    if lay == 0:   d.rectangle([0, 0, W, 120], fill=bg)
    elif lay == 1: d.rectangle([0, 0, 190, H], fill=bg)
    else:          d.polygon([(0, 0), (W, 0), (W, 90), (0, 150)], fill=bg)
    bx = 215 if lay == 1 else 28
    d.text((bx + jx(), 22 + jx()), name, font=font("b", 50), fill=fg if lay != 1 else (30, 30, 30))
    ty = 130 if lay != 1 else 90
    d.text((bx + jx(), ty + jx()), f'{prod["generic"]} {prod["strength"]}', font=font("b", 26), fill=(25, 25, 25))
    d.text((bx + jx(), ty + 36 + jx()), prod["form"], font=font("r", 19), fill=(60, 60, 60))
    d.text((bx, ty + 66), "Rx only - FICTIONAL SAMPLE" if lay == 2 else "Store below 25 C. Keep away from children.",
           font=font("r", 14), fill=(90, 90, 90))
    # info block
    iy = ty + 98
    for k, (lab, val) in enumerate([("Mfg:", mfg_s), ("Exp:", exp_s), ("B.No.:", batch)]):
        d.text((bx + jx(), iy + 22 * k + jx()), f"{lab} {val}", font=font("m", 17), fill=(15, 15, 15))
    d.text((bx, iy + 70), "Mfd. by: " + prod["maker"], font=font("r", 14), fill=(60, 60, 60))

    # hologram strip
    if "no_hologram" not in defects:
        hx = W - 40 if lay != 1 else 170
        for yy in range(20, H - 20, 6):
            c = tuple(int(v) for v in np.array([r.randint(120, 255), r.randint(120, 255), r.randint(120, 255)]))
            d.rectangle([hx, yy, hx + 14, yy + 4], fill=c)

    # EAN-13
    ean12 = prod["ean12"]
    chk = ean_check(ean12)
    if "bad_ean" in defects:
        chk = str((int(chk) + r.randint(1, 9)) % 10)
    ean = ean12 + chk
    if "ean_missing" not in defects:
        bc = draw_ean(ean)
        d_img = img
        d_img.paste(bc, (bx - 6 if lay != 1 else 205, H - bc.size[1] - 14))

    # QR  (payload = what a real pack's QR would hold: product + batch + expiry)
    qr_payload = f"GTIN:{ean12 + ean_check(ean12)}|B:{batch}|E:{exp.strftime('%Y-%m')}"
    if "qr_mismatch" in defects:
        qr_payload = f"GTIN:{ean12 + ean_check(ean12)}|B:{batch[:2] + ''.join(r.choice(string.digits) for _ in range(5))}|E:{(exp + timedelta(days=r.randint(200, 900))).strftime('%Y-%m')}"
    if "qr_missing" not in defects:
        q = qrcode.QRCode(box_size=4, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
        q.add_data(qr_payload); q.make(fit=True)
        qi = q.make_image(fill_color="black", back_color="white").convert("RGB").resize((118, 118), Image.NEAREST)
        img.paste(qi, (W - 150 if lay != 1 else W - 150, H - 138))

    # print-quality / colour defects
    if "blur_print" in defects:
        img = img.filter(ImageFilter.GaussianBlur(r.uniform(3.0, 5.0) if strong else r.uniform(1.2, 2.4)))
    if "lowres_print" in defects:
        f = r.uniform(0.12, 0.2) if strong else r.uniform(0.35, 0.55)
        img = img.resize((int(W * f), int(H * f)), Image.BILINEAR).resize((W, H), Image.NEAREST)
    if "color_shift" in defects:
        a = np.asarray(img).astype("float32")
        a *= np.array([r.uniform(.8, 1.2), r.uniform(.8, 1.2), r.uniform(.8, 1.2)])
        img = Image.fromarray(np.clip(a, 0, 255).astype("uint8"))
    info = dict(brand=name, ean=ean, ean_valid=int(ean[-1] == ean_check(ean12)), batch=batch, exp=exp_s,
                qr_present=int("qr_missing" not in defects), qr_matches=int("qr_mismatch" not in defects),
                ean_present=int("ean_missing" not in defects), defects="+".join(defects))
    return img, info


def photo_effect(img, r, size):
    """Makes the flat render look like a phone photo: background, perspective, rotation, light, noise, JPEG."""
    a = np.asarray(img)
    bgc = [r.randint(60, 230) for _ in range(3)]
    canvas = np.full((int(H * 1.5), int(W * 1.4), 3), bgc, dtype=np.uint8)
    canvas += np.random.randint(0, 25, canvas.shape, dtype=np.uint8) // 2
    ch, cw = canvas.shape[:2]
    m = 0.1
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    ox, oy = (cw - W) / 2, (ch - H) / 2
    dst = np.float32([[ox + r.uniform(-m, m) * W, oy + r.uniform(-m, m) * H],
                      [ox + W + r.uniform(-m, m) * W, oy + r.uniform(-m, m) * H],
                      [ox + W + r.uniform(-m, m) * W, oy + H + r.uniform(-m, m) * H],
                      [ox + r.uniform(-m, m) * W, oy + H + r.uniform(-m, m) * H]])
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(a, M, (cw, ch), dst=canvas.copy(), borderMode=cv2.BORDER_TRANSPARENT)
    ang = r.uniform(-8, 8)
    R = cv2.getRotationMatrix2D((cw / 2, ch / 2), ang, 1.0)
    warped = cv2.warpAffine(warped, R, (cw, ch), borderMode=cv2.BORDER_REPLICATE)
    out = Image.fromarray(warped).resize((size, size), Image.LANCZOS)
    out = ImageEnhance.Brightness(out).enhance(r.uniform(.7, 1.25))
    out = ImageEnhance.Contrast(out).enhance(r.uniform(.8, 1.2))
    arr = np.asarray(out).astype("float32")
    gy, gx = np.mgrid[0:size, 0:size]                                 # uneven lighting gradient
    arr *= (1 + r.uniform(-.25, .25) * (gx / size) + r.uniform(-.25, .25) * (gy / size))[..., None]
    arr += np.random.normal(0, r.uniform(1, 6), arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))


def job(args):
    idx, genuine, n_products, out, size, seed, allow_missing, visual_only, strong = args
    r = random.Random(seed * 1000003 + idx)
    np.random.seed((seed * 1000003 + idx) % (2 ** 32))
    pid = r.randrange(n_products)
    prod = make_product(pid)
    flat, info = render(prod, genuine, r, allow_missing, visual_only, strong)
    img = photo_effect(flat, r, size)
    cls = "genuine" if genuine else "counterfeit"
    sp = split_of(pid)
    fn = f"P{pid:05d}_{cls[0]}{idx:06d}.jpg"            # P<product>_ prefix -> --group-by-prefix works too
    img.save(os.path.join(out, sp, cls, fn), quality=r.randint(70, 95))
    return [sp, cls, fn, pid] + [info[k] for k in ("brand", "ean", "ean_valid", "qr_present", "qr_matches", "ean_present", "batch", "exp", "defects")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=120000, help="total images (half genuine, half counterfeit)")
    ap.add_argument("--out", default="dataset")
    ap.add_argument("--size", type=int, default=224)
    ap.add_argument("--products", type=int, default=3000, help="number of different fictional products")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--visual-only", action="store_true",
                    help="counterfeit = only defects a CNN can see (blur, low-res, colour, misaligned text, no hologram). "
                         "Barcode / QR defects are then left to services/code_verify.py")
    ap.add_argument("--strong", action="store_true",
                    help="use with --visual-only: stronger blur / low-res / text shift (visible at 224px) and NO colour_shift defect")
    ap.add_argument("--allow-missing-codes", action="store_true",
                    help="some counterfeits then have NO QR or NO barcode (default: every image has both)")
    a = ap.parse_args()
    for sp in ("train", "validation", "test"):
        for c in ("genuine", "counterfeit"):
            os.makedirs(os.path.join(a.out, sp, c), exist_ok=True)
    jobs = [(i, i % 2 == 0, a.products, a.out, a.size, a.seed, a.allow_missing_codes, a.visual_only, a.strong) for i in range(a.count)]
    rows = []
    with ProcessPoolExecutor(a.workers) as ex:
        for k, row in enumerate(ex.map(job, jobs, chunksize=32), 1):
            rows.append(row)
            if k % 2000 == 0:
                print(f"  {k}/{a.count}", end="\r")
    with open(os.path.join(a.out, "labels.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["split", "class", "file", "product_id", "brand", "ean13", "ean_valid", "qr_present", "qr_matches",
                    "ean_present", "batch", "expiry", "defects"])
        w.writerows(rows)
    counts = {}
    for r_ in rows:
        counts[f"{r_[0]}/{r_[1]}"] = counts.get(f"{r_[0]}/{r_[1]}", 0) + 1
    info = dict(created=datetime.now().isoformat(timespec="seconds"), total_images=len(rows), size=a.size,
                products=a.products, seed=a.seed, counts=counts, genuine_source="synthetic render (fictional brands)",
                counterfeit_source="simulated defects: " + ", ".join(([x for x in VISUAL_DEFECTS if x != "color_shift"] if a.strong else VISUAL_DEFECTS) if a.visual_only else (DEFECTS if a.allow_missing_codes else [x for x in DEFECTS if x not in ("qr_missing", "ean_missing")])),
                note="Synthetic proof-of-concept dataset. Not real medicine photos. Fine-tune on real packs.")
    json.dump(info, open(os.path.join(a.out, "DATASET_INFO.json"), "w"), indent=2)
    print(f"\nDone: {len(rows)} images -> {a.out}\n{json.dumps(counts, indent=1)}")


if __name__ == "__main__":
    main()