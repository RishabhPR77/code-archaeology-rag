# app/routers/repos.py
import json
import logging
import threading
import uuid
from collections import OrderedDict
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query as Q, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import llm
from app.config import get_settings
from app.db import SessionLocal, get_db
from app.deps import client_ip, demo_limiter, demo_total_limiter, owned_repo, search_limiter, verified_user
from app.llm import ProviderError
from app.models import Conversation, IngestEvent, Query, Repo, RepoData, User, utcnow
from app.routers.providers import provider_http_error
from app.schemas import (GITHUB_URL, MAX_COMMIT_REACH, AskIn, CommitBriefOut, ConversationOut, QueryOut,
                         RangePreviewOut, RepoIn, RepoOut, StoppedIn, SuspectsIn, SuspectsOut, TimelineIn, TimelineOut,
                         as_utc)
from app.security import decrypt_secret
from app.services import demo, github, ingest, rag
from app.services.users import credential, limits_for
from ingestion import bug_origins
from retrieval import analytics

router = APIRouter(prefix="/api/repos", tags=["repos"])
log = logging.getLogger(__name__)


def repo_out(repo: Repo) -> RepoOut:
    return RepoOut(id=repo.id, url=repo.url, full_name=repo.full_name, is_private=repo.is_private,
                   status=repo.status,
                   stage_message=repo.stage_message, error=repo.error,
                   warnings=[w for w in repo.warnings.split("\n") if w],
                   max_commits=repo.max_commits, skip_commits=repo.skip_commits or 0,
                   commit_count=repo.commit_count, pr_count=repo.pr_count,
                   created_at=as_utc(repo.created_at), ready_at=as_utc(repo.ready_at),
                   expires_at=as_utc(repo.expires_at))


def _ready_data(repo: Repo) -> RepoData:
    if repo.status != "ready" or repo.data is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This repository is still being ingested")
    return repo.data


# Parsed commit histories, most recently used last. The stored JSON is megabytes for a large repository and
# the Overview tab alone asks for it several times, so parsing it once matters on a small server.
_PARSED: OrderedDict[tuple[str, str], list[dict]] = OrderedDict()
_PARSED_MAX = 4
_parsed_lock = threading.Lock()


def _chunks(repo: Repo) -> list[dict]:
    """A ready repository's stored commits. Keyed by when it became ready, so a re-sync never serves the old ones."""
    if repo.status != "ready":
        _ready_data(repo)   # raises the "still being ingested" error
    key = (repo.id, repo.ready_at.isoformat() if repo.ready_at else "")
    with _parsed_lock:
        if key in _PARSED:
            _PARSED.move_to_end(key)
            return _PARSED[key]
    chunks = json.loads(_ready_data(repo).chunks_json)
    with _parsed_lock:
        _PARSED[key] = chunks
        while len(_PARSED) > _PARSED_MAX:
            _PARSED.popitem(last=False)
    return chunks


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


def _credential_for(db: Session, user: User) -> tuple[str, str, str]:
    """(provider, model, api_key) for the user's active provider."""
    if not user.active_provider:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect a model provider in Settings first")
    cred = credential(db, user, user.active_provider)
    if cred is None or not cred.model:
        raise HTTPException(status.HTTP_409_CONFLICT, "Choose a model in Settings first")
    return cred.provider, cred.model, decrypt_secret(cred.key_enc)


def _llm_for(db: Session, user: User):
    """Return (provider, model, generate) for the user's active provider."""
    provider, model, api_key = _credential_for(db, user)

    def generate(system: str, prompt: str) -> str:
        return llm.generate(provider, api_key, model, system, prompt)

    return provider, model, generate


def _optional_llm(db: Session, user: User):
    """Like _llm_for, but (None, None, None) when no model is connected, for features that work without one."""
    cred = credential(db, user, user.active_provider) if user.active_provider else None
    return _llm_for(db, user) if cred and cred.model else (None, None, None)


def _limit_search(user: User):
    """Searches embed the question with the server's Pinecone allowance; cap each account per hour."""
    search_limiter.check(f"search:{user.id}")


def _limit_demo(request: Request, user: User, feature: str):
    """Demo visitors share one account, so searches that cost embedding tokens are capped per visitor and overall."""
    if user.is_demo:
        demo_limiter.check(f"{feature}:{client_ip(request)}")
        demo_total_limiter.check(feature)


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


@router.get("/{repo_id}/origins")
def repo_origins(repo: Repo = Depends(owned_repo)):
    raw = _ready_data(repo).origins_json
    if raw is None:
        # Ingested before bug origins existed, or tracing failed: a re-sync computes them
        return {"computed": False, "summary": None, "fixes": []}
    fixes = json.loads(raw)
    return {"computed": True, "summary": bug_origins.summarize(fixes), "fixes": fixes}


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
    return QueryOut(id=q.id, kind=q.kind, conversation_id=q.conversation_id, question=q.question,
                    search_query=q.search_query, answer=q.answer, mode=q.mode,
                    provider=q.provider, model=q.model, sources=json.loads(q.sources_json),
                    stopped=q.stopped, created_at=as_utc(q.created_at))


