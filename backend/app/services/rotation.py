# app/services/rotation.py
"""Changing the encryption key without losing stored secrets.

To rotate: set ENCRYPTION_KEY to a new key and ENCRYPTION_KEY_PREVIOUS to the old one, then deploy.
On start-up every stored secret is re-encrypted with the new key, after which the old one can go."""
import logging

from sqlalchemy import or_, select

from app.config import get_settings
from app.db import SessionLocal
from app.models import ProviderCredential, User
from app.security import reencrypt_secret

log = logging.getLogger(__name__)
USER_SECRETS = ("github_token_enc", "github_refresh_enc", "totp_secret_enc", "totp_pending_enc")


def reencrypt_stored_secrets() -> int:
    if not get_settings().encryption_key_previous:
        return 0
    count = 0
    with SessionLocal() as db:
        for cred in db.scalars(select(ProviderCredential)):
            cred.key_enc = reencrypt_secret(cred.key_enc)
            count += 1
        holders = db.scalars(select(User).where(or_(*(getattr(User, f).is_not(None) for f in USER_SECRETS))))
        for user in holders:
            for field in USER_SECRETS:
                if getattr(user, field):
                    setattr(user, field, reencrypt_secret(getattr(user, field)))
                    count += 1
        db.commit()
    log.info("Re-encrypted %d stored secrets with the current ENCRYPTION_KEY", count)
    return count
