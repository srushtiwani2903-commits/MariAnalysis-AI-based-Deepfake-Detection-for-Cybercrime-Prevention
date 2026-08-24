"""Cybercrime reporting portal + blockchain evidence ledger.

Registers a scan as a case (DF-YYYY-NNNN), anchors it in the tamper-evident
chain and generates the evidence PDF; also serves the cases, chain, verify
and status endpoints.
"""
import hashlib
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from config import Config
from extensions import db
from models import BlockchainBlock, EvidenceCase, Log, ScanHistory
from services import blockchain
from utils.idps import audit
from utils.mailer import send_case_email
from utils.report_generator import generate_pdf_report
from utils.security import limiter, sanitize_string

evidence_bp = Blueprint("evidence", __name__)


def _get_owned_scan(scan_id):
    user_id = int(get_jwt_identity())
    scan = db.session.get(ScanHistory, scan_id)
    if not scan or scan.user_id != user_id:
        return None
    return scan


def _next_case_id():
    year = datetime.now(timezone.utc).year
    count = EvidenceCase.query.count()
    for _ in range(200):
        count += 1
        case_id = f"DF-{year}-{count:04d}"
        if not EvidenceCase.query.filter_by(case_id=case_id).first():
            return case_id
    raise RuntimeError("Could not allocate a case ID.")


def _rate_limited():
    key = f"user:{get_jwt_identity()}"
    if Config.RATE_LIMIT_ENABLED and not limiter.allow(key)[0]:
        return True
    return False


@evidence_bp.route("/<int:scan_id>/register", methods=["POST"])
@jwt_required()
def register_case(scan_id):
    """Report a detected deepfake to the cybercrime portal."""
    if _rate_limited():
        return jsonify({"message": "Too many requests. Try again later."}), 429
    scan = _get_owned_scan(scan_id)
    if not scan:
        return jsonify({"message": "Scan not found."}), 404
    if EvidenceCase.query.filter_by(scan_id=scan.id).first():
        return jsonify({"message": "This scan has already been reported."}), 409

    data = request.get_json(silent=True) or {}
    platform = sanitize_string(data.get("platform", ""), 120)
    notes = sanitize_string(data.get("notes", ""), 2000)

    case_id = _next_case_id()
    report_path = generate_pdf_report(scan, Config.REPORT_FOLDER)
    report_hash = hashlib.sha256(open(report_path, "rb").read()).hexdigest()

    case = EvidenceCase(
        case_id=case_id,
        scan_id=scan.id,
        user_id=scan.user_id,
        status="open",
        platform=platform,
        notes=notes,
        report_hash=report_hash,
    )
    db.session.add(case)
    db.session.flush()
    block = blockchain.add_block(scan=scan, file_hash=scan.file_hash or "",
                                 report_hash=report_hash, case_id=case_id,
                                 extra={"report_url": f"/api/reports/{scan.id}/pdf"})
    db.session.add(Log(user_id=scan.user_id, action="report_case",
                       details=f"Case {case_id} registered for scan #{scan.id}",
                       ip_address=request.remote_addr))
    db.session.commit()
    audit("create", scan.user_id, "EvidenceCase", case.id, request.remote_addr,
          f"Deepfake reported as case {case_id}")

    send_case_email(scan.user.email if scan.user else "", case_id, scan)
    return jsonify({
        "message": f"Evidence registered. Case ID {case_id}.",
        "case": case.to_dict(),
        "block": block,
        "chain_valid": blockchain.is_chain_valid()[0],
    }), 201


