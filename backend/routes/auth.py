"""Authentication endpoints: register, login, password reset, profile.

Passwords are hashed with werkzeug, sessions use expiring JWTs, and inputs are
validated (email regex, password strength) and rate-limited.
"""
import queue
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, jwt_required
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from extensions import db
from models import ActiveSession, Log, User
from utils.helpers import generate_reset_token
from utils.idps import audit, ban_remaining_seconds, is_banned, record_failure, record_success
from utils.mailer import send_reset_email
from utils.otp import issue_otp, send_email_otp, send_phone_otp, verify_otp
from utils.security import (encrypt_secret, is_encrypted, limiter, sanitize_string,
                            decrypt_secret)

auth_bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")


def _client_key():
    """Rate-limit key: authenticated user or IP."""
    user_id = get_jwt_identity() if request.headers.get("Authorization") else None
    return f"user:{user_id}" if user_id else f"ip:{request.remote_addr}"


def _reject_if_banned():
    """Return a Flask response if the client IP is IDPS-banned, else None."""
    if not Config.IDPS_ENABLED or not is_banned(request.remote_addr):
        return None
    remaining = ban_remaining_seconds(request.remote_addr)
    return jsonify({"message": f"Too many failed attempts. Try again in {remaining}s.",
                    "banned": True, "retry_after": remaining}), 429


def _validate_password(pw):
    if len(pw) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", pw) or not re.search(r"[a-z]", pw):
        return "Password must contain upper and lower case letters."
    if not re.search(r"\d", pw):
        return "Password must contain at least one number."
    if not re.search(r"[^A-Za-z0-9]", pw):
        return "Password must contain at least one special character."
    return None


def _now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _purge_stale_sessions(user_id):
    now = _now_naive()
    ActiveSession.query.filter_by(user_id=user_id, is_active=True).filter(
        ActiveSession.expires_at < now).update({"is_active": False})
    db.session.commit()


def _active_sessions(user_id):
    """Return the user's non-expired, active sessions."""
    _purge_stale_sessions(user_id)
    now = _now_naive()
    return (ActiveSession.query.filter_by(user_id=user_id, is_active=True)
            .filter(ActiveSession.expires_at > now).all())


def _issue_session(user):
    """Create an ActiveSession row and return a JWT carrying its jti."""
    jti = uuid4().hex
    now = _now_naive()
    db.session.add(ActiveSession(
        user_id=user.id, jti=jti,
        expires_at=now + Config.JWT_ACCESS_TOKEN_EXPIRES,
        ip_address=request.remote_addr,
        user_agent=(request.user_agent.string or "")[:255],
    ))
    db.session.commit()
    return create_access_token(identity=str(user.id), additional_claims={"jti": jti})


# In-memory pub/sub: tells other devices to log out the instant this user
# signs in elsewhere (Server-Sent Events).
_EVENTS = {}            # user_id -> set[queue.Queue]
_EVENTS_LOCK = threading.Lock()


def _subscribe(user_id):
    q = queue.Queue(maxsize=16)
    with _EVENTS_LOCK:
        _EVENTS.setdefault(user_id, set()).add(q)
    return q


def _unsubscribe(user_id, q):
    with _EVENTS_LOCK:
        subs = _EVENTS.get(user_id)
        if subs:
            subs.discard(q)
            if not subs:
                _EVENTS.pop(user_id, None)


def _publish(user_id, event, data=""):
    with _EVENTS_LOCK:
        subs = list(_EVENTS.get(user_id, ()))
    for q in subs:
        try:
            q.put_nowait((event, data))
        except queue.Full:
            pass


