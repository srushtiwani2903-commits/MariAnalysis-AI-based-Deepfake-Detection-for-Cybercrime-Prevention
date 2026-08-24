"""Encrypted secret vault for all confidential values.

Every secret (SECRET_KEY, JWT_SECRET_KEY, ADMIN_PASSWORD, API keys, SMTP/Kaggle
credentials) lives in ``secrets.vault`` instead of plaintext in ``.env`` or
``config.py``. Each entry stores:

  * ``s256``: SHA-256 hex of the plaintext (integrity / quick-lookup hash)
  * ``enc``:  Fernet token of the plaintext (symmetric encryption)

The vault file is useless without the master key. The master key comes from the
``SECRETS_MASTER_KEY`` environment variable or from ``master.key`` in this
folder (auto-generated on first run, never committed). Nothing in this module
imports ``config.py`` so config may safely import this module.
"""
import base64
import hashlib
import json
import os
import secrets as pysecrets

from cryptography.fernet import Fernet, InvalidToken

SECURITY_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_FILE = os.path.join(SECURITY_DIR, "secrets.vault")
MASTER_KEY_FILE = os.path.join(SECURITY_DIR, "master.key")
ADMIN_NOTE_FILE = os.path.join(SECURITY_DIR, "ADMIN_CREDENTIALS.txt")

# Core secrets that must always exist; auto-seeded with strong random values.
CORE_SECRETS = ("SECRET_KEY", "JWT_SECRET_KEY", "API_KEY_ENCRYPTION_SECRET",
                "ADMIN_PASSWORD")

# Optional secrets migrated from the environment into the vault on first boot.
ENV_SECRETS = ("KAGGLE_USERNAME", "KAGGLE_KEY", "GEMINI_API_KEY",
               "MSG91_AUTHKEY", "SMTP_PASSWORD")


def _master_key() -> str:
    """Return the vault master key (env var > master.key > auto-generate)."""
    key = (os.environ.get("SECRETS_MASTER_KEY") or "").strip()
    if not key and os.path.exists(MASTER_KEY_FILE):
        try:
            with open(MASTER_KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
        except OSError:
            key = ""
    if key:
        return key
    key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    try:
        with open(MASTER_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(key + "\n")
    except OSError:
        pass
    return key


def _fernet() -> Fernet:
    """Deterministic Fernet derived from the master key."""
    raw = _master_key().encode("utf-8")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw).digest()))


def _load() -> dict:
    if not os.path.exists(VAULT_FILE):
        return {}
    try:
        with open(VAULT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    with open(VAULT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def set_secret(name: str, value: str) -> None:
    """Encrypt ``value`` and store it with its SHA-256 hash."""
    data = _load()
    data[name] = {
        "s256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        "enc": _fernet().encrypt(value.encode("utf-8")).decode("ascii"),
    }
    _save(data)


def get_secret(name: str):
    """Decrypt and return a secret, or None when missing/corrupt."""
    entry = _load().get(name)
    if not isinstance(entry, dict):
        return None
    try:
        plain = _fernet().decrypt(entry["enc"].encode("ascii")).decode("utf-8")
    except (InvalidToken, KeyError, ValueError, TypeError):
        return None
    if entry.get("s256") != hashlib.sha256(plain.encode("utf-8")).hexdigest():
        return None
    return plain


def has_secret(name: str) -> bool:
    return isinstance(_load().get(name), dict)


def _random_password(length: int = 16) -> str:
    """Strong password satisfying the app's password policy."""
    upper = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    lower = "abcdefghijkmnopqrstuvwxyz"
    digits = "23456789"
    special = "!@#$%^&*_-+=?"
    pools = (upper, lower, digits, special)
    parts = [pysecrets.choice(p) for p in pools]
    parts += [pysecrets.choice("".join(pools)) for _ in range(length - len(parts))]
    return "".join(parts)


def ensure_seeded() -> None:
    """Seed core secrets and migrate existing env secrets into the vault."""
    pending = {}
    for name in CORE_SECRETS:
        if has_secret(name):
            continue
        value = os.environ.get(name, "").strip()
        if not value:
            if name == "ADMIN_PASSWORD":
                value = _random_password()
                _note_admin_credentials(value)
            else:
                value = pysecrets.token_hex(32)
        pending[name] = value
    for name in ENV_SECRETS:
        if not has_secret(name) and os.environ.get(name, "").strip():
            pending[name] = os.environ[name].strip()
    for name, value in pending.items():
        set_secret(name, value)


def _note_admin_credentials(password: str) -> None:
    """One-time dev bootstrap note; gitignored, never committed."""
    if os.path.exists(ADMIN_NOTE_FILE):
        return
    try:
        with open(ADMIN_NOTE_FILE, "w", encoding="utf-8") as f:
            f.write("Generated ADMIN_PASSWORD for the first boot (delete after saving):\n")
            f.write(password + "\n")
    except OSError:
        pass
    print("ADMIN_PASSWORD auto-generated; see backend/security/ADMIN_CREDENTIALS.txt")


if __name__ == "__main__":
    ensure_seeded()
    print(f"Vault ready: {VAULT_FILE}")
    for name in sorted(_load()):
        print(f"  {name}: {'stored' if get_secret(name) is not None else 'ERROR'}")
