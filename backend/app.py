"""MariAnalysis - Flask app factory and entry point.

Local:   python run.py
Prod:    gunicorn -w 4 -b 0.0.0.0:5001 app:app
"""
import os
from datetime import datetime, timezone

from flask import Flask, jsonify
from flask_cors import CORS
from sqlalchemy import text
from werkzeug.security import generate_password_hash

from config import Config
from extensions import db, jwt
from models import ActiveSession, User

# Register blueprints
from routes.admin import admin_bp
from routes.analytics import analytics_bp
from routes.auth import auth_bp
from routes.chat import chat_bp
from routes.detection import detect_bp
from routes.evidence import evidence_bp
from routes.history import history_bp
from routes.keys import keys_bp
from routes.model import model_bp
from routes.reports import reports_bp


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # --- CORS ---
    # supports_credentials lets the cookie-based web session flow through when
    # the API is called cross-origin; the dev frontend is same-origin via the
    # CRA proxy so no CORS is even involved there.
    CORS(app, resources={r"/api/*": {"origins": Config.CORS_ORIGINS}}, supports_credentials=True)

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

    # A JWT dies with its ActiveSession row: once that row is deactivated
    # (new login elsewhere, logout, inactivity timeout) the token gets a 401
    # immediately. Also keeps last_seen_at fresh so the backend is the single
    # source of truth for session state.
    @jwt.token_in_blocklist_loader
    def check_session_revoked(_jwt_header, jwt_payload):
        jti = jwt_payload.get("jti")
        if not jti:
            return True
        session = ActiveSession.query.filter_by(jti=jti).first()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if not session or not session.is_active:
            return True
        if session.expires_at < now:
            return True
        # Inactivity timeout: if the user hasn't made an authenticated request
        # for SESSION_INACTIVITY_MINUTES, treat the session as stale.
        inactivity = Config.SESSION_INACTIVITY_MINUTES
        if inactivity and session.last_seen_at:
            idle = (now - session.last_seen_at).total_seconds()
            if idle > inactivity * 60:
                session.is_active = False
                session.revoked_reason = "inactivity"
                db.session.commit()
                return True
        # Valid token: refresh the activity stamp. This runs once at SSE
        # connect time, so it doesn't keep idle tabs alive on its own.
        session.last_seen_at = now
        db.session.commit()
        return False

    # --- JWT error loaders: every 401 uses {"success": false, "message": ...}
    # so the frontend can reliably detect "kicked out" vs "not logged in". ---
    @jwt.unauthorized_loader
    def missing_token(reason):
        return jsonify({"success": False,
                        "message": "Authentication required. Please log in."}), 401

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return jsonify({"success": False,
                        "message": "Your session is no longer valid. Please log in again."}), 401

    @jwt.expired_token_loader
    def expired_token(_jwt_header, jwt_payload):
        return jsonify({"success": False,
                        "message": "Your session has expired. Please log in again."}), 401

    @jwt.revoked_token_loader
    def revoked_token(_jwt_header, jwt_payload):
        # A revoked token means its ActiveSession row was deactivated - which
        # happens when the same account logs in elsewhere.
        jti = jwt_payload.get("jti")
        reason = "superseded"
        if jti:
            session = ActiveSession.query.filter_by(jti=jti).first()
            if session and session.revoked_reason:
                reason = session.revoked_reason
        if reason == "inactivity":
            message = "Your session expired due to inactivity. Please log in again."
        elif reason == "logout":
            message = "You have been logged out."
        else:
            message = ("Your account was logged in from another device. "
                       "You have been logged out.")
        return jsonify({"success": False, "message": message}), 401

    # --- Blueprints ---
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(detect_bp, url_prefix="/api/detect")
    app.register_blueprint(history_bp, url_prefix="/api/history")
    app.register_blueprint(analytics_bp, url_prefix="/api/analytics")
    app.register_blueprint(reports_bp, url_prefix="/api/reports")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")
    app.register_blueprint(evidence_bp, url_prefix="/api/evidence")
    app.register_blueprint(keys_bp, url_prefix="/api")
    app.register_blueprint(model_bp, url_prefix="/api/model")

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
                         "POST /api/auth/change-password",
                         "POST /api/auth/logout",
                         "GET /api/auth/events (SSE - real-time logout)",
                         "NOTE: single active session per account - a new login revokes older sessions (401)"],
                "detection": ["POST /api/detect/image", "POST /api/detect/video",
                              "POST /api/detect/audio", "POST /api/detect/text",
                              "POST /api/detect/email (phishing scanner)",
                              "POST /api/detect/post (image + caption / fake news)",
                              "POST /api/detect/realtime (webcam frame, not stored)",
                              "POST /api/detect/url (analyze media from a remote URL)"],
                "history": ["GET /api/history", "GET /api/history/stats",
                            "GET /api/history/<id>", "DELETE /api/history/<id>"],
                "analytics": ["GET /api/analytics/overview", "GET /api/analytics/daily",
                              "GET /api/analytics/weekly", "GET /api/analytics/fake-vs-real",
                              "GET /api/analytics/by-type", "GET /api/analytics/activity",
                              "GET /api/analytics/accuracy-trend",
                              "GET /api/analytics/deepfake-types (leaderboard)",
                              "GET /api/analytics/org-dashboard (organisation view)"],
                "reports": ["GET /api/reports/<scan_id>/pdf", "GET /api/reports/<scan_id>/csv",
                            "GET /api/reports/<scan_id>/qr",
                            "GET /api/reports/<scan_id>/heatmap (XAI manipulation map)"],
                "evidence": ["POST /api/evidence/<scan_id>/register (case + blockchain anchor)",
                             "GET /api/evidence/cases", "GET /api/evidence/chain",
                             "GET /api/evidence/verify/<scan_id>",
                             "POST /api/evidence/<case_id>/status"],
                "chat": ["POST /api/chat (deepfake awareness assistant)",
                         "GET /api/chat/suggestions"],
                "keys": ["GET /api/keys", "POST /api/keys (browser-extension API key)",
                         "DELETE /api/keys/<id>", "POST /api/extend/analyze"],
                "model": ["POST /api/model/train (admin - start Kaggle GPU cloud training {media: image|video|audio|text})",
                          "GET /api/model/train/<media> (admin - job status)",
                          "POST /api/model/train/<media>/download (admin - pull trained weights)",
                          "GET /api/model/weights (admin - local trained models)",
                          "GET /api/model/health (admin - kaggle client + credentials)"],
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

    # --- DB bootstrap + default admin + schema migration + upkeep ---
    with app.app_context():
        db.create_all()
        _migrate_schema(app)
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
        _purge_stale_uploads(app)

    # Kaggle credentials checked in the background; datasets are only pulled
    # on demand during training, never at startup.
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

    # Pre-build the Kaggle reference profile in the background so the webcam
    # and URL scans already have it ready on the first frame.
    if Config.KAGGLE_REFERENCE_ENABLED:
        from services.kaggle_reference import kaggle_reference
        import threading

        threading.Thread(target=kaggle_reference.ensure_built, daemon=True).start()

    return app