@auth_bp.route("/events", methods=["GET"])
@jwt_required()
def sse_events():
    """Long-lived stream: other tabs/devices get 'session_revoked' when this
    user signs in again, so they log themselves out immediately (no refresh)."""
    user_id = int(get_jwt_identity())
    sub = _subscribe(user_id)

    def stream():
        try:
            yield "retry: 5000\n\n"
            while True:
                try:
                    event, data = sub.get(timeout=15)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                yield f"event: {event}\ndata: {data}\n\n"
                if event == "session_revoked":
                    break
        finally:
            _unsubscribe(user_id, sub)

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    banned = _reject_if_banned()
    if banned:
        return banned
    if Config.RATE_LIMIT_ENABLED and not limiter.allow(_client_key())[0]:
        return jsonify({"message": "Too many requests. Try again later."}), 429

    username = sanitize_string(data.get("username", "")).strip()
    email = (sanitize_string(data.get("email", "")) or "").strip().lower()
    password = data.get("password", "") or ""
    full_name = sanitize_string(data.get("full_name", ""), 120).strip()
    phone = (sanitize_string(data.get("phone", "")) or "").strip()

    if not username or not email or not password:
        return jsonify({"message": "Username, email and password are required."}), 400
    if not EMAIL_RE.match(email):
        return jsonify({"message": "Please provide a valid email address."}), 400
    pw_error = _validate_password(password)
    if pw_error:
        return jsonify({"message": pw_error}), 400
    if phone and not PHONE_RE.match(phone):
        return jsonify({"message": "Please provide a valid phone number (7-15 digits, optional +)."}), 400
    if User.query.filter((User.email == email) | (User.username == username)).first():
        return jsonify({"message": "Username or email is already registered."}), 409
    if phone and User.query.filter_by(phone=phone).first():
        return jsonify({"message": "This phone number is already registered."}), 409

    user = User(
        username=username,
        email=email,
        full_name=full_name,
        password_hash=generate_password_hash(password),
        phone=phone or None,
        is_verified=True,
        phone_verified=True if phone else False,
    )
    db.session.add(user)
    db.session.flush()
    db.session.add(Log(user_id=user.id, action="register", details=f"New user {username}",
                       ip_address=request.remote_addr))
    db.session.commit()
    audit("register", user.username, "User", user.id, request.remote_addr,
          f"New user registered: {username}")

    # No OTP gate for now - the account is active immediately and the user is
    # logged straight in. (Phone OTP/email verification removed for now.)
    token = _issue_session(user)
    return jsonify({
        "message": "Account created. Welcome!",
        "token": token,
        "user": user.to_dict(),
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    banned = _reject_if_banned()
    if banned:
        return banned
    if Config.RATE_LIMIT_ENABLED and not limiter.allow(_client_key())[0]:
        return jsonify({"message": "Too many requests. Try again later."}), 429

    identifier = sanitize_string(data.get("identifier", "")).strip().lower()
    password = data.get("password", "") or ""
    if not identifier or not password:
        return jsonify({"message": "Email/username/phone and password are required."}), 400

    user = User.query.filter(
        (User.email == identifier) | (User.username == identifier) | (User.phone == identifier)
    ).first()
    if not user or not check_password_hash(user.password_hash, password):
        attempts = record_failure(request.remote_addr, identifier) if Config.IDPS_ENABLED else 0
        return jsonify({"message": "Invalid credentials.", "failed_attempts": attempts}), 401

    # OTP/email verification gate is removed for now - any registered account
    # can log in (by email, username or phone) immediately.

    # Single-session rule: this login is the only active session. Any other
    # active session is revoked immediately and those devices are told via SSE
    # to log out on the spot - no refresh or manual logout needed.
    if _active_sessions(user.id):
        ActiveSession.query.filter_by(user_id=user.id, is_active=True).update(
            {"is_active": False, "revoked_reason": "superseded"})
        db.session.commit()
        _publish(user.id, "session_revoked", str(user.id))

    record_success(request.remote_addr)
    user.last_login = datetime.now(timezone.utc)
    db.session.add(Log(user_id=user.id, action="login", details="Successful login",
                       ip_address=request.remote_addr))
    db.session.commit()
    audit("login", user.username, "User", user.id, request.remote_addr, "Successful login")

    token = _issue_session(user)
    return jsonify({"message": "Login successful.", "token": token, "user": user.to_dict()})


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json(silent=True) or {}
    banned = _reject_if_banned()
    if banned:
        return banned
    email = (sanitize_string(data.get("email", "")) or "").strip().lower()
    if not EMAIL_RE.match(email):
        return jsonify({"message": "Please provide a valid email address."}), 400

    user = User.query.filter_by(email=email).first()
    if user:
        token = generate_reset_token()
        # Stored encrypted at rest; the plaintext lives only in the emailed link.
        user.reset_token = encrypt_secret(token)
        user.reset_token_expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
            hours=Config.RESET_TOKEN_TTL_HOURS)
        link = (f"{Config.FRONTEND_URL}/reset-password?"
                f"token={token}&email={email}")
        delivered = send_reset_email(email, link)
        db.session.add(Log(user_id=user.id, action="forgot_password",
                           details="Password reset link sent to email",
                           ip_address=request.remote_addr))
        db.session.commit()
        # Never leak the token to the client; expose a debug link only when
        # SMTP is off (logged locally) so dev builds can test the flow.
        response = {"message": "If that email exists, a reset link was sent."}
        if not delivered:
            response["debug_link"] = link
        return jsonify(response), 200
    return jsonify({"message": "If that email exists, a reset link was sent."}), 200


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or {}
    banned = _reject_if_banned()
    if banned:
        return banned
    email = (sanitize_string(data.get("email", "")) or "").strip().lower()
    token = (data.get("token") or "").strip()
    new_password = data.get("new_password", "") or ""
    pw_error = _validate_password(new_password)
    if pw_error:
        return jsonify({"message": pw_error}), 400
    if not email or not token:
        return jsonify({"message": "Email and reset token are required."}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"message": "Reset link is invalid or has expired."}), 400
    if not user.reset_token or not user.reset_token_expires:
        return jsonify({"message": "Reset link is invalid or has expired."}), 400
    stored = user.reset_token
    if is_encrypted(stored):
        try:
            stored = decrypt_secret(stored)
        except Exception:  # noqa: BLE001 - bad/rotated ciphertext -> treat as invalid
            return jsonify({"message": "Reset link is invalid or has expired."}), 400
    if not secrets.compare_digest(stored, token):
        return jsonify({"message": "Reset link is invalid or has expired."}), 400
    if datetime.now(timezone.utc).replace(tzinfo=None) > user.reset_token_expires:
        return jsonify({"message": "Reset link has expired. Please request a new one."}), 400

    user.password_hash = generate_password_hash(new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.session.add(Log(user_id=user.id, action="reset_password", details="Password reset",
                       ip_address=request.remote_addr))
    db.session.commit()
    audit("update", user.username, "User", user.id, request.remote_addr, "Password reset")
    return jsonify({"message": "Password updated. You can log in now."})


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return jsonify({"message": "User not found."}), 404
    return jsonify({"user": user.to_dict()})


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    jti = get_jwt().get("jti")
    if jti:
        ActiveSession.query.filter_by(jti=jti).update(
            {"is_active": False, "revoked_reason": "logout"})
        db.session.commit()
    return jsonify({"message": "Logged out."})


@auth_bp.route("/profile", methods=["PUT"])
@jwt_required()
def update_profile():
    user = db.session.get(User, int(get_jwt_identity()))
    data = request.get_json(silent=True) or {}
    if not user:
        return jsonify({"message": "User not found."}), 404
    response = {}
    if "full_name" in data:
        user.full_name = sanitize_string(data["full_name"], 120)
    if "phone" in data:
        phone = (sanitize_string(data["phone"]) or "").strip()
        if phone and not PHONE_RE.match(phone):
            return jsonify({"message": "Please provide a valid phone number (7-15 digits, optional +)."}), 400
        if phone != (user.phone or ""):
            existing = User.query.filter_by(phone=phone).first() if phone else None
            if existing and existing.id != user.id:
                return jsonify({"message": "This phone number is already registered."}), 409
            user.phone = phone or None
            user.phone_verified = False
            if phone:
                code = issue_otp(user)
                send_phone_otp(phone, code)
                response["phone_otp_sent"] = True
                response["debug_otp"] = code if (Config.DEBUG_OTP and not Config.SMS_ENABLED) else None
                response["message"] = "OTP sent to your phone - verify it to enable phone login."
    db.session.commit()
    response["user"] = user.to_dict()
    return jsonify(response)


@auth_bp.route("/verify-email", methods=["POST"])
def verify_email():
    data = request.get_json(silent=True) or {}
    banned = _reject_if_banned()
    if banned:
        return banned
    email = (sanitize_string(data.get("email", "")) or "").strip().lower()
    otp = data.get("otp", "")
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"message": "Account not found for this email."}), 404
    ok, msg = verify_otp(user, otp)
    if not ok:
        db.session.commit()
        return jsonify({"message": msg}), 400

    user.is_verified = True
    user.otp_code = None
    user.otp_expires = None
    db.session.add(Log(user_id=user.id, action="verify_email", details="Email verified via OTP",
                       ip_address=request.remote_addr))
    db.session.commit()
    audit("update", user.username, "User", user.id, request.remote_addr, "Email OTP verified")

    active = _active_sessions(user.id)
    token = _issue_session(user) if not active else None
    return jsonify({"message": "Email verified. Welcome!", "token": token, "user": user.to_dict()})


