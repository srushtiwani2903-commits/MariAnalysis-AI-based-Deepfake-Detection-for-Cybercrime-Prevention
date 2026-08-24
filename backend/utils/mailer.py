"""Sends password reset e-mails via smtplib (stdlib only, no extra deps).

With SMTP off (MAIL_ENABLED=false) the reset link is logged to
security/logs/reset_links.log so local/dev builds still work.
"""
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import Config

logger = logging.getLogger("mailer")


def _log_link(to_email: str, link: str):
    """Fallback: persist the reset link so dev builds can test the flow."""
    log_dir = os.path.join(Config.BASE_DIR, "security", "logs")
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "reset_links.log")
    line = f"[{datetime.now(timezone.utc).isoformat()}] {to_email} -> {link}\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
    logger.info("Reset link for %s logged (MAIL_ENABLED=false): %s", to_email, link)


def send_raw(to_email: str, subject: str, body: str) -> bool:
    """Send a plain-text email via SMTP. When SMTP is off, log the body.

    Returns True if delivered, False if logged instead. Never raises.
    """
    if not Config.MAIL_ENABLED or not Config.SMTP_HOST:
        _append_log("mails.log", f"{to_email} | {subject} | {body}")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = Config.MAIL_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain"))
    try:
        server = smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=15)
        if Config.MAIL_STARTTLS:
            server.starttls()
        if Config.SMTP_USER:
            server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        server.sendmail(Config.SMTP_USER or Config.MAIL_FROM, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send email to %s", to_email)
        _append_log("mails.log", f"{to_email} | {subject} | {body}")
        return False


def _append_log(filename: str, line: str):
    log_dir = os.path.join(Config.BASE_DIR, "security", "logs")
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, filename)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] {line}\n")


def send_case_email(to_email: str, case_id: str, scan) -> bool:
    """Send an evidence-case confirmation email (deepfake cybercrime report)."""
    if not to_email or to_email.endswith(".local"):
        _append_log("case_emails.log", f"{to_email} | {case_id} | {scan.id} | {scan.result}")
        return False
    result = scan.result.upper() if scan else ""
    body = (
        f"MariAnalysis - Deepfake Evidence Case {case_id}\n"
        f"==========================================\n"
        f"Scan: {scan.original_filename or scan.filename}\n"
        f"Verdict: {result} (fake probability {scan.fake_probability:.1f}%)\n"
        f"Trust score: {scan.trust_score:.1f}/100\n"
        f"File SHA-256: {scan.file_hash}\n\n"
        f"Keep this email and the attached forensic PDF as evidence.\n"
        f"Report it to your local cybercrime helpline (India: 1930) for follow-up."
    )
    subject = f"MariAnalysis - Evidence Case {case_id} registered"
    return send_raw(to_email, subject, body)


def send_reset_email(to_email: str, reset_link: str) -> bool:
    """Send a password reset email. Returns True if delivered via SMTP,
    False if it was logged instead (SMTP not configured)."""
    if not Config.MAIL_ENABLED or not Config.SMTP_HOST:
        _log_link(to_email, reset_link)
        return False

    html = f"""\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background:#f1f5f9;font-family:Segoe UI,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 16px;">
      <tr><td align="center">
        <table role="presentation" width="520" cellpadding="0" cellspacing="0" style="max-width:520px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,0.08);">
          <tr>
            <td style="background:linear-gradient(135deg,#22d3ee,#a855f7);padding:24px 32px;">
              <span style="color:#ffffff;font-size:20px;font-weight:700;">MariAnalysis</span>
            </td>
          </tr>
          <tr>
            <td style="padding:32px;">
              <h2 style="margin:0 0 12px;color:#0f172a;font-size:20px;">Reset your password</h2>
              <p style="margin:0 0 20px;color:#475569;font-size:14px;line-height:1.6;">
                We received a request to reset the password for your MariAnalysis account.
                Click the button below to choose a new password. This link expires in 1 hour.
              </p>
              <p style="margin:0 0 24px;">
                <a href="{reset_link}" style="display:inline-block;background:linear-gradient(135deg,#22d3ee,#a855f7);color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;padding:12px 28px;border-radius:10px;">
                  Reset Password
                </a>
              </p>
              <p style="margin:0 0 8px;color:#94a3b8;font-size:12px;">
                If the button does not work, copy and paste this link into your browser:
              </p>
              <p style="margin:0 0 20px;word-break:break-all;color:#2563eb;font-size:12px;">{reset_link}</p>
              <p style="margin:0;color:#94a3b8;font-size:12px;">
                If you did not request this, you can safely ignore this email.
              </p>
            </td>
          </tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "MariAnalysis - Reset your password"
    msg["From"] = Config.MAIL_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        server = smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=15)
        if Config.MAIL_STARTTLS:
            server.starttls()
        if Config.SMTP_USER:
            server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        server.sendmail(Config.SMTP_USER or Config.MAIL_FROM, [to_email], msg.as_string())
        server.quit()
        logger.info("Reset email sent to %s", to_email)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send reset email to %s", to_email)
        _log_link(to_email, reset_link)
        return False
