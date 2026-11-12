"""Finds labelled dates (MFG / EXP) in OCR text, parses them, and gives the expiry status.
Only dates that follow a label such as "EXP" or "MFG" are used. Nothing is guessed."""
import calendar
import re
from datetime import date

MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}

DATE_TOKEN = (r"(?:\d{1,2}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{2,4}"      # 12/03/2027
              r"|\d{4}\s*[/\-.]\s*\d{1,2}(?:\s*[/\-.]\s*\d{1,2})?"     # 2027-03
              r"|\d{1,2}\s*[/\-.]\s*\d{2,4}"                           # 03/2027, 03/27
              r"|[A-Z]{3,9}\s*[\-./,']?\s*\d{2,4})")                   # MAR 2027, MARCH-27

EXP_KEY = r"(?:EXP(?:IRY|IRES)?\.?(?:\s*DATE|\s*DT\.?)?|USE\s*BEFORE|BEST\s*BEFORE)"
MFG_KEY = (r"(?:M\.?\s?F\.?\s?G\.?(?:\s*(?:DATE|DT\.?|ON))?|MFD\.?(?:\s*(?:DATE|DT\.?|ON))?"
           r"|MANUFACTUR(?:ED|ING)\s*(?:DATE|ON)?)")


def _year(y):
    y = int(y)
    return 2000 + y if y < 100 else y


def parse_date(token):
    """Returns {'year','month','day'(or None)} or None if it is not a valid date."""
    t = token.upper().strip()
    if not re.search(r"[A-Z]{3,}", t):                  # numeric date: fix common OCR confusions
        t = t.translate(str.maketrans("OIL|", "0111"))
    try:
        m = re.fullmatch(r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})", t)
        if m:
            d, mo, y = int(m[1]), int(m[2]), _year(m[3])
            date(y, mo, d)
            return {"year": y, "month": mo, "day": d}
        m = re.fullmatch(r"(\d{4})\s*[/\-.]\s*(\d{1,2})(?:\s*[/\-.]\s*(\d{1,2}))?", t)
        if m:
            y, mo = int(m[1]), int(m[2]); d = int(m[3]) if m[3] else None
            date(y, mo, d or 1)
            return {"year": y, "month": mo, "day": d}
        m = re.fullmatch(r"(\d{1,2})\s*[/\-.]\s*(\d{2,4})", t)
        if m:
            mo, y = int(m[1]), _year(m[2])
            date(y, mo, 1)
            return {"year": y, "month": mo, "day": None}
        m = re.fullmatch(r"([A-Z]{3,9})\s*[\-./,']?\s*(\d{2,4})", t)
        if m and m[1][:3] in MONTHS:
            y = _year(m[2]); mo = MONTHS[m[1][:3]]
            date(y, mo, 1)
            return {"year": y, "month": mo, "day": None}
    except ValueError:
        return None
    return None


def valid_range(d):
    return d is not None and 2000 <= d["year"] <= 2100


def display(d):
    if d["day"]:
        return f'{d["day"]:02d}/{d["month"]:02d}/{d["year"]}'
    return f'{d["month"]:02d}/{d["year"]}'


def end_date(d):
    """Expiry on month-only dates means the LAST day of that month."""
    day = d["day"] or calendar.monthrange(d["year"], d["month"])[1]
    return date(d["year"], d["month"], day)


def _fix_zeros(t):
    """OCR often reads 0 as O inside dates (O2/2O27). Fix only the O next to digits or date separators."""
    return re.sub(r"(?<=\d)O(?=[\d/\-.]|\b)|(?<=[/\-.\s])O(?=\d)", "0", t)


def find_labelled(text, key):
    for m in re.finditer(key + r"[\s:.\-]*(" + DATE_TOKEN + ")", _fix_zeros(text.upper())):
        d = parse_date(m.group(1))
        if valid_range(d):
            return d
    return None


def extract_dates(text):
    return find_labelled(text, MFG_KEY), find_labelled(text, EXP_KEY)


def expiry_status(exp, today=None, soon_days=30):
    """Returns (status, days_left). status: Valid / Expiring Soon / Expired / None (unknown)."""
    if exp is None:
        return None, None
    today = today or date.today()
    days = (end_date(exp) - today).days
    if days < 0:
        return "Expired", days
    if days <= soon_days:
        return "Expiring Soon", days
    return "Valid", days


def status_from_iso(iso, soon_days=30, today=None):
    """Status for a stored expiry date (ISO string of the LAST valid day). Recomputed every time it is shown."""
    if not iso:
        return None, None
    days = (date.fromisoformat(iso) - (today or date.today())).days
    if days < 0:
        return "Expired", days
    if days <= soon_days:
        return "Expiring Soon", days
    return "Valid", days
