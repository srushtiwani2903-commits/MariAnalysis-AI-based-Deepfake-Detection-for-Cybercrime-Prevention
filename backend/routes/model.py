"""Cloud model training endpoints (admin) - Kaggle GPU training integration.

Training happens entirely on Kaggle's cloud: the backend pushes a training
notebook, Kaggle mounts the dataset on its own machine, trains, and the backend
pulls back only the trained weights. No dataset is ever stored in the project.

- POST /api/model/train              start a cloud training job {media}
- GET  /api/model/train/<media>      job status + kernel state
- POST /api/model/train/<media>/download   pull weights for a completed job
- GET  /api/model/weights            which trained models are checked out locally
- GET  /api/model/health             kaggle client + credentials check
"""
from functools import wraps

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from config import Config
from extensions import db
from ml import cloud_trainer
from models import Log, User
from utils.idps import audit

model_bp = Blueprint("model", __name__)


def admin_required(fn=None):
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


def _log(user_id, action, details, ip):
    db.session.add(Log(user_id=user_id, action=action, details=details, ip_address=ip))
    db.session.commit()
    audit("create", user_id, "Model", action, ip, details)


@model_bp.route("/train", methods=["POST"])
@admin_required()
def start_train():
    data = request.get_json(silent=True) or {}
    media = (data.get("media") or "").strip().lower()
    if media not in cloud_trainer.TRAINERS:
        return jsonify({"message": f"Media must be one of: {sorted(cloud_trainer.TRAINERS)}"}), 400
    try:
        job = cloud_trainer.submit_training(media)
    except RuntimeError as exc:
        return jsonify({"message": str(exc)}), 400
    user_id = int(get_jwt_identity())
    _log(user_id, "start_model_training",
         f"Cloud training started for {media} (kernel {job.get('kernel_slug')})",
         request.remote_addr)
    return jsonify({"message": f"Training started for {media} on Kaggle's GPU cloud.",
                    "job": job}), 202


@model_bp.route("/train/<media>", methods=["GET"])
@admin_required()
def train_status(media):
    if media not in cloud_trainer.TRAINERS:
        return jsonify({"message": f"Media must be one of: {sorted(cloud_trainer.TRAINERS)}"}), 400
    return jsonify({"media": media, "job": cloud_trainer.job_status(media)})


@model_bp.route("/train/<media>/download", methods=["POST"])
@admin_required()
def pull_weights(media):
    if media not in cloud_trainer.TRAINERS:
        return jsonify({"message": f"Media must be one of: {sorted(cloud_trainer.TRAINERS)}"}), 400
    try:
        path = cloud_trainer.download_weights(media)
    except RuntimeError as exc:
        return jsonify({"message": str(exc)}), 400
    user_id = int(get_jwt_identity())
    _log(user_id, "download_model_weights", f"Trained weights pulled for {media}", request.remote_addr)
    return jsonify({"message": f"Trained weights for {media} are ready.", "path": path})


@model_bp.route("/weights", methods=["GET"])
@admin_required()
def weights_list():
    return jsonify({"weights": cloud_trainer.local_weights()})


@model_bp.route("/health", methods=["GET"])
@admin_required()
def health():
    try:
        from ml.kaggle_pipeline import resolve_credentials
        username, _ = resolve_credentials()
        creds_ok = True
    except Exception:  # noqa: BLE001
        username, creds_ok = None, False
    return jsonify({
        "kaggle_client": cloud_trainer.kernel_available(),
        "kaggle_username": username or "",
        "credentials_ok": creds_ok,
        "model_folder": cloud_trainer.MODEL_FOLDER,
        "trainers": list(cloud_trainer.TRAINERS),
        "models": cloud_trainer.local_weights(),
    })
