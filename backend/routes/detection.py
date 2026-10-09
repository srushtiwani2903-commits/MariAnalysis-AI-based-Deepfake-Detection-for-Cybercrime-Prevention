"""Detection endpoints: upload media, submit text, run the AI pipeline.

Every request validates auth + rate limit, checks the file (extension, size,
magic bytes where feasible), saves it under a random name, runs the pipeline,
persists ScanHistory/AIPrediction and returns the full result.
"""
import html
import os
import threading
import time as _time
from collections import deque
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


# --------------------------------------------------------------------------- #
# Replay guard: per-user rolling frame history for the live webcam loop.     #
# A real person behind the camera keeps moving (natural motion), while a     #
# screen replaying content is typically still (low inter-frame movement).    #
# --------------------------------------------------------------------------- #
_LIVE_MEM = {}
_LIVE_MEM_LOCK = threading.Lock()
_LIVE_MEM_MAX = 6
_MOTION_STILL = 0.045   # mean abs pixel diff below this = "still"
_BANDING_HIGH = 0.05    # column-intensity variation above this = screen bands


def _liveness_probe(user_id, path, faces_detected):
    """Track recent frames and return replay-guard metrics for this frame."""
    try:
        import numpy as np
        from PIL import Image
        thumb = np.asarray(
            Image.open(path).convert("L").resize((64, 48)), dtype=np.float32) / 255.0
    except Exception:  # noqa: BLE001
        return None

    now = _time.time()
    prev = None
    with _LIVE_MEM_LOCK:
        history = _LIVE_MEM.get(user_id) or deque(maxlen=_LIVE_MEM_MAX)
        history = deque([(t, th) for t, th in history if now - t <= 3.0], maxlen=_LIVE_MEM_MAX)
        if history:
            prev = history[-1][1]
        history.append((now, thumb))
        _LIVE_MEM[user_id] = history

    if prev is None:
        return {"sample_frames": 1, "motion": 0.0, "motion_avg": 0.0,
                "banding": 0.0, "replay_suspected": False}

    diff = float(np.mean(np.abs(thumb - prev)))

    items = list(history)
    motion_list = []
    for i in range(1, len(items)):
        motion_list.append(float(np.mean(np.abs(items[i][1] - items[i - 1][1]))))
    motion_avg = float(np.mean(motion_list)) if motion_list else 0.0
    row_var = float(np.std(np.mean(thumb, axis=1)))
    col_var = float(np.std(np.mean(thumb, axis=0)))
    banding = max(row_var, col_var)

    still = motion_avg < _MOTION_STILL and len(motion_list) >= 2
    replay = bool(still and (faces_detected > 0 or banding > _BANDING_HIGH))
    return {
        "sample_frames": len(items),
        "motion": diff,
        "motion_avg": round(motion_avg, 4),
        "banding": round(banding, 4),
        "replay_suspected": replay,
    }


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
    # Social-post link preview (thumbnail / caption / platform) so the source
    # of a pasted post URL stays visible on the results page and in History.
    for key in ("source_url", "platform", "post_thumbnail", "post_caption"):
        if result.get(key):
            metadata[key] = result[key]
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
    image_url = sanitize_text(request.form.get("image_url", ""), 2_000).strip()
    user_id = int(get_jwt_identity())

    path = stored_name = original_filename = None
    size = 0
    platform = platform_slug = ""
    post_thumbnail = post_caption = ""

    has_file = bool(file and file.filename and file.filename.lower() not in ("null", "undefined"))
    if has_file:
        ok, msg, size = validate_upload(file, Config.ALLOWED_IMAGE, Config.MAX_IMAGE_BYTES)
        if not ok:
            return jsonify({"message": msg}), 400
        path, stored_name, size = save_upload(file, Config.UPLOAD_FOLDER, file.filename)
        original_filename = sanitize_filename(file.filename)
    elif source_url:
        from werkzeug.datastructures import FileStorage
        from utils.helpers import fetch_from_url
        platform, platform_slug = _detect_platform(source_url)

        # Try to open the link. Many social sites block server requests (403 /
        # 429 / connection reset), so a failure here is expected often — fall
        # back to whatever caption we already have instead of hard-failing.
        page_ok = False
        stream = None
        content_type = ""
        try:
            stream, size, content_type = fetch_from_url(
                source_url, Config.MAX_IMAGE_BYTES, user_agent=_BROWSER_UA)
            page_ok = True
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception:  # noqa: BLE001
            page_ok = False

        direct_ext = _ext_for_content_type(content_type) if page_ok else None
        if page_ok and direct_ext in Config.ALLOWED_IMAGE and _is_decodable_image(stream):
            # The link itself points straight at an image / video.
            fname = f"remote.{direct_ext}"
            fpath, stored_name, size = save_upload(
                FileStorage(stream=stream, filename=fname), Config.UPLOAD_FOLDER, fname)
            path = fpath
            original_filename = source_url.split("/")[-1][:120] or "remote-image"
            post_thumbnail = source_url
        else:
            # Parse the page for its Open Graph image + description.
            og_img = ""
            if page_ok:
                html = stream.read().decode("utf-8", "ignore")
                og_img = _usable_img_url(
                    _og_tag(html, "og:image") or _og_tag(html, "og:image:secure_url")
                    or _og_tag(html, "twitter:image") or _og_tag(html, "twitter:image:src"),
                    source_url)
                if not og_img:
                    og_img = _usable_img_url(_first_img_src(html), source_url)
                og_text = (_og_tag(html, "og:description") or _og_tag(html, "og:title")
                           or _og_tag(html, "twitter:description") or "").strip()
                site = _og_tag(html, "og:site_name")
                if site:
                    platform = site
                # Last resort: fall back to the page's visible text so a bare
                # link (news article, blog, etc.) can still be analysed.
                if not og_text:
                    og_text = _extract_visible_text(html)
                post_caption = og_text
                caption = caption or og_text

            # The frontend already resolved the post image during its link
            # preview — trust that if the page itself exposed nothing usable.
            if not og_img and image_url:
                og_img = _usable_img_url(image_url, source_url)

            # Prefer the post's own image; otherwise analyze the caption text.
            img_stream = img_name = None
            if og_img:
                try:
                    img_stream, _isize, ict = fetch_from_url(
                        og_img, Config.MAX_IMAGE_BYTES, user_agent=_BROWSER_UA)
                    if not _is_decodable_image(img_stream):
                        img_stream = None
                    else:
                        iext = _ext_for_content_type(ict) or "jpg"
                        if iext not in Config.ALLOWED_IMAGE:
                            iext = "jpg"
                        img_name = f"remote.{iext}"
                except Exception:  # noqa: BLE001
                    img_stream = None
            if img_stream is not None:
                fpath, stored_name, size = save_upload(
                    FileStorage(stream=img_stream, filename=img_name),
                    Config.UPLOAD_FOLDER, img_name)
                path = fpath
                original_filename = og_img.split("/")[-1][:120] or "remote-image"
                post_thumbnail = og_img
            elif len(caption.strip()) >= 20:
                stored_name = "url-caption.txt"
                original_filename = "url-caption.txt"
                size = len(caption.encode("utf-8"))
            else:
                # Nothing analysable was exposed. Still complete the scan (as
                # UNCERTAIN) so the user always gets a result page instead of a
                # dead-end error, with a note on how to get a definite verdict.
                reason = ("The site blocked automated access, so this post's content could "
                          if not page_ok else
                          "This post didn't expose a usable image or caption, so its content could ")
                _unreadable = {
                    "scan_type": "post",
                    "filename": "post-url.txt",
                    "result": "inconclusive",
                    "confidence": 50,
                    "fake_probability": 50.0,
                    "misinformation_probability": 50.0,
                    "trust_score": 50,
                    "risk_level": "medium",
                    "explanation": reason + "not be read automatically. Paste the caption text "
                                            "or upload a screenshot of the post for a Real/Fake verdict.",
                    "recommendations": "Open the original post, verify the account and the source "
                                       "before trusting or sharing it.",
                    "suspicious_sections": [],
                    "models": [],
                    "reasons": [],
                    "features": {},
                    "metadata": {},
                    "processing_time_ms": 0,
                    "source_url": source_url,
                    "platform": platform,
                    "platform_slug": platform_slug,
                    "post_thumbnail": post_thumbnail,
                    "post_caption": post_caption or caption,
                }
                scan_id = _store_scan(user_id, "post", "post-url.txt", "post-url.txt",
                                      None, 0, _unreadable, caption)
                _unreadable["scan_id"] = scan_id
                _unreadable["can_download_pdf"] = True
                return jsonify({"result": _unreadable}), 200
    elif len(caption.strip()) >= 20:
        stored_name = "caption.txt"
        original_filename = "caption.txt"
        size = len(caption.encode("utf-8"))
    else:
        return jsonify({"message": "Upload an image, paste a caption (min 20 chars), or provide a post URL."}), 400

    try:
        result = service.analyze("post", path, stored_name, size,
                                 caption=caption, source_url=source_url)
    except Exception:  # noqa: BLE001
        return jsonify({"message": "Could not analyse that post. Try a different "
                                   "image or paste the caption text instead."}), 500
    if "error" in result:
        return jsonify({"message": result["error"]}), 500
    if source_url:
        result["source_url"] = source_url
        result["platform"] = platform
        result["platform_slug"] = platform_slug
        result["post_thumbnail"] = post_thumbnail
        result["post_caption"] = post_caption or caption
    scan_id = _store_scan(user_id, "post", stored_name, original_filename,
                          path, size, result, caption)
    result["scan_id"] = scan_id
    result["can_download_pdf"] = True
    return jsonify({"result": result}), 200


