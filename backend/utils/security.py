"""Security utilities: rate limiting, file validation, sanitization.

Queries use SQLAlchemy parameters (no raw f-strings), the API is JWT-only so
CSRF doesn't apply, dynamic content is escaped client-side, and uploads are
sanitised, size-capped and checked against magic bytes.
"""
import base64
import hashlib
import re
import threading
import time
from pathlib import Path

from cryptography.fernet import Fernet

from config import Config

# --------------------------------------------------------------------------- #
# Rate limiting (in-memory sliding window per client key)
# --------------------------------------------------------------------------- #
class RateLimiter:
    """Simple thread-safe sliding-window rate limiter."""

    def __init__(self, max_requests=60, window_seconds=60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits = {}          # key -> list[timestamps]
        self._lock = threading.Lock()

    def allow(self, key):
        """Returns (allowed: bool, retry_after_seconds: int)."""
        now = time.time()
        with self._lock:
            stamps = [t for t in self._hits.get(key, []) if now - t < self.window_seconds]
            if len(stamps) >= self.max_requests:
                self._hits[key] = stamps
                retry = int(self.window_seconds - (now - stamps[0]))
                return False, max(1, retry)
            stamps.append(now)
            self._hits[key] = stamps
            return True, 0


limiter = RateLimiter()

# --------------------------------------------------------------------------- #
# API key protection: hash (lookup/verification) + encryption (at rest)
# --------------------------------------------------------------------------- #
def _api_key_fernet() -> Fernet:
    """Deterministic Fernet instance derived from Config.API_KEY_ENCRYPTION_SECRET."""
    raw = (Config.API_KEY_ENCRYPTION_SECRET or Config.SECRET_KEY or "insecure").encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def hash_api_key(plaintext: str) -> str:
    """SHA-256 digest used for fast lookups / verification (never reversible)."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def encrypt_api_key(plaintext: str) -> str:
    """Fernet-encrypt the plaintext key so it is unreadable at rest."""
    return _api_key_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_api_key(ciphertext: str) -> str:
    """Decrypt a stored ciphertext back to the plaintext key (master-secret only)."""
    return _api_key_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")


def encrypt_secret(plaintext: str) -> str:
    """Fernet-encrypt any confidential value at rest (same key domain as API keys)."""
    return encrypt_api_key(plaintext)


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a confidential value stored with encrypt_secret()."""
    return decrypt_api_key(ciphertext)


def is_encrypted(ciphertext: str) -> bool:
    """True if a stored value looks like a Fernet token (encrypt_secret/encrypt_api_key)."""
    return bool(ciphertext) and ciphertext.startswith("gAAAAA")

# --------------------------------------------------------------------------- #
# File validation
# --------------------------------------------------------------------------- #
_IMAGE_MAGIC = {
    b"\xff\xd8\xff": "jpg",                    # JPEG / JFIF / EXIF
    b"\x89PNG\r\n\x1a\n": "png",               # PNG
    b"GIF87a": "gif", b"GIF89a": "gif",        # GIF
}


def sanitize_filename(filename: str) -> str:
    """Strip paths and dangerous characters from an uploaded filename."""
    name = Path(filename or "upload").name
    name = re.sub(r"[^A-Za-z0-9._\- ]", "", name)
    return (name or "upload")[:120]


def allowed_extension(filename: str, allowed_exts: set) -> bool:
    return Path(filename).suffix.lower().lstrip(".") in allowed_exts


def sniff_matches_magic(extension: str, head: bytes) -> bool:
    """Best-effort magic-byte check. Returns True when the extension matches file content."""
    ext = Path(extension).suffix.lower().lstrip(".") or extension.lower().lstrip(".")
    if len(head) < 4:
        return True  # too short to validate — trust extension

    # RIFF wraps WEBP (image), WAVE (audio) and AVI (video); bytes 8:12 tell them apart.
    if head[:4] == b"RIFF":
        kind = head[8:12]
        if kind == b"WEBP":
            return ext in {"webp", "jfif"}
        if kind == b"WAVE":
            return ext in {"wav", "pcm"}
        if kind == b"AVI ":
            return ext == "avi"
        return ext in {"webp", "wav", "avi", "pcm", "jfif"}

    # ID3 tag → MP3
    if head[:3] == b"ID3":
        return ext in {"mp3", "mp2"}

    # MPEG audio frame sync word (0xFF + byte with top 3 bits set)
    if head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        layer = (head[1] >> 2) & 0x03
        if layer == 0:
            # Layer 0 = AAC (ADTS)
            return ext in {"aac", "m4a"}
        # Layer I/II/III = MP3/MP2
        return ext in {"mp3", "mp2"}

    if head[:4] == b"OggS":
        return ext in {"ogg", "opus"}
    if head[:4] == b"fLaC":
        return ext in {"flac", "alac"}
    # AIFF: 'FORM' + size + 'AIFF' or 'AIFC'
    if head[:4] == b"FORM" and head[8:12] in {b"AIFF", b"AIFC"}:
        return ext in {"aiff", "aif"}
    # MIDI: 'MThd'
    if head[:4] == b"MThd":
        return ext in {"mid", "midi"}
    # AMR: '#!AMR\n'
    if head[:6] == b"#!AMR\n":
        return ext == "amr"

    # ISO BMFF ('ftyp') — shared by MP4, MOV, M4A, 3GP, AVIF, HEIC, HEIF
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        # M4A audio
        if brand in {b"M4A ", b"m4a ", b"M4B ", b"M4P "}:
            return ext == "m4a"
        if ext == "m4a":
            return True
        # QuickTime / MOV
        if brand in {b"qt  ", b"M4V ", b"mpg1"}:
            return ext in {"mp4", "m4v", "mov"}
        # 3GP family
        if brand[:3] == b"3g":
            return ext in {"3gp", "3g2"}
        # AVIF image brands
        if brand in {b"avif", b"avis"}:
            return ext in {"avif", "heic", "heif"}
        # HEIF / HEIC image brands
        if brand in {b"heic", b"heix", b"heim", b"heis", b"mif1", b"msf1"}:
            return ext in {"heic", "heif", "avif"}
        # Generic ISOBMFF container (mp4 family)
        return ext in {"mp4", "m4v", "mov", "3gp", "3g2"}

    # ICO: reserved=0, type=1 (icon) or type=2 (cursor)
    # Must check before MPEG-PS because \x00\x00\x01\x00 starts with \x00\x00\x01.
    if len(head) >= 4 and head[0] == 0 and head[1] == 0 and head[2] in (1, 2) and head[3] == 0:
        return ext == "ico"

    # MPEG-PS start codes (0x000001BA = pack header, 0x000001B3 = sequence header)
    if head[:3] == b"\x00\x00\x01":
        return ext in {"mpeg", "mpg", "ts", "mts", "m2ts", "vob", "mpg2"}

    # Matroska / WebM share the EBML magic.
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return ext in {"mkv", "webm"}

    # FLV: 'FLV\x01'
    if head[:4] == b"FLV\x01":
        return ext in {"flv", "swf"}

    # ASF header GUID (ASF/WMA/WMV)
    if head[:16] == b"\x30\x26\xb2\x75\x8e\x66\xcf\x11\xa6\xd9\x00\xaa\x00\x62\xce\x6c":
        return ext in {"asf", "wmv", "wma"}

    # Image magic bytes.
    for magic, magic_ext in _IMAGE_MAGIC.items():
        if head.startswith(magic):
            # JPEG magic is shared by JFIF
            if magic_ext == "jpg":
                return ext in {"jpg", "jpeg", "jfif"}
            return ext == magic_ext

    # BMP: 'BM'
    if head[:2] == b"BM":
        return ext in {"bmp", "dib"}
    # TIFF: 'II' (little-endian) or 'MM' (big-endian) + magic 42
    if head[:2] in {b"II", b"MM"}:
        return ext in {"tiff", "tif", "dng", "cr2", "nef", "arw", "raw"}
    # PSD: '8BPS'
    if head[:4] == b"8BPS":
        return ext == "psd"

    # Unknown magic: fall back to the known extension list (degraded trust).
    return ext in {
        "jpg", "jpeg", "jfif", "png", "bmp", "dib", "tiff", "tif", "webp",
        "gif", "avif", "heic", "heif", "ico", "tga", "raw", "cr2", "nef",
        "arw", "dng", "psd", "eps", "svg",
        "mp4", "avi", "mov", "mkv", "webm", "3gp", "3g2", "mpeg", "mpg",
        "m4v", "ogv", "flv", "wmv", "asf", "ts", "vob", "mts", "m2ts", "swf",
        "wav", "ogg", "flac", "m4a", "aac", "opus", "wma", "aiff", "aif",
        "alac", "amr", "mid", "midi", "pcm", "ape", "mp3", "mp2",
    }


def format_limit(max_bytes: int) -> str:
    """Format a byte cap as '1 GB' / '500 MB' for user-facing messages."""
    gb = max_bytes / (1024 ** 3)
    if gb >= 1:
        return f"{int(gb)} GB" if gb == int(gb) else f"{gb:.1f} GB"
    return f"{max_bytes // (1024 * 1024)} MB"


def validate_upload(file_storage, allowed_exts: set, max_bytes: int):
    """Validate an uploaded file. Returns (ok, error_message, size_bytes)."""
    if not file_storage or not file_storage.filename:
        return False, "No file provided.", 0

    filename = sanitize_filename(file_storage.filename)
    if not allowed_extension(filename, allowed_exts):
        return False, f"File type not allowed. Allowed: {', '.join(sorted(allowed_exts))}.", 0

    size = 0
    head = b""
    file_storage.stream.seek(0)
    while True:
        chunk = file_storage.stream.read(1024 * 1024)
        if not chunk:
            break
        if size == 0:
            head = chunk[:16]
        size += len(chunk)
        if size > max_bytes:
            file_storage.stream.seek(0)
            limit = format_limit(max_bytes)
            return False, f"File exceeds the {limit} limit. Not more than {limit} will accept.", size
    file_storage.stream.seek(0)
    if size == 0:
        return False, "Empty file uploaded.", 0

    # Reject files whose content doesn't match the extension (magic bytes).
    if head and not sniff_matches_magic(filename, head):
        return False, "File content does not match its extension.", size
    return True, "", size


def sanitize_text(text: str, max_length: int = 100_000) -> str:
    """Strip control characters and cap length to harden against XSS/DoS abuse."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text or "")
    return text[:max_length]


def sanitize_string(value: str, max_length: int = 255) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", value or "")[:max_length]
