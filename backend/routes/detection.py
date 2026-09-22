"""Detection endpoints: upload media, submit text, run the AI pipeline.

Every request validates auth + rate limit, checks the file (extension, size,
magic bytes where feasible), saves it under a random name, runs the pipeline,
persists ScanHistory/AIPrediction and returns the full result.
"""
import html
import os
from datetime import datetime

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
    metadata["ai_origin"] = result.get("ai_origin", "")
    metadata["suspicious_scale"] = result.get("suspicious_scale", 0)
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
    ok, msg, size = validate_upload(file, Config.ALLOWED_IMAGE, Config.MAX_IMAGE_BYTES)
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
    ok, msg, size = validate_upload(file, Config.ALLOWED_VIDEO, Config.MAX_VIDEO_BYTES)
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
    ok, msg, size = validate_upload(file, Config.ALLOWED_AUDIO, Config.MAX_AUDIO_BYTES)
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
    text = data.get("text", "")
    if len(text.encode("utf-8")) > Config.MAX_TEXT_BYTES:
        return jsonify({"message": "Text exceeds the 20 GB limit. Not more than 20 GB will accept."}), 400
    text = sanitize_text(text)
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
    """Fake-news + deepfake combined: image + caption, caption-only, or a post URL."""
    if _rate_limit():
        return jsonify({"message": "Too many requests. Try again later."}), 429
    file = request.files.get("file")
    caption = sanitize_text(request.form.get("caption", ""), 5_000)
    source_url = sanitize_text(request.form.get("source_url", ""), 2_000).strip()
    user_id = int(get_jwt_identity())

    path = stored_name = original_filename = None
    size = 0

    has_file = bool(file and file.filename and file.filename.lower() not in ("null", "undefined"))
    if has_file:
        ok, msg, size = validate_upload(file, Config.ALLOWED_IMAGE, Config.MAX_IMAGE_BYTES)
        if not ok:
            return jsonify({"message": msg}), 400
        path, stored_name, size = save_upload(file, Config.UPLOAD_FOLDER, file.filename)
        original_filename = sanitize_filename(file.filename)
    elif source_url:
        from urllib.parse import urljoin
        from werkzeug.datastructures import FileStorage
        from utils.helpers import fetch_from_url
        try:
            stream, size, content_type = fetch_from_url(source_url, Config.MAX_IMAGE_BYTES)
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception:  # noqa: BLE001
            return jsonify({"message": "Could not fetch the post URL."}), 400

        ext = _ext_for_content_type(content_type)
        if ext in Config.ALLOWED_IMAGE:
            fname = f"remote.{ext}"
            fpath, stored_name, size = save_upload(
                FileStorage(stream=stream, filename=fname), Config.UPLOAD_FOLDER, fname)
            path = fpath
            original_filename = source_url.split("/")[-1][:120] or "remote-image"
        else:
            html = stream.read().decode("utf-8", "ignore")
            og_img = _og_tag(html, "og:image")
            if not og_img:
                og_img = _first_img_src(html)
            og_text = (_og_tag(html, "og:description") or _og_tag(html, "og:title")
                       or _og_tag(html, "twitter:description") or "").strip()
            caption = caption or og_text
            if og_img:
                abs_url = urljoin(source_url, og_img)
                try:
                    istream, isize, ict = fetch_from_url(abs_url, Config.MAX_IMAGE_BYTES)
                except Exception:  # noqa: BLE001
                    return jsonify({"message": "Could not fetch the image inside the post URL."}), 400
                iext = _ext_for_content_type(ict) or "jpg"
                if iext not in Config.ALLOWED_IMAGE:
                    iext = "jpg"
                fname = f"remote.{iext}"
                fpath, stored_name, size = save_upload(
                    FileStorage(stream=istream, filename=fname), Config.UPLOAD_FOLDER, fname)
                path = fpath
                original_filename = og_img.split("/")[-1][:120] or "remote-image"
            elif len(caption.strip()) >= 30:
                stored_name = "url-caption.txt"
                original_filename = "url-caption.txt"
                size = len(caption.encode("utf-8"))
            else:
                return jsonify({"message": "No usable image or text found in that post URL."}), 400
    elif len(caption.strip()) >= 30:
        stored_name = "caption.txt"
        original_filename = "caption.txt"
        size = len(caption.encode("utf-8"))
    else:
        return jsonify({"message": "Upload an image, paste a caption (min 30 chars), or provide a post URL."}), 400

    result = service.analyze("post", path, stored_name, size,
                             caption=caption, source_url=source_url)
    if "error" in result:
        return jsonify({"message": result["error"]}), 500
    scan_id = _store_scan(user_id, "post", stored_name, original_filename,
                          path, size, result, caption)
    result["scan_id"] = scan_id
    result["can_download_pdf"] = True
    if source_url:
        result["source_url"] = source_url
    return jsonify({"result": result}), 200