@detect_bp.route("/post/preview", methods=["POST"])
@jwt_required()
def preview_post():
    """Return the thumbnail, caption and platform name for a pasted post URL.

    Used by the Social Post page to show a link preview before analysis.
    """
    if _rate_limit():
        return jsonify({"message": "Too many requests. Try again later."}), 429
    data = request.get_json(silent=True) or {}
    url = sanitize_text(data.get("url", ""), 2_000).strip()
    if not url:
        return jsonify({"message": "Paste a post URL first."}), 400
    if not url.lower().startswith(("http://", "https://")):
        return jsonify({"message": "Enter a full http(s) URL."}), 400
    preview = _extract_post_meta(url)
    return jsonify({"preview": preview}), 200


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
    source = str(request.form.get("source") or "webcam")[:16].strip().lower()
    if source not in ("webcam", "call"):
        source = "webcam"
    path, stored_name, _ = save_upload(file, Config.UPLOAD_FOLDER, file.filename)
    try:
        result = service.analyze("image", path, stored_name, size)
        if "error" in result:
            return jsonify({"message": result["error"]}), 500
        result.pop("scan_id", None)
        result["persisted"] = False
        result["live"] = True
        result["source"] = source
        faces = result.get("features", {}).get("faces_detected", 0)
        liveness = _liveness_probe(str(get_jwt_identity()), path, faces)
        if liveness is not None:
            if liveness["replay_suspected"]:
                if source == "call":
                    # Call feeds freeze on network lag too, so report the still
                    # feed as an advisory instead of boosting the fake score.
                    result["reasons"].append({
                        "check": "Replay guard: feed looks frozen",
                        "passed": False,
                        "detail": "The remote feed showed no motion (network freeze or still image). Verify the person through a second channel.",
                    })
                else:
                    boost = min(100.0, result.get("fake_probability", 0.0) + 20.0)
                    result["fake_probability"] = round(boost, 1)
                    result["reasons"].append({
                        "check": "Replay guard: feed is still (no liveness)",
                        "passed": False,
                        "detail": "Webcam feed showed a still/static source; treat it as replayed content.",
                    })
            result["liveness"] = liveness
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
    ct = (content_type or "").lower()
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