@auth_bp.route("/verify-phone", methods=["POST"])
def verify_phone():
    data = request.get_json(silent=True) or {}
    banned = _reject_if_banned()
    if banned:
        return banned
    email = (sanitize_string(data.get("email", "")) or "").strip().lower()
    otp = data.get("otp", "")
    user = User.query.filter_by(email=email).first()
    if not user or not user.phone:
        return jsonify({"message": "No phone number is linked to this account."}), 404
    ok, msg = verify_otp(user, otp)
    if not ok:
        db.session.commit()
        return jsonify({"message": msg}), 400

    user.phone_verified = True
    user.is_verified = True
    user.otp_code = None
    user.otp_expires = None
    db.session.add(Log(user_id=user.id, action="verify_phone", details="Phone verified via OTP",
                       ip_address=request.remote_addr))
    db.session.commit()
    audit("update", user.username, "User", user.id, request.remote_addr, "Phone OTP verified")

    active = _active_sessions(user.id)
    token = _issue_session(user) if not active else None
    return jsonify({"message": "Phone number verified. You can now log in with it.",
                    "token": token, "user": user.to_dict()})


@auth_bp.route("/resend-otp", methods=["POST"])
def resend_otp():
    data = request.get_json(silent=True) or {}
    banned = _reject_if_banned()
    if banned:
        return banned
    email = (sanitize_string(data.get("email", "")) or "").strip().lower()
    channel = (data.get("channel") or "email").strip().lower()
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"message": "Account not found for this email."}), 404
    if channel == "phone":
        if not user.phone:
            return jsonify({"message": "No phone number is linked to this account."}), 400
        code = issue_otp(user)
        send_phone_otp(user.phone, code)
    else:
        code = issue_otp(user)
        send_email_otp(email, code)
    db.session.commit()
    response = {"message": "A new OTP was sent."}
    if Config.DEBUG_OTP and not Config.SMS_ENABLED:
        response["debug_otp"] = code
    return jsonify(response)


@auth_bp.route("/change-password", methods=["POST"])
@jwt_required()
def change_password():
    user = db.session.get(User, int(get_jwt_identity()))
    data = request.get_json(silent=True) or {}
    if not user:
        return jsonify({"message": "User not found."}), 404
    if not check_password_hash(user.password_hash, data.get("current_password", "")):
        return jsonify({"message": "Current password is incorrect."}), 400
    pw_error = _validate_password(data.get("new_password", ""))
    if pw_error:
        return jsonify({"message": pw_error}), 400
    user.password_hash = generate_password_hash(data["new_password"])
    db.session.commit()
    audit("update", user.username, "User", user.id, request.remote_addr, "Password changed")
    return jsonify({"message": "Password changed successfully."})
