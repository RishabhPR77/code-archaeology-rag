# utils/rate_limiter.py
import os
import json
from datetime import date
import urllib.request
import urllib.parse

LINKEDIN  = "https://linkedin.com/in/rishabh-ptdr"
EMAIL     = "rishabhpatidar400@gmail.com"

LIMITS = {
    "max_commits": 100,
    "max_repos":   2,
    "max_queries": 5,
}

CONTACT_MSG = (
    f"This is a free demo — limits exist to keep it live for everyone. "
    f"Interested in the full version or want to collaborate? "
    f"Reach out on [LinkedIn]({LINKEDIN}) or at {EMAIL}"
)

# ── Upstash Redis REST client (no extra library needed) ────────────
def _redis(method: str, *args):
    url   = os.getenv("UPSTASH_REDIS_REST_URL", "").rstrip("/")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
    if not url or not token:
        return None
    endpoint = url + "/" + "/".join(urllib.parse.quote(str(a), safe="") for a in [method, *args])
    req = urllib.request.Request(
        endpoint,
        headers={"Authorization": f"Bearer {token}"},
        method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read()).get("result")
    except Exception:
        return None


def _get_ip() -> str:
    try:
        import streamlit as st
        headers = st.context.headers
        ip = headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not ip:
            ip = headers.get("X-Real-Ip", "unknown")
        return ip or "unknown"
    except Exception:
        return "unknown"


def _key(ip: str, field: str) -> str:
    safe = ip.replace(":", "_").replace(".", "_")
    return f"ca:{safe}:{field}"


def _get_int(ip: str, field: str) -> int:
    val = _redis("GET", _key(ip, field))
    try:
        return int(val) if val is not None else 0
    except Exception:
        return 0


def _incr(ip: str, field: str):
    _redis("INCR", _key(ip, field))


def _get_query_date(ip: str) -> str:
    val = _redis("GET", _key(ip, "query_date"))
    return val or ""


def _set_query_date(ip: str, d: str):
    _redis("SET", _key(ip, "query_date"), d)


def _reset_queries(ip: str):
    _redis("SET", _key(ip, "queries_today"), 0)


# ── Public interface ───────────────────────────────────────────────

def can_ingest(commit_count: int) -> tuple[bool, str]:
    ip = _get_ip()

    repos = _get_int(ip, "repos_ingested")
    if repos >= LIMITS["max_repos"]:
        return False, (
            f"You have already ingested {repos} repositories from this device. "
            f"The free demo allows {LIMITS['max_repos']} per user.\n\n{CONTACT_MSG}"
        )

    if commit_count > LIMITS["max_commits"]:
        return False, (
            f"The free demo supports up to {LIMITS['max_commits']} commits. "
            f"You requested {commit_count}. Please lower the commit count.\n\n{CONTACT_MSG}"
        )

    return True, ""


def record_ingestion(commit_count: int):
    ip = _get_ip()
    _incr(ip, "repos_ingested")
    _redis("INCRBY", _key(ip, "commits_ingested"), commit_count)


def can_query() -> tuple[bool, str]:
    ip    = _get_ip()
    today = str(date.today())

    # Reset daily count if new day
    stored_date = _get_query_date(ip)
    if stored_date != today:
        _reset_queries(ip)
        _set_query_date(ip, today)

    queries = _get_int(ip, "queries_today")
    if queries >= LIMITS["max_queries"]:
        return False, (
            f"You have used all {LIMITS['max_queries']} free questions for today. "
            f"Limits reset at midnight.\n\n{CONTACT_MSG}"
        )

    return True, ""


def record_query():
    ip    = _get_ip()
    today = str(date.today())
    stored_date = _get_query_date(ip)
    if stored_date != today:
        _reset_queries(ip)
        _set_query_date(ip, today)
    _incr(ip, "queries_today")


def get_usage_display() -> dict:
    ip    = _get_ip()
    today = str(date.today())
    stored_date = _get_query_date(ip)
    if stored_date != today:
        queries = 0
    else:
        queries = _get_int(ip, "queries_today")
    repos = _get_int(ip, "repos_ingested")
    return {
        "queries_used":    queries,
        "queries_left":    max(0, LIMITS["max_queries"] - queries),
        "repos_used":      repos,
        "can_ingest_more": repos < LIMITS["max_repos"],
    }