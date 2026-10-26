# app/services/ingest.py
"""Background ingestion: clone -> extract commits -> fetch PRs -> chunk -> embed."""
import json
import logging
import os
import shutil
import stat
import tempfile
import threading
from datetime import datetime, timedelta

import git

from app.config import get_settings
from app.db import SessionLocal
from app.models import Repo, RepoData, User, utcnow
from app.services import github
from ingestion.chunker import build_chunks
from ingestion.git_loader import load_commits
from ingestion.github_enricher import fetch_prs
from storage.vector_store import VectorStore

log = logging.getLogger(__name__)

TERMINAL = {"ready", "failed"}
_slots = threading.BoundedSemaphore(get_settings().max_concurrent_ingests)


def _update(repo_id: str, **fields):
    with SessionLocal() as db:
        repo = db.get(Repo, repo_id)
        if repo is None:
            raise _Cancelled()
        for k, v in fields.items():
            setattr(repo, k, v)
        db.commit()


class _Cancelled(Exception):
    """The repo was deleted while its ingest was running."""


def _rmtree(path: str):
    # git marks pack files read-only, which rmtree can't delete on Windows
    def _force(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onexc=_force)


def run_ingest(repo_id: str):
    settings = get_settings()
    with SessionLocal() as db:
        repo = db.get(Repo, repo_id)
        if repo is None:
            return
        user = db.get(User, repo.user_id)
        user_token = None
        if user and user.github_token_enc:
            try:
                user_token = github.user_token(db, user)
            except github.GitHubNotConnected:
                user_token = None
        url, full_name, namespace, max_commits = repo.url, repo.full_name, repo.namespace, repo.max_commits
        private = repo.is_private
    api_token = user_token or settings.github_token or None

    _update(repo_id, status="queued", stage_message="Waiting for a free ingest slot", error=None)
    if private and not user_token:
        _update(repo_id, status="failed", stage_message="Failed",
                error="This is a private repository. Connect GitHub in Settings, then use Re-sync.")
        return
    tmp = None
    try:
        with _slots:
            _update(repo_id, status="cloning", stage_message=f"Cloning {full_name}")
            tmp = tempfile.mkdtemp(prefix="ca-clone-")
            # Shallow clone: twice the window so every ingested commit still has its parent.
            # Private repos authenticate through the environment, never the URL.
            git.Repo.clone_from(url, tmp, depth=max_commits * 2, single_branch=True, no_tags=True,
                                env=github.git_auth_env(user_token) if private else {"GIT_TERMINAL_PROMPT": "0"})

            _update(repo_id, status="extracting", stage_message=f"Reading the last {max_commits} commits")
            commits = load_commits(tmp, max_count=max_commits)
            if not commits:
                raise RuntimeError("No commits could be read from this repository.")

            _update(repo_id, status="fetching_prs", stage_message="Fetching pull requests and reviews")
            prs, warnings = [], []
            try:
                oldest = min(datetime.fromisoformat(c.timestamp) for c in commits)
                result = fetch_prs(full_name, max_prs=min(200, max_commits * 2), token=api_token, since=oldest)
                prs, warnings = result.prs, result.warnings
            except Exception as e:
                warnings.append(f"Pull requests unavailable ({e}). Answers use commit data only.")

            chunks = build_chunks(commits, pull_requests=prs)

            _update(repo_id, status="embedding",
                    stage_message=f"Embedding {len(chunks)} commits", warnings="\n".join(warnings))
            VectorStore(namespace).ingest(chunks, overwrite=True)

            with SessionLocal() as db:
                repo = db.get(Repo, repo_id)
                if repo is None:
                    raise _Cancelled()
                if repo.data is None:
                    repo.data = RepoData(repo_id=repo_id, chunks_json=json.dumps(chunks))
                else:
                    repo.data.chunks_json = json.dumps(chunks)
                repo.status = "ready"
                repo.stage_message = "Ready"
                repo.commit_count = len(chunks)
                repo.pr_count = len({c["metadata"]["pr_number"] for c in chunks if c["metadata"]["pr_number"]})
                repo.ready_at = utcnow()
                if settings.repo_ttl_hours > 0:
                    repo.expires_at = utcnow() + timedelta(hours=settings.repo_ttl_hours)
                db.commit()
    except _Cancelled:
        VectorStore(namespace).delete_namespace()
    except Exception as e:
        log.exception("Ingest failed for %s", full_name)
        message = str(e).strip().splitlines()[0][:300] if str(e).strip() else type(e).__name__
        if isinstance(e, git.GitCommandError):
            message = ("Couldn't clone this private repository. Check that the GitHub App still has access to it."
                       if private else "Couldn't clone the repository. Check that it exists and is public.")
        try:
            _update(repo_id, status="failed", stage_message="Failed", error=message)
        except _Cancelled:
            pass
    finally:
        if tmp:
            _rmtree(tmp)


def mark_interrupted():
    """On startup, jobs that were mid-flight when the server stopped can't resume."""
    with SessionLocal() as db:
        for repo in db.query(Repo).filter(Repo.status.notin_(TERMINAL)):
            repo.status = "failed"
            repo.stage_message = "Failed"
            repo.error = "Ingestion was interrupted by a server restart. Use Re-sync to try again."
        db.commit()


def delete_repo_data(repo: Repo):
    """Remove a repo's vectors; the caller deletes the row."""
    try:
        VectorStore(repo.namespace).delete_namespace()
    except Exception:
        log.exception("Couldn't delete vectors for %s", repo.namespace)


def cleanup_expired() -> int:
    with SessionLocal() as db:
        expired = db.query(Repo).filter(Repo.expires_at.is_not(None), Repo.expires_at < utcnow()).all()
        for repo in expired:
            delete_repo_data(repo)
            db.delete(repo)
        db.commit()
        return len(expired)
