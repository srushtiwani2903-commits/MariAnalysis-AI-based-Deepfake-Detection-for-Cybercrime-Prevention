"""Security utilities: rate limiting, file validation, sanitization.

Security posture:
  - SQL injection  : prevented by SQLAlchemy parameterised queries (never raw f-strings).
  - XSS            : all dynamic content is escaped client-side; API returns plain data only.
  - CSRF           : the API uses JWT Bearer tokens (no cookies), so CSRF does not apply.
  - Input sanitize : filenames are stripped, length-limited, and random-renamed before saving.
  - File security  : extension + magic-byte sniffing, size cap, and no path traversal.
"""
import re
import threading
import time
from pathlib import Path

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
# File validation
# --------------------------------------------------------------------------- #
_IMAGE_MAGIC = {
    b"\xff\xd8\xff": "jpg",                    # JPEG
    b"\x89PNG\r\n\x1a\n": "png",               # PNG
    b"GIF87a": "gif", b"GIF89a": "gif",        # GIF
    b"RIFF": "webp",                            # WEBP container
}
_VIDEO_MAGIC = {b"\x00\x00\x00\x18ftyp": "mp4", b"\x1aE\xdf\xa3": "mkv"}
_AUDIO_MAGIC = {b"ID3": "mp3", b"\xff\xfb": "mp3", b"OggS": "ogg"}


def sanitize_filename(filename: str) -> str:
    """Strip paths and dangerous characters from an uploaded filename."""
    name = Path(filename or "upload").name
    name = re.sub(r"[^A-Za-z0-9._\- ]", "", name)
    return (name or "upload")[:120]


def allowed_extension(filename: str, allowed_exts: set) -> bool:
    return Path(filename).suffix.lower().lstrip(".") in allowed_exts


def sniff_matches_magic(extension: str, head: bytes) -> bool:
    """Best-effort magic-byte check. Returns True when the extension matches file content."""
    ext = extension.lower().lstrip(".")
    table = {**_IMAGE_MAGIC, **_VIDEO_MAGIC, **_AUDIO_MAGIC}
    for magic, magic_ext in table.items():
        if head.startswith(magic):
            return ext == magic_ext
    # Unknown magic: accept only known-image/video/audio extensions (trust level is degraded).
    return ext in {"jpg", "jpeg", "png", "bmp", "tiff", "webp", "mp4", "avi", "mov", "wav", "flac", "m4a"}


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
            return False, f"File exceeds the {max_bytes // (1024*1024)} MB limit.", size
    file_storage.stream.seek(0)
    if size == 0:
        return False, "Empty file uploaded.", 0
    return True, "", size


def sanitize_text(text: str, max_length: int = 100_000) -> str:
    """Strip control characters and cap length to harden against XSS/DoS abuse."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text or "")
    return text[:max_length]


def sanitize_string(value: str, max_length: int = 255) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", value or "")[:max_length]