@evidence_bp.route("/cases", methods=["GET"])
@jwt_required()
def list_cases():
    user_id = int(get_jwt_identity())
    cases = (EvidenceCase.query.filter_by(user_id=user_id)
             .order_by(EvidenceCase.created_at.desc()).all())
    out = []
    for c in cases:
        item = c.to_dict()
        scan = db.session.get(ScanHistory, c.scan_id)
        if scan:
            item["scan"] = {"result": scan.result, "filename": scan.filename,
                            "scan_type": scan.scan_type, "fake_probability": scan.fake_probability,
                            "trust_score": scan.trust_score}
        item["block"] = BlockchainBlock.query.filter_by(scan_id=c.scan_id).first().to_dict() \
            if BlockchainBlock.query.filter_by(scan_id=c.scan_id).first() else None
        out.append(item)
    return jsonify({"cases": out})


@evidence_bp.route("/chain", methods=["GET"])
@jwt_required()
def chain():
    valid, problems = blockchain.is_chain_valid()
    return jsonify({
        "chain_valid": valid,
        "problems": problems[:10],
        "blocks": blockchain.chain_summary(25),
        "length": BlockchainBlock.query.count(),
    })


@evidence_bp.route("/verify/<int:scan_id>", methods=["GET"])
@jwt_required()
def verify(scan_id):
    scan = _get_owned_scan(scan_id)
    if not scan:
        return jsonify({"message": "Scan not found."}), 404
    res = blockchain.verify_scan(scan_id)
    if not res:
        return jsonify({"message": "No blockchain evidence exists for this scan.",
                        "registered": False}), 404
    return jsonify({"registered": True, **res})


def _public_case_payload(case):
    """Shared payload for the public verify endpoints (no auth needed)."""
    scan = db.session.get(ScanHistory, case.scan_id)
    block = BlockchainBlock.query.filter_by(scan_id=case.scan_id).first()
    res = blockchain.verify_scan(case.scan_id) if block else None
    return {
        "case": {
            "case_id": case.case_id,
            "status": case.status,
            "platform": case.platform,
            "created_at": case.created_at.isoformat() if case.created_at else None,
            "report_hash": case.report_hash,
        },
        "scan": {
            "id": case.scan_id,
            "result": scan.result if scan else None,
            "scan_type": scan.scan_type if scan else None,
            "fake_probability": scan.fake_probability if scan else None,
            "trust_score": scan.trust_score if scan else None,
        } if scan else None,
        "registered": bool(block),
        "intact": bool(res and res["intact"]),
        "chain_valid": blockchain.is_chain_valid()[0],
        "block": res["block"] if res else None,
    }


@evidence_bp.route("/verify-case/<case_id>", methods=["GET"])
def verify_public_case(case_id):
    """Public proof check: anyone with a case ID can confirm the evidence."""
    case = EvidenceCase.query.filter_by(case_id=case_id).first()
    if not case:
        return jsonify({"message": "Case not found.", "found": False}), 404
    return jsonify({"found": True, **_public_case_payload(case)})


@evidence_bp.route("/verify-scan/<int:scan_id>", methods=["GET"])
def verify_public_scan(scan_id):
    """Public proof check by scan ID (works even without a registered case)."""
    res = blockchain.verify_scan(scan_id)
    if not res:
        return jsonify({"message": "No blockchain evidence exists for this scan.",
                        "found": False, "registered": False}), 404
    case = EvidenceCase.query.filter_by(scan_id=scan_id).first()
    return jsonify({"found": True, "registered": True,
                    "case": case.to_dict() if case else None, **res})


@evidence_bp.route("/<string:case_id>/status", methods=["POST"])
@jwt_required()
def update_status(case_id):
    user_id = int(get_jwt_identity())
    case = EvidenceCase.query.filter_by(case_id=case_id, user_id=user_id).first()
    if not case:
        return jsonify({"message": "Case not found."}), 404
    status = sanitize_string((request.get_json(silent=True) or {}).get("status", ""))
    if status not in {"open", "reviewed", "closed"}:
        return jsonify({"message": "Invalid status."}), 400
    case.status = status
    db.session.add(Log(user_id=user_id, action="case_status",
                       details=f"Case {case.case_id} -> {status}",
                       ip_address=request.remote_addr))
    db.session.commit()
    return jsonify({"message": "Case status updated.", "case": case.to_dict()})
