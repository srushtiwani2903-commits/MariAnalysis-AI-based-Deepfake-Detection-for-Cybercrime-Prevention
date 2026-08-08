"""Analytics endpoints: overview, daily/weekly scans, fake-vs-real, user activity."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from extensions import db
from models import Log, ScanHistory, User

analytics_bp = Blueprint("analytics", __name__)


def _day_buckets(days):
    """Return list of (day_label, start_datetime)."""
    today = datetime.now(timezone.utc).date()
    buckets = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        start = datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)
        buckets.append((d.isoformat(), start))
    return buckets


@analytics_bp.route("/overview", methods=["GET"])
@jwt_required()
def overview():
    user_id = int(get_jwt_identity())
    total = ScanHistory.query.filter_by(user_id=user_id).count()
    fake = ScanHistory.query.filter_by(user_id=user_id, result="fake").count()
    real = ScanHistory.query.filter_by(user_id=user_id, result="authentic").count()
    acc = round((fake + real) / total * 100, 1) if total else 0.0
    avg_conf = db.session.query(db.func.avg(ScanHistory.confidence)).filter_by(user_id=user_id).scalar() or 0
    return jsonify({
        "total_scans": total,
        "fake": fake,
        "authentic": real,
        "accuracy": acc,
        "avg_confidence": round(float(avg_conf), 1),
    })


@analytics_bp.route("/daily", methods=["GET"])
@jwt_required()
def daily():
    user_id = int(get_jwt_identity())
    days = min(30, max(1, request.args.get("days", 7, type=int)))
    rows = []
    for label, start in _day_buckets(days):
        end = start + timedelta(days=1)
        count = ScanHistory.query.filter(ScanHistory.user_id == user_id,
                                         ScanHistory.created_at >= start,
                                         ScanHistory.created_at < end).count()
        rows.append({"date": label, "scans": count})
    return jsonify({"days": days, "series": rows})


@analytics_bp.route("/weekly", methods=["GET"])
@jwt_required()
def weekly():
    user_id = int(get_jwt_identity())
    weeks = min(12, max(1, request.args.get("weeks", 8, type=int)))
    today = datetime.now(timezone.utc).date()
    rows = []
    for i in range(weeks - 1, -1, -1):
        end = today - timedelta(days=7 * i)
        start = end - timedelta(days=6)
        start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = start_dt + timedelta(days=7)
        count = ScanHistory.query.filter(ScanHistory.user_id == user_id,
                                         ScanHistory.created_at >= start_dt,
                                         ScanHistory.created_at < end_dt).count()
        rows.append({"week": start.isoformat(), "scans": count})
    return jsonify({"series": rows})


@analytics_bp.route("/fake-vs-real", methods=["GET"])
@jwt_required()
def fake_vs_real():
    user_id = int(get_jwt_identity())
    fake = ScanHistory.query.filter_by(user_id=user_id, result="fake").count()
    real = ScanHistory.query.filter_by(user_id=user_id, result="authentic").count()
    incon = ScanHistory.query.filter_by(user_id=user_id, result="inconclusive").count()
    return jsonify({"fake": fake, "authentic": real, "inconclusive": incon})


@analytics_bp.route("/by-type", methods=["GET"])
@jwt_required()
def by_type():
    user_id = int(get_jwt_identity())
    types = ["image", "video", "audio", "text"]
    data = {}
    for t in types:
        data[t] = ScanHistory.query.filter_by(user_id=user_id, scan_type=t).count()
    return jsonify(data)


@analytics_bp.route("/activity", methods=["GET"])
@jwt_required()
def activity():
    user_id = int(get_jwt_identity())
    last = (Log.query.filter(Log.user_id == user_id)
            .order_by(Log.created_at.desc()).limit(10).all())
    return jsonify({"items": [l.to_dict() for l in last]})


@analytics_bp.route("/accuracy-trend", methods=["GET"])
@jwt_required()
def accuracy_trend():
    """Cumulative accuracy over the last N scans (confidence-weighted proxy)."""
    user_id = int(get_jwt_identity())
    scans = (ScanHistory.query.filter_by(user_id=user_id)
             .order_by(ScanHistory.created_at.asc()).limit(200).all())
    series, cumulative = [], []
    fake_count = 0
    for i, s in enumerate(scans, 1):
        cumulative.append(round(s.confidence, 1))
        if len(cumulative) % 5 == 0 or i == len(scans):
            series.append({
                "scan_index": i,
                "confidence": round(sum(cumulative[-5:]) / len(cumulative[-5:]), 1),
            })
    return jsonify({"series": series})
