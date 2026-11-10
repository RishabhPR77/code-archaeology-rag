# app/routers/chats.py
"""Asking questions (answers stream as server-sent events) and the saved chats."""
import json
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import llm
from app.db import SessionLocal, get_db
from app.deps import owned_repo, verified_user
from app.llm import ProviderError
from app.models import Conversation, Query, Repo, User, utcnow
from app.routers.providers import provider_http_error
from app.schemas import AskIn, ConversationOut, QueryOut, StoppedIn, as_utc
from app.services import rag
from app.services.repo_context import credential_for, history, limit_search, llm_for, ready_data

router = APIRouter(prefix="/api/repos", tags=["chats"])
log = logging.getLogger(__name__)


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
    limit_search(user)
    chunks = history(repo)
    chat = _owned_chat(db, repo, body.conversation_id) if body.conversation_id is not None else None
    provider, model, generate = llm_for(db, user)
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
    limit_search(user)
    chunks = history(repo)
    chat = _owned_chat(db, repo, body.conversation_id) if body.conversation_id is not None else None
    provider, model_id, api_key = credential_for(db, user)
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
    ready_data(repo)
    chat = _owned_chat(db, repo, body.conversation_id) if body.conversation_id is not None else None
    provider, model, _ = credential_for(db, user)
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