def _usable_img_url(raw, base_url):
    """Resolve a scraped image reference to an absolute http(s) URL.

    Returns "" for blank values and inline ``data:`` placeholders (several
    sites, e.g. Instagram, embed base64 placeholders as ``og:image``).
    """
    from urllib.parse import urljoin, urlparse
    if not raw:
        return ""
    raw = raw.strip()
    if raw.lower().startswith("data:"):
        return ""
    abs_url = urljoin(base_url, raw)
    return abs_url if urlparse(abs_url).scheme in ("http", "https") else ""


def _extract_visible_text(html_text, limit=2000):
    """Strip scripts/styles/tags and return readable page text (best effort).

    Used as a last-resort caption source when a page has no Open Graph
    description, so a bare URL can still produce a verdict.
    """
    import re
    text = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", html_text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _is_decodable_image(stream):
    """True if the buffered bytes open as an image the pipeline can read.

    Guards against SVG / icon / corrupt payloads that some sites expose as
    ``og:image`` but Pillow can't decode (which would otherwise crash the run).
    """
    from PIL import Image
    try:
        stream.seek(0)
        with Image.open(stream) as im:
            im.verify()
        stream.seek(0)
        return True
    except Exception:  # noqa: BLE001
        try:
            stream.seek(0)
        except Exception:  # noqa: BLE001
            pass
        return False


