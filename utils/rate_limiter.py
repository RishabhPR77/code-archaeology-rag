import json
import os
from datetime import datetime, date
from pathlib import Path

USAGE_FILE = "./data/usage.json"
LINKEDIN   = "https://linkedin.com/in/rishabh-ptdr"
EMAIL      = "rishabhpatidar400@gmail.com"

LIMITS = {
    "max_commits":  100,
    "max_repos":    2,
    "max_queries":  5,
}

CONTACT_MSG = (
    f"This is a free demo — limits exist to keep it live for everyone. "
    f"Interested in the full version or want to collaborate? "
    f"Reach out on [LinkedIn]({LINKEDIN}) or at {EMAIL}"
)


def _load() -> dict:
    if Path(USAGE_FILE).exists():
        with open(USAGE_FILE) as f:
            return json.load(f)
    return {}


def _save(data: dict):
    Path("./data").mkdir(exist_ok=True)
    with open(USAGE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _get_ip() -> str:
    """Get visitor IP from Streamlit headers."""
    try:
        import streamlit as st
        headers = st.context.headers
        # Streamlit Cloud puts real IP in X-Forwarded-For
        ip = headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not ip:
            ip = headers.get("X-Real-Ip", "unknown")
        return ip or "unknown"
    except Exception:
        return "unknown"


def _record(ip: str) -> dict:
    """Get or create usage record for this IP."""
    data   = _load()
    today  = str(date.today())
    if ip not in data:
        data[ip] = {
            "commits_ingested": 0,
            "repos_ingested":   0,
            "queries_today":    0,
            "query_date":       today,
            "first_seen":       datetime.now().isoformat(),
        }
    # Reset daily query count if it's a new day
    if data[ip]["query_date"] != today:
        data[ip]["queries_today"] = 0
        data[ip]["query_date"]    = today
    return data, ip


# ------------------------------------------------------------------
# Public interface
# ------------------------------------------------------------------

def can_ingest(commit_count: int) -> tuple[bool, str]:
    """
    Returns (allowed, message).
    Checks both repo limit and commit limit for this IP.
    """
    ip       = _get_ip()
    data, ip = _record(ip)
    record   = data[ip]

    if record["repos_ingested"] >= LIMITS["max_repos"]:
        return False, (
            f"You have already ingested a repository from this device. "
            f"The free demo allows 1 repository per user.\n\n{CONTACT_MSG}"
        )

    if commit_count > LIMITS["max_commits"]:
        return False, (
            f"The free demo supports up to {LIMITS['max_commits']} commits. "
            f"You requested {commit_count}. Please lower the commit count.\n\n{CONTACT_MSG}"
        )

    return True, ""


def record_ingestion(commit_count: int):
    """Call this after successful ingestion."""
    ip       = _get_ip()
    data, ip = _record(ip)
    data[ip]["commits_ingested"] += commit_count
    data[ip]["repos_ingested"]   += 1
    _save(data)


def can_query() -> tuple[bool, str]:
    """
    Returns (allowed, message).
    Checks daily query limit for this IP.
    """
    ip       = _get_ip()
    data, ip = _record(ip)
    record   = data[ip]

    if record["queries_today"] >= LIMITS["max_queries"]:
        return False, (
            f"You have used all {LIMITS['max_queries']} free questions for today. "
            f"Limits reset at midnight.\n\n{CONTACT_MSG}"
        )

    return True, ""


def record_query():
    """Call this after a successful query."""
    ip       = _get_ip()
    data, ip = _record(ip)
    data[ip]["queries_today"] += 1
    _save(data)


def get_usage_display() -> dict:
    """Returns current IP's usage stats for display in the UI."""
    ip       = _get_ip()
    data, ip = _record(ip)
    r        = data[ip]
    return {
        "queries_used":     r["queries_today"],
        "queries_left":     max(0, LIMITS["max_queries"] - r["queries_today"]),
        "repos_used":       r["repos_ingested"],
        "can_ingest_more":  r["repos_ingested"] < LIMITS["max_repos"],
    }