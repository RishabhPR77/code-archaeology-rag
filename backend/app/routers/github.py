# app/routers/github.py
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import verified_user
from app.models import User
from app.schemas import GitHubInstallationOut, GitHubRepoOut, GitHubStatusOut
from app.services import audit, github

router = APIRouter(prefix="/api/github", tags=["github"])


@router.get("/status", response_model=GitHubStatusOut)
def github_status(user: User = Depends(verified_user), db: Session = Depends(get_db)):
    settings = get_settings()
    out = GitHubStatusOut(enabled=settings.github_oauth_enabled, connected=False, login=user.github_login,
                          install_url=settings.github_install_url, installations=[])
    if not settings.github_oauth_enabled or not user.github_token_enc:
        return out
    try:
        token = github.user_token(db, user)
        out.installations = [GitHubInstallationOut(**i) for i in github.installations(token)]
        out.connected = True
    except github.GitHubNotConnected as e:
        out.error = str(e)
    except httpx.HTTPError:
        out.connected, out.error = True, "GitHub is unreachable right now"
    return out


@router.get("/repos", response_model=list[GitHubRepoOut])
def github_repos(user: User = Depends(verified_user), db: Session = Depends(get_db)):
    try:
        return github.shared_repos(github.user_token(db, user))
    except github.GitHubNotConnected as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "GitHub is unreachable right now") from None


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_github(request: Request, user: User = Depends(verified_user), db: Session = Depends(get_db)):
    """Forget the tokens. Removing the app from the user's GitHub account is done on GitHub."""
    github.clear_tokens(user)
    db.commit()
    audit.record(db, user, "github_disconnected", request)
