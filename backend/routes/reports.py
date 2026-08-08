"""Report endpoints: generate/download PDF, CSV, QR code for a scan."""
import io
import os

from flask import Blueprint, Response, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from config import Config
from extensions import db
from models import Log, Report, ScanHistory
from utils.idps import audit
from utils.report_generator import (generate_csv_report, generate_pdf_report,
                                    generate_qr_image)

reports_bp = Blueprint("reports", __name__)


def _get_owned_scan(scan_id):
    user_id = int(get_jwt_identity())
    scan = db.session.get(ScanHistory, scan_id)
    if not scan or scan.user_id != user_id:
        return None
    return scan


@reports_bp.route("/<int:scan_id>/pdf", methods=["GET"])
@jwt_required()
def download_pdf(scan_id):
    scan = _get_owned_scan(scan_id)
    if not scan:
        return jsonify({"message": "Scan not found."}), 404
    path = generate_pdf_report(scan, Config.REPORT_FOLDER)
    report = Report.query.filter_by(scan_id=scan.id, format="pdf").first()
    if not report:
        db.session.add(Report(scan_id=scan.id, user_id=scan.user_id, format="pdf", file_path=path))
        db.session.commit()
        audit("create", scan.user_id, "Report", scan.id, request.remote_addr, "PDF report generated")
    db.session.add(Log(user_id=scan.user_id, action="download_pdf",
                       details=f"PDF report for scan #{scan.id}",
                       ip_address=request.remote_addr))
    db.session.commit()
    return send_file(path, as_attachment=True,
                     download_name=f"marianalysis-report-{scan.id}.pdf",
                     mimetype="application/pdf")


@reports_bp.route("/<int:scan_id>/csv", methods=["GET"])
@jwt_required()
def download_csv(scan_id):
    scan = _get_owned_scan(scan_id)
    if not scan:
        return jsonify({"message": "Scan not found."}), 404
    csv_text = generate_csv_report(scan)
    db.session.add(Log(user_id=scan.user_id, action="download_csv",
                       details=f"CSV report for scan #{scan.id}",
                       ip_address=request.remote_addr))
    db.session.commit()
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=marianalysis-report-{scan.id}.csv"},
    )


@reports_bp.route("/<int:scan_id>/qr", methods=["GET"])
@jwt_required()
def download_qr(scan_id):
    scan = _get_owned_scan(scan_id)
    if not scan:
        return jsonify({"message": "Scan not found."}), 404
    path = generate_qr_image(scan, Config.REPORT_FOLDER)
    return send_file(path, mimetype="image/png")