# Browser-like UA so social platforms return their Open Graph tags.
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

# (domains, display name, slug) - order matters (most specific first).
_PLATFORM_MAP = (
    (("youtube.com", "youtu.be", "youtube-nocookie.com"), "YouTube", "youtube"),
    (("instagram.com", "instagr.am"), "Instagram", "instagram"),
    (("twitter.com", "x.com", "t.co"), "X (Twitter)", "x"),
    (("facebook.com", "fb.com", "fb.watch", "fb.me"), "Facebook", "facebook"),
    (("tiktok.com",), "TikTok", "tiktok"),
    (("linkedin.com", "lnkd.in"), "LinkedIn", "linkedin"),
    (("reddit.com", "redd.it"), "Reddit", "reddit"),
    (("pinterest.com", "pinterest.co.uk", "pin.it"), "Pinterest", "pinterest"),
    (("threads.net", "threads.com"), "Threads", "threads"),
    (("snapchat.com",), "Snapchat", "snapchat"),
    (("telegram.org", "t.me", "telegram.me"), "Telegram", "telegram"),
    (("whatsapp.com", "wa.me"), "WhatsApp", "whatsapp"),
    (("tumblr.com",), "Tumblr", "tumblr"),
    (("vimeo.com",), "Vimeo", "vimeo"),
    (("medium.com",), "Medium", "medium"),
    (("weibo.com",), "Weibo", "weibo"),
    (("vk.com",), "VK", "vk"),
    (("mastodon.social",), "Mastodon", "mastodon"),
)


def _detect_platform(url):
    """Map a URL's host to a social platform (display name, slug)."""
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for domains, name, slug in _PLATFORM_MAP:
        for d in domains:
            if host == d or host.endswith("." + d):
                return name, slug
    return (host or "Website", "web")


def _extract_post_meta(source_url):
    """Best-effort Open Graph scrape of a social post URL for a link preview.

    Returns platform name/slug, thumbnail, caption, title and author. Network
    failures degrade gracefully to just the platform name from the host.
    """
    from urllib.parse import urljoin
    from utils.helpers import fetch_from_url

    platform, platform_slug = _detect_platform(source_url)
    preview = {
        "url": source_url,
        "platform": platform,
        "platform_slug": platform_slug,
        "thumbnail": "",
        "caption": "",
        "title": "",
        "author": "",
    }
    try:
        stream, _size, content_type = fetch_from_url(
            source_url, min(Config.MAX_IMAGE_BYTES, 4 * 1024 * 1024),
            user_agent=_BROWSER_UA)
    except Exception:  # noqa: BLE001
        return preview

    if (content_type or "").lower().startswith("image/"):
        preview["thumbnail"] = source_url
        return preview

    html_text = stream.read().decode("utf-8", "ignore")
    og_img = (_og_tag(html_text, "og:image") or _og_tag(html_text, "og:image:secure_url")
              or _og_tag(html_text, "twitter:image") or _og_tag(html_text, "twitter:image:src"))
    if not og_img:
        og_img = _first_img_src(html_text)
    preview["thumbnail"] = _usable_img_url(og_img, source_url)
    title = (_og_tag(html_text, "og:title") or _og_tag(html_text, "twitter:title")
             or _og_tag(html_text, "title"))
    caption = (_og_tag(html_text, "og:description") or _og_tag(html_text, "twitter:description")
               or _og_tag(html_text, "description") or title)
    preview["title"] = title.strip()
    preview["caption"] = caption.strip()
    preview["author"] = (_og_tag(html_text, "article:author")
                         or _og_tag(html_text, "twitter:creator")
                         or _og_tag(html_text, "author")).strip()
    site = _og_tag(html_text, "og:site_name")
    if site:
        preview["platform"] = site.strip()
    return preview
