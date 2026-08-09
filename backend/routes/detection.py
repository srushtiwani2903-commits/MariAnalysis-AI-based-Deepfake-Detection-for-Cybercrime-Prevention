"""Detection endpoints: upload image/video/audio, submit text, run the AI pipeline.

Each request:
  1. Validates auth token + rate limit.
  2. Validates file extension + size (+ magic bytes where feasible).
  3. Saves the file to /uploads with a random name (no path traversal).
  4. Runs the AI pipeline (heuristic or real model).
  5. Persists ScanHistory + AIPrediction.
  6. Returns the full result payload.
"""
import os

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from config import Config
from extensions import db
from models import AIPrediction, Log, ScanHistory
from services.ai_service import service
from utils.helpers import save_upload
from utils.idps import audit
from utils.security import (limiter, sanitize_filename, sanitize_text, validate_upload)

detect_bp = Blueprint("detect", __name__)


def _rate_limit():
    key = f"user:{get_jwt_identity()}"
    if Config.RATE_LIMIT_ENABLED and not limiter.allow(key)[0]:
        return True
    return False


def _store_scan(user_id, scan_type, filename, original_filename, file_path, file_size, result, text_content=None):
    metadata = dict(result.get("metadata", {}))
    metadata["reference_dataset"] = result.get("reference_dataset", "")
    metadata["reference_source"] = result.get("reference_source", "")
    if result.get("heatmap_file"):
        metadata["heatmap_file"] = result.get("heatmap_file")
    scan = ScanHistory(
        user_id=user_id,
        scan_type=scan_type,
        filename=filename,
        original_filename=original_filename,
        file_path=file_path,
        file_size=file_size,
        result=result["result"],
        confidence=result.get("confidence", 0),
        fake_probability=result.get("fake_probability", 0),
        risk_level=result.get("risk_level", "low"),
        explanation=result.get("explanation", ""),
        recommendations=result.get("recommendations", ""),
        suspicious_sections=result.get("suspicious_sections", []),
        trust_score=result.get("trust_score", 0),
        file_hash=result.get("file_hash", ""),
        models=result.get("models", []),
        reasons=result.get("reasons", []),
        processing_time_ms=result.get("processing_time_ms", 0),
        scan_metadata=metadata,
    )
    db.session.add(scan)
    db.session.flush()
    pred = AIPrediction(
        scan_id=scan.id,
        model_name=result.get("model", "heuristic-ensemble-v1"),
        model_version=result.get("model_version", "1.0.0"),
        prediction=result["result"],
        confidence=result.get("confidence", 0),
        features=result.get("features", {}),
    )
    db.session.add(pred)
    db.session.add(Log(user_id=user_id, action=f"scan_{scan_type}",
                       details=f"{filename} -> {result['result']}",
                       ip_address=request.remote_addr))
    db.session.commit()
    audit("create", user_id, "ScanHistory", scan.id, request.remote_addr,
          f"{scan_type} scan -> {result['result']}")
    return scan.id


def _analyze_and_store(scan_type, filename, original_filename, file_path, file_size, text=None):
    user_id = int(get_jwt_identity())
    result = service.analyze(scan_type, file_path, filename, file_size, text=text)
    if "error" in result:
        return None, result
    scan_id = _store_scan(user_id, scan_type, filename, original_filename, file_path, file_size, result, text)
    result["scan_id"] = scan_id
    result["can_download_pdf"] = True
    return scan_id, result


@detect_bp.route("/image", methods=["POST"])
@jwt_required()
def detect_image():
    if _rate_limit():
        return jsonify({"message": "Too many requests. Try again later."}), 429
    file = request.files.get("file")
    ok, msg, size = validate_upload(file, Config.ALLOWED_IMAGE, Config.MAX_CONTENT_LENGTH)
    if not ok:
        return jsonify({"message": msg}), 400
    path, stored_name, size = save_upload(file, Config.UPLOAD_FOLDER, file.filename)
    scan_id, result = _analyze_and_store("image", stored_name, sanitize_filename(file.filename), path, size)
    if result is None:
        return jsonify({"message": result["error"]}), 500
    return jsonify({"result": result}), 200


