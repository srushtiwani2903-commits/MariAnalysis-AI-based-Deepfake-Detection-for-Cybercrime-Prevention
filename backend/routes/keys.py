"""API keys (for the browser extension) + the extension analysis endpoint.

- POST   /api/keys            create a key (plaintext shown once; hash + encrypted blob stored)
- GET    /api/keys            list your keys
- DELETE /api/keys/<id>       revoke a key
- POST   /api/extend/analyze  analyse a media URL with an API key (no JWT needed)
"""
import hashlib
import os
import secrets

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from config import Config
from extensions import db
from models import ApiKey, Log
from services.ai_service import service
from utils.helpers import fetch_from_url, save_upload
from utils.idps import audit
from utils.security import encrypt_api_key, hash_api_key, limiter, sanitize_string

keys_bp = Blueprint("keys", __name__)


def _hash_key(key: str) -> str:
    return hash_api_key(key)


@keys_bp.route("/keys", methods=["GET"])
@jwt_required()
def list_keys():
    user_id = int(get_jwt_identity())
    keys = ApiKey.query.filter_by(user_id=user_id).order_by(ApiKey.created_at.desc()).all()
    return jsonify({"keys": [k.to_dict() for k in keys]})


@keys_bp.route("/keys", methods=["POST"])
@jwt_required()
def create_key():
    if Config.RATE_LIMIT_ENABLED and not limiter.allow(f"user:{get_jwt_identity()}")[0]:
        return jsonify({"message": "Too many requests. Try again later."}), 429
    user_id = int(get_jwt_identity())
    label = sanitize_string((request.get_json(silent=True) or {}).get("label", ""), 120)
    if ApiKey.query.filter_by(user_id=user_id).count() >= 5:
        return jsonify({"message": "Maximum of 5 API keys per account."}), 400
    plaintext = f"ma_{secrets.token_urlsafe(28)}"
    key = ApiKey(user_id=user_id, label=label or "Browser Extension",
                 key_hash=_hash_key(plaintext),
                 key_encrypted=encrypt_api_key(plaintext))
    db.session.add(key)
    db.session.add(Log(user_id=user_id, action="create_api_key",
                       details=f"API key '{key.label}' created", ip_address=request.remote_addr))
    db.session.commit()
    audit("create", user_id, "ApiKey", key.id, request.remote_addr, "API key created")
    # Plaintext is returned exactly once; at rest only its SHA-256 hash and a
    # Fernet-encrypted blob exist (recoverable only via the server master secret).
    return jsonify({"message": "API key created. Copy it now - it won't be shown again.",
                    "key": plaintext, "record": key.to_dict()}), 201


@keys_bp.route("/keys/<int:key_id>", methods=["DELETE"])
@jwt_required()
def revoke_key(key_id):
    user_id = int(get_jwt_identity())
    key = ApiKey.query.filter_by(id=key_id, user_id=user_id).first()
    if not key:
        return jsonify({"message": "Key not found."}), 404
    db.session.delete(key)
    db.session.add(Log(user_id=user_id, action="revoke_api_key",
                       details=f"API key '{key.label}' revoked", ip_address=request.remote_addr))
    db.session.commit()
    return jsonify({"message": "API key revoked."})


def _resolve_key(api_key: str):
    if not api_key:
        return None
    key_hash = _hash_key(api_key)
    return ApiKey.query.filter_by(key_hash=key_hash).first()


@keys_bp.route("/extend/analyze", methods=["POST"])
def extend_analyze():
    """Public endpoint used by the browser extension (authenticated via API key)."""
    if Config.RATE_LIMIT_ENABLED and not limiter.allow(f"ip:{request.remote_addr}")[0]:
        return jsonify({"message": "Too many requests. Try again later."}), 429
    data = request.get_json(silent=True) or {}
    api_key = sanitize_string(data.get("api_key", ""), 128)
    url = (data.get("url") or "").strip()
    key = _resolve_key(api_key)
    if not key:
        return jsonify({"message": "Invalid API key."}), 401
    if not url:
        return jsonify({"message": "A 'url' is required."}), 400

    key.last_used = __import__("datetime").datetime.utcnow()
    db.session.commit()

    from werkzeug.datastructures import FileStorage
    from utils.security import validate_upload
    try:
        stream, size, content_type = fetch_from_url(url, Config.MAX_CONTENT_LENGTH)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except Exception:  # noqa: BLE001
        return jsonify({"message": "Could not fetch the URL."}), 400

    ext = _ext_for_content_type(content_type) or "jpg"
    if ext not in Config.ALLOWED_IMAGE:
        return jsonify({"message": "Only image analysis is supported by the extension."}), 400
    file = FileStorage(stream=stream, filename=f"ext.{ext}")
    ok, msg, size = validate_upload(file, Config.ALLOWED_IMAGE, min(Config.MAX_CONTENT_LENGTH, 10 * 1024 * 1024))
    if not ok:
        return jsonify({"message": msg}), 400
    path, stored_name, _ = save_upload(file, Config.UPLOAD_FOLDER, file.filename)
    try:
        result = service.analyze("image", path, stored_name, size)
        if "error" in result:
            return jsonify({"message": result["error"]}), 500
        # Compact payload for the lightweight extension UI.
        return jsonify({"result": {
            "result": result["result"],
            "fake_probability": result["fake_probability"],
            "confidence": result["confidence"],
            "trust_score": result["trust_score"],
            "risk_level": result["risk_level"],
            "explanation": result["explanation"],
            "processing_time_ms": result["processing_time_ms"],
        }}), 200
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _ext_for_content_type(content_type: str):
    mapping = {
        "jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp",
        "bmp": "bmp", "tiff": "tiff", "gif": "gif",
    }
    for key, ext in mapping.items():
        if key in (content_type or "").lower():
            return ext
    return None
