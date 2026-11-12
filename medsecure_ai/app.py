from flask import Flask, render_template, jsonify
from pymongo.errors import PyMongoError

from config import Config
from extensions import get_db
from routes.auth import auth_bp
from routes.main import main_bp
import routes.analyze  # noqa: F401  (adds /analyze and /result routes to main_bp)
import routes.records  # noqa: F401  (History, Reports, PDF, Profile, Pharmacy)
from datetime import timezone
from utils.security import check_csrf, csrf_token


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.before_request(check_csrf)
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.template_filter("localdt")
    def localdt(v, fmt="%d %b %Y, %I:%M %p"):
        if not v:
            return ""
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone().strftime(fmt)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    @app.route("/health")
    def health():
        try:
            get_db().command("ping")
            return jsonify(status="running", mongodb=True)
        except PyMongoError as e:
            return jsonify(status="running", mongodb=False, error=e.__class__.__name__)

    @app.errorhandler(404)
    def not_found(_):
        return render_template("coming_soon.html", title="Page Not Found"), 404

    @app.errorhandler(400)
    def bad_request(_):
        return render_template("coming_soon.html", title="Security check failed. Please go back, refresh the page and try again."), 400

    @app.errorhandler(503)
    def db_down(_):
        return render_template("coming_soon.html", title="Database not available. Please start MongoDB."), 503

    @app.errorhandler(413)
    def too_large(_):
        return "File too large. Maximum size is 8 MB.", 413

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=app.config["DEBUG"])
