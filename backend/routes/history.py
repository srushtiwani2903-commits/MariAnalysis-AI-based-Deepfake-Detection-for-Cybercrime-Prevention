"""Scan history endpoints: list, search, filter, detail, delete and stats."""
import io
import os

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from config import Config
from extensions import db
from models import Log, ScanHistory, User, _iso
from utils.idps import audit

history_bp = Blueprint("history", __name__)


def _is_admin(user_id):
    """True when the current user has the admin flag (global history view)."""
    user = db.session.get(User, user_id)
    return bool(user and user.is_admin)


def _global_scope(user_id):
    """Admins may pass ?scope=all to see every user's scans (team view)."""
    wants_all = (request.args.get("scope") or "").strip().lower() == "all"
    return wants_all and _is_admin(user_id)


@history_bp.route("", methods=["GET"])
@jwt_required()
def list_history():
    """List scans with pagination, search + type/result filters.

    Admins can opt into the combined team view with ?scope=all."""
    user_id = int(get_jwt_identity())
    q = (request.args.get("q") or "").strip().lower()
    scan_type = (request.args.get("type") or "").strip().lower()
    result = (request.args.get("result") or "").strip().lower()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, max(1, request.args.get("limit", 10, type=int)))

    query = ScanHistory.query
    if not _global_scope(user_id):
        query = query.filter_by(user_id=user_id)
    if q:
        query = query.filter(db.or_(
            ScanHistory.filename.ilike(f"%{q}%"),
            ScanHistory.original_filename.ilike(f"%{q}%"),
        ))
    if scan_type:
        query = query.filter(ScanHistory.scan_type == scan_type)
    if result:
        query = query.filter(ScanHistory.result == result)
    pagination = query.order_by(ScanHistory.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "items": [s.to_dict() for s in pagination.items],
        "page": page,
        "pages": pagination.pages,
        "total": pagination.total,
        "has_next": pagination.has_next,
        "scope": "all" if _global_scope(user_id) else "self",
    })


@history_bp.route("/stats", methods=["GET"])
@jwt_required()
def stats():
    """Dashboard summary counts (current user, or all users for admins)."""
    user_id = int(get_jwt_identity())
    query = ScanHistory.query
    if not _global_scope(user_id):
        query = query.filter_by(user_id=user_id)
    total = query.count()
    fake = query.filter_by(result="fake").count()
    real = query.filter_by(result="authentic").count()
    inconclusive = total - fake - real
    accuracy = round((fake + real) / total * 100, 1) if total else 0.0
    last = query.order_by(ScanHistory.created_at.desc()).first()
    return jsonify({
        "total_scans": total,
        "fake_detected": fake,
        "real_detected": real,
        "inconclusive": inconclusive,
        "accuracy": accuracy,
        "last_scan_at": _iso(last.created_at) if last else None,
        "last_result": last.to_dict() if last else None,
    })


@history_bp.route("/<int:scan_id>", methods=["GET"])
@jwt_required()
def detail(scan_id):
    user_id = int(get_jwt_identity())
    scan = db.session.get(ScanHistory, scan_id)
    if not scan or (scan.user_id != user_id and not _is_admin(user_id)):
        return jsonify({"message": "Scan not found."}), 404
    return jsonify({"scan": scan.to_dict(include_full=True)})


@history_bp.route("/<int:scan_id>/media", methods=["GET"])
@jwt_required()
def media(scan_id):
    """Serve the stored original media for a scan (history thumbnails).

    Add ``?thumb=1`` to get a small downscaled JPEG instead of the full file.
    """
    user_id = int(get_jwt_identity())
    scan = db.session.get(ScanHistory, scan_id)
    if not scan or scan.user_id != user_id:
        return jsonify({"message": "Scan not found."}), 404

    path = scan.file_path or ""
    if not path or not os.path.isfile(path):
        return jsonify({"message": "Original media is not available."}), 404

    # Never serve anything outside the uploads directory (path-traversal guard).
    upload_root = os.path.realpath(Config.UPLOAD_FOLDER)
    real = os.path.realpath(path)
    if not os.path.normcase(real).startswith(os.path.normcase(upload_root + os.sep)):
        return jsonify({"message": "Invalid media path."}), 403

    if request.args.get("thumb") and scan.scan_type in ("image", "post"):
        try:
            from PIL import Image as _Image
            with _Image.open(real) as im:
                im = im.convert("RGB")
                im.thumbnail((160, 160))
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=82)
            buf.seek(0)
            return send_file(buf, mimetype="image/jpeg")
        except Exception:  # noqa: BLE001 - fall back to the original file
            pass

    return send_file(real, as_attachment=False, conditional=True)


@history_bp.route("/<int:scan_id>", methods=["DELETE"])
@jwt_required()
def delete_scan(scan_id):
    user_id = int(get_jwt_identity())
    scan = db.session.get(ScanHistory, scan_id)
    if not scan or (scan.user_id != user_id and not _is_admin(user_id)):
        return jsonify({"message": "Scan not found."}), 404
    db.session.add(Log(user_id=user_id, action="delete_scan",
                       details=f"Deleted scan #{scan.id}", ip_address=request.remote_addr))
    db.session.delete(scan)
    db.session.commit()
    audit("delete", user_id, "ScanHistory", scan_id, request.remote_addr, "Deleted scan")
    return jsonify({"message": "Scan deleted."})
