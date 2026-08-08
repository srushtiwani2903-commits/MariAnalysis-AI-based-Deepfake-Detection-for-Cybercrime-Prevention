"""Authentication endpoints: register, login, forgot/reset password, profile.

Security:
  - Passwords hashed with werkzeug (PBKDF2) - never stored in plain text.
  - JWT access tokens (flask-jwt-extended) with expiry.
  - Email regex validation, password strength rules, rate limiting.
"""
import re
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from extensions import db
from models import Log, User
from utils.helpers import generate_reset_token
from utils.security import limiter, sanitize_string

auth_bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _client_key():
    """Rate-limit key: authenticated user or IP."""
    user_id = get_jwt_identity() if request.headers.get("Authorization") else None
    return f"user:{user_id}" if user_id else f"ip:{request.remote_addr}"


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


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    if Config.RATE_LIMIT_ENABLED and not limiter.allow(_client_key())[0]:
        return jsonify({"message": "Too many requests. Try again later."}), 429

    username = sanitize_string(data.get("username", "")).strip()
    email = (sanitize_string(data.get("email", "")) or "").strip().lower()
    password = data.get("password", "") or ""
    full_name = sanitize_string(data.get("full_name", ""), 120).strip()

    if not username or not email or not password:
        return jsonify({"message": "Username, email and password are required."}), 400
    if not EMAIL_RE.match(email):
        return jsonify({"message": "Please provide a valid email address."}), 400
    pw_error = _validate_password(password)
    if pw_error:
        return jsonify({"message": pw_error}), 400
    if User.query.filter((User.email == email) | (User.username == username)).first():
        return jsonify({"message": "Username or email is already registered."}), 409

    user = User(
        username=username,
        email=email,
        full_name=full_name,
        password_hash=generate_password_hash(password),
        is_verified=True,
    )
    db.session.add(user)
    db.session.flush()
    db.session.add(Log(user_id=user.id, action="register", details=f"New user {username}",
                       ip_address=request.remote_addr))
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({"message": "Registration successful.", "token": token, "user": user.to_dict()}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    if Config.RATE_LIMIT_ENABLED and not limiter.allow(_client_key())[0]:
        return jsonify({"message": "Too many requests. Try again later."}), 429

    identifier = sanitize_string(data.get("identifier", "")).strip().lower()
    password = data.get("password", "") or ""
    if not identifier or not password:
        return jsonify({"message": "Email/username and password are required."}), 400

    user = User.query.filter((User.email == identifier) | (User.username == identifier)).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"message": "Invalid credentials."}), 401

    user.last_login = datetime.now(timezone.utc)
    db.session.add(Log(user_id=user.id, action="login", details="Successful login",
                       ip_address=request.remote_addr))
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({"message": "Login successful.", "token": token, "user": user.to_dict()})


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (sanitize_string(data.get("email", "")) or "").strip().lower()
    if not EMAIL_RE.match(email):
        return jsonify({"message": "Please provide a valid email address."}), 400

    user = User.query.filter_by(email=email).first()
    if user:
        token = generate_reset_token()
        # In production: email the token via your mail provider.
        # We return it in the response for demo purposes only.
        db.session.add(Log(user_id=user.id, action="forgot_password",
                           details="Password reset requested", ip_address=request.remote_addr))
        db.session.commit()
        return jsonify({"message": "Reset link generated.", "reset_token": token}), 200
    return jsonify({"message": "If that email exists, a reset link was sent."}), 200


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or {}
    email = (sanitize_string(data.get("email", "")) or "").strip().lower()
    new_password = data.get("new_password", "") or ""
    pw_error = _validate_password(new_password)
    if pw_error:
        return jsonify({"message": pw_error}), 400
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"message": "User not found."}), 404
    user.password_hash = generate_password_hash(new_password)
    db.session.add(Log(user_id=user.id, action="reset_password", details="Password reset",
                       ip_address=request.remote_addr))
    db.session.commit()
    return jsonify({"message": "Password updated. You can log in now."})


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return jsonify({"message": "User not found."}), 404
    return jsonify({"user": user.to_dict()})


@auth_bp.route("/profile", methods=["PUT"])
@jwt_required()
def update_profile():
    user = db.session.get(User, int(get_jwt_identity()))
    data = request.get_json(silent=True) or {}
    if not user:
        return jsonify({"message": "User not found."}), 404
    if "full_name" in data:
        user.full_name = sanitize_string(data["full_name"], 120)
    db.session.commit()
    return jsonify({"user": user.to_dict()})


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
    return jsonify({"message": "Password changed successfully."})
