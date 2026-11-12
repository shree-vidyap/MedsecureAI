"""All database access for saved analyses. Every query is filtered by user_id,
so a user can only ever see / change / delete their own reports."""
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

import extensions
from services import expiry_service, code_verify


def _oid(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def _col():
    return extensions.get_db().medicine_reports


def save_report(user_id, a):
    doc = {
        "user_id": user_id,
        "medicine_name": a.get("name"), "manufacturer": a.get("manufacturer"), "batch_number": a.get("batch"),
        "manufacturing_date": a.get("mfg"), "expiry_date": a.get("exp"), "expiry_iso": a.get("exp_iso"),
        "authenticity_result": a.get("result"),
        "overall_confidence": a.get("overall_confidence"), "ai_confidence": a.get("ai_confidence"),
        "ocr_confidence": a.get("ocr_conf"),
        "qr_data": (a.get("qr") or {}).get("data"), "qr_source": (a.get("qr") or {}).get("source"),
        "barcode_data": (a.get("barcode") or {}).get("data"), "barcode_type": (a.get("barcode") or {}).get("type"),
        "barcode_source": (a.get("barcode") or {}).get("source"),
        "ocr_text": a.get("ocr_text"), "ocr_error": a.get("ocr_error"),
        "image": a.get("image"), "threshold": a.get("threshold"), "poc": bool(a.get("poc")), "override": bool(a.get("override")),
        "created_at": datetime.now(timezone.utc),
    }
    return str(_col().insert_one(doc).inserted_id)


def to_view(doc, soon_days=30):
    """Turns a database document into the same dict the Result page template uses."""
    status, days = expiry_service.status_from_iso(doc.get("expiry_iso"), soon_days)
    v = {
        "id": str(doc["_id"]), "created_at": doc.get("created_at"), "image": doc.get("image"),
        "result": doc.get("authenticity_result"), "overall_confidence": doc.get("overall_confidence"),
        "ai_confidence": doc.get("ai_confidence"), "ocr_conf": doc.get("ocr_confidence"),
        "name": doc.get("medicine_name"), "manufacturer": doc.get("manufacturer"), "batch": doc.get("batch_number"),
        "mfg": doc.get("manufacturing_date"), "exp": doc.get("expiry_date"), "exp_iso": doc.get("expiry_iso"),
        "expiry_status": status, "days_left": days,
        "qr": {"data": doc["qr_data"], "source": doc.get("qr_source") or "image"} if doc.get("qr_data") else None,
        "barcode": {"data": doc["barcode_data"], "type": doc.get("barcode_type"),
                    "source": doc.get("barcode_source") or "image"} if doc.get("barcode_data") else None,
        "barcode_error": None, "ocr_text": doc.get("ocr_text"), "ocr_error": doc.get("ocr_error"),
        "model_note": None, "threshold": doc.get("threshold"), "poc": doc.get("poc", False),
        "override": doc.get("override", False),
    }
    v["verify"] = code_verify.verify(v)
    return v


def list_reports(user_id, soon_days=30, limit=500):
    docs = _col().find({"user_id": user_id}).sort("created_at", -1).limit(limit)
    return [to_view(d, soon_days) for d in docs]


def get_report(user_id, rid, soon_days=30):
    oid = _oid(rid)
    doc = _col().find_one({"_id": oid, "user_id": user_id}) if oid else None
    return to_view(doc, soon_days) if doc else None


def delete_report(user_id, rid):
    """Deletes one report. Returns the deleted view dict (so the caller can remove the image) or None."""
    a = get_report(user_id, rid)
    if a:
        _col().delete_one({"_id": _oid(rid), "user_id": user_id})
    return a


def clear_reports(user_id):
    items = list_reports(user_id, limit=100000)
    _col().delete_many({"user_id": user_id})
    return items


FILTERS = ("genuine", "suspicious", "counterfeit", "expired")


def matches(a, f):
    if f == "expired":
        return a["expiry_status"] == "Expired"
    return (a["result"] or "").lower() == f


def stats(reports):
    s = {"total": len(reports)}
    for f in FILTERS:
        s[f] = sum(1 for r in reports if matches(r, f))
    return s


def reminders(reports, soon_days=30, limit=5):
    """Only reports with a KNOWN expiry date that is today or within soon_days. Unknown dates never create reminders."""
    due = [r for r in reports if r["days_left"] is not None and 0 <= r["days_left"] <= soon_days]
    return sorted(due, key=lambda r: r["days_left"])[:limit]
