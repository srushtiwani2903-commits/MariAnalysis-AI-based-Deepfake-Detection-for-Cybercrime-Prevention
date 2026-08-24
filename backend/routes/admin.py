"""Admin endpoints: system stats, user management, logs, model health.

All routes require the admin_required decorator (JWT + is_admin flag).
"""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from functools import wraps

from config import Config
from extensions import db
from models import AIPrediction, Log, Report, ScanHistory, User
from utils.idps import audit

admin_bp = Blueprint("admin", __name__)


def admin_required(fn=None):
    """Decorator factory: supports both @admin_required and @admin_required()."""
    def decorator(func):
        @wraps(func)
        @jwt_required()
        def wrapper(*args, **kwargs):
            user = db.session.get(User, int(get_jwt_identity()))
            if not user or not user.is_admin:
                return jsonify({"message": "Admin access required."}), 403
            return func(*args, **kwargs)
        return wrapper
    return decorator(fn) if fn else decorator


@admin_bp.route("/stats", methods=["GET"])
@admin_required()
def stats():
    total_users = User.query.count()
    total_scans = ScanHistory.query.count()
    fake = ScanHistory.query.filter_by(result="fake").count()
    real = ScanHistory.query.filter_by(result="authentic").count()
    total_reports = Report.query.count()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    scans_today = ScanHistory.query.filter(ScanHistory.created_at >= today_start).count()
    accuracy = round((fake + real) / total_scans * 100, 1) if total_scans else 0.0
    return jsonify({
        "total_users": total_users,
        "total_scans": total_scans,
        "fake_detected": fake,
        "real_detected": real,
        "total_reports": total_reports,
        "scans_today": scans_today,
        "accuracy": accuracy,
    })


@admin_bp.route("/users", methods=["GET"])
@admin_required()
def list_users():
    users = User.query.order_by(User.created_at.desc()).limit(200).all()
    return jsonify({"items": [u.to_dict() for u in users]})


@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@admin_required()
def delete_user(user_id):
    target = db.session.get(User, user_id)
    if not target:
        return jsonify({"message": "User not found."}), 404
    if target.id == int(get_jwt_identity()):
        return jsonify({"message": "You cannot delete your own account."}), 400
    db.session.delete(target)
    db.session.commit()
    audit("delete", get_jwt_identity(), "User", user_id, request.remote_addr, "Deleted user account")
    return jsonify({"message": "User deleted."})


@admin_bp.route("/users/<int:user_id>/toggle-admin", methods=["POST"])
@admin_required()
def toggle_admin(user_id):
    target = db.session.get(User, user_id)
    if not target:
        return jsonify({"message": "User not found."}), 404
    if target.id == int(get_jwt_identity()):
        return jsonify({"message": "You cannot change your own role."}), 400
    target.is_admin = not target.is_admin
    db.session.commit()
    audit("update", get_jwt_identity(), "User", user_id, request.remote_addr,
          f"Toggled admin role -> {target.is_admin}")
    return jsonify({"message": "Role updated.", "is_admin": target.is_admin})


@admin_bp.route("/logs", methods=["GET"])
@admin_required()
def logs():
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("limit", 20, type=int)))
    pagination = Log.query.order_by(Log.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "items": [l.to_dict() for l in pagination.items],
        "page": page,
        "pages": pagination.pages,
        "total": pagination.total,
    })


@admin_bp.route("/health", methods=["GET"])
@admin_required()
def health():
    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    storage_free = 0
    try:
        import shutil
        storage_free = shutil.disk_usage(Config.UPLOAD_FOLDER).free
    except Exception:
        pass
    return jsonify({
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "error",
        "model_enabled": Config.MODEL_ENABLED,
        "storage_free_bytes": storage_free,
        "uptime_seconds": _uptime(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@admin_bp.route("/model-performance", methods=["GET"])
@admin_required()
def model_performance():
    """Aggregate model metrics across all predictions."""
    total = AIPrediction.query.count()
    per_model = {}
    for pred in AIPrediction.query.limit(1000).all():
        per_model[pred.model_name] = per_model.get(pred.model_name, 0) + 1
    avg_conf = db.session.query(db.func.avg(AIPrediction.confidence)).scalar() or 0
    return jsonify({
        "total_predictions": total,
        "models_used": per_model,
        "avg_confidence": round(float(avg_conf), 1),
        "engine_mode": "trained-models" if Config.MODEL_ENABLED else "heuristic-ensemble-v1",
    })


_start_time = datetime.now(timezone.utc)


def _uptime():
    return int((datetime.now(timezone.utc) - _start_time).total_seconds())