@detect_bp.route("/realtime", methods=["POST"])
@jwt_required()
def detect_realtime():
    """Analyse a single webcam frame for live deepfake detection. Never stored."""
    if _rate_limit():
        return jsonify({"message": "Too many requests. Try again later."}), 429
    file = request.files.get("file") or request.files.get("frame")
    if file is None:
        try:
            first = request.get_data(cache=False)[:200]
            with open(r"C:\Users\Harshal\AppData\Local\Temp\opencode\realtime-diag.log", "a",
                      encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] files={list(request.files.keys())} "
                        f"form={list(request.form.keys())} ct={request.content_type} "
                        f"len={request.content_length} first={first}\n")
        except Exception as e:
            with open(r"C:\Users\Harshal\AppData\Local\Temp\opencode\realtime-diag.log", "a",
                      encoding="utf-8") as f:
                f.write(f"[diag error] {e}\n")
    ok, msg, size = validate_upload(file, Config.ALLOWED_IMAGE, min(Config.MAX_IMAGE_BYTES, 5 * 1024 * 1024))
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

    per_type_max = {
        "image": Config.MAX_IMAGE_BYTES,
        "video": Config.MAX_VIDEO_BYTES,
        "audio": Config.MAX_AUDIO_BYTES,
    }.get(media_type, Config.MAX_CONTENT_LENGTH)
    if size > per_type_max:
        from utils.security import format_limit
        limit = format_limit(per_type_max)
        return jsonify({"message": f"File exceeds the {limit} limit. Not more than {limit} will accept."}), 400

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
        # Images
        "jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp",
        "bmp": "bmp", "tiff": "tiff", "tif": "tiff", "gif": "gif",
        "avif": "avif", "heic": "heic", "heif": "heif", "svg": "svg",
        "ico": "ico", "jfif": "jfif",
        # Videos
        "mp4": "mp4", "quicktime": "mov", "x-msvideo": "avi",
        "x-matroska": "mkv", "x-matroska-video": "mkv",
        "webm": "webm", "3gpp": "3gp", "3gpp2": "3g2",
        "mpeg": "mpg", "mpg": "mpeg", "mp2p": "mpeg",
        "x-ms-wmv": "wmv", "x-flv": "flv", "x-ms-asf": "asf",
        "mp2t": "ts", "vob": "vob",
        # Audio
        "ogg": "ogg", "wav": "wav", "wave": "wav",
        "mpeg": "mp3", "mpeg3": "mp3", "x-mpeg": "mp3",
        "m4a": "m4a", "mp4": "m4a", "x-m4a": "m4a",
        "flac": "flac", "x-flac": "flac",
        "aac": "aac", "x-aac": "aac",
        "opus": "opus", "x-opus": "opus",
        "x-wav": "wav", "x-ms-wma": "wma",
        "aiff": "aiff", "x-aiff": "aiff",
        "amr": "amr", "amr-wb": "amr",
        "x-midi": "mid", "midi": "mid",
        "pcm": "pcm", "l16": "pcm",
    }
    ct = content_type.lower()
    for key, ext in mapping.items():
        if key in ct:
            return ext
    return None


def _og_tag(html_text, prop):
    """Return the content of the first <meta> tag whose property/name matches."""
    import re
    pattern = (
        r'<meta[^>]+(?:property|name)=["\']' + re.escape(prop)
        + r'["\'][^>]+content=["\']([^"\']+)["\']'
    )
    match = re.search(pattern, html_text, re.IGNORECASE)
    if not match:
        pattern = (
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']'
            + re.escape(prop) + r'["\']'
        )
        match = re.search(pattern, html_text, re.IGNORECASE)
    return html.unescape(match.group(1)).strip() if match else ""


def _first_img_src(html_text):
    """Return the first <img src> present in a page, or empty string."""
    import re
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html_text, re.IGNORECASE)
    return match.group(1).strip() if match else ""
