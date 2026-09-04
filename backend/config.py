"""Application configuration.

Secrets (SECRET_KEY, JWT_SECRET_KEY, ADMIN_PASSWORD, API keys, Kaggle/Gemini/
MSG91/SMTP credentials) live in an encrypted vault file
(security/secrets.vault) guarded by a master key, never in this file or .env
in plaintext. Non-secret values can still be overridden with environment
variables.
"""
import os
from datetime import timedelta
from dotenv import load_dotenv

from security.vault import ensure_seeded, get_secret

load_dotenv()

# Make sure every secret exists in the encrypted vault before Config reads it.
ensure_seeded()


class Config:
    # --- Flask core ---
    # Auto-generated and stored encrypted; never a hardcoded default.
    SECRET_KEY = get_secret("SECRET_KEY") or os.urandom(32).hex()
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    # --- JWT Authentication ---
    JWT_SECRET_KEY = get_secret("JWT_SECRET_KEY") or SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.environ.get("JWT_EXPIRES_HOURS", 2)))
    JWT_REMEMBER_ME_EXPIRES = timedelta(days=int(os.environ.get("JWT_REMEMBER_ME_DAYS", 30)))
    JWT_ERROR_MESSAGE_KEY = "message"
    # Web sessions ride in an HttpOnly, Secure, SameSite cookie so the token is
    # never readable from JS/localStorage. The Authorization header stays
    # enabled for API/curl clients.
    JWT_TOKEN_LOCATION = ["cookies", "headers"]
    JWT_COOKIE_SECURE = os.environ.get("JWT_COOKIE_SECURE", "true").lower() == "true"
    JWT_COOKIE_HTTPONLY = True
    JWT_COOKIE_SAMESITE = os.environ.get("JWT_COOKIE_SAMESITE", "Strict")
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_CSRF_IN_COOKIES = True
    JWT_ACCESS_COOKIE_NAME = "deepguard_session"
    JWT_ACCESS_CSRF_COOKIE_NAME = "deepguard_csrf"
    JWT_CSRF_HEADER_NAME = "X-CSRF-TOKEN"
    # Single active-session enforcement: after this many minutes without an
    # authenticated request the session is treated as stale and invalidated.
    # 0 disables the inactivity timeout (JWT expiry still applies).
    SESSION_INACTIVITY_MINUTES = int(os.environ.get("SESSION_INACTIVITY_MINUTES", 1440))

    # --- Database ---
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(os.path.dirname(__file__), "deepfake.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- File storage ---
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, os.environ.get("UPLOAD_FOLDER", "uploads"))
    REPORT_FOLDER = os.path.join(BASE_DIR, os.environ.get("REPORT_FOLDER", "reports"))
    HEATMAP_FOLDER = os.path.join(BASE_DIR, os.environ.get("HEATMAP_FOLDER", "reports/heatmaps"))
    # Uploaded media is kept for forensic re-download, then auto-purged.
    UPLOAD_RETENTION_DAYS = int(os.environ.get("UPLOAD_RETENTION_DAYS", 7))

    # Per-media-type upload caps: image 1 GB, video 20 GB, text 20 GB, audio 10 GB.
    IMAGE_MAX_MB = int(os.environ.get("IMAGE_MAX_MB", 1024))
    VIDEO_MAX_MB = int(os.environ.get("VIDEO_MAX_MB", 20480))
    TEXT_MAX_MB = int(os.environ.get("TEXT_MAX_MB", 20480))
    AUDIO_MAX_MB = int(os.environ.get("AUDIO_MAX_MB", 10240))
    MAX_IMAGE_BYTES = IMAGE_MAX_MB * 1024 * 1024
    MAX_VIDEO_BYTES = VIDEO_MAX_MB * 1024 * 1024
    MAX_TEXT_BYTES = TEXT_MAX_MB * 1024 * 1024
    MAX_AUDIO_BYTES = AUDIO_MAX_MB * 1024 * 1024
    # Flask's MAX_CONTENT_LENGTH is the hard global cap on the request body;
    # it must be at least the largest per-media-type limit.
    MAX_CONTENT_LENGTH = max(
        MAX_IMAGE_BYTES, MAX_VIDEO_BYTES, MAX_TEXT_BYTES, MAX_AUDIO_BYTES)
    ALLOWED_IMAGE = {
        "png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif",
        "gif", "avif", "heic", "heif", "ico", "svg",
        "tga", "jfif", "raw", "cr2", "nef", "arw", "dng",
        "psd", "eps",
    }
    ALLOWED_VIDEO = {
        "mp4", "avi", "mov", "mkv", "webm",
        "3gp", "3g2", "mpeg", "mpg", "m4v", "ogv",
        "flv", "wmv", "asf", "ts", "vob", "mts", "m2ts",
    }
    ALLOWED_AUDIO = {
        "mp3", "wav", "ogg", "flac", "m4a",
        "aac", "opus", "wma", "aiff", "alac", "amr",
        "mid", "midi", "pcm", "ape",
    }

    # --- AI Engine ---
    # Heuristics run by default with no model weights. Set MODEL_ENABLED=true
    # and drop a checkpoint trained by ml/train_cnn_kaggle.py into models/ to
    # blend a real PyTorch CNN into every image verdict.
    MODEL_ENABLED = os.environ.get("MODEL_ENABLED", "false").lower() == "true"
    MODEL_DIR = os.path.join(BASE_DIR, "models")
    IMAGE_CNN_PATH = os.environ.get(
        "IMAGE_CNN_PATH", os.path.join(MODEL_DIR, "faces_real_vs_fake_cnn.pt"))
    # How much of the final image base score comes from the trained CNN
    # (0..1; the rest stays with the explainable heuristic engines).
    IMAGE_CNN_WEIGHT = float(os.environ.get("IMAGE_CNN_WEIGHT", "0.45"))

    # Kaggle credentials live in the encrypted vault; only the (optional)
    # pointer to a kaggle.json file stays in the environment. Datasets are
    # pulled into a temp cache that is auto-deleted after use.
    KAGGLE_USERNAME = get_secret("KAGGLE_USERNAME") or os.environ.get("KAGGLE_USERNAME", "")
    KAGGLE_KEY = get_secret("KAGGLE_KEY") or os.environ.get("KAGGLE_KEY", "")
    KAGGLE_JSON_PATH = os.environ.get("KAGGLE_JSON_PATH", "")
    KAGGLE_AUTOSYNC = os.environ.get("KAGGLE_AUTOSYNC", "false").lower() == "true"
    KAGGLE_FORCE = os.environ.get("KAGGLE_FORCE", "false").lower() == "true"
    # Reference comparison: a small real+fake sample is pulled from Kaggle
    # once, per-class feature stats are built in-process, and later scans are
    # scored against them. Disable with KAGGLE_REFERENCE_ENABLED=false.
    KAGGLE_REFERENCE_ENABLED = os.environ.get("KAGGLE_REFERENCE_ENABLED", "true").lower() == "true"
    KAGGLE_REFERENCE_SAMPLE_SIZE = int(os.environ.get("KAGGLE_REFERENCE_SAMPLE_SIZE", 10))

    # --- Real AI model providers (Hybrid engine) ---
    # Gemini (Google AI Studio free key, https://aistudio.google.com/app/apikey):
    # one multimodal API that scans images, sampled video frames, audio and text.
    # Free tier: gemini-2.5-flash ~250 req/day, gemini-2.5-flash-lite ~1000 req/day.
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
    GEMINI_TIMEOUT_SECONDS = int(os.environ.get("GEMINI_TIMEOUT_SECONDS", 20))
    # Local Hugging Face transformers (offline image + text) - free & unlimited.
    LOCAL_MODELS_ENABLED = os.environ.get("LOCAL_MODELS_ENABLED", "true").lower() == "true"
    # Blend weights for the final verdict. Unavailable providers are dropped and
    # the remaining weights re-normalised, so heuristics stay as the fallback.
    AI_BLEND_HEURISTIC = float(os.environ.get("AI_BLEND_HEURISTIC", 0.35))
    AI_BLEND_GEMINI = float(os.environ.get("AI_BLEND_GEMINI", 0.40))
    AI_BLEND_LOCAL = float(os.environ.get("AI_BLEND_LOCAL", 0.25))

    # --- Cloud model training (Kaggle GPU notebooks) ---
    # Training runs entirely on Kaggle's cloud: the app pushes a notebook,
    # Kaggle mounts the dataset on its own machine, and only the trained
    # weights are pulled back into models/<media>/. The datasets themselves
    # are never downloaded into the project.
    MODEL_WEIGHTS_FOLDER = os.path.join(BASE_DIR, "models")
    KAGGLE_TRAIN_POLL_SECONDS = int(os.environ.get("KAGGLE_TRAIN_POLL_SECONDS", 45))
    KAGGLE_TRAIN_MAX_HOURS = int(os.environ.get("KAGGLE_TRAIN_MAX_HOURS", 6))

    # --- CORS ---
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")

    # --- Security ---
    RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", 60))
    RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", 60))

    # API keys are stored as a SHA-256 hash (for lookup) plus a Fernet-encrypted
    # blob, so a leaked database still doesn't expose the keys. The encryption
    # secret itself lives in the vault.
    API_KEY_ENCRYPTION_SECRET = (get_secret("API_KEY_ENCRYPTION_SECRET")
                                 or os.environ.get("API_KEY_ENCRYPTION_SECRET", "")
                                 or SECRET_KEY)

    # --- Intrusion Detection & Prevention (fail2ban-style) ---
    IDPS_ENABLED = os.environ.get("IDPS_ENABLED", "true").lower() == "true"
    IDPS_MAX_FAILED_ATTEMPTS = int(os.environ.get("IDPS_MAX_FAILED_ATTEMPTS", 5))
    IDPS_WINDOW_SECONDS = int(os.environ.get("IDPS_WINDOW_SECONDS", 600))
    IDPS_BAN_SECONDS = int(os.environ.get("IDPS_BAN_SECONDS", 900))

    # --- Admin bootstrap ---
    # The password comes from the encrypted vault (auto-generated if the
    # ADMIN_PASSWORD env var was never provided on first boot).
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@marianalysis.local")
    ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "")

    # --- E-mail (password reset links) ---
    # MAIL_ENABLED=false -> links are logged to security/logs/reset_links.log
    # so local/dev builds still work without an SMTP account.
    MAIL_ENABLED = os.environ.get("MAIL_ENABLED", "false").lower() == "true"
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = get_secret("SMTP_PASSWORD") or os.environ.get("SMTP_PASSWORD", "")
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

    # --- AI assistant (Gemini) ---
    # GEMINI_API_KEY lives in the encrypted vault. Without a key the chatbot
    # falls back to the built-in rule-based replies.
    GEMINI_API_KEY = get_secret("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_TIMEOUT_SECONDS = int(os.environ.get("GEMINI_TIMEOUT_SECONDS", 25))
    GEMINI_MAX_OUTPUT_TOKENS = int(os.environ.get("GEMINI_MAX_OUTPUT_TOKENS", 1024))

    # --- MSG91 SMS (India) ---
    MSG91_AUTHKEY = get_secret("MSG91_AUTHKEY") or os.environ.get("MSG91_AUTHKEY", "")
    MSG91_SENDER_ID = os.environ.get("MSG91_SENDER_ID", "MARIIN")
    MSG91_TEMPLATE_ID = os.environ.get("MSG91_TEMPLATE_ID", "")
    MSG91_COUNTRY_CODE = os.environ.get("MSG91_COUNTRY_CODE", "91")
    SMS_ENABLED = bool(MSG91_AUTHKEY and MSG91_TEMPLATE_ID)


# Folder setup (run once at import time)
for folder in (Config.UPLOAD_FOLDER, Config.REPORT_FOLDER, Config.HEATMAP_FOLDER, Config.MODEL_DIR):
    os.makedirs(folder, exist_ok=True)
