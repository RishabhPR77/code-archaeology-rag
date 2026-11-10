# app/services/repo_context.py
"""What the repository routes share: a ready repository's parsed history (cached), the user's model,
and the search limits."""
import json
import threading
from collections import OrderedDict

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app import llm
from app.deps import client_ip, demo_limiter, demo_total_limiter, search_limiter
from app.models import Repo, RepoData, User
from app.security import decrypt_secret
from app.services.users import credential


def ready_data(repo: Repo) -> RepoData:
    if repo.status != "ready" or repo.data is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This repository is still being ingested")
    return repo.data


# Parsed commit histories, most recently used last. The stored JSON is megabytes for a large repository and
# the Overview tab alone asks for it several times, so parsing it once matters on a small server.
PARSED: OrderedDict[tuple[str, str], list[dict]] = OrderedDict()
PARSED_MAX = 4
_parsed_lock = threading.Lock()


def history(repo: Repo) -> list[dict]:
    """A ready repository's stored commits. Keyed by when it became ready, so a re-sync never serves the old ones."""
    if repo.status != "ready":
        ready_data(repo)   # raises the "still being ingested" error
    key = (repo.id, repo.ready_at.isoformat() if repo.ready_at else "")
    with _parsed_lock:
        if key in PARSED:
            PARSED.move_to_end(key)
            return PARSED[key]
    chunks = json.loads(ready_data(repo).chunks_json)
    with _parsed_lock:
        PARSED[key] = chunks
        while len(PARSED) > PARSED_MAX:
            PARSED.popitem(last=False)
    return chunks


def credential_for(db: Session, user: User) -> tuple[str, str, str]:
    """(provider, model, api_key) for the user's active provider."""
    if not user.active_provider:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect a model provider in Settings first")
    cred = credential(db, user, user.active_provider)
    if cred is None or not cred.model:
        raise HTTPException(status.HTTP_409_CONFLICT, "Choose a model in Settings first")
    return cred.provider, cred.model, decrypt_secret(cred.key_enc)


def llm_for(db: Session, user: User):
    """Return (provider, model, generate) for the user's active provider."""
    provider, model, api_key = credential_for(db, user)

    def generate(system: str, prompt: str) -> str:
        return llm.generate(provider, api_key, model, system, prompt)

    return provider, model, generate


def optional_llm(db: Session, user: User):
    """Like _llm_for, but (None, None, None) when no model is connected, for features that work without one."""
    cred = credential(db, user, user.active_provider) if user.active_provider else None
    return llm_for(db, user) if cred and cred.model else (None, None, None)


def limit_search(user: User):
    """Searches embed the question with the server's Pinecone allowance; cap each account per hour."""
    search_limiter.check(f"search:{user.id}")


def limit_demo(request: Request, user: User, feature: str):
    """Demo visitors share one account, so searches that cost embedding tokens are capped per visitor and overall."""
    if user.is_demo:
        demo_limiter.check(f"{feature}:{client_ip(request)}")
        demo_total_limiter.check(feature)
