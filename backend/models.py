"""Database models: Users, ScanHistory, Reports, Logs, AIPredictions."""
from datetime import datetime, timezone

from extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), default="")
    is_admin = db.Column(db.Boolean, default=False)
    is_verified = db.Column(db.Boolean, default=False)
    phone = db.Column(db.String(24), unique=True, nullable=True, index=True)
    phone_verified = db.Column(db.Boolean, default=False)
    otp_code = db.Column(db.String(128), nullable=True)
    otp_expires = db.Column(db.DateTime, nullable=True)
    otp_attempts = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    reset_token = db.Column(db.String(128), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)

    scans = db.relationship("ScanHistory", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    reports = db.relationship("Report", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    sessions = db.relationship("ActiveSession", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "is_admin": self.is_admin,
            "is_verified": self.is_verified,
            "phone": self.phone,
            "phone_verified": self.phone_verified,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "scan_count": self.scans.count(),
        }


class ActiveSession(db.Model):
    """One row per logged-in session (JWT jti). Used to detect duplicate logins
    and to revoke sessions on logout."""
    __tablename__ = "active_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    jti = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=utcnow)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    ip_address = db.Column(db.String(64), default="")


class ScanHistory(db.Model):
    __tablename__ = "scan_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    scan_type = db.Column(db.String(20), nullable=False, index=True)  # image | video | audio | text
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), default="")
    file_path = db.Column(db.String(500))
    file_size = db.Column(db.Integer, default=0)

    result = db.Column(db.String(20), nullable=False)       # authentic | fake | inconclusive
    confidence = db.Column(db.Float, default=0.0)           # 0-100 confidence in result
    fake_probability = db.Column(db.Float, default=0.0)     # 0-100 AI/fake probability
    risk_level = db.Column(db.String(20), default="low")    # low | medium | high | critical
    explanation = db.Column(db.Text, default="")
    recommendations = db.Column(db.Text, default="")
    suspicious_sections = db.Column(db.JSON, default=list)  # text highlights / timestamps

    processing_time_ms = db.Column(db.Integer, default=0)
    scan_metadata = db.Column(db.JSON, default=dict)        # extracted metadata (EXIF etc.)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    prediction = db.relationship("AIPrediction", backref="scan", uselist=False, cascade="all, delete-orphan")
    report = db.relationship("Report", backref="scan", uselist=False, cascade="all, delete-orphan")

    def to_dict(self, include_full=False):
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "scan_type": self.scan_type,
            "filename": self.original_filename or self.filename,
            "file_size": self.file_size,
            "result": self.result,
            "confidence": self.confidence,
            "fake_probability": self.fake_probability,
            "risk_level": self.risk_level,
            "processing_time_ms": self.processing_time_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_full:
            data.update({
                "explanation": self.explanation,
                "recommendations": self.recommendations,
                "suspicious_sections": self.suspicious_sections or [],
                "scan_metadata": self.scan_metadata or {},
                "model": self.prediction.to_dict() if self.prediction else None,
            })
        return data


class AIPrediction(db.Model):
    __tablename__ = "ai_predictions"

    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.Integer, db.ForeignKey("scan_history.id"), nullable=False, unique=True)
    model_name = db.Column(db.String(120), default="heuristic-ensemble-v1")
    model_version = db.Column(db.String(40), default="1.0.0")
    prediction = db.Column(db.String(20))
    confidence = db.Column(db.Float)
    features = db.Column(db.JSON, default=dict)  # feature importances for XAI
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "prediction": self.prediction,
            "confidence": self.confidence,
            "features": self.features or {},
        }


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.Integer, db.ForeignKey("scan_history.id"), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    format = db.Column(db.String(10), default="pdf")   # pdf | csv
    file_path = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "scan_id": self.scan_id,
            "format": self.format,
            "file_path": self.file_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Log(db.Model):
    __tablename__ = "logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text, default="")
    ip_address = db.Column(db.String(64), default="")
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
