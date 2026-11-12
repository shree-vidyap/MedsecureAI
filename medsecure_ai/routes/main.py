from flask import Blueprint, current_app, render_template, redirect, url_for, session

from utils.auth import login_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("main.dashboard"))
    return render_template("welcome.html")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    due, reminders_on = [], True
    try:
        import extensions
        from bson import ObjectId
        from services import report_repo
        user = extensions.get_db().users.find_one({"_id": ObjectId(session["user_id"])})
        reminders_on = bool(user.get("expiry_reminders", True)) if user else True
        if reminders_on:
            soon = current_app.config["EXPIRY_SOON_DAYS"]
            due = report_repo.reminders(report_repo.list_reports(session["user_id"], soon), soon)
    except Exception:          # the dashboard must always open, even if MongoDB has a problem
        due = []
    return render_template("dashboard.html", due=due)


# Pages that will be built in later phases (placeholders for now)
PLACEHOLDERS = {
}


def _make_view(title):
    @login_required
    def view():
        return render_template("coming_soon.html", title=title)
    return view


for _key, _title in PLACEHOLDERS.items():
    _path = "/" + _key.replace("_", "/")
    main_bp.add_url_rule(_path, endpoint=_key, view_func=_make_view(_title))