@detect_bp.route("/video", methods=["POST"])
@jwt_required()
def detect_video():
    if _rate_limit():
        return jsonify({"message": "Too many requests. Try again later."}), 429
    file = request.files.get("file")
    ok, msg, size = validate_upload(file, Config.ALLOWED_VIDEO, Config.MAX_CONTENT_LENGTH)
    if not ok:
        return jsonify({"message": msg}), 400
    path, stored_name, size = save_upload(file, Config.UPLOAD_FOLDER, file.filename)
    scan_id, result = _analyze_and_store("video", stored_name, sanitize_filename(file.filename), path, size)
    if result is None:
        return jsonify({"message": result["error"]}), 500
    return jsonify({"result": result}), 200


@detect_bp.route("/audio", methods=["POST"])
@jwt_required()
def detect_audio():
    if _rate_limit():
        return jsonify({"message": "Too many requests. Try again later."}), 429
    file = request.files.get("file")
    ok, msg, size = validate_upload(file, Config.ALLOWED_AUDIO, Config.MAX_CONTENT_LENGTH)
    if not ok:
        return jsonify({"message": msg}), 400
    path, stored_name, size = save_upload(file, Config.UPLOAD_FOLDER, file.filename)
    scan_id, result = _analyze_and_store("audio", stored_name, sanitize_filename(file.filename), path, size)
    if result is None:
        return jsonify({"message": result["error"]}), 500
    return jsonify({"result": result}), 200


@detect_bp.route("/text", methods=["POST"])
@jwt_required()
def detect_text():
    if _rate_limit():
        return jsonify({"message": "Too many requests. Try again later."}), 429
    data = request.get_json(silent=True) or {}
    text = sanitize_text(data.get("text", ""))
    if len(text.strip()) < 30:
        return jsonify({"message": "Please provide at least 30 characters of text."}), 400
    filename = sanitize_text(data.get("filename", ""), 120) or "text-input.txt"
    scan_id, result = _analyze_and_store("text", filename, filename, None, len(text.encode("utf-8")), text=text)
    if result is None:
        return jsonify({"message": result["error"]}), 500
    return jsonify({"result": result}), 200


@detect_bp.route("/email", methods=["POST"])
@jwt_required()
def detect_email():
    """Detect phishing / scam emails from pasted content (no file needed)."""
    if _rate_limit():
        return jsonify({"message": "Too many requests. Try again later."}), 429
    data = request.get_json(silent=True) or {}
    text = sanitize_text(data.get("text", ""), 60_000)
    if len(text.strip()) < 30:
        return jsonify({"message": "Please provide the full email content (min 30 chars)."}), 400
    subject = sanitize_text(data.get("subject", ""), 300)
    body = f"Subject: {subject}\n\n{text}" if subject else text
    filename = sanitize_text(data.get("filename", ""), 120) or "email-input.txt"
    scan_id, result = _analyze_and_store("email", filename, filename, None,
                                         len(body.encode("utf-8")), text=body)
    if result is None:
        return jsonify({"message": result["error"]}), 500
    return jsonify({"result": result}), 200


@detect_bp.route("/post", methods=["POST"])
@jwt_required()
def detect_post():
    """Fake-news + deepfake combined: image + optional caption."""
    if _rate_limit():
        return jsonify({"message": "Too many requests. Try again later."}), 429
    file = request.files.get("file")
    ok, msg, size = validate_upload(file, Config.ALLOWED_IMAGE, Config.MAX_CONTENT_LENGTH)
    if not ok:
        return jsonify({"message": msg}), 400
    caption = sanitize_text(request.form.get("caption", ""), 5_000)
    path, stored_name, size = save_upload(file, Config.UPLOAD_FOLDER, file.filename)
    user_id = int(get_jwt_identity())
    result = service.analyze("post", path, stored_name, size, caption=caption)
    if "error" in result:
        return jsonify({"message": result["error"]}), 500
    scan_id = _store_scan(user_id, "post", stored_name, sanitize_filename(file.filename),
                          path, size, result, caption)
    result["scan_id"] = scan_id
    result["can_download_pdf"] = True
    return jsonify({"result": result}), 200


