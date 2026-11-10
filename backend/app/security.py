import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import get_settings

SESSION_COOKIE = "ca_session"
TWO_FACTOR_COOKIE = "ca_2fa"      # between the password (or Google/GitHub) and the authenticator code
TWO_FACTOR_TTL = timedelta(minutes=5)
_JWT_ALG = "HS256"


# ── Passwords ──────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


@lru_cache
def _dummy_hash() -> str:
    return hash_password("not-a-real-password")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Always does the slow bcrypt check, even with no hash to check against, so the response
    takes as long for an unknown email as for a wrong password and timing can't reveal accounts."""
    try:
        ok = bcrypt.checkpw(password.encode(), (password_hash or _dummy_hash()).encode())
    except ValueError:
        return False
    return ok and password_hash is not None


# ── Signing keys ───────────────────────────────────────────────────
def key_id(secret: str) -> str:
    """A short, public name for a signing key, so a token says which key signed it."""
    return hashlib.sha256(secret.encode()).hexdigest()[:8]


def _verify_keys(kid: str | None) -> list[str]:
    keys = get_settings().secret_keys
    named = [k for k in keys if key_id(k) == kid]
    return named or keys


def sign(message: str) -> str:
    """HMAC with the current key, e.g. for email codes and recovery codes."""
    return hmac.new(get_settings().secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()


def signature_matches(message: str, digest: str) -> bool:
    """Checks against every accepted key, so codes sent just before a rotation still work."""
    return any(hmac.compare_digest(digest, hmac.new(k.encode(), message.encode(), hashlib.sha256).hexdigest())
               for k in get_settings().secret_keys)


def _encode(payload: dict, ttl: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode({**payload, "iat": now, "exp": now + ttl}, settings.secret_key,
                      algorithm=_JWT_ALG, headers={"kid": key_id(settings.secret_key)})


def _decode(token: str) -> dict | None:
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError:
        return None
    for key in _verify_keys(kid):
        try:
            return jwt.decode(token, key, algorithms=[_JWT_ALG])
        except jwt.ExpiredSignatureError:
            return None
        except jwt.PyJWTError:
            continue
    return None


# ── Sessions ───────────────────────────────────────────────────────
def create_session_token(user_id: int, version: int = 0) -> str:
    """A signed token naming the user and their session version; it expires after SESSION_TTL_HOURS."""
    return _encode({"sub": str(user_id), "v": version}, timedelta(hours=get_settings().session_ttl_hours))


def decode_session_token(token: str) -> tuple[int, int] | None:
    """(user id, session version) if the token is a genuine, unexpired session, else None."""
    payload = _decode(token)
    # A half-finished two-step sign-in token is never accepted as a session
    if payload is None or "purpose" in payload:
        return None
    try:
        return int(payload["sub"]), int(payload.get("v", 0))
    except (KeyError, ValueError, TypeError):
        return None


def create_two_factor_token(user_id: int, version: int, method: str) -> str:
    """Proof that the first step (password, Google or GitHub) passed, valid for five minutes."""
    return _encode({"sub": str(user_id), "v": version, "purpose": "2fa", "method": method}, TWO_FACTOR_TTL)


def decode_two_factor_token(token: str) -> tuple[int, int, str] | None:
    payload = _decode(token)
    if payload is None or payload.get("purpose") != "2fa":
        return None
    try:
        return int(payload["sub"]), int(payload.get("v", 0)), str(payload.get("method", "password"))
    except (KeyError, ValueError, TypeError):
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


def two_factor_cookie_kwargs() -> dict:
    return {"key": TWO_FACTOR_COOKIE, "httponly": True, "secure": get_settings().is_production,
            "samesite": "lax", "max_age": int(TWO_FACTOR_TTL.total_seconds()), "path": "/api/auth"}


# ── API key encryption ─────────────────────────────────────────────
@lru_cache
def _fernet() -> MultiFernet:
    # Encrypts with the first key; decrypts with any of them, so ENCRYPTION_KEY can be rotated
    return MultiFernet([Fernet(k.encode()) for k in get_settings().encryption_keys])


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise RuntimeError("Stored secret can't be decrypted — was ENCRYPTION_KEY changed?") from e


def reencrypt_secret(token: str) -> str:
    """The same secret, encrypted with the current key."""
    return _fernet().rotate(token.encode()).decode()


def key_hint(key: str) -> str:
    """Show just enough of a key to recognise it — never more than a fifth of it."""
    return f"{key[:4]}…{key[-4:]}" if len(key) >= 40 else f"…{key[-2:]}"
