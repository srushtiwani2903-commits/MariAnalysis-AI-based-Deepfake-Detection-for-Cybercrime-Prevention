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

    # --- AI Model ---
    # When MODEL_ENABLED=false the app uses smart heuristic "dummy" predictions
    # so the whole pipeline works without a trained model.
    MODEL_ENABLED = os.environ.get("MODEL_ENABLED", "false").lower() == "true"
    MODEL_PATH = os.environ.get("MODEL_PATH", os.path.join(BASE_DIR, "models", "weights"))
    HF_MODEL_NAME = os.environ.get("HF_MODEL_NAME", "roberta-base-openai-detector")

    # --- CORS ---
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")

    # --- Security ---
    RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", 60))
    RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", 60))

    # --- Admin bootstrap ---
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@deepguard.local")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@12345")


# Folder setup (run once at import time)
for folder in (Config.UPLOAD_FOLDER, Config.REPORT_FOLDER):
    os.makedirs(folder, exist_ok=True)
