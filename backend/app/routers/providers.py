# app/routers/providers.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import llm
from app.db import get_db
from app.deps import verified_user
from app.llm import PROVIDERS, ProviderError
from app.models import ProviderCredential, User
from app.schemas import (ActiveProviderIn, ModelOut, ProviderOut, SaveKeyIn, SaveKeyOut,
                         SelectModelIn)
from app.security import decrypt_secret, encrypt_secret, key_hint
from app.services.users import credential

router = APIRouter(prefix="/api/providers", tags=["providers"])

_ERROR_STATUS = {"auth": 400, "rate_limit": 429, "not_found": 404, "bad_request": 400, "unavailable": 502}


def provider_http_error(e: ProviderError) -> HTTPException:
    # Never 401: that status means "your session ended" to the frontend
    return HTTPException(_ERROR_STATUS[e.kind], e.message)


def _provider_out(user: User, provider_id: str, cred: ProviderCredential | None) -> ProviderOut:
    p = PROVIDERS[provider_id]
    return ProviderOut(id=p.id, name=p.name, key_url=p.key_url, docs_url=p.docs_url,
                       configured=cred is not None, key_hint=cred.key_hint if cred else None,
                       model=cred.model if cred else None, active=user.active_provider == p.id)


def _require_provider(provider_id: str):
    if provider_id not in PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown provider '{provider_id}'")


def _require_credential(db: Session, user: User, provider_id: str) -> ProviderCredential:
    _require_provider(provider_id)
    cred = credential(db, user, provider_id)
    if cred is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Add a {PROVIDERS[provider_id].name} API key first")
    return cred


@router.get("", response_model=list[ProviderOut])
def list_providers(user: User = Depends(verified_user), db: Session = Depends(get_db)):
    creds = {c.provider: c for c in user.credentials}
    return [_provider_out(user, pid, creds.get(pid)) for pid in PROVIDERS]


@router.put("/{provider_id}/key", response_model=SaveKeyOut)
def save_key(provider_id: str, body: SaveKeyIn,
             user: User = Depends(verified_user), db: Session = Depends(get_db)):
    _require_provider(provider_id)
    # Listing models with the key is the validation step
    try:
        models = llm.list_models(provider_id, body.api_key, refresh=True)
    except ProviderError as e:
        raise provider_http_error(e)
    if not models:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "This key works but has access to no text-generation models.")

    cred = credential(db, user, provider_id)
    if cred is None:
        cred = ProviderCredential(user_id=user.id, provider=provider_id, key_enc="", key_hint="")
        db.add(cred)
    cred.key_enc = encrypt_secret(body.api_key)
    cred.key_hint = key_hint(body.api_key)
    if cred.model not in {m.id for m in models}:
        cred.model = None   # the user picks one explicitly
    if user.active_provider is None:
        user.active_provider = provider_id
    db.commit()
    return SaveKeyOut(provider=_provider_out(user, provider_id, cred),
                      models=[ModelOut(**m.public()) for m in models])


@router.delete("/{provider_id}/key", status_code=status.HTTP_204_NO_CONTENT)
def delete_key(provider_id: str, user: User = Depends(verified_user), db: Session = Depends(get_db)):
    cred = _require_credential(db, user, provider_id)
    db.delete(cred)
    if user.active_provider == provider_id:
        others = [c for c in user.credentials if c.provider != provider_id]
        user.active_provider = others[0].provider if others else None
    db.commit()


@router.get("/{provider_id}/models", response_model=list[ModelOut])
def provider_models(provider_id: str, refresh: bool = Query(False),
                    user: User = Depends(verified_user), db: Session = Depends(get_db)):
    cred = _require_credential(db, user, provider_id)
    try:
        models = llm.list_models(provider_id, decrypt_secret(cred.key_enc), refresh=refresh)
    except ProviderError as e:
        raise provider_http_error(e)
    return [ModelOut(**m.public()) for m in models]


@router.put("/{provider_id}/model", response_model=ProviderOut)
def select_model(provider_id: str, body: SelectModelIn,
                 user: User = Depends(verified_user), db: Session = Depends(get_db)):
    cred = _require_credential(db, user, provider_id)
    try:
        llm.find_model(provider_id, decrypt_secret(cred.key_enc), body.model)
    except ProviderError as e:
        raise provider_http_error(e)
    cred.model = body.model
    db.commit()
    return _provider_out(user, provider_id, cred)


@router.put("/active", response_model=ProviderOut)
def set_active(body: ActiveProviderIn, user: User = Depends(verified_user), db: Session = Depends(get_db)):
    cred = _require_credential(db, user, body.provider)
    if not cred.model:
        raise HTTPException(status.HTTP_409_CONFLICT, "Choose a model for this provider first")
    user.active_provider = body.provider
    db.commit()
    return _provider_out(user, body.provider, cred)
