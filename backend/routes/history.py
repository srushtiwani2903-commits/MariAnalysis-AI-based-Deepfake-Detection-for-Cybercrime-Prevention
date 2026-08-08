"""Scan history endpoints: list, search, filter, detail, delete, dashboard stats."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from extensions import db
from models import Log, ScanHistory

history_bp = Blueprint("history", __name__)


@history_bp.route("", methods=["GET"])
@jwt_required()
def list_history():
    """List scans with pagination, search + type/result filters."""
    user_id = int(get_jwt_identity())
    q = (request.args.get("q") or "").strip().lower()
    scan_type = (request.args.get("type") or "").strip().lower()
    result = (request.args.get("result") or "").strip().lower()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, max(1, request.args.get("limit", 10, type=int)))

    query = ScanHistory.query.filter_by(user_id=user_id)
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
    })


@history_bp.route("/stats", methods=["GET"])
@jwt_required()
def stats():
    """Dashboard summary counts for the current user."""
    user_id = int(get_jwt_identity())
    total = ScanHistory.query.filter_by(user_id=user_id).count()
    fake = ScanHistory.query.filter_by(user_id=user_id, result="fake").count()
    real = ScanHistory.query.filter_by(user_id=user_id, result="authentic").count()
    inconclusive = total - fake - real
    accuracy = round((fake + real) / total * 100, 1) if total else 0.0
    last = ScanHistory.query.filter_by(user_id=user_id).order_by(ScanHistory.created_at.desc()).first()
    return jsonify({
        "total_scans": total,
        "fake_detected": fake,
        "real_detected": real,
        "inconclusive": inconclusive,
        "accuracy": accuracy,
        "last_scan_at": last.created_at.isoformat() if last else None,
        "last_result": last.to_dict() if last else None,
    })


@history_bp.route("/<int:scan_id>", methods=["GET"])
@jwt_required()
def detail(scan_id):
    user_id = int(get_jwt_identity())
    scan = db.session.get(ScanHistory, scan_id)
    if not scan or scan.user_id != user_id:
        return jsonify({"message": "Scan not found."}), 404
    return jsonify({"scan": scan.to_dict(include_full=True)})


@history_bp.route("/<int:scan_id>", methods=["DELETE"])
@jwt_required()
def delete_scan(scan_id):
    user_id = int(get_jwt_identity())
    scan = db.session.get(ScanHistory, scan_id)
    if not scan or scan.user_id != user_id:
        return jsonify({"message": "Scan not found."}), 404
    db.session.add(Log(user_id=user_id, action="delete_scan",
                       details=f"Deleted scan #{scan.id}", ip_address=request.remote_addr))
    db.session.delete(scan)
    db.session.commit()
    return jsonify({"message": "Scan deleted."})
