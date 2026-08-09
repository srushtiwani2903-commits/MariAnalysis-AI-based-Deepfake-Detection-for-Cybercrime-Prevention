"""Database models: Users, ScanHistory, Reports, Logs, AIPredictions,
EvidenceCases, BlockchainBlocks, ApiKeys."""
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
    """One row per logged-in session (JWT jti). Used to enforce the single
    active-session rule: a new login replaces every previous session, so old
    JWTs are rejected server-side the moment the row is deactivated."""
    __tablename__ = "active_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    jti = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=utcnow)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    ip_address = db.Column(db.String(64), default="")
    user_agent = db.Column(db.String(255), default="")
    # Why a session was deactivated: superseded (new login) | logout |
    # inactivity | expired. Drives the client-facing 401 message.
    revoked_reason = db.Column(db.String(32), nullable=True)


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
    trust_score = db.Column(db.Float, default=0.0)          # 0-100 evidence trust score
    file_hash = db.Column(db.String(64), default="")        # SHA-256 of the analyzed file
    models = db.Column(db.JSON, default=list)               # per-model ensemble verdicts
    reasons = db.Column(db.JSON, default=list)              # XAI checklist: {check, passed, detail}

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
                "trust_score": self.trust_score,
                "file_hash": self.file_hash,
                "models": self.models or [],
                "reasons": self.reasons or [],
                "case": EvidenceCase.query.filter_by(scan_id=self.id).first().to_dict()
                        if EvidenceCase.query.filter_by(scan_id=self.id).first() else None,
                "chain": BlockchainBlock.query.filter_by(scan_id=self.id).first().to_dict()
                         if BlockchainBlock.query.filter_by(scan_id=self.id).first() else None,
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


class EvidenceCase(db.Model):
    """Cybercrime reporting portal: one case per reported scan. Case IDs look
    like DF-2026-0001 and are immutable identifiers for law-enforcement follow-up."""
    __tablename__ = "evidence_cases"

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.String(40), unique=True, nullable=False, index=True)
    scan_id = db.Column(db.Integer, db.ForeignKey("scan_history.id"), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.String(20), default="open")      # open | reviewed | closed
    platform = db.Column(db.String(120), default="")
    notes = db.Column(db.Text, default="")
    report_hash = db.Column(db.String(64), default="")     # SHA-256 of the evidence report
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "case_id": self.case_id,
            "scan_id": self.scan_id,
            "status": self.status,
            "platform": self.platform,
            "notes": self.notes,
            "report_hash": self.report_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class BlockchainBlock(db.Model):
    """Simulated blockchain evidence ledger. Each analysed scan gets a block
    chained to the previous one via its SHA-256 hash, so reports can be
    verified against tampering (immutability is demonstrated, not enforced)."""
    __tablename__ = "blockchain_blocks"

    id = db.Column(db.Integer, primary_key=True)
    index = db.Column(db.Integer, unique=True, nullable=False)
    scan_id = db.Column(db.Integer, db.ForeignKey("scan_history.id"), nullable=True, unique=True)
    case_id = db.Column(db.String(40), nullable=True)
    file_hash = db.Column(db.String(64), default="")       # SHA-256 of analysed media
    report_hash = db.Column(db.String(64), default="")     # SHA-256 of generated report
    timestamp = db.Column(db.String(40), nullable=False)   # ISO-8601 UTC
    data = db.Column(db.JSON, default=dict)                # immutable summary payload
    prev_hash = db.Column(db.String(64), nullable=False)
    nonce = db.Column(db.Integer, default=0)
    hash = db.Column(db.String(64), nullable=False)

    def to_dict(self):
        return {
            "index": self.index,
            "scan_id": self.scan_id,
            "case_id": self.case_id,
            "file_hash": self.file_hash,
            "report_hash": self.report_hash,
            "timestamp": self.timestamp,
            "data": self.data or {},
            "prev_hash": self.prev_hash,
            "nonce": self.nonce,
            "hash": self.hash,
        }


class ApiKey(db.Model):
    """API keys for the browser-extension / external tooling. Only a SHA-256
    hash and a Fernet-encrypted blob of the key are stored; the plaintext is
    shown once at creation and is otherwise recoverable only with the server
    master secret (Config.API_KEY_ENCRYPTION_SECRET)."""
    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    label = db.Column(db.String(120), default="")
    key_hash = db.Column(db.String(64), unique=True, nullable=False)
    key_encrypted = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    last_used = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "label": self.label,
            "key_hash": self.key_hash[:16],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_used": self.last_used.isoformat() if self.last_used else None,
        }
