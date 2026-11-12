"""Offline checks on the scanned barcode / QR text. Pure functions, never raise, no network.

What is checked (all honest, none of it proves a medicine is real):
  1. Barcode GTIN check digit (EAN-8 / UPC-A / EAN-13 / GTIN-14, GS1 mod-10). A wrong digit = misprinted or forged number.
  2. QR payload fields (GTIN / batch / expiry) are read, in either "GTIN:..|B:..|E:.." style or GS1 "(01)..(10)..(17).." style.
  3. QR batch + expiry are compared with what OCR read from the pack text.
  4. QR GTIN is compared with the barcode GTIN.

A passing check only means "consistent". A real counterfeiter can print a valid check digit and a matching QR.
Real authentication needs the manufacturer / GS1 / regulator database, which this app does not have.
"""
import re

from services import expiry_service as ex

GS1_PREFIX_NOTE = {"890": "India (GS1 India prefix)"}


# ---------- GTIN ----------
def gtin_check_digit(body):
    """GS1 mod-10 check digit for the digits WITHOUT the last digit."""
    total = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(body)))
    return (10 - total % 10) % 10


def check_gtin(value):
    """Returns None if the text has no GTIN-length digit string, else a dict."""
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    kind = {8: "EAN-8", 12: "UPC-A", 13: "EAN-13", 14: "GTIN-14"}.get(len(digits))
    if not kind:
        return None
    ok = gtin_check_digit(digits[:-1]) == int(digits[-1])
    return {"digits": digits, "kind": kind, "valid": ok, "expected": gtin_check_digit(digits[:-1]),
            "prefix_note": GS1_PREFIX_NOTE.get(digits[:3]) if kind == "EAN-13" else None}


# ---------- QR payload ----------
def _gs1_expiry(yymmdd):
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    return {"year": 2000 + yy, "month": mm, "day": dd or None}


def parse_qr(text):
    """Returns {'gtin','batch','expiry'} (values may be None) or None if nothing known was found."""
    if not text:
        return None
    t = str(text).strip()
    out = {"gtin": None, "batch": None, "expiry": None}
    # GS1 Application Identifiers: (01) GTIN-14, (10) batch, (17) expiry YYMMDD
    if "(01)" in t or "(10)" in t or "(17)" in t:
        m = re.search(r"\(01\)(\d{14})", t)
        if m:
            out["gtin"] = m.group(1)
        m = re.search(r"\(10\)([^(]{1,20})", t)
        if m:
            out["batch"] = m.group(1).strip()
        m = re.search(r"\(17\)(\d{6})", t)
        if m:
            try:
                out["expiry"] = _gs1_expiry(m.group(1))
            except ValueError:
                pass
    else:
        for part in re.split(r"[|;&,\n]", t):
            if ":" not in part and "=" not in part:
                continue
            k, v = re.split(r"[:=]", part, 1)
            k, v = k.strip().upper(), v.strip()
            if k in ("GTIN", "EAN", "BARCODE", "01"):
                out["gtin"] = re.sub(r"\D", "", v) or None
            elif k in ("B", "BATCH", "BNO", "B.NO", "LOT", "10"):
                out["batch"] = v or None
            elif k in ("E", "EXP", "EXPIRY", "EXPIRES", "17"):
                d = ex.parse_date(v)
                out["expiry"] = d if ex.valid_range(d) else None
    return out if any(out.values()) else None


def _norm(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _same_gtin(a, b):
    a, b = re.sub(r"\D", "", a or ""), re.sub(r"\D", "", b or "")
    return a.lstrip("0") == b.lstrip("0") if a and b else None          # EAN-13 vs GTIN-14 differ only by leading zeros


# ---------- main entry ----------
def verify(a):
    """a = the analysis dict (needs keys: qr, barcode, batch, exp_iso). Returns {'checks': [...], 'hard_fail': bool, 'reasons': [...]}"""
    checks, reasons = [], []

    def add(label, status, text):
        checks.append({"label": label, "status": status, "text": text})     # status: ok / bad / na
        if status == "bad":
            reasons.append(text)

    bc = (a.get("barcode") or {}).get("data")
    g = check_gtin(bc)
    if not bc:
        add("Barcode check digit", "na", "No barcode was read, so the check digit could not be tested.")
    elif not g:
        add("Barcode check digit", "na", f"Barcode text '{bc}' is not an EAN/UPC/GTIN number, so no check digit test was done.")
    elif g["valid"]:
        extra = f" Prefix: {g['prefix_note']}." if g["prefix_note"] else ""
        add("Barcode check digit", "ok", f"{g['kind']} {g['digits']}: check digit is correct.{extra}")
    else:
        add("Barcode check digit", "bad",
            f"{g['kind']} {g['digits']}: check digit is WRONG (should be {g['expected']}). The number may be misprinted or forged.")

    q = parse_qr((a.get("qr") or {}).get("data"))
    if not (a.get("qr") or {}).get("data"):
        add("QR content", "na", "No QR code was read.")
    elif not q:
        add("QR content", "na", "QR code was read, but it has no batch / expiry / GTIN fields this app understands "
                               "(for example it may be a website link).")
    else:
        found = ", ".join(k for k, v in (("GTIN", q["gtin"]), ("batch", q["batch"]), ("expiry", q["expiry"])) if v)
        add("QR content", "ok", f"QR contains: {found}.")

        if q["gtin"] and (qg := check_gtin(q["gtin"])) and not qg["valid"]:
            add("QR GTIN check digit", "bad", f"GTIN {qg['digits']} inside the QR has a WRONG check digit (should be {qg['expected']}).")
        if q["gtin"] and g:
            same = _same_gtin(q["gtin"], g["digits"])
            add("QR vs barcode", "ok" if same else "bad",
                "QR GTIN and barcode number are the same." if same else
                f"QR GTIN ({q['gtin']}) and barcode ({g['digits']}) are DIFFERENT.")
        if q["batch"]:
            if a.get("batch"):
                same = _norm(q["batch"]) == _norm(a["batch"])
                add("QR batch vs printed batch", "ok" if same else "bad",
                    f"Batch {q['batch']} matches the printed batch." if same else
                    f"QR batch ({q['batch']}) is DIFFERENT from the printed batch ({a['batch']}). OCR may also have misread it; check the pack.")
            else:
                add("QR batch vs printed batch", "na", "Printed batch was not read by OCR, so it could not be compared.")
        if q["expiry"]:
            if a.get("exp_iso"):
                qe = ex.end_date(q["expiry"]).isoformat()[:7]
                same = qe == a["exp_iso"][:7]
                add("QR expiry vs printed expiry", "ok" if same else "bad",
                    "QR expiry month matches the printed expiry." if same else
                    f"QR expiry ({qe}) is DIFFERENT from the printed expiry ({a['exp_iso'][:7]}). OCR may also have misread it; check the pack.")
            else:
                add("QR expiry vs printed expiry", "na", "Printed expiry was not read by OCR, so it could not be compared.")

    return {"checks": checks, "hard_fail": bool(reasons), "reasons": reasons}
