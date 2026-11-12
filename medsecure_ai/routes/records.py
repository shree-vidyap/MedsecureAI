"""Save to History, History, Reports, PDF, Profile, Pharmacy, Expiry reminders."""
import os
import re
from datetime import datetime, timezone
from io import BytesIO

from bson import ObjectId
from flask import (abort, current_app, flash, redirect, render_template, request, send_file, session, url_for)
from PIL import Image, UnidentifiedImageError
from pymongo.errors import PyMongoError
from werkzeug.security import check_password_hash, generate_password_hash

import extensions
from routes.main import main_bp
from services import pdf_service, report_repo
from utils.auth import login_required

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DB_DOWN = "Database not available. Please start MongoDB."


def uid():
    return session["user_id"]


def soon():
    return current_app.config["EXPIRY_SOON_DAYS"]


def _abs_upload(rel):
    """Absolute path of an upload, only if it really is inside static/uploads (no path tricks)."""
    if not rel:
        return None
    root = os.path.abspath(os.path.join(current_app.root_path, "static", "uploads"))
    path = os.path.abspath(os.path.join(current_app.root_path, "static", rel))
    return path if path.startswith(root + os.sep) else None


def _remove_image(a):
    """Delete the image file of a report, but only from this user's own upload folder."""
    path = _abs_upload(a.get("image"))
    mine = os.path.abspath(os.path.join(current_app.root_path, "static", "uploads", uid())) + os.sep
    if path and path.startswith(mine) and os.path.isfile(path):
        os.remove(path)


# ---------------- Result page: Save + PDF ----------------
@main_bp.route("/result/save", methods=["POST"])
@login_required
def result_save():
    a = session.get("last_analysis")
    if not a:
        flash("Please upload a medicine image.", "warning")
        return redirect(url_for("main.analyze"))
    if a.get("saved_id"):
        flash("This analysis is already saved.", "info")
        return redirect(url_for("main.result"))
    try:
        a["saved_id"] = report_repo.save_report(uid(), a)
    except PyMongoError:
        flash(DB_DOWN, "danger")
        return redirect(url_for("main.result"))
    session["last_analysis"] = a
    flash("Saved to History.", "success")
    return redirect(url_for("main.result"))


@main_bp.route("/result/pdf")
@login_required
def result_pdf():
    a = session.get("last_analysis")
    if not a:
        return redirect(url_for("main.analyze"))
    data = pdf_service.build_pdf(a, datetime.now(), _abs_upload(a.get("image")))
    return send_file(BytesIO(data), mimetype="application/pdf", as_attachment=True, download_name="MedSecure_Report.pdf")


# ---------------- History ----------------
@main_bp.route("/history")
@login_required
def history():
    f = request.args.get("f", "all")
    try:
        reports = report_repo.list_reports(uid(), soon())
    except PyMongoError:
        flash(DB_DOWN, "danger")
        reports = []
    stats = report_repo.stats(reports)
    shown = reports if f not in report_repo.FILTERS else [r for r in reports if report_repo.matches(r, f)]
    return render_template("history.html", reports=shown, stats=stats, f=f if f in report_repo.FILTERS else "all")


@main_bp.route("/history/clear", methods=["POST"])
@login_required
def history_clear():
    try:
        for a in report_repo.clear_reports(uid()):
            _remove_image(a)
        flash("History cleared.", "success")
    except PyMongoError:
        flash(DB_DOWN, "danger")
    return redirect(url_for("main.profile"))


# ---------------- Reports ----------------
@main_bp.route("/reports")
@login_required
def reports():
    try:
        items = report_repo.list_reports(uid(), soon())
    except PyMongoError:
        flash(DB_DOWN, "danger")
        items = []
    return render_template("reports.html", reports=items)


def _get_or_404(rid):
    try:
        a = report_repo.get_report(uid(), rid, soon())
    except PyMongoError:
        abort(503)
    if not a:
        abort(404)
    return a


@main_bp.route("/reports/<rid>")
@login_required
def report_view(rid):
    a = _get_or_404(rid)
    origin = "history" if request.args.get("from") == "history" else "reports"
    return render_template("report_view.html", a=a, origin=origin, simulated=a["poc"])


@main_bp.route("/reports/<rid>/pdf")
@login_required
def report_pdf(rid):
    a = _get_or_404(rid)
    data = pdf_service.build_pdf(a, _local(a["created_at"]), _abs_upload(a.get("image")))
    return send_file(BytesIO(data), mimetype="application/pdf", as_attachment=True,
                     download_name=f"MedSecure_Report_{rid[-6:]}.pdf")


