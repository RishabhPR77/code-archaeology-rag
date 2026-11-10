# app/routers/repos.py
"""Adding, listing, re-syncing and deleting repositories, and sharing one in the public demo."""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query as Q, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import owned_repo, verified_user
from app.models import IngestEvent, Repo, User
from app.schemas import (GITHUB_URL, MAX_COMMIT_REACH, CommitBriefOut, RangePreviewOut, RepoIn, RepoOut,
                         as_utc)
from app.services import demo, github, ingest
from app.services.users import limits_for

router = APIRouter(prefix="/api/repos", tags=["repos"])


def repo_out(repo: Repo) -> RepoOut:
    return RepoOut(id=repo.id, url=repo.url, full_name=repo.full_name, is_private=repo.is_private,
                   status=repo.status,
                   stage_message=repo.stage_message, error=repo.error,
                   warnings=[w for w in repo.warnings.split("\n") if w],
                   max_commits=repo.max_commits, skip_commits=repo.skip_commits or 0,
                   commit_count=repo.commit_count, pr_count=repo.pr_count,
                   created_at=as_utc(repo.created_at), ready_at=as_utc(repo.ready_at),
                   expires_at=as_utc(repo.expires_at))


def _check_ingest_allowed(db: Session, user: User, max_commits: int, new_repo: bool):
    limits = limits_for(db, user)
    if limits.unlimited:
        return
    if max_commits > limits.max_commits:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"The limit is {limits.max_commits} commits per repository.")
    if new_repo and limits.repos_used >= limits.max_repos:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"You can keep up to {limits.max_repos} repositories. Delete one to add another.")
    if limits.ingests_today >= limits.max_ingests_day:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"You've used all {limits.max_ingests_day} ingests for the last 24 hours.")


# ── Repos ──────────────────────────────────────────────────────────
@router.get("", response_model=list[RepoOut])
def list_repos(user: User = Depends(verified_user), db: Session = Depends(get_db)):
    repos = db.scalars(select(Repo).where(Repo.user_id == user.id).order_by(Repo.created_at.desc()))
    return [repo_out(r) for r in repos]


def _github_token_for(db: Session, user: User) -> str | None:
    """The user's own GitHub token when connected (it can see their private repositories)."""
    if not user.github_token_enc:
        return None
    try:
        return github.user_token(db, user)
    except github.GitHubNotConnected:
        return None


@router.get("/range-preview", response_model=RangePreviewOut)
def range_preview(url: str, skip: int = Q(0, ge=0, le=MAX_COMMIT_REACH), count: int = Q(100, ge=1, le=2000),
                  user: User = Depends(verified_user), db: Session = Depends(get_db)):
    """How many commits a repository has, and which commits a range would start and end at."""
    m = GITHUB_URL.match(url.strip())
    if not m:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Enter a GitHub repository URL")
    full_name = f"{m.group(2)}/{m.group(3)}"
    token = _github_token_for(db, user) or get_settings().github_token or None
    try:
        total = github.commit_total(full_name, token)
        if total is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Couldn't find {full_name} on GitHub")
        first = min(skip + 1, total)
        last = min(skip + count, total)
        newest = github.commit_at(full_name, first, token) if total else None
        oldest = github.commit_at(full_name, last, token) if total and last != first else newest
    except github.GitHubUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "GitHub isn't answering right now, so the range can't be previewed. "
                            "You can still ingest it.") from None
    return RangePreviewOut(full_name=full_name, total=total, reach=MAX_COMMIT_REACH,
                           newest=CommitBriefOut(**newest) if newest else None,
                           oldest=CommitBriefOut(**oldest) if oldest else None)


@router.post("", response_model=RepoOut, status_code=status.HTTP_202_ACCEPTED)
def create_repo(body: RepoIn, tasks: BackgroundTasks,
                user: User = Depends(verified_user), db: Session = Depends(get_db)):
    _check_ingest_allowed(db, user, body.max_commits, new_repo=True)
    m = GITHUB_URL.match(body.url)
    owner, name = m.group(2), m.group(3)
    full_name = f"{owner}/{name}"

    token = _github_token_for(db, user)
    visibility = github.repo_visibility(full_name, token or get_settings().github_token or None)
    if visibility == "missing":
        hint = ("If it's private, give the GitHub App access to it." if token
                else "If it's private, connect GitHub first and choose it there.")
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Couldn't find {full_name} on GitHub. {hint}")

    repo = Repo(user_id=user.id, url=f"https://github.com/{full_name}", full_name=full_name,
                is_private=visibility == "private",
                namespace=f"u{user.id}_{uuid.uuid4().hex[:12]}", max_commits=body.max_commits,
                skip_commits=body.skip_commits)
    db.add(repo)
    db.add(IngestEvent(user_id=user.id))
    db.commit()
    tasks.add_task(ingest.run_ingest, repo.id)
    return repo_out(repo)


@router.get("/{repo_id}", response_model=RepoOut)
def get_repo(repo: Repo = Depends(owned_repo)):
    return repo_out(repo)


@router.post("/{repo_id}/resync", response_model=RepoOut, status_code=status.HTTP_202_ACCEPTED)
def resync_repo(tasks: BackgroundTasks, repo: Repo = Depends(owned_repo),
                user: User = Depends(verified_user), db: Session = Depends(get_db)):
    if repo.status not in ingest.TERMINAL:
        raise HTTPException(status.HTTP_409_CONFLICT, "This repository is already being ingested")
    _check_ingest_allowed(db, user, repo.max_commits, new_repo=False)
    repo.status, repo.stage_message, repo.error, repo.warnings = "queued", "Waiting to start", None, ""
    repo.ingest_attempts = 0
    db.add(IngestEvent(user_id=user.id))
    db.commit()
    tasks.add_task(ingest.run_ingest, repo.id)
    return repo_out(repo)


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repo(repo: Repo = Depends(owned_repo), db: Session = Depends(get_db)):
    ingest.delete_repo_data(repo)
    db.delete(repo)
    db.commit()


# ── Public demo ────────────────────────────────────────────────────
@router.post("/{repo_id}/make-demo", status_code=status.HTTP_204_NO_CONTENT)
def make_demo(repo: Repo = Depends(owned_repo), user: User = Depends(verified_user), db: Session = Depends(get_db)):
    """Admins only: hand this repository, with its chats, to the public demo account."""
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can choose the demo repositories")
    if repo.is_private:
        raise HTTPException(status.HTTP_409_CONFLICT, "Private repositories can't be shown in the public demo")
    if repo.status != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, "Wait until the repository is ready")
    demo.make_demo(db, repo)
