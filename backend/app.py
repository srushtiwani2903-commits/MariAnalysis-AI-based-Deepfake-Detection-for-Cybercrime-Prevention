"""MariAnalysis - Flask application factory and entry point.

Run locally:   python run.py
Run in prod:   gunicorn -w 4 -b 0.0.0.0:5000 app:app
"""
import os
from datetime import datetime, timezone

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash

from config import Config
from extensions import db, jwt
from models import ActiveSession, User

# Register blueprints
from routes.admin import admin_bp
from routes.analytics import analytics_bp
from routes.auth import auth_bp
from routes.detection import detect_bp
from routes.history import history_bp
from routes.reports import reports_bp


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # --- CORS ---
    CORS(app, resources={r"/api/*": {"origins": Config.CORS_ORIGINS}}, supports_credentials=False)

    # --- Security headers on every response ---
    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        response.headers.setdefault("Permissions-Policy",
                                    "geolocation=(), microphone=(), camera=(), autoplay=(self)")
        if response.content_type and "text/html" in response.content_type:
            response.headers.setdefault("Content-Security-Policy",
                                        "default-src 'self'; img-src 'self' data:; "
                                        "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
        response.headers.setdefault("Cache-Control",
                                    "no-store, no-cache, must-revalidate, max-age=0")
        return response

    # --- Extensions ---
    db.init_app(app)
    jwt.init_app(app)

    # --- Revoked-session check: a JWT is rejected (401) as soon as its
    # ActiveSession row is deactivated, e.g. by a newer login somewhere else
    # or by logout. This is what makes the kicked-out device fail immediately.
    @jwt.token_in_blocklist_loader
    def check_session_revoked(_jwt_header, jwt_payload):
        jti = jwt_payload.get("jti")
        if not jti:
            return True
        session = ActiveSession.query.filter_by(jti=jti).first()
        if not session or not session.is_active:
            return True
        return session.expires_at < datetime.now(timezone.utc).replace(tzinfo=None)

    # --- Blueprints ---
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(detect_bp, url_prefix="/api/detect")
    app.register_blueprint(history_bp, url_prefix="/api/history")
    app.register_blueprint(analytics_bp, url_prefix="/api/analytics")
    app.register_blueprint(reports_bp, url_prefix="/api/reports")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")

    @app.get("/")
    def root():
        return jsonify({
            "name": "MariAnalysis",
            "version": "1.0.0",
            "description": "AI-Based Deepfake Detection for Cybercrime Prevention",
            "docs": "/api/docs",
            "status": "online",
        })

    @app.get("/api/health")
    def api_health():
        return jsonify({"status": "ok", "model_enabled": Config.MODEL_ENABLED})

    @app.get("/api/docs")
    def api_docs():
        """Inline API documentation (also rendered on the frontend Docs page)."""
        return jsonify({
            "endpoints": {
                "auth": ["POST /api/auth/register", "POST /api/auth/login (email, username or phone)",
                         "POST /api/auth/verify-email", "POST /api/auth/verify-phone",
                         "POST /api/auth/resend-otp",
                         "POST /api/auth/forgot-password", "POST /api/auth/reset-password",
                         "GET /api/auth/me", "PUT /api/auth/profile",
                         "POST /api/auth/change-password"],
                "detection": ["POST /api/detect/image", "POST /api/detect/video",
                              "POST /api/detect/audio", "POST /api/detect/text",
                              "POST /api/detect/url (analyze media from a remote URL)"],
                "history": ["GET /api/history", "GET /api/history/stats",
                            "GET /api/history/<id>", "DELETE /api/history/<id>"],
                "analytics": ["GET /api/analytics/overview", "GET /api/analytics/daily",
                              "GET /api/analytics/weekly", "GET /api/analytics/fake-vs-real",
                              "GET /api/analytics/by-type", "GET /api/analytics/activity",
                              "GET /api/analytics/accuracy-trend"],
                "reports": ["GET /api/reports/<scan_id>/pdf", "GET /api/reports/<scan_id>/csv",
                            "GET /api/reports/<scan_id>/qr"],
                "admin": ["GET /api/admin/stats", "GET /api/admin/users",
                          "DELETE /api/admin/users/<id>", "POST /api/admin/users/<id>/toggle-admin",
                          "GET /api/admin/logs", "GET /api/admin/health",
                          "GET /api/admin/model-performance"],
            }
        })

    # --- Error handlers ---
    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"message": "Resource not found."}), 404

    @app.errorhandler(405)
    def method_not_allowed(_):
        return jsonify({"message": "Method not allowed."}), 405

    @app.errorhandler(413)
    def too_large(_):
        return jsonify({"message": "File too large."}), 413

    @app.errorhandler(500)
    def server_error(_):
        return jsonify({"message": "Internal server error."}), 500

    # --- DB bootstrap + default admin ---
    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(username=Config.ADMIN_USERNAME).first()
        if not admin:
            admin = User(
                username=Config.ADMIN_USERNAME,
                email=Config.ADMIN_EMAIL,
                full_name="System Administrator",
                password_hash=generate_password_hash(Config.ADMIN_PASSWORD),
                is_admin=True,
                is_verified=True,
            )
            db.session.add(admin)
            db.session.commit()

    # --- Kaggle credential check (data is fetched on-demand during training,
    # never downloaded at startup) ---
    if Config.KAGGLE_AUTOSYNC:
        from ml.kaggle_pipeline import write_kaggle_json
        import threading

        def _check_creds():
            try:
                write_kaggle_json()
                app.logger.info("Kaggle credentials OK (data is pulled on-demand during training).")
            except Exception as exc:  # noqa: BLE001
                app.logger.warning("Kaggle credentials missing: %s", exc)

        threading.Thread(target=_check_creds, daemon=True).start()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=Config.DEBUG)
