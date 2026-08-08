"""Application configuration. All values can be overridden with environment variables."""
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    # --- Flask core ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    # --- JWT Authentication ---
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.environ.get("JWT_EXPIRES_HOURS", 2)))
    JWT_ERROR_MESSAGE_KEY = "message"

    # --- Database ---
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(os.path.dirname(__file__), "deepfake.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- File storage ---
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, os.environ.get("UPLOAD_FOLDER", "uploads"))
    REPORT_FOLDER = os.path.join(BASE_DIR, os.environ.get("REPORT_FOLDER", "reports"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", 50)) * 1024 * 1024
    ALLOWED_IMAGE = {"png", "jpg", "jpeg", "webp", "bmp", "tiff"}
    ALLOWED_VIDEO = {"mp4", "avi", "mov", "mkv", "webm"}
    ALLOWED_AUDIO = {"mp3", "wav", "ogg", "flac", "m4a"}

    # --- AI Engine ---
    # Heuristic-only: no model weights are used, predictions come from the
    # explainable heuristic engines in services/. Flag kept for API compat.
    MODEL_ENABLED = os.environ.get("MODEL_ENABLED", "false").lower() == "true"

    # --- Kaggle auto data pipeline ---
    # Credentials: KAGGLE_USERNAME + KAGGLE_KEY (or KAGGLE_JSON_PATH).
    # Datasets are fetched directly from Kaggle into a temp cache, extracted,
    # used, then the temp cache is auto-deleted - nothing is persisted. No
    # model training occurs anywhere in the app.
    KAGGLE_USERNAME = os.environ.get("KAGGLE_USERNAME", "")
    KAGGLE_KEY = os.environ.get("KAGGLE_KEY", "")
    KAGGLE_JSON_PATH = os.environ.get("KAGGLE_JSON_PATH", "")
    KAGGLE_AUTOSYNC = os.environ.get("KAGGLE_AUTOSYNC", "false").lower() == "true"
    KAGGLE_FORCE = os.environ.get("KAGGLE_FORCE", "false").lower() == "true"

    # --- CORS ---
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")

    # --- Security ---
    RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", 60))
    RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", 60))

    # --- Intrusion Detection & Prevention (fail2ban-style) ---
    IDPS_ENABLED = os.environ.get("IDPS_ENABLED", "true").lower() == "true"
    IDPS_MAX_FAILED_ATTEMPTS = int(os.environ.get("IDPS_MAX_FAILED_ATTEMPTS", 5))
    IDPS_WINDOW_SECONDS = int(os.environ.get("IDPS_WINDOW_SECONDS", 600))
    IDPS_BAN_SECONDS = int(os.environ.get("IDPS_BAN_SECONDS", 900))

    # --- Admin bootstrap ---
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@marianalysis.local")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@12345")

    # --- E-mail (password reset links) ---
    # MAIL_ENABLED=false -> links are logged to security/logs/reset_links.log
    # so local/dev builds still work without an SMTP account.
    MAIL_ENABLED = os.environ.get("MAIL_ENABLED", "false").lower() == "true"
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    MAIL_FROM = os.environ.get("MAIL_FROM", "MariAnalysis <no-reply@marianalysis.local>")
    MAIL_STARTTLS = os.environ.get("MAIL_STARTTLS", "true").lower() == "true"
    FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    RESET_TOKEN_TTL_HOURS = int(os.environ.get("RESET_TOKEN_TTL_HOURS", 1))

    # --- OTP verification (email + phone) ---
    # Phone OTPs go through MSG91 when MSG91_AUTHKEY is set, else they are
    # logged to security/logs/otp_phone.log and shown on screen via DEBUG_OTP.
    # Set DEBUG_OTP=false in production (real SMS enabled).
    OTP_TTL_SECONDS = int(os.environ.get("OTP_TTL_SECONDS", 600))
    OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", 5))
    DEBUG_OTP = os.environ.get("DEBUG_OTP", "true").lower() == "true"

    # --- MSG91 SMS (India) ---
    MSG91_AUTHKEY = os.environ.get("MSG91_AUTHKEY", "")
    MSG91_SENDER_ID = os.environ.get("MSG91_SENDER_ID", "MARIIN")
    MSG91_TEMPLATE_ID = os.environ.get("MSG91_TEMPLATE_ID", "")
    MSG91_COUNTRY_CODE = os.environ.get("MSG91_COUNTRY_CODE", "91")
    SMS_ENABLED = bool(MSG91_AUTHKEY and MSG91_TEMPLATE_ID)


# Folder setup (run once at import time)
for folder in (Config.UPLOAD_FOLDER, Config.REPORT_FOLDER):
    os.makedirs(folder, exist_ok=True)
