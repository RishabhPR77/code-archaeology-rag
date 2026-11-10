# app/routers/admin.py
"""Admin-only tools: choosing which repositories the public demo shows, and checking how the
host passes on visitors' addresses."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import client_ip, verified_user
from app.models import Repo, User, utcnow
from app.routers.repos import repo_out
from app.schemas import RepoOut
from app.services import demo

router = APIRouter(prefix="/api/admin", tags=["admin"])


def admin_user(user: User = Depends(verified_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return user


@router.get("/demo", response_model=list[RepoOut])
def list_demo(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return [repo_out(r) for r in demo.demo_repos(db)]


@router.delete("/demo/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
def stop_sharing(repo_id: str, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Take a repository out of the demo and give it, with its chats, back to this admin."""
    owner = demo.demo_user(db)
    repo = db.get(Repo, repo_id)
    if repo is None or owner is None or repo.user_id != owner.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That repository isn't in the demo")
    repo.user_id = user.id
    ttl = get_settings().repo_ttl_hours
    repo.expires_at = utcnow() + timedelta(hours=ttl) if ttl > 0 else None
    db.commit()


# Headers a proxy or CDN may use for the visitor's address
_IP_HEADERS = ("true-client-ip", "cf-connecting-ip", "x-real-ip", "x-forwarded-for", "forwarded")


@router.get("/request-info")
def request_info(request: Request, _: User = Depends(admin_user)):
    """The admin's own request as the server sees it: which address-carrying headers arrived and the
    address the rate limiters use. Used to pick CLIENT_IP_HEADER, and to check it can't be faked."""
    return {"client_ip": client_ip(request), "connection_ip": request.client.host if request.client else None,
            "client_ip_header": get_settings().client_ip_header or None,
            "headers": {h: request.headers[h] for h in _IP_HEADERS if h in request.headers}}
