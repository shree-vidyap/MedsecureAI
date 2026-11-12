"""PDF report with reportlab. Only real data is printed; missing data is written as 'Not Detected' / 'Not assessed'."""
import os
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _t(v):
    """Safe text for the built-in PDF fonts (Latin-1 only)."""
    return escape(str(v).encode("latin-1", "replace").decode("latin-1"))


def build_pdf(a, created, image_path=None):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title="MedSecure AI - Medicine Analysis Report")
    ss = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=ss["Title"], textColor=colors.HexColor("#0d9488"), fontSize=22)
    cell = ParagraphStyle("c", parent=ss["Normal"], fontSize=10, leading=13)
    small = ParagraphStyle("s", parent=ss["Normal"], fontSize=8.5, textColor=colors.HexColor("#475569"), leading=11)
    story = [Paragraph("MedSecure AI", title),
             Paragraph("Medicine Analysis Report", ParagraphStyle("st", parent=ss["Heading3"], alignment=1)),
             Spacer(1, 6)]

    if image_path and os.path.isfile(image_path):
        try:
            from PIL import Image as PILImage
            w, h = PILImage.open(image_path).size
            sc = min(75 * mm / w, 75 * mm / h)
            story += [Image(image_path, width=w * sc, height=h * sc), Spacer(1, 8)]
        except Exception:
            pass

    nd = "Not Detected"
    pct = lambda v: f"{v}%" if v is not None else "Not available"
    qr = f'{a["qr"]["data"]}' if a.get("qr") else "QR Code Not Detected"
    bc = (f'{a["barcode"]["data"]}' + (f' ({a["barcode"]["type"]})' if a["barcode"].get("type") else "")) if a.get("barcode") else "Barcode Not Detected"
    rows = [
        ("Authenticity Result", a.get("result") or "Not assessed (AI model not available)"),
        ("Overall Confidence", pct(a.get("overall_confidence"))),
        ("AI Confidence", pct(a.get("ai_confidence"))),
        ("OCR Confidence", pct(a.get("ocr_conf"))),
        ("Expiry Status", a.get("expiry_status") or "Expiry date could not be detected"),
        ("Medicine Name", a.get("name") or nd),
        ("Manufacturer", a.get("manufacturer") or nd),
        ("Batch Number", a.get("batch") or nd),
        ("Manufacturing Date", a.get("mfg") or nd),
        ("Expiry Date", a.get("exp") or nd),
        ("QR Code", qr),
        ("Barcode", bc),
        ("Date / Time of Analysis", created.strftime("%d %b %Y, %I:%M %p") if created else ""),
    ]
    table = Table([[Paragraph(f"<b>{_t(k)}</b>", cell), Paragraph(_t(v), cell)] for k, v in rows], colWidths=[55 * mm, 115 * mm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0fdfa")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [table, Spacer(1, 10)]

    notes = []
    if a.get("expiry_status") == "Expired":
        notes.append("Expired is not the same as counterfeit. Do not use an expired medicine.")
    if a.get("result") == "Suspicious":
        notes.append("Suspicious means the AI model was not confident enough to call this Genuine or Counterfeit. "
                     "The model has two trained classes only.")
    if a.get("poc"):
        notes.append("Proof-of-concept model: its Counterfeit class was trained with simulated (digitally altered) samples, "
                     "not real counterfeit packs.")
    try:
        from services import code_verify
        for c in code_verify.verify(a)["checks"]:
            if c["status"] == "bad":
                notes.append("Code check: " + c["text"])
    except Exception:
        pass
    if a.get("override"):
        notes.append("The AI model said Genuine, but a QR / barcode check failed, so the result was changed to Suspicious.")
    notes.append("Values were read automatically from the image and may contain mistakes. QR and barcode data are shown "
                 "as scanned; the check digit and QR-vs-print checks show consistency only, not authenticity.")
    notes.append("MedSecure AI is an assistive verification tool. It does not replace professional or pharmacist verification.")
    story += [Paragraph(_t(n), small) for n in notes for _ in (0,)]
    doc.build(story)
    return buf.getvalue()
