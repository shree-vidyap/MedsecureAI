import hmac
import secrets

from flask import abort, request, session


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def check_csrf():
    """Every POST must carry the token (hidden form field or X-CSRF-Token header)."""
    if request.method == "POST":
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        expected = session.get("_csrf", "")
        if not sent or not expected or not hmac.compare_digest(sent, expected):   # empty token is never valid
            abort(400)
