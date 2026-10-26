# app/routers/repos.py
import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query as Q, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import llm
from app.config import get_settings
from app.db import get_db
from app.deps import owned_repo, verified_user
from app.llm import ProviderError
from app.models import IngestEvent, Query, Repo, User
from app.routers.providers import provider_http_error
from app.schemas import (GITHUB_URL, AskIn, QueryOut, RepoIn, RepoOut, TimelineIn, TimelineOut,
                         as_utc)
from app.security import decrypt_secret
from app.services import github, ingest, rag
from app.services.users import credential, limits_for
from retrieval import analytics

router = APIRouter(prefix="/api/repos", tags=["repos"])


def repo_out(repo: Repo) -> RepoOut:
    return RepoOut(id=repo.id, url=repo.url, full_name=repo.full_name, is_private=repo.is_private,
                   status=repo.status,
                   stage_message=repo.stage_message, error=repo.error,
                   warnings=[w for w in repo.warnings.split("\n") if w],
                   max_commits=repo.max_commits, commit_count=repo.commit_count, pr_count=repo.pr_count,
                   created_at=as_utc(repo.created_at), ready_at=as_utc(repo.ready_at),
                   expires_at=as_utc(repo.expires_at))


def _chunks(repo: Repo) -> list[dict]:
    if repo.status != "ready" or repo.data is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This repository is still being ingested")
    return json.loads(repo.data.chunks_json)


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


def _llm_for(db: Session, user: User):
    """Return (provider, model, generate) for the user's active provider."""
    if not user.active_provider:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect a model provider in Settings first")
    cred = credential(db, user, user.active_provider)
    if cred is None or not cred.model:
        raise HTTPException(status.HTTP_409_CONFLICT, "Choose a model in Settings first")
    api_key, provider, model = decrypt_secret(cred.key_enc), cred.provider, cred.model

    def generate(system: str, prompt: str) -> str:
        return llm.generate(provider, api_key, model, system, prompt)

    return provider, model, generate


# ── Repos ──────────────────────────────────────────────────────────
@router.get("", response_model=list[RepoOut])
def list_repos(user: User = Depends(verified_user), db: Session = Depends(get_db)):
    repos = db.scalars(select(Repo).where(Repo.user_id == user.id).order_by(Repo.created_at.desc()))
    return [repo_out(r) for r in repos]


@router.post("", response_model=RepoOut, status_code=status.HTTP_202_ACCEPTED)
def create_repo(body: RepoIn, tasks: BackgroundTasks,
                user: User = Depends(verified_user), db: Session = Depends(get_db)):
    _check_ingest_allowed(db, user, body.max_commits, new_repo=True)
    m = GITHUB_URL.match(body.url)
    owner, name = m.group(2), m.group(3)
    full_name = f"{owner}/{name}"

    token = None
    if user.github_token_enc:
        try:
            token = github.user_token(db, user)
        except github.GitHubNotConnected:
            token = None
    visibility = github.repo_visibility(full_name, token or get_settings().github_token or None)
    if visibility == "missing":
        hint = ("If it's private, give the GitHub App access to it." if token
                else "If it's private, connect GitHub first and choose it there.")
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Couldn't find {full_name} on GitHub. {hint}")

    repo = Repo(user_id=user.id, url=f"https://github.com/{full_name}", full_name=full_name,
                is_private=visibility == "private",
                namespace=f"u{user.id}_{uuid.uuid4().hex[:12]}", max_commits=body.max_commits)
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
    db.add(IngestEvent(user_id=user.id))
    db.commit()
    tasks.add_task(ingest.run_ingest, repo.id)
    return repo_out(repo)


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repo(repo: Repo = Depends(owned_repo), db: Session = Depends(get_db)):
    ingest.delete_repo_data(repo)
    db.delete(repo)
    db.commit()


# ── Analytics ──────────────────────────────────────────────────────
@router.get("/{repo_id}/overview")
def repo_overview(repo: Repo = Depends(owned_repo)):
    return analytics.overview(_chunks(repo))


@router.get("/{repo_id}/commits")
def repo_commits(repo: Repo = Depends(owned_repo)):
    return analytics.commit_log(_chunks(repo))


@router.get("/{repo_id}/files")
def repo_files(repo: Repo = Depends(owned_repo)):
    return analytics.all_files(_chunks(repo))


@router.get("/{repo_id}/hotfiles")
def repo_hotfiles(limit: int = Q(15, ge=1, le=100), repo: Repo = Depends(owned_repo)):
    return analytics.hottest_files(_chunks(repo), top_n=limit)


@router.get("/{repo_id}/cochange")
def repo_cochange(limit: int = Q(10, ge=1, le=100), repo: Repo = Depends(owned_repo)):
    return analytics.co_change_analysis(_chunks(repo), top_n=limit)


@router.get("/{repo_id}/authors")
def repo_authors(repo: Repo = Depends(owned_repo)):
    return analytics.author_analysis(_chunks(repo))


@router.get("/{repo_id}/pulls")
def repo_pulls(repo: Repo = Depends(owned_repo)):
    return analytics.pull_requests(_chunks(repo))


# ── LLM features ───────────────────────────────────────────────────
def _query_out(q: Query) -> QueryOut:
    return QueryOut(id=q.id, kind=q.kind, question=q.question, answer=q.answer, mode=q.mode,
                    provider=q.provider, model=q.model, sources=json.loads(q.sources_json),
                    created_at=as_utc(q.created_at))


@router.post("/{repo_id}/ask", response_model=QueryOut)
def ask(body: AskIn, repo: Repo = Depends(owned_repo),
        user: User = Depends(verified_user), db: Session = Depends(get_db)):
    _chunks(repo)  # ensures the repo is ready
    provider, model, generate = _llm_for(db, user)
    try:
        result = rag.ask(body.question, repo.namespace, generate, mode=body.mode, only_pr=body.only_pr)
    except ProviderError as e:
        raise provider_http_error(e)
    q = Query(repo_id=repo.id, kind="ask", question=body.question, answer=result["answer"],
              mode=body.mode, provider=provider, model=model, sources_json=json.dumps(result["sources"]))
    db.add(q)
    db.commit()
    return _query_out(q)


@router.get("/{repo_id}/queries", response_model=list[QueryOut])
def list_queries(repo: Repo = Depends(owned_repo), db: Session = Depends(get_db)):
    qs = db.scalars(select(Query).where(Query.repo_id == repo.id, Query.kind == "ask")
                    .order_by(Query.created_at.asc(), Query.id.asc()).limit(100))
    return [_query_out(q) for q in qs]


@router.delete("/{repo_id}/queries", status_code=status.HTTP_204_NO_CONTENT)
def clear_queries(repo: Repo = Depends(owned_repo), db: Session = Depends(get_db)):
    for q in db.scalars(select(Query).where(Query.repo_id == repo.id)):
        db.delete(q)
    db.commit()


@router.post("/{repo_id}/timeline", response_model=TimelineOut)
def timeline(body: TimelineIn, repo: Repo = Depends(owned_repo),
             user: User = Depends(verified_user), db: Session = Depends(get_db)):
    chunks = _chunks(repo)
    if not analytics.file_timeline(chunks, body.path):
        return TimelineOut(path=body.path, answer=None, provider=None, model=None, entries=[])
    provider, model, generate = _llm_for(db, user)
    try:
        result = rag.timeline(body.path, chunks, generate)
    except ProviderError as e:
        raise provider_http_error(e)
    return TimelineOut(path=body.path, answer=result["answer"], provider=provider, model=model,
                       entries=result["entries"])