def _migrate_schema(app):
    """Add newly introduced columns to pre-existing tables (SQLite-safe)."""
    try:
        insp = db.inspect(db.engine)
        cols = {c["name"] for c in insp.get_columns("scan_history")}
        adds = []
        if "trust_score" not in cols:
            adds.append("ALTER TABLE scan_history ADD COLUMN trust_score FLOAT DEFAULT 0")
        if "file_hash" not in cols:
            adds.append("ALTER TABLE scan_history ADD COLUMN file_hash VARCHAR(64) DEFAULT ''")
        if "models" not in cols:
            adds.append("ALTER TABLE scan_history ADD COLUMN models JSON")
        if "reasons" not in cols:
            adds.append("ALTER TABLE scan_history ADD COLUMN reasons JSON")
        for stmt in adds:
            db.session.execute(text(stmt))
        if adds:
            db.session.commit()
            app.logger.info("Applied schema migration: %d new columns", len(adds))
        key_cols = {c["name"] for c in insp.get_columns("api_keys")}
        if "key_encrypted" not in key_cols:
            db.session.execute(text("ALTER TABLE api_keys ADD COLUMN key_encrypted TEXT"))
            db.session.commit()
            app.logger.info("Applied schema migration: api_keys.key_encrypted")
        sess_cols = {c["name"] for c in insp.get_columns("active_sessions")}
        sess_adds = []
        if "user_agent" not in sess_cols:
            sess_adds.append("ALTER TABLE active_sessions ADD COLUMN user_agent VARCHAR(255) DEFAULT ''")
        if "revoked_reason" not in sess_cols:
            sess_adds.append("ALTER TABLE active_sessions ADD COLUMN revoked_reason VARCHAR(32)")
        for stmt in sess_adds:
            db.session.execute(text(stmt))
        if sess_adds:
            db.session.commit()
            app.logger.info("Applied schema migration: active_sessions %d new columns", len(sess_adds))
    except Exception as exc:  # noqa: BLE001
        app.logger.warning("Schema migration skipped: %s", exc)


def _purge_stale_uploads(app):
    """Delete uploaded media older than the retention window to limit disk usage."""
    try:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None).timestamp() - \
            Config.UPLOAD_RETENTION_DAYS * 86400
        removed = 0
        for name in os.listdir(Config.UPLOAD_FOLDER):
            path = os.path.join(Config.UPLOAD_FOLDER, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError:
                continue
        if removed:
            app.logger.info("Purged %d stale upload files", removed)
    except Exception as exc:  # noqa: BLE001
        app.logger.warning("Upload purge skipped: %s", exc)


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=Config.DEBUG)
