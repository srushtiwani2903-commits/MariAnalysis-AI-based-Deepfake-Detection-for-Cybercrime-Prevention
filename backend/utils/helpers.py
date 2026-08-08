"""Small shared helpers: timestamps, upload saving, id helpers."""
import os
import secrets
import uuid
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc)


def now_iso():
    return utcnow().isoformat()


def random_filename(original_name: str) -> str:
    """Generate a safe, unique stored filename while keeping the extension."""
    ext = os.path.splitext(original_name)[1].lower()
    return f"{uuid.uuid4().hex}{ext}"


def save_upload(file_storage, folder: str, original_name: str):
    """Persist an uploaded file to disk. Returns (stored_path, stored_name, size_bytes)."""
    stored_name = random_filename(original_name)
    stored_path = os.path.join(folder, stored_name)
    file_storage.stream.seek(0)
    file_storage.save(stored_path)
    size = os.path.getsize(stored_path)
    return stored_path, stored_name, size


def human_size(num_bytes: int) -> str:
    size = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


def generate_reset_token():
    return secrets.token_urlsafe(48)


def fetch_from_url(url: str, max_bytes: int = 50 * 1024 * 1024, timeout: int = 15):
    """Download a URL into a BytesIO, enforcing size + timeout + redirect limits.

    Returns (stream, size_bytes, content_type) or raises ValueError on failure.
    """
    import io
    import urllib.parse
    import urllib.request

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed.")
    if not parsed.hostname:
        raise ValueError("Invalid URL.")

    req = urllib.request.Request(
        url, headers={"User-Agent": "MariAnalysis/1.0", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get("Content-Type", "")
        total = 0
        buf = io.BytesIO()
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"Remote file exceeds the {max_bytes // (1024*1024)} MB limit.")
            buf.write(chunk)
        if total == 0:
            raise ValueError("Remote URL returned an empty response.")
        buf.seek(0)
        return buf, total, content_type
