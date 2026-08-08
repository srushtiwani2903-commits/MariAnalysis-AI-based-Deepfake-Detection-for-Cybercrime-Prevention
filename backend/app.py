"""DeepGuard AI - Flask application factory and entry point.

Run locally:   python run.py
Run in prod:   gunicorn -w 4 -b 0.0.0.0:5000 app:app
"""
import os

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash

from config import Config
from extensions import db, jwt
from models import User

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

    # --- Extensions ---
    db.init_app(app)
    jwt.init_app(app)

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
            "name": "DeepGuard AI",
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
                "auth": ["POST /api/auth/register", "POST /api/auth/login",
                         "POST /api/auth/forgot-password", "POST /api/auth/reset-password",
                         "GET /api/auth/me", "PUT /api/auth/profile",
                         "POST /api/auth/change-password"],
                "detection": ["POST /api/detect/image", "POST /api/detect/video",
                              "POST /api/detect/audio", "POST /api/detect/text"],
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

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=Config.DEBUG)