@main_bp.route("/reports/<rid>/delete", methods=["POST"])
@login_required
def report_delete(rid):
    try:
        a = report_repo.delete_report(uid(), rid)
    except PyMongoError:
        flash(DB_DOWN, "danger")
        return redirect(url_for("main.reports"))
    if a:
        _remove_image(a)
        flash("Report deleted.", "success")
    else:
        flash("Report not found.", "warning")
    return redirect(url_for("main.history" if request.form.get("from") == "history" else "main.reports"))


def _local(v):
    if not v:
        return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.astimezone()


# ---------------- Pharmacy ----------------
@main_bp.route("/pharmacy")
@login_required
def pharmacy():
    return render_template("pharmacy.html")


# ---------------- Profile ----------------
def _user():
    return extensions.get_db().users.find_one({"_id": ObjectId(uid())})


@main_bp.route("/profile")
@login_required
def profile():
    try:
        user = _user()
        stats = report_repo.stats(report_repo.list_reports(uid(), soon()))
    except PyMongoError:
        flash(DB_DOWN, "danger")
        return redirect(url_for("main.dashboard"))
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))
    return render_template("profile.html", user=user, stats=stats)


@main_bp.route("/profile/edit", methods=["POST"])
@login_required
def profile_edit():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    photo = request.files.get("photo")
    if not name or not EMAIL_RE.match(email):
        flash("Please enter a name and a valid email address.", "danger")
        return redirect(url_for("main.profile"))
    try:
        users = extensions.get_db().users
        if users.find_one({"email": email, "_id": {"$ne": ObjectId(uid())}}):
            flash("This email is already used by another account.", "danger")
            return redirect(url_for("main.profile"))
        update = {"name": name, "email": email}
        if photo and photo.filename:
            if not photo.filename.lower().endswith((".jpg", ".jpeg", ".png")):
                flash("Unsupported file format. Please upload JPG, JPEG, or PNG.", "danger")
                return redirect(url_for("main.profile"))
            try:
                img = Image.open(photo.stream); img.verify(); photo.stream.seek(0)
                img = Image.open(photo.stream).convert("RGB")
            except (UnidentifiedImageError, OSError):
                flash("Unsupported file format. Please upload JPG, JPEG, or PNG.", "danger")
                return redirect(url_for("main.profile"))
            side = min(img.size)
            img = img.crop(((img.width - side) // 2, (img.height - side) // 2,
                            (img.width + side) // 2, (img.height + side) // 2)).resize((256, 256))
            folder = os.path.join(current_app.root_path, "static", "uploads", "profile")
            os.makedirs(folder, exist_ok=True)
            img.save(os.path.join(folder, f"{uid()}.jpg"), "JPEG", quality=90)
            update["profile_photo"] = f"uploads/profile/{uid()}.jpg"
        users.update_one({"_id": ObjectId(uid())}, {"$set": update})
        session["user_name"] = name
        flash("Profile updated.", "success")
    except PyMongoError:
        flash(DB_DOWN, "danger")
    return redirect(url_for("main.profile"))


@main_bp.route("/profile/password", methods=["POST"])
@login_required
def profile_password():
    cur, new, conf = (request.form.get(k, "") for k in ("current", "new", "confirm"))
    try:
        users = extensions.get_db().users
        user = users.find_one({"_id": ObjectId(uid())})
        if not user or not check_password_hash(user["password_hash"], cur):
            flash("Current password is incorrect.", "danger")
        elif len(new) < 8:
            flash("Password must be at least 8 characters.", "danger")
        elif new != conf:
            flash("Passwords do not match.", "danger")
        else:
            users.update_one({"_id": user["_id"]}, {"$set": {"password_hash": generate_password_hash(new)}})
            flash("Password changed.", "success")
    except PyMongoError:
        flash(DB_DOWN, "danger")
    return redirect(url_for("main.profile"))


@main_bp.route("/reminders/toggle", methods=["POST"])
@login_required
def reminders_toggle():
    try:
        users = extensions.get_db().users
        user = users.find_one({"_id": ObjectId(uid())})
        on = not user.get("expiry_reminders", True)
        users.update_one({"_id": user["_id"]}, {"$set": {"expiry_reminders": on}})
        flash("Expiry reminders turned " + ("on." if on else "off."), "success")
    except PyMongoError:
        flash(DB_DOWN, "danger")
    return redirect(request.form.get("next") or url_for("main.profile"))
