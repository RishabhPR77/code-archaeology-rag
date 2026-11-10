# app/services/two_factor.py
"""Two-step sign-in with an authenticator app (TOTP, RFC 6238), plus one-time recovery codes.

The app and the server share a secret. Every 30 seconds both turn it and the current time into a
six-digit code, so a stolen password alone isn't enough to sign in."""
import json
import secrets
import time

import pyotp
import segno

from app.config import get_settings
from app.models import User, utcnow
from app.security import decrypt_secret, encrypt_secret, sign, signature_matches

STEP_SECONDS = 30
RECOVERY_CODES = 10
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"   # no 0/o, 1/l/i: easy to copy by hand


def enabled(user: User) -> bool:
    return user.totp_secret_enc is not None


def start_setup(user: User) -> tuple[str, str, str]:
    """A new secret, kept as pending until the first code confirms the app has it.
    Returns (secret, otpauth URI, QR code as an SVG data URI)."""
    secret = pyotp.random_base32()
    user.totp_pending_enc = encrypt_secret(secret)
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=get_settings().app_name)
    qr = segno.make(uri, error="m").svg_data_uri(scale=5, border=2)
    return secret, uri, qr


def _matching_step(secret: str, code: str, last_step: int) -> int | None:
    """The time step this code belongs to, allowing one step of clock drift either way.
    A step at or before the last one used is refused, so a code can't be replayed."""
    code = code.strip().replace(" ", "")
    if not (len(code) == 6 and code.isdigit()):
        return None
    totp = pyotp.TOTP(secret)
    now = int(time.time()) // STEP_SECONDS
    for step in (now - 1, now, now + 1):
        if step > last_step and secrets.compare_digest(totp.at(step * STEP_SECONDS), code):
            return step
    return None


def confirm_setup(user: User, code: str) -> list[str] | None:
    """Turn two-step sign-in on if the code matches the pending secret. Returns the recovery codes."""
    if user.totp_pending_enc is None:
        return None
    secret = decrypt_secret(user.totp_pending_enc)
    step = _matching_step(secret, code, 0)
    if step is None:
        return None
    user.totp_secret_enc, user.totp_pending_enc = user.totp_pending_enc, None
    user.totp_enabled_at, user.totp_last_step = utcnow(), step
    return new_recovery_codes(user)


def _normal(code: str) -> str:
    return code.strip().lower().replace("-", "").replace(" ", "")


def _recovery_message(user: User, code: str) -> str:
    return f"recovery:{user.id}:{_normal(code)}"


def new_recovery_codes(user: User) -> list[str]:
    """Ten single-use codes for when the phone is lost. Only their HMACs are kept."""
    codes = []
    for _ in range(RECOVERY_CODES):
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    user.recovery_codes_json = json.dumps([sign(_recovery_message(user, c)) for c in codes])
    return codes


def recovery_codes_left(user: User) -> int:
    return len(json.loads(user.recovery_codes_json or "[]")) if enabled(user) else 0


def verify(user: User, code: str) -> str | None:
    """'app' or 'recovery' if the code is right (a recovery code is used up), else None."""
    if not enabled(user):
        return None
    step = _matching_step(decrypt_secret(user.totp_secret_enc), code, user.totp_last_step or 0)
    if step is not None:
        user.totp_last_step = step
        return "app"
    hashes = json.loads(user.recovery_codes_json or "[]")
    for digest in hashes:
        if signature_matches(_recovery_message(user, code), digest):
            hashes.remove(digest)
            user.recovery_codes_json = json.dumps(hashes)
            return "recovery"
    return None


def disable(user: User):
    user.totp_secret_enc = user.totp_pending_enc = user.recovery_codes_json = None
    user.totp_enabled_at, user.totp_last_step = None, 0
