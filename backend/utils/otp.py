"""Email + phone OTP generation, issuing and verification.

Email OTPs go through utils.mailer and phone OTPs through MSG91 when
configured, otherwise they're logged for local testing. Stored hashed (never
plain text) with an expiry and a max-attempts cap.
"""
import hashlib
import logging
import os
import random
import re
import secrets
from datetime import datetime, timedelta, timezone

from config import Config

logger = logging.getLogger("otp")

LOG_DIR = os.path.join(Config.BASE_DIR, "security", "logs")


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def generate_otp() -> str:
    """Return a 6-digit numeric OTP."""
    return f"{random.SystemRandom().randint(0, 999999):06d}"


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _append_log(filename: str, line: str):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, filename), "a", encoding="utf-8") as f:
        f.write(f"[{_now().isoformat()}] {line}\n")


def issue_otp(user) -> str:
    """Generate + store a fresh OTP for a user (overwrites previous)."""
    code = generate_otp()
    user.otp_code = _hash(code)
    user.otp_expires = _now() + timedelta(seconds=Config.OTP_TTL_SECONDS)
    user.otp_attempts = 0
    return code


def verify_otp(user, code: str):
    """Verify an OTP. Returns (ok, message). Increments failed attempts."""
    code = (code or "").strip()
    if not user.otp_code or not user.otp_expires:
        return False, "No OTP was requested for this account."
    if user.otp_attempts >= Config.OTP_MAX_ATTEMPTS:
        return False, "Too many wrong attempts. Please request a new OTP."
    if _now() > user.otp_expires:
        return False, "This OTP has expired. Please request a new one."
    if not secrets.compare_digest(user.otp_code, _hash(code)):
        user.otp_attempts = (user.otp_attempts or 0) + 1
        return False, "Incorrect OTP. Please try again."
    return True, ""


def send_email_otp(email: str, code: str) -> bool:
    """Deliver an email OTP (SMTP) or log it for dev builds."""
    subject = "MariAnalysis - Verify your email"
    body = (f"Your MariAnalysis verification code is: {code}\n\n"
            "This code expires in a few minutes. If you did not request it, ignore this email.")
    try:
        from utils.mailer import send_raw
        delivered = send_raw(email, subject, body)
    except Exception:  # noqa: BLE001
        logger.exception("email OTP send failed")
        delivered = False
    if not delivered:
        _append_log("otp_email.log", f"{email} -> {code}")
    return delivered


def _normalize_phone(phone: str) -> str:
    """Return MSG91 mobile format (country code + 10-digit number), e.g. 919876543210."""
    digits = re.sub(r"\D", "", phone or "")
    cc = Config.MSG91_COUNTRY_CODE
    if digits.startswith("0"):
        digits = digits[1:]
    if digits.startswith(cc):
        return digits
    if len(digits) == 10:
        return cc + digits
    return digits


def send_phone_otp(phone: str, code: str) -> bool:
    """Deliver a phone OTP via MSG91 SMS. Falls back to dev logging when the
    SMS gateway is not configured."""
    if Config.SMS_ENABLED:
        try:
            import requests as _requests
            params = {
                "authkey": Config.MSG91_AUTHKEY,
                "mobile": _normalize_phone(phone),
                "otp": code,
                "sender": Config.MSG91_SENDER_ID,
                "template_id": Config.MSG91_TEMPLATE_ID,
                "otp_expiry": str(max(Config.OTP_TTL_SECONDS // 60, 1)),
            }
            resp = _requests.get("https://api.msg91.com/api/v5/otp",
                                 params=params, timeout=15)
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if resp.status_code == 200 and data.get("type") == "success":
                logger.info("Phone OTP sent via MSG91 to %s", _normalize_phone(phone))
                return True
            logger.warning("MSG91 OTP failed (%s): %s", resp.status_code, data.get("message", resp.text[:200]))
        except Exception:  # noqa: BLE001
            logger.exception("MSG91 phone OTP send failed")
        # Fall through to dev logging so a gateway error still lets the user
        # complete verification locally.
    _append_log("otp_phone.log", f"{phone} -> {code}")
    return False