def _chat_title(question: str) -> str:
    text = " ".join(question.split())
    return text if len(text) <= 80 else text[:79].rstrip() + "…"


def _owned_chat(db: Session, repo: Repo, chat_id: int) -> Conversation:
    chat = db.get(Conversation, chat_id)
    if chat is None or chat.repo_id != repo.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
    return chat


def _chat_history(db: Session, chat: Conversation | None) -> rag.History:
    if chat is None:
        return []
    recent = db.scalars(select(Query).where(Query.conversation_id == chat.id)
                        .order_by(Query.created_at.desc(), Query.id.desc()).limit(rag.HISTORY_TURNS)).all()
    return [(q.question, q.answer) for q in reversed(recent)]


def _save_exchange(db: Session, repo_id: str, chat_id: int | None, body: AskIn, provider: str, model: str,
                   answer: str, sources: list[dict], search_query: str, stopped: bool = False) -> QueryOut:
    # The chat is created only once there is an answer, so a failed first question leaves no empty chat
    chat = db.get(Conversation, chat_id) if chat_id is not None else None
    if chat is None:
        chat = Conversation(repo_id=repo_id, title=_chat_title(body.question))
        db.add(chat)
        db.flush()
    chat.updated_at = utcnow()
    q = Query(repo_id=repo_id, kind="ask", conversation_id=chat.id, question=body.question,
              search_query=search_query if search_query != body.question else None,
              answer=answer, mode=body.mode, provider=provider, model=model, sources_json=json.dumps(sources),
              stopped=stopped)
    db.add(q)
    db.commit()
    return _query_out(q)


