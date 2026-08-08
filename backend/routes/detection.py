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
from utils.security import (limiter, sanitize_filename, sanitize_text, validate_upload)

detect_bp = Blueprint("detect", __name__)


def _rate_limit():
    key = f"user:{get_jwt_identity()}"
    if Config.RATE_LIMIT_ENABLED and not limiter.allow(key)[0]:
        return True
    return False


def _store_scan(user_id, scan_type, filename, original_filename, file_path, file_size, result, text_content=None):
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
        processing_time_ms=result.get("processing_time_ms", 0),
        scan_metadata=result.get("metadata", {}),
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


@detect_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model_enabled": Config.MODEL_ENABLED,
                    "engine": "heuristic-v1" if not Config.MODEL_ENABLED else "trained-models"})
