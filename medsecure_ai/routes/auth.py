import re
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from pymongo.errors import PyMongoError
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import get_db

auth_bp = Blueprint("auth", __name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not name or not email or not password:
            flash("Please fill all the fields.", "danger")
        elif not EMAIL_RE.match(email):
            flash("Please enter a valid email address.", "danger")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        else:
            try:
                users = get_db().users
                if users.find_one({"email": email}):
                    flash("This email is already registered. Please login.", "warning")
                else:
                    users.insert_one({
                        "name": name,
                        "email": email,
                        "password_hash": generate_password_hash(password),
                        "profile_photo": None,
                        "expiry_reminders": True,
                        "created_at": datetime.now(timezone.utc),
                    })
                    flash("Account created! Please login.", "success")
                    return redirect(url_for("auth.login"))
            except PyMongoError:
                flash("Database not available. Please start MongoDB.", "danger")
    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        try:
            user = get_db().users.find_one({"email": email})
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = str(user["_id"])
                session["user_name"] = user["name"]
                return redirect(url_for("main.dashboard"))
            flash("Invalid email or password.", "danger")
        except PyMongoError:
            flash("Database not available. Please start MongoDB.", "danger")
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