@router.post("/{repo_id}/ask", response_model=QueryOut)
def ask(body: AskIn, repo: Repo = Depends(owned_repo),
        user: User = Depends(verified_user), db: Session = Depends(get_db)):
    _limit_search(user)
    chunks = _chunks(repo)
    chat = _owned_chat(db, repo, body.conversation_id) if body.conversation_id is not None else None
    provider, model, generate = _llm_for(db, user)
    try:
        result = rag.ask(body.question, repo.namespace, generate, mode=body.mode, only_pr=body.only_pr,
                         history=_chat_history(db, chat), chunks=chunks)
    except ProviderError as e:
        raise provider_http_error(e) from e
    return _save_exchange(db, repo.id, chat.id if chat else None, body, provider, model,
                          result["answer"], result["sources"], result["search_query"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/{repo_id}/ask/stream")
def ask_stream(body: AskIn, repo: Repo = Depends(owned_repo),
               user: User = Depends(verified_user), db: Session = Depends(get_db)):
    """Like /ask, but the answer arrives as server-sent events while the model writes it:
    `sources` (what was found), then `delta` pieces, then `done` with the saved exchange, or `error`."""
    _limit_search(user)
    chunks = _chunks(repo)
    chat = _owned_chat(db, repo, body.conversation_id) if body.conversation_id is not None else None
    provider, model_id, api_key = _credential_for(db, user)
    try:
        # A bad key, a retired model or a failed search is a normal error response, before anything streams
        model = llm.find_model(provider, api_key, model_id)
        prepared = rag.prepare(body.question, repo.namespace,
                               lambda system, prompt: llm.generate(provider, api_key, model_id, system, prompt),
                               mode=body.mode, only_pr=body.only_pr, history=_chat_history(db, chat),
                               chunks=chunks)
    except ProviderError as e:
        raise provider_http_error(e) from e
    repo_id, chat_id = repo.id, chat.id if chat else None
    searched = prepared["search_query"]

    def events():
        yield _sse("sources", {"sources": prepared["sources"],
                               "search_query": searched if searched != body.question else None})
        parts = []
        try:
            pieces = (llm.stream(provider, model, api_key, rag.SYSTEM_PROMPT, prepared["prompt"])
                      if prepared["prompt"] else iter([rag.NO_COMMITS]))
            for piece in pieces:
                parts.append(piece)
                yield _sse("delta", {"text": piece})
        except ProviderError as e:
            yield _sse("error", {"message": e.message})
            return
        except Exception:
            log.exception("Streaming an answer failed")
            yield _sse("error", {"message": "Something went wrong while writing the answer. Please try again."})
            return
        # Only a complete answer is saved; if the browser disconnects, this generator just stops.
        # The request's session isn't used here: it may already be closed when the stream ends.
        with SessionLocal() as s:
            saved = _save_exchange(s, repo_id, chat_id, body, provider, model_id, "".join(parts).strip(),
                                   prepared["sources"], searched)
        yield _sse("done", saved.model_dump(mode="json"))

    # no-cache and X-Accel-Buffering stop proxies from holding the stream back
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{repo_id}/ask/stopped", response_model=QueryOut)
def ask_stopped(body: StoppedIn, repo: Repo = Depends(owned_repo),
                user: User = Depends(verified_user), db: Session = Depends(get_db)):
    """Keep an answer the user stopped part-way: the page sends the text written so far, and it's saved to
    the chat marked as stopped, creating the chat if this was its first question."""
    _ready_data(repo)
    chat = _owned_chat(db, repo, body.conversation_id) if body.conversation_id is not None else None
    provider, model, _ = _credential_for(db, user)
    # The answer may have finished just as Stop was pressed; then keep the complete one rather than a copy
    finished = select(Query).where(Query.repo_id == repo.id, Query.kind == "ask", Query.question == body.question,
                                   Query.stopped.is_(False), Query.created_at >= utcnow() - timedelta(minutes=2))
    if chat is not None:
        finished = finished.where(Query.conversation_id == chat.id)
    if (done := db.scalars(finished.order_by(Query.id.desc()).limit(1)).first()) is not None:
        return _query_out(done)
    return _save_exchange(db, repo.id, chat.id if chat else None, body, provider, model, body.answer.strip(),
                          [s.model_dump() for s in body.sources], body.search_query or body.question, stopped=True)


@router.get("/{repo_id}/chats", response_model=list[ConversationOut])
def list_chats(repo: Repo = Depends(owned_repo), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Conversation, func.count(Query.id))
        .outerjoin(Query, Query.conversation_id == Conversation.id)
        .where(Conversation.repo_id == repo.id)
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(100))
    return [ConversationOut(id=c.id, title=c.title, questions=n, created_at=as_utc(c.created_at),
                            updated_at=as_utc(c.updated_at)) for c, n in rows]


@router.get("/{repo_id}/chats/{chat_id}", response_model=list[QueryOut])
def chat_messages(chat_id: int, repo: Repo = Depends(owned_repo), db: Session = Depends(get_db)):
    chat = _owned_chat(db, repo, chat_id)
    qs = db.scalars(select(Query).where(Query.conversation_id == chat.id)
                    .order_by(Query.created_at.asc(), Query.id.asc()))
    return [_query_out(q) for q in qs]


@router.delete("/{repo_id}/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(chat_id: int, repo: Repo = Depends(owned_repo), db: Session = Depends(get_db)):
    db.delete(_owned_chat(db, repo, chat_id))
    db.commit()


@router.get("/{repo_id}/queries", response_model=list[QueryOut])
def list_queries(repo: Repo = Depends(owned_repo), db: Session = Depends(get_db)):
    qs = db.scalars(select(Query).where(Query.repo_id == repo.id, Query.kind == "ask")
                    .order_by(Query.created_at.asc(), Query.id.asc()).limit(100))
    return [_query_out(q) for q in qs]


@router.delete("/{repo_id}/queries", status_code=status.HTTP_204_NO_CONTENT)
def clear_queries(repo: Repo = Depends(owned_repo), db: Session = Depends(get_db)):
    for chat in db.scalars(select(Conversation).where(Conversation.repo_id == repo.id)):
        db.delete(chat)
    for q in db.scalars(select(Query).where(Query.repo_id == repo.id)):
        db.delete(q)
    db.commit()


@router.post("/{repo_id}/suspects", response_model=SuspectsOut)
def suspects(body: SuspectsIn, request: Request, repo: Repo = Depends(owned_repo),
             user: User = Depends(verified_user), db: Session = Depends(get_db)):
    data = _ready_data(repo)
    _limit_demo(request, user, "suspects")
    _limit_search(user)
    # The ranking needs no model; an explanation is added when one is connected
    provider, model, generate = _optional_llm(db, user)
    try:
        result = rag.find_suspects(body.description, repo.namespace, _chunks(repo),
                                   json.loads(data.origins_json) if data.origins_json else None,
                                   body.since.isoformat() if body.since else None, generate)
    except ProviderError as e:
        raise provider_http_error(e) from e
    return SuspectsOut(**result, provider=provider, model=model)


@router.post("/{repo_id}/timeline", response_model=TimelineOut)
def timeline(body: TimelineIn, repo: Repo = Depends(owned_repo),
             user: User = Depends(verified_user), db: Session = Depends(get_db)):
    chunks = _chunks(repo)
    if not analytics.file_timeline(chunks, body.path, body.match):
        return TimelineOut(path=body.path, answer=None, provider=None, model=None, entries=[])
    # The commit list needs no model; the written summary is added when one is connected
    provider, model, generate = _optional_llm(db, user)
    try:
        result = rag.timeline(body.path, chunks, generate, body.match)
    except ProviderError as e:
        raise provider_http_error(e) from e
    return TimelineOut(path=body.path, answer=result["answer"], provider=provider if generate else None,
                       model=model if generate else None, entries=result["entries"])


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
