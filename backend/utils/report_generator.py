"""PDF / CSV / QR report generation for scan results."""
import csv
import io
import os
import uuid

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, Image, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from utils.helpers import human_size

APP_NAME = "DeepGuard AI"
APP_TAGLINE = "AI-Based Deepfake Detection for Cybercrime Prevention"


def _style_sheet():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleNeon", parent=styles["Title"],
                              textColor=colors.HexColor("#0a0e27"), fontSize=20,
                              spaceAfter=4))
    styles.add(ParagraphStyle(name="SubNeon", parent=styles["Normal"],
                              textColor=colors.HexColor("#7c3aed"), fontSize=9,
                              spaceAfter=12))
    styles.add(ParagraphStyle(name="H2Neon", parent=styles["Heading2"],
                              textColor=colors.HexColor("#0a0e27"), fontSize=12,
                              spaceBefore=10, spaceAfter=4))
    styles.add(ParagraphStyle(name="BodyNeon", parent=styles["Normal"],
                              textColor=colors.HexColor("#1f2937"), fontSize=9, leading=13))
    return styles


def _confidence_bar(width_mm, pct):
    """Draw a simple progress bar as a table for the PDF confidence meter."""
    pct = max(0, min(100, float(pct)))
    fill = colors.HexColor("#22d3ee" if pct < 60 else "#f43f5e")
    data = [["", "", ""]]
    table = Table(data, colWidths=[width_mm * (pct / 100), width_mm * ((100 - pct) / 100), 18 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), fill),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#e5e7eb")),
        ("TEXTCOLOR", (2, 0), (2, 0), colors.HexColor("#0a0e27")),
        ("FONTSIZE", (2, 0), (2, 0), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def generate_pdf_report(scan, out_dir: str) -> str:
    """Generate a branded PDF report for a scan. Returns the file path."""
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"report_{scan.id}_{uuid.uuid4().hex[:8]}.pdf")
    styles = _style_sheet()

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"{APP_NAME} - Detection Report #{scan.id}",
                            author=APP_NAME)
    story = []

    # Header
    story.append(Paragraph(APP_NAME, styles["TitleNeon"]))
    story.append(Paragraph(APP_TAGLINE, styles["SubNeon"]))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#22d3ee")))
    story.append(Spacer(1, 4))

    # Result badge line
    result_color = {"authentic": "#10b981", "fake": "#f43f5e", "inconclusive": "#f59e0b"}
    rc = result_color.get(scan.result, "#6b7280")
    result_title = scan.result.upper()
    story.append(Paragraph(f"VERDICT: <font color='{rc}'>{result_title}</font>", styles["H2Neon"]))
    story.append(Spacer(1, 2))

    # Summary table
    summary = [
        ["Report ID", f"#{scan.id}"],
        ["Scan Type", scan.scan_type.title()],
        ["File", scan.filename],
        ["File Size", human_size(scan.file_size)],
        ["Timestamp", scan.created_at.strftime("%Y-%m-%d %H:%M UTC") if scan.created_at else "N/A"],
        ["Confidence", f"{scan.confidence:.1f}%"],
        ["Fake Probability", f"{scan.fake_probability:.1f}%"],
        ["Risk Level", scan.risk_level.title()],
        ["Processing Time", f"{scan.processing_time_ms} ms"],
        ["Model", scan.prediction.model_name if scan.prediction else "heuristic-ensemble-v1"],
    ]
    t = Table(summary, colWidths=[40 * mm, 110 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#111827")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)
    story.append(Spacer(1, 6))

    # Confidence meter
    story.append(Paragraph("Confidence Meter", styles["H2Neon"]))
    story.append(_confidence_bar(140, scan.confidence))
    story.append(Spacer(1, 6))

    # Explanation (XAI)
    story.append(Paragraph("Explainable AI Analysis", styles["H2Neon"]))
    story.append(Paragraph(scan.explanation or "No explanation available.", styles["BodyNeon"]))
    story.append(Spacer(1, 4))

    # Suspicious sections
    if scan.suspicious_sections:
        story.append(Paragraph("Suspicious Regions", styles["H2Neon"]))
        for sec in scan.suspicious_sections[:10]:
            snippet = str(sec)[:180]
            story.append(Paragraph(f"&bull; {snippet}", styles["BodyNeon"]))
        story.append(Spacer(1, 4))

    # Recommendations
    story.append(Paragraph("Recommendations", styles["H2Neon"]))
    for rec in (scan.recommendations or "").split("\n"):
        if rec.strip():
            story.append(Paragraph(f"&bull; {rec.strip()}", styles["BodyNeon"]))
    story.append(Spacer(1, 4))

    # Footer
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))
    story.append(Paragraph(
        "This report was automatically generated by DeepGuard AI. Confidence scores are "
        "probabilistic outputs of the detection model and are provided for forensic guidance, "
        "not as legal proof.", styles["SubNeon"]))

    doc.build(story)
    return out_path


def generate_csv_report(scan) -> str:
    """Generate CSV text for a scan report."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Field", "Value"])
    writer.writerow(["report_id", scan.id])
    writer.writerow(["scan_type", scan.scan_type])
    writer.writerow(["filename", scan.filename])
    writer.writerow(["file_size", scan.file_size])
    writer.writerow(["timestamp", scan.created_at.strftime("%Y-%m-%d %H:%M UTC") if scan.created_at else ""])
    writer.writerow(["result", scan.result])
    writer.writerow(["confidence", f"{scan.confidence:.2f}"])
    writer.writerow(["fake_probability", f"{scan.fake_probability:.2f}"])
    writer.writerow(["risk_level", scan.risk_level])
    writer.writerow(["processing_time_ms", scan.processing_time_ms])
    writer.writerow(["explanation", scan.explanation])
    writer.writerow(["recommendations", scan.recommendations.replace("\n", " | ")])
    return buf.getvalue()


def generate_qr_content(scan) -> str:
    """Build a shareable verification string encoded into the QR code."""
    base = "https://deepguard.ai/verify/"
    return f"{base}scan/{scan.id}?r={scan.result}&c={scan.confidence:.1f}&p={scan.fake_probability:.1f}"


def generate_qr_image(scan, out_dir: str) -> str:
    """Render a QR code PNG for a scan. Returns the file path."""
    import qrcode
    os.makedirs(out_dir, exist_ok=True)
    qr = qrcode.make(generate_qr_content(scan))
    out_path = os.path.join(out_dir, f"qr_{scan.id}.png")
    qr.save(out_path)
    return out_path