@detect_bp.route("/realtime", methods=["POST"])
@jwt_required()
def detect_realtime():
    """Analyse a single webcam frame for live deepfake detection. Never stored."""
    if _rate_limit():
        return jsonify({"message": "Too many requests. Try again later."}), 429
    file = request.files.get("file")
    ok, msg, size = validate_upload(file, Config.ALLOWED_IMAGE, min(Config.MAX_CONTENT_LENGTH, 5 * 1024 * 1024))
    if not ok:
        return jsonify({"message": msg}), 400
    path, stored_name, _ = save_upload(file, Config.UPLOAD_FOLDER, file.filename)
    try:
        result = service.analyze("image", path, stored_name, size)
        if "error" in result:
            return jsonify({"message": result["error"]}), 500
        result.pop("scan_id", None)
        result["persisted"] = False
        result["live"] = True
        return jsonify({"result": result}), 200
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


@detect_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model_enabled": Config.MODEL_ENABLED,
                    "engine": "heuristic-v1" if not Config.MODEL_ENABLED else "trained-models"})


@detect_bp.route("/url", methods=["POST"])
@jwt_required()
def detect_url():
    """Fetch a media file from a URL and analyze it (same pipeline as upload)."""
    if _rate_limit():
        return jsonify({"message": "Too many requests. Try again later."}), 429
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    media_type = (data.get("media_type") or "").strip().lower()
    if not url:
        return jsonify({"message": "A 'url' is required."}), 400
    if media_type not in Config.ALLOWED_IMAGE | Config.ALLOWED_VIDEO | Config.ALLOWED_AUDIO:
        # Map common terms to extensions, else default to image.
        media_type = {"image": "image", "video": "video", "audio": "audio"}.get(
            media_type, "image")

    from utils.helpers import fetch_from_url
    try:
        stream, size, content_type = fetch_from_url(url, Config.MAX_CONTENT_LENGTH)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except Exception:  # noqa: BLE001
        return jsonify({"message": "Could not fetch the URL."}), 400

    # Pick an extension from content-type or the URL path.
    ext = _ext_for_content_type(content_type) or "jpg"
    allowed = {
        "image": Config.ALLOWED_IMAGE,
        "video": Config.ALLOWED_VIDEO,
        "audio": Config.ALLOWED_AUDIO,
    }
    if media_type != "image" and ext in allowed[media_type]:
        pass
    elif ext in allowed["image"]:
        media_type = "image"
    elif ext in allowed["video"]:
        media_type = "video"
    elif ext in allowed["audio"]:
        media_type = "audio"
    else:
        return jsonify({"message": "Unsupported media type from URL."}), 400

    if not allowed[media_type].__contains__(ext):
        return jsonify({"message": f"File type not allowed for {media_type} detection."}), 400

    from werkzeug.datastructures import FileStorage
    file = FileStorage(stream=stream, filename=f"remote.{ext}")
    path, stored_name, size = save_upload(file, Config.UPLOAD_FOLDER, file.filename)
    scan_id, result = _analyze_and_store(media_type, stored_name, sanitize_filename(url.split("/")[-1] or "remote"), path, size)
    if result is None:
        return jsonify({"message": result["error"]}), 500
    result["source_url"] = url
    return jsonify({"result": result}), 200


def _ext_for_content_type(content_type: str):
    mapping = {
        "jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp",
        "bmp": "bmp", "tiff": "tiff", "mp4": "mp4", "quicktime": "mov",
        "x-msvideo": "avi", "ogg": "ogg", "wav": "wav", "mpeg": "mp3",
        "mpeg3": "mp3", "m4a": "m4a", "flac": "flac", "matroska": "mkv",
    }
    for key, ext in mapping.items():
        if key in content_type.lower():
            return ext
    return None
