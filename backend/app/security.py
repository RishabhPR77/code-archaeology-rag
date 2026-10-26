# app/security.py
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

SESSION_COOKIE = "ca_session"
_JWT_ALG = "HS256"


# ── Passwords ──────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


# ── Sessions ───────────────────────────────────────────────────────
def create_session_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now,
               "exp": now + timedelta(hours=settings.session_ttl_hours)}
    return jwt.encode(payload, settings.secret_key, algorithm=_JWT_ALG)


def decode_session_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[_JWT_ALG])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def session_cookie_kwargs() -> dict:
    settings = get_settings()
    return {
        "key":      SESSION_COOKIE,
        "httponly": True,
        "secure":   settings.is_production,
        "samesite": "lax",     # blocks cross-site POSTs carrying the session
        "max_age":  settings.session_ttl_hours * 3600,
        "path":     "/",
    }


# ── API key encryption ─────────────────────────────────────────────
@lru_cache
def _fernet() -> Fernet:
    return Fernet(get_settings().encryption_key.encode())


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise RuntimeError("Stored secret can't be decrypted — was ENCRYPTION_KEY changed?") from e


def key_hint(key: str) -> str:
    """Show just enough of a key to recognise it — never more than a fifth of it."""
    return f"{key[:4]}…{key[-4:]}" if len(key) >= 40 else f"…{key[-2:]}"
