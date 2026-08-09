"""IDPS: fail2ban-style intrusion detection and prevention.

Tracks failed logins per IP with a sliding window and temporarily bans IPs
that pass the threshold. Events go to the logs table and an append-only
security/logs/intrusions.jsonl so incidents survive restarts. Also exposes the
audit helper for every create/update/delete. All state is lock-guarded.
"""
import json
import logging
import os
import threading
import time

from config import Config

logger = logging.getLogger("idps")

# --------------------------------------------------------------------------- #
# State (in-memory + disk). Locked so concurrent requests are safe.
# --------------------------------------------------------------------------- #
_failures = {}     # ip -> list[epoch timestamps]
_bans = {}         # ip -> ban_until_epoch
_lock = threading.Lock()

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG_DIR = os.path.join(os.path.dirname(_BASE_DIR), "security", "logs")
_INT_LOG = os.path.join(_LOG_DIR, "intrusions.jsonl")
_AUDIT_LOG = os.path.join(_LOG_DIR, "audit.jsonl")


def _write_line(path, payload):
    """Append a JSON line to a log file (creates dir/file if missing)."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:  # never break the request path on logging errors
        logger.warning("IDPS: failed to write %s: %s", path, exc)


def _record(event, action, ip, details):
    """Persist an event to the DB logs table when available."""
    try:
        from extensions import db
        from models import Log
        db.session.add(Log(user_id=None, action=action, details=details,
                           ip_address=ip or ""))
        db.session.commit()
    except Exception:
        db.session.rollback()
    _write_line(_INT_LOG, {"ts": time.time(), "event": event, "ip": ip,
                           "action": action, "details": details})


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def is_banned(ip: str) -> bool:
    """True while the IP is under an active ban."""
    ip = ip or ""
    now = time.time()
    with _lock:
        until = _bans.get(ip, 0)
        if until > now:
            return True
        if until:                       # expired ban -> forget it
            _bans.pop(ip, None)
    return False


def ban_remaining_seconds(ip: str) -> int:
    ip = ip or ""
    with _lock:
        until = _bans.get(ip, 0)
    return max(0, int(until - time.time())) if until else 0


def record_failure(ip: str, identifier: str) -> int:
    """Register a failed login attempt. Returns the failure count (1-based)."""
    ip = ip or ""
    now = time.time()
    with _lock:
        stamps = [t for t in _failures.get(ip, []) if now - t < Config.IDPS_WINDOW_SECONDS]
        stamps.append(now)
        _failures[ip] = stamps
        count = len(stamps)
        if count >= Config.IDPS_MAX_FAILED_ATTEMPTS:
            until = now + Config.IDPS_BAN_SECONDS
            _bans[ip] = until
            _failures[ip] = []
            _record("ban", "idps_ip_banned", ip,
                    f"IP banned for {Config.IDPS_BAN_SECONDS}s after "
                    f"{count} failed login attempts (user='{identifier}')")
    return count


def record_success(ip: str):
    """Reset failure state after a successful login."""
    ip = ip or ""
    with _lock:
        _failures.pop(ip, None)
        _bans.pop(ip, None)


def audit(action: str, actor: str, target: str, entity: str, ip: str,
          summary: str = ""):
    """Audit trail for every data write (create/update/delete).

    action: "create" | "update" | "delete" | "register" | "login" | ...
    actor:  user id / username or "system"
    target: e.g. "ScanHistory", "Report", "User"
    entity: the row id or identifier that changed
    """
    payload = {"ts": time.time(), "action": action, "actor": actor,
               "target": target, "entity": entity, "ip": ip or "",
               "summary": summary}
    try:
        from extensions import db
        from models import Log
        db.session.add(Log(user_id=None, action=f"data_{action}",
                           details=f"{target} [{entity}] {summary}".strip(),
                           ip_address=ip or ""))
        db.session.commit()
    except Exception:
        db.session.rollback()
    _write_line(_AUDIT_LOG, payload)
