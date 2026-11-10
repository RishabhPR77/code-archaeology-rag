# app/routers/analytics.py
"""What a ready repository's history shows: the analytics tabs, Who broke it? and file timelines."""
import json

from fastapi import APIRouter, Depends, Query as Q, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import owned_repo, verified_user
from app.llm import ProviderError
from app.models import Repo, User
from app.routers.providers import provider_http_error
from app.schemas import SuspectsIn, SuspectsOut, TimelineIn, TimelineOut
from app.services import rag
from app.services.repo_context import history, limit_demo, limit_search, optional_llm, ready_data
from ingestion import bug_origins
from retrieval import analytics

router = APIRouter(prefix="/api/repos", tags=["analytics"])


# ── Analytics ──────────────────────────────────────────────────────
@router.get("/{repo_id}/overview")
def repo_overview(repo: Repo = Depends(owned_repo)):
    return analytics.overview(history(repo))


@router.get("/{repo_id}/commits")
def repo_commits(repo: Repo = Depends(owned_repo)):
    return analytics.commit_log(history(repo))


@router.get("/{repo_id}/files")
def repo_files(repo: Repo = Depends(owned_repo)):
    return analytics.all_files(history(repo))


@router.get("/{repo_id}/hotfiles")
def repo_hotfiles(limit: int = Q(15, ge=1, le=100), repo: Repo = Depends(owned_repo)):
    return analytics.hottest_files(history(repo), top_n=limit)


@router.get("/{repo_id}/origins")
def repo_origins(repo: Repo = Depends(owned_repo)):
    raw = ready_data(repo).origins_json
    if raw is None:
        # Ingested before bug origins existed, or tracing failed: a re-sync computes them
        return {"computed": False, "summary": None, "fixes": []}
    fixes = json.loads(raw)
    return {"computed": True, "summary": bug_origins.summarize(fixes), "fixes": fixes}


@router.get("/{repo_id}/cochange")
def repo_cochange(limit: int = Q(10, ge=1, le=100), repo: Repo = Depends(owned_repo)):
    return analytics.co_change_analysis(history(repo), top_n=limit)


@router.get("/{repo_id}/authors")
def repo_authors(repo: Repo = Depends(owned_repo)):
    return analytics.author_analysis(history(repo))


@router.get("/{repo_id}/pulls")
def repo_pulls(repo: Repo = Depends(owned_repo)):
    return analytics.pull_requests(history(repo))


# ── Searches ───────────────────────────────────────────────────────
@router.post("/{repo_id}/suspects", response_model=SuspectsOut)
def suspects(body: SuspectsIn, request: Request, repo: Repo = Depends(owned_repo),
             user: User = Depends(verified_user), db: Session = Depends(get_db)):
    data = ready_data(repo)
    limit_demo(request, user, "suspects")
    limit_search(user)
    # The ranking needs no model; an explanation is added when one is connected
    provider, model, generate = optional_llm(db, user)
    try:
        result = rag.find_suspects(body.description, repo.namespace, history(repo),
                                   json.loads(data.origins_json) if data.origins_json else None,
                                   body.since.isoformat() if body.since else None, generate)
    except ProviderError as e:
        raise provider_http_error(e) from e
    return SuspectsOut(**result, provider=provider, model=model)


@router.post("/{repo_id}/timeline", response_model=TimelineOut)
def timeline(body: TimelineIn, repo: Repo = Depends(owned_repo),
             user: User = Depends(verified_user), db: Session = Depends(get_db)):
    chunks = history(repo)
    if not analytics.file_timeline(chunks, body.path, body.match):
        return TimelineOut(path=body.path, answer=None, provider=None, model=None, entries=[])
    # The commit list needs no model; the written summary is added when one is connected
    provider, model, generate = optional_llm(db, user)
    try:
        result = rag.timeline(body.path, chunks, generate, body.match)
    except ProviderError as e:
        raise provider_http_error(e) from e
    return TimelineOut(path=body.path, answer=result["answer"], provider=provider if generate else None,
                       model=model if generate else None, entries=result["entries"])
