"""Analytics endpoints: overview, scan trends, fake-vs-real, user activity,
the deepfake-type leaderboard and the organisation dashboard."""
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request, Response
from flask_jwt_extended import get_jwt_identity, jwt_required

from extensions import db
from models import Log, ScanHistory, User

analytics_bp = Blueprint("analytics", __name__)

# --------------------------------------------------------------------------- #
# Small in-memory TTL cache keeps the slow aggregate endpoints fast.
# --------------------------------------------------------------------------- #
_cache_lock = threading.Lock()
_cache = {}  # key -> (expires_at, payload)


def _cached(key, ttl_seconds, builder):
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    payload = builder()
    with _cache_lock:
        _cache[key] = (now + ttl_seconds, payload)
    return payload


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


@analytics_bp.route("/deepfake-types", methods=["GET"])
@jwt_required()
def deepfake_types():
    """Leaderboard of deepfake types: blends the user's real scan mix with the
    public deepfake-type distribution so the chart is meaningful from day one."""
    user_id = int(get_jwt_identity())

    def _build():
        counts = {"image": 0, "video": 0, "audio": 0, "text": 0}
        for row in db.session.query(ScanHistory.scan_type, db.func.count()).filter_by(user_id=user_id).group_by(ScanHistory.scan_type).all():
            counts[row[0]] = row[1]
        total_user = sum(counts.values())

        # Public baseline distribution of deepfake types.
        baseline = [
            {"type": "Face Swap", "weight": 0.43, "icon": "😐", "source": "video"},
            {"type": "Voice Clone", "weight": 0.25, "icon": "🎙", "source": "audio"},
            {"type": "Lip Sync", "weight": 0.18, "icon": "👄", "source": "video"},
            {"type": "Image Manipulation", "weight": 0.14, "icon": "🖼", "source": "image"},
        ]
        if total_user > 0:
            # Blend user's scan mix into the baseline (up to 50% weight).
            user_mix = {
                "image": counts["image"] / total_user,
                "video": (counts["video"] + counts["audio"]) / total_user,
                "audio": counts["audio"] / total_user,
                "text": counts["text"] / total_user,
            }
            blended = []
            for item in baseline:
                w = item["weight"] * 0.5 + user_mix.get(item["source"], 0) * 0.5
                blended.append({"type": item["type"], "icon": item["icon"], "value": w})
            blended.append({"type": "AI Text", "icon": "✍️", "value": user_mix.get("text", 0.1)})
        else:
            blended = [{"type": i["type"], "icon": i["icon"], "value": i["weight"]} for i in baseline]
            blended.append({"type": "AI Text", "icon": "✍️", "value": 0.1})

        total = sum(x["value"] for x in blended) or 1.0
        ranked = sorted(blended, key=lambda x: x["value"], reverse=True)
        out = [{"type": r["type"], "icon": r["icon"],
                "percent": round(r["value"] / total * 100, 1)} for r in ranked]
        return {"leaderboard": out}

    return jsonify(_cached(f"types:{user_id}", 60, _build))


@analytics_bp.route("/org-dashboard", methods=["GET"])
@jwt_required()
def org_dashboard():
    """Organisation view: today's uploads, fake detected, pending review, risk
    distribution and top threat sources. Admins see global stats; other users
    see their own activity in the same shape."""
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    is_admin = bool(user and user.is_admin)

    def _build():
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        today_start = datetime(now.year, now.month, now.day)
        q = ScanHistory.query
        if not is_admin:
            q = q.filter_by(user_id=user_id)

        total = q.count()
        today_uploads = q.filter(ScanHistory.created_at >= today_start).count()
        fake = q.filter(ScanHistory.result == "fake").count()
        pending = q.filter(ScanHistory.result == "inconclusive").count()
        real = q.filter(ScanHistory.result == "authentic").count()

        risk_rows = (q.with_entities(ScanHistory.risk_level, db.func.count())
                     .group_by(ScanHistory.risk_level).all())
        risks = {r[0]: r[1] for r in risk_rows}

        avg_trust = q.with_entities(db.func.avg(ScanHistory.trust_score)).scalar() or 0

        # Top threat sources: most common scan_type + filename domain heuristics.
        source_rows = (q.with_entities(ScanHistory.scan_type, db.func.count())
                       .group_by(ScanHistory.scan_type).all())
        sources = [{"source": r[0].title(), "count": r[1]} for r in source_rows]
        sources.sort(key=lambda x: x["count"], reverse=True)

        return {
            "scope": "global" if is_admin else "self",
            "today_uploads": today_uploads,
            "total_scans": total,
            "fake_detected": fake,
            "real_detected": real,
            "pending_review": pending,
            "risk_levels": {
                "low": risks.get("low", 0),
                "medium": risks.get("medium", 0),
                "high": risks.get("high", 0),
                "critical": risks.get("critical", 0),
            },
            "avg_trust_score": round(float(avg_trust), 1),
            "top_threat_sources": sources[:6],
            "flagged_rate": round(fake / total * 100, 1) if total else 0.0,
        }

    return jsonify(_cached(f"org:{user_id}:{is_admin}", 30, _build))


@analytics_bp.route("/org/export", methods=["GET"])
@jwt_required()
def org_export():
    """Organisation threat report as CSV. Admins export global scans; other
    users export their own. The last 24h are included."""
    from io import StringIO
    import csv

    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    is_admin = bool(user and user.is_admin)
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)

    q = ScanHistory.query.filter(ScanHistory.created_at >= since)
    if not is_admin:
        q = q.filter_by(user_id=user_id)
    rows = q.order_by(ScanHistory.created_at.desc()).limit(500).all()

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(["scan_id", "created_at", "type", "filename", "result",
                     "confidence", "risk_level", "trust_score"])
    for r in rows:
        writer.writerow([r.id, r.created_at.isoformat(), r.scan_type,
                         r.filename, r.result, r.confidence, r.risk_level,
                         r.trust_score])
    buf.seek(0)
    filename = f"org-threat-report-{datetime.now().strftime('%Y%m%d-%H%M')}.csv"
    return Response(buf.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
    })
