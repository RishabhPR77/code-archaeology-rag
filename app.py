# app.py
import os

from dotenv import load_dotenv
load_dotenv()

import json
import git
import streamlit as st
import plotly.express as px
import pandas as pd
from pathlib import Path

from ingestion.git_loader import load_commits
from ingestion.chunker import build_chunks
from ingestion.github_enricher import fetch_prs, FetchResult
from storage.vector_store import VectorStore
from retrieval.graph import CommitGraph
from query.engine import ask, timeline_ask

from utils.rate_limiter import (
    can_ingest, record_ingestion,
    can_query, record_query,
    get_usage_display
)

# ---------------------------------------------------------------
# Auto cleanup — delete Pinecone namespaces after TTL expires
# ---------------------------------------------------------------
import hmac
import secrets
import uuid
import urllib.request
import urllib.parse

from pinecone.exceptions import NotFoundException

TTL_SECONDS = 3 * 60 * 60  # 3 hours

def _redis(method: str, *args):
    url   = os.getenv("UPSTASH_REDIS_REST_URL", "").rstrip("/")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
    if not url or not token:
        return None
    endpoint = url + "/" + "/".join(urllib.parse.quote(str(a), safe="") for a in [method, *args])
    req = urllib.request.Request(endpoint, headers={"Authorization": f"Bearer {token}"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read()).get("result")
    except Exception:
        return None

def chunks_path_for(key: str) -> str:
    return f"./data/raw/{key}_chunks.json"

def register_namespace_for_cleanup(namespace: str):
    """Store namespace in Redis with TTL so it gets cleaned up later."""
    _redis("SET", f"ca:ns:{namespace}", "1", "EX", TTL_SECONDS)
    # Permanent set of everything registered — the TTL key alone vanishes on expiry
    _redis("SADD", "ca:ns:all", namespace)

def unregister_namespace(namespace: str):
    """Stop tracking a namespace the user deleted by hand."""
    _redis("DEL", f"ca:ns:{namespace}")
    _redis("SREM", "ca:ns:all", namespace)

def run_cleanup():
    """On app load — delete Pinecone namespaces whose TTL key has expired."""
    try:
        for ns in _redis("SMEMBERS", "ca:ns:all") or []:
            # 0 = TTL expired. None = Redis unreachable, so never delete on doubt
            if _redis("EXISTS", f"ca:ns:{ns}") != 0:
                continue
            try:
                VectorStore(collection_name=ns).delete_namespace()
            except NotFoundException:
                pass  # already gone
            except Exception:
                continue  # Pinecone hiccup — retry on a later session
            Path(chunks_path_for(ns)).unlink(missing_ok=True)
            _redis("SREM", "ca:ns:all", ns)
    except Exception:
        pass

ADMIN_TOKEN_TTL = 24 * 60 * 60  # 1 day

def is_admin() -> bool:
    """Returns True if user has entered the admin password this session."""
    # Check session state first, then the admin token in query params (cross-tab)
    if st.session_state.get("is_admin", False):
        return True
    token = st.query_params.get("admin")
    if token and _redis("GET", f"ca:admin:{token}") == "1":
        st.session_state.is_admin = True
        return True
    return False

def grant_admin(pw: str) -> bool:
    """Check the password; on success put a random token (never the password) in the URL."""
    expected = os.getenv("ADMIN_PASSWORD", "")
    if not expected or not hmac.compare_digest(pw.encode(), expected.encode()):
        return False
    st.session_state.is_admin = True
    token = secrets.token_urlsafe(16)
    if _redis("SET", f"ca:admin:{token}", "1", "EX", ADMIN_TOKEN_TTL) == "OK":
        st.query_params["admin"] = token
    return True

def _check_limits(commit_count=None):
    """Returns (allowed, msg). Bypasses limits for admin."""
    if is_admin():
        return True, ""
    if commit_count is not None:
        return can_ingest(commit_count)
    return can_query()


# ---------------------------------------------------------------
# Page config
# ---------------------------------------------------------------
st.set_page_config(
    page_title="Code Archaeologist",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ---------------------------------------------------------------
# Global styles
# ---------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');

section[data-testid="stSidebar"] { display: none !important; }
#MainMenu, footer, header { visibility: hidden; }

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background-color: #0d0d0f;
    color: #e8e6e0;
}

.block-container {
    padding: 0 3rem 2rem 3rem !important;
    max-width: 1200px !important;
}

/* Nav logo */
.nav-logo {
    font-family: 'DM Mono', monospace;
    font-size: 0.95rem;
    font-weight: 500;
    color: #e8e6e0;
    letter-spacing: 0.05em;
    line-height: 1;
    padding-top: 0.1rem;
}

/* Nav border line under the whole first row */
[data-testid="stHorizontalBlock"]:first-of-type {
    border-bottom: 1px solid #222226;
    padding-bottom: 0.6rem;
    margin-bottom: 1.8rem;
    align-items: center !important;
}

/* Radio nav - hide the widget label */
[data-testid="stRadio"] > label { display: none !important; }

/* Radio group: horizontal flex row */
[data-testid="stRadio"] > div[role="radiogroup"] {
    display: flex !important;
    flex-direction: row !important;
    gap: 0.1rem !important;
    flex-wrap: nowrap !important;
    align-items: center !important;
    padding-top: 0 !important;
}

/* Hide the radio circle */
[data-baseweb="radio"] > div:first-child { display: none !important; }

/* Style each option label as a nav tab */
[data-baseweb="radio"] > div:last-child {
    padding: 0.35rem 0.85rem !important;
    border-radius: 6px !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    color: #555 !important;
    cursor: pointer !important;
    transition: all 0.15s !important;
    white-space: nowrap !important;
    line-height: 1 !important;
}

[data-baseweb="radio"]:hover > div:last-child {
    color: #e8e6e0 !important;
    background: #1a1a1e !important;
}

/* Active / selected tab */
[data-baseweb="radio"]:has(input:checked) > div:last-child {
    color: #c4b5fd !important;
    background: rgba(127,119,221,0.12) !important;
}

/* Repo pill */
.repo-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background: #1a1a1e;
    border: 1px solid #2a2a30;
    border-radius: 20px;
    padding: 0.3rem 0.9rem 0.3rem 0.65rem;
    font-family: 'DM Mono', monospace;
    font-size: 0.75rem;
    color: #888;
    margin-bottom: 2rem;
}
.repo-pill-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #4ade80;
    display: inline-block;
    flex-shrink: 0;
}
.repo-pill-name { color: #c4b5fd; }

/* Page title */
.page-title {
    font-size: 2rem;
    font-weight: 600;
    color: #e8e6e0;
    margin-bottom: 0.4rem;
    letter-spacing: -0.02em;
}
.page-sub {
    font-size: 0.9rem;
    color: #555;
    margin-bottom: 2rem;
}

/* Cards */
.stat-card {
    background: #111115;
    border: 1px solid #1e1e24;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
}
.stat-label {
    font-size: 0.75rem;
    color: #555;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.4rem;
    font-family: 'DM Mono', monospace;
}
.stat-value {
    font-size: 1.6rem;
    font-weight: 600;
    color: #e8e6e0;
}

/* Answer box */
.answer-box {
    background: #111115;
    border: 1px solid #1e1e24;
    border-left: 3px solid #7F77DD;
    border-radius: 0 12px 12px 0;
    padding: 1.5rem;
    margin: 1rem 0;
    font-size: 0.95rem;
    line-height: 1.75;
    color: #d4d2cc;
}

/* Source card */
.source-card {
    background: #111115;
    border: 1px solid #1e1e24;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.6rem;
    font-size: 0.82rem;
}
.source-author {
    font-family: 'DM Mono', monospace;
    color: #7F77DD;
    font-size: 0.78rem;
}
.source-score {
    float: right;
    color: #1D9E75;
    font-family: 'DM Mono', monospace;
    font-size: 0.78rem;
}

/* Inputs */
.stTextInput input {
    background: #111115 !important;
    border: 1px solid #2a2a30 !important;
    border-radius: 8px !important;
    color: #e8e6e0 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.9rem !important;
    padding: 0.6rem 1rem !important;
}
.stTextInput input:focus {
    border-color: #7F77DD !important;
    box-shadow: 0 0 0 2px rgba(127,119,221,0.15) !important;
}

/* Action Buttons */
.stButton button {
    background: #7F77DD !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    padding: 0.5rem 1.5rem !important;
    transition: background 0.15s !important;
}
.stButton button:hover {
    background: #6a62c4 !important;
}

/* Delete button - scoped via wrapper div */
.delete-btn .stButton button {
    background: transparent !important;
    border: 1px solid #3d1f1f !important;
    color: #e05252 !important;
}
.delete-btn .stButton button:hover {
    background: #2a1010 !important;
    border-color: #e05252 !important;
    color: #e05252 !important;
}

/* Selectbox */
.stSelectbox div[data-baseweb="select"] > div {
    background: #111115 !important;
    border: 1px solid #2a2a30 !important;
    border-radius: 8px !important;
    color: #e8e6e0 !important;
}

/* Slider */
.stSlider [data-baseweb="slider"] {
    padding: 0 !important;
}

/* Divider */
hr { border-color: #1e1e24 !important; }

/* Expander */
.streamlit-expanderHeader {
    background: #111115 !important;
    border: 1px solid #1e1e24 !important;
    border-radius: 8px !important;
    font-size: 0.85rem !important;
    color: #aaa !important;
}

/* Dataframe */
.stDataFrame { border-radius: 10px !important; overflow: hidden; }

/* Status */
.stAlert {
    background: #111115 !important;
    border: 1px solid #1e1e24 !important;
    border-radius: 10px !important;
}

/* Checkbox */
.stCheckbox label { font-size: 0.85rem !important; color: #888 !important; }
</style>
""", unsafe_allow_html=True)

REPOS_INDEX = "./data/repos.json"

# ---------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------
def load_registry() -> dict:
    if Path(REPOS_INDEX).exists():
        with open(REPOS_INDEX) as f:
            return json.load(f)
    return {}

def save_registry(registry: dict):
    Path("./data").mkdir(exist_ok=True)
    with open(REPOS_INDEX, "w") as f:
        json.dump(registry, f, indent=2)

def repo_key(repo_url: str) -> str:
    parts = repo_url.rstrip("/").split("/")
    return parts[-2] + "_" + parts[-1]

def session_key(repo_url: str) -> str:
    """Per-session key so users never share (or delete) each other's namespace."""
    return f"{repo_key(repo_url)}_{st.session_state.session_id}"

def ingest_repo(repo_url: str, max_commits: int) -> str:
    key         = session_key(repo_url)
    clone_path  = f"./data/repos/{repo_key(repo_url)}"  # clone is read-only, safe to share
    chunks_path = chunks_path_for(key)

    if not Path(clone_path).exists():
        st.write(f"Cloning {repo_url}...")
        git.Repo.clone_from(repo_url, clone_path)
    else:
        st.write("Repo already cloned.")

    st.write(f"Extracting {max_commits} commits...")
    commits = load_commits(clone_path, max_count=max_commits)

    repo_name = repo_url.replace("https://github.com/", "").rstrip("/")
    st.write("Fetching pull requests and review comments...")
    prs = []
    try:
        fetch_result = fetch_prs(repo_name, max_prs=200)
        prs = fetch_result.prs
        for w in fetch_result.warnings:
            st.warning(w)
    except Exception as e:
        st.warning(f"PR fetch failed: {e}. Continuing without PR data.")

    chunks = build_chunks(commits, pull_requests=prs)

    Path("./data/raw").mkdir(parents=True, exist_ok=True)
    with open(chunks_path, "w") as f:
        json.dump(chunks, f, indent=2)

    st.write("Embedding and storing in Pinecone...")
    store = VectorStore(collection_name=key)
    store.ingest(chunks)

    # Save to session state registry (per-user, not shared)
    if "registry" not in st.session_state:
        st.session_state.registry = {}
    st.session_state.registry[key] = {
        "url":         repo_url,
        "key":         key,
        "chunks_path": chunks_path,
        "clone_path":  clone_path,
        "commits":     len(chunks),
        "max_commits": max_commits,
    }
    # Register for auto cleanup after TTL expires
    register_namespace_for_cleanup(key)
    return key

# ---------------------------------------------------------------
# State
# ---------------------------------------------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex[:8]

if "page" not in st.session_state:
    st.session_state.page = "ingest"
    run_cleanup()  # clean up expired namespaces on fresh session

# Registry is per-session — not shared across users
if "registry" not in st.session_state:
    st.session_state.registry = {}

registry  = st.session_state.registry
repo_keys = list(registry.keys())

if "active_key" not in st.session_state:
    st.session_state.active_key = repo_keys[0] if repo_keys else None

active_key         = st.session_state.active_key
active_chunks_path = registry[active_key]["chunks_path"] if active_key else None

# ---------------------------------------------------------------
# Nav bar
# ---------------------------------------------------------------
pages = [
    ("ingest",   "Ingest"),
    ("ask",      "Ask"),
    ("timeline", "Timeline"),
    ("hotfiles", "Hot Files"),
    ("cochange", "Co-Change"),
    ("authors",  "Authors"),
    ("prs",      "Pull Requests"),
]

page_keys   = [k for k, _ in pages]
page_labels = {k: l for k, l in pages}
current_idx = page_keys.index(st.session_state.page) if st.session_state.page in page_keys else 0

logo_col, radio_col, admin_col = st.columns([2, 6, 1])
with logo_col:
    st.markdown('<div class="nav-logo">code-archaeologist</div>', unsafe_allow_html=True)
with admin_col:
    if not is_admin():
        pw = st.text_input("", placeholder="admin", type="password",
                           label_visibility="collapsed", key="admin_pw_input")
        if pw and grant_admin(pw):
            st.rerun()
    else:
        st.markdown('<div style="font-size:11px;color:#1D9E75;padding-top:6px;">✓ admin</div>',
                    unsafe_allow_html=True)
with radio_col:
    selected_page = st.radio(
        "nav",
        options=page_keys,
        format_func=lambda k: page_labels[k],
        horizontal=True,
        label_visibility="collapsed",
        index=current_idx,
    )

if selected_page != st.session_state.page:
    st.session_state.page = selected_page
    st.rerun()

page = st.session_state.page

# Active repo pill
if active_key:
    short_url = registry[active_key]["url"].replace("https://github.com/", "")
    st.markdown(
        f'<div class="repo-pill">'
        f'<span class="repo-pill-dot"></span>'
        f'<span class="repo-pill-name">{short_url}</span>'
        f'&nbsp;·&nbsp; {registry[active_key]["commits"]} commits'
        f'</div>',
        unsafe_allow_html=True
    )

# ---------------------------------------------------------------
# Page: Ingest
# ---------------------------------------------------------------
if page == "ingest":
    st.markdown('<div class="page-title">Ingest a Repository</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Paste any public GitHub URL. The system extracts commits, embeds them, and makes them queryable.</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        repo_url = st.text_input("GitHub URL", placeholder="https://github.com/pallets/flask", label_visibility="collapsed")
    with col2:
        max_commits = st.selectbox("Commits", [50, 100], index=1, label_visibility="collapsed")

    st.caption("50 commits ~ 2min   |   100 commits ~ 4min   |   Free demo limit: 100 commits")

    if st.button("Ingest Repository"):
        if not repo_url:
            st.warning("Please enter a GitHub URL.")
        else:
            allowed, msg = _check_limits(max_commits)
            if not allowed:
                st.error(msg)
            else:    
                try:
                    with st.status("Ingesting...", expanded=True):
                        key = ingest_repo(repo_url.strip(), max_commits)
                        st.session_state.active_key = key
                    record_ingestion(max_commits)
                    st.success("Done. Select Ask from the nav to start querying.")
                    st.balloons()
                except Exception as e:
                    st.error(f"Failed: {e}")

    if registry:
        st.divider()
        st.markdown("**Previously ingested**")
        for k, v in registry.items():
            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                st.markdown(f"`{v['url']}` - {v['commits']} commits")
            with col2:
                if st.session_state.get(f"confirm_switch_{k}"):
                    st.warning("Switch to this repo?")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Yes", key=f"switch_yes_{k}"):
                            st.session_state.active_key = k
                            st.session_state.page = "ask"
                            del st.session_state[f"confirm_switch_{k}"]
                            st.rerun()
                    with c2:
                        if st.button("No", key=f"switch_no_{k}"):
                            del st.session_state[f"confirm_switch_{k}"]
                            st.rerun()
                else:
                    if st.button("Switch", key=f"switch_{k}"):
                        st.session_state[f"confirm_switch_{k}"] = True
                        st.rerun()
            with col3:
                if st.session_state.get(f"confirm_delete_{k}"):
                    st.warning("Sure? This deletes all data.")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Yes", key=f"delete_yes_{k}"):
                            try:
                                vs = VectorStore(collection_name=k)
                                vs.delete_namespace()
                            except Exception:
                                pass
                            unregister_namespace(k)
                            # Clone is shared with other sessions, so it stays
                            chunks_path = v.get("chunks_path")
                            if chunks_path and Path(chunks_path).exists():
                                Path(chunks_path).unlink(missing_ok=True)
                            registry.pop(k)
                            st.session_state.registry = registry
                            if st.session_state.active_key == k:
                                remaining = list(registry.keys())
                                st.session_state.active_key = remaining[0] if remaining else None
                            del st.session_state[f"confirm_delete_{k}"]
                            st.rerun()
                    with c2:
                        if st.button("No", key=f"delete_no_{k}"):
                            del st.session_state[f"confirm_delete_{k}"]
                            st.rerun()
                else:
                    if st.button("Delete", key=f"delete_{k}"):
                        st.session_state[f"confirm_delete_{k}"] = True
                        st.rerun()

# ---------------------------------------------------------------
# Page: Ask
# ---------------------------------------------------------------
elif page == "ask":
    st.markdown('<div class="page-title">Ask</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Ask anything about this repository\'s commit history in plain English.</div>', unsafe_allow_html=True)

    if not active_key:
        st.warning("No repository ingested yet. Go to Ingest.")
        st.stop()

    # ── Suggested questions ──────────────────────────────────────
    SUGGESTIONS = [
        "What are the most significant changes made recently?",
        "Which part of the codebase changed the most?",
        "What bugs were fixed and by whom?",
        "Summarize what each author worked on.",
        "Were there any major refactors or cleanups?",
        "What new features were added?",
        "Which files are most error-prone based on fix commits?",
        "What did the team work on this month?",
    ]

    if "ask_question" not in st.session_state:
        st.session_state.ask_question = ""
    if "ask_history" not in st.session_state:
        st.session_state.ask_history = []

    st.markdown("**Suggested questions**")
    cols = st.columns(4)
    for i, suggestion in enumerate(SUGGESTIONS):
        with cols[i % 4]:
            if st.button(suggestion, key=f"sug_{i}", use_container_width=True):
                st.session_state.question_input = suggestion
                st.rerun()

    st.markdown("<div style='margin-top:1.2rem'></div>", unsafe_allow_html=True)

    # ── Input ────────────────────────────────────────────────────
    col_q, col_btn = st.columns([5, 1])
    with col_q:
        question = st.text_input(
            "Question",
            placeholder="e.g. Why was the auth module refactored?",
            label_visibility="collapsed",
            key="question_input"
        )
    with col_btn:
        ask_clicked = st.button("Ask →", use_container_width=True)

    col1, col2 = st.columns([2, 1])
    with col1:
        only_pr = st.checkbox("Only commits with linked PRs")
    with col2:
        mode = st.selectbox("Mode", ["Detailed", "Quick summary", "Bullet points"], label_visibility="collapsed")

    # ── Run query ────────────────────────────────────────────────
    if ask_clicked and question:
        st.session_state.ask_question = ""

        allowed, msg = _check_limits()
        if not allowed:
            st.warning(msg)
            st.stop()

        mode_prompt = {
            "Detailed":       "",
            "Quick summary":  " Answer in 2-3 sentences only.",
            "Bullet points":  " Answer as a concise bullet point list.",
        }.get(mode, "")

        full_question = question + mode_prompt
        filters = {"has_pr": True} if only_pr else None

        with st.spinner("Searching commits and generating answer..."):
            result = ask(full_question, top_k=8, filters=filters, collection_name=active_key)

        record_query()   # record after success

        usage = get_usage_display()
        st.caption(f"{usage['queries_left']} free questions remaining today. Resets at midnight.")

        st.session_state.ask_history.insert(0, {
            "question": question,
            "answer":   result["answer"],
            "mode":     mode,
        })
        st.session_state.ask_history = st.session_state.ask_history[:10]

    # ── Show history ─────────────────────────────────────────────
    if st.session_state.ask_history:
        for i, item in enumerate(st.session_state.ask_history):
            with st.expander(f"{'▶ ' if i == 0 else ''}Q: {item['question']}", expanded=(i == 0)):
                badge_color = {"Detailed": "#7F77DD", "Quick summary": "#1D9E75", "Bullet points": "#378ADD"}.get(item["mode"], "#888")
                st.markdown(
                    f'<span style="display:inline-block;padding:2px 10px;border-radius:20px;'
                    f'font-size:10px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;'
                    f'background:{badge_color}22;color:{badge_color};margin-bottom:10px;">'
                    f'{item["mode"]}</span>',
                    unsafe_allow_html=True
                )
                st.markdown(f'<div class="answer-box">{item["answer"]}</div>', unsafe_allow_html=True)

        if st.button("Clear history"):
            st.session_state.ask_history = []
            st.rerun()

# ---------------------------------------------------------------
# Page: Timeline
# ---------------------------------------------------------------
elif page == "timeline":
    st.markdown('<div class="page-title">File Timeline</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Trace how any file evolved with an LLM summary of every change.</div>', unsafe_allow_html=True)

    if not active_key:
        st.warning("No repository ingested yet.")
        st.stop()

    filename = st.text_input("File name", placeholder="sessions.py", label_visibility="collapsed")

    if st.button("Trace Evolution"):
        if not filename:
            st.warning("Enter a file name.")
        else:
            with st.spinner(f"Building timeline for {filename}..."):
                result = timeline_ask(filename, chunks_path=active_chunks_path)

            if not result["timeline"]:
                st.warning(f"No commits found touching `{filename}`")
            else:
                st.markdown(f'<div class="answer-box">{result["answer"]}</div>', unsafe_allow_html=True)

                st.divider()
                st.markdown(f"**{len(result['timeline'])} commits found**")

                df = pd.DataFrame(result["timeline"])
                df["date"]    = pd.to_datetime(df["timestamp"]).dt.date
                df["message"] = df["message"].str[:80]
                st.dataframe(df[["date", "author", "message", "has_pr"]], use_container_width=True, hide_index=True)

                df["month"] = pd.to_datetime(df["timestamp"]).dt.to_period("M").astype(str)
                monthly = df.groupby("month").size().reset_index(name="commits")
                fig = px.bar(monthly, x="month", y="commits",
                             color_discrete_sequence=["#7F77DD"],
                             labels={"month": "", "commits": "Commits"})
                fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                                  font_color="#888", margin=dict(l=0, r=0, t=20, b=0))
                st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------
# Page: Graph
# ---------------------------------------------------------------
# ---------------------------------------------------------------
# Page: Hot Files
# ---------------------------------------------------------------
elif page == "hotfiles":
    st.markdown('<div class="page-title">Hot Files</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Files changed most frequently, the core of the codebase.</div>', unsafe_allow_html=True)

    if not active_key:
        st.warning("No repository ingested yet.")
        st.stop()

    graph = CommitGraph(chunks_path=active_chunks_path)
    top_n = st.slider("Files to show", 5, 30, 15)
    data  = graph.hottest_files(top_n=top_n)
    df    = pd.DataFrame(data)

    fig = px.bar(df.sort_values("change_count"), x="change_count", y="file",
                 orientation="h", color="change_count",
                 color_continuous_scale=["#3C3489", "#7F77DD", "#D85A30"],
                 labels={"change_count": "Times Changed", "file": ""})
    fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      coloraxis_showscale=False, height=480,
                      font_color="#888", margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------
# Page: Co-Change
# ---------------------------------------------------------------
elif page == "cochange":
    st.markdown('<div class="page-title">Co-Change Analysis</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">File pairs that are almost always changed together, reveals hidden dependencies.</div>', unsafe_allow_html=True)

    if not active_key:
        st.warning("No repository ingested yet.")
        st.stop()

    graph = CommitGraph(chunks_path=active_chunks_path)
    top_n = st.slider("Pairs to show", 5, 20, 10)
    data  = graph.co_change_analysis(top_n=top_n)

    rows = [{"File A": i["files"][0], "File B": i["files"][1], "Co-changes": i["co_changes"]} for i in data]
    df   = pd.DataFrame(rows)
    df["pair"] = df["File A"].str.split("/").str[-1] + " + " + df["File B"].str.split("/").str[-1]

    fig = px.bar(df.sort_values("Co-changes"), x="Co-changes", y="pair",
                 orientation="h", color="Co-changes",
                 color_continuous_scale=["#085041", "#1D9E75", "#9FE1CB"],
                 labels={"Co-changes": "Times Changed Together", "pair": ""})
    fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      coloraxis_showscale=False, height=420,
                      font_color="#888", margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df[["File A", "File B", "Co-changes"]], use_container_width=True, hide_index=True)

# ---------------------------------------------------------------
# Page: Authors
# ---------------------------------------------------------------
elif page == "authors":
    st.markdown('<div class="page-title">Author Breakdown</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Who built this codebase and what did they focus on?</div>', unsafe_allow_html=True)

    if not active_key:
        st.warning("No repository ingested yet.")
        st.stop()

    graph = CommitGraph(chunks_path=active_chunks_path)
    data  = graph.author_analysis()

    authors = [d["author"] for d in data]
    commits = [d["commits"] for d in data]

    main   = [(a, c) for a, c in zip(authors, commits) if c >= 3]
    others = sum(c for c in commits if c < 3)
    if others:
        main.append(("Others", others))

    col1, col2 = st.columns([1, 1])
    with col1:
        fig = px.pie(values=[c for _, c in main], names=[a for a, _ in main],
                     color_discrete_sequence=["#7F77DD","#1D9E75","#D85A30","#378ADD","#BA7517","#888780"],
                     hole=0.5)
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#888",
                          legend=dict(font=dict(color="#888")),
                          margin=dict(l=0, r=0, t=20, b=0))
        fig.update_traces(textfont_color="#fff")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("**Top contributors**")
        for author_data in data[:8]:
            with st.expander(f"{author_data['author']} - {author_data['commits']} commits"):
                for f in author_data["top_files"]:
                    st.markdown(f"`{f['file']}` - {f['changes']}x")
# ---------------------------------------------------------------
# Page: Pull Requests
# ---------------------------------------------------------------
elif page == "prs":
    st.markdown('<div class="page-title">Pull Requests</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">All pull requests found in this repository.</div>', unsafe_allow_html=True)

    if not active_key:
        st.warning("No repository ingested yet.")
        st.stop()

    # Read PR data from chunks
    import json as _json
    try:
        with open(active_chunks_path) as f:
            all_chunks = _json.load(f)
    except Exception:
        st.warning("Chunk data not found. Please re-ingest the repository.")
        st.stop()

    # Collect unique PRs
    pr_map = {}
    for chunk in all_chunks:
        meta = chunk.get("metadata", {})
        if meta.get("has_pr") and meta.get("pr_number", 0) > 0:
            pr_num = meta["pr_number"]
            if pr_num not in pr_map:
                # Extract PR title and author from chunk text
                text = chunk.get("text", "")
                pr_title = ""
                pr_author = ""
                for line in text.split("\n"):
                    if line.startswith("PR #"):
                        parts = line.split(":", 1)
                        if len(parts) > 1:
                            pr_title = parts[1].strip()
                        # Extract author from "PR #N by Author: title"
                        by_part = line.split(" by ")
                        if len(by_part) > 1:
                            pr_author = by_part[1].split(":")[0].strip()
                        break
                pr_map[pr_num] = {
                    "number":  pr_num,
                    "title":   pr_title or "No title",
                    "author":  pr_author or meta.get("author", ""),
                    "date":    meta.get("timestamp", "")[:10],
                    "labels":  meta.get("pr_labels", ""),
                    "files":   meta.get("files", ""),
                }

    if not pr_map:
        st.warning("No pull requests found for this repository.")
        if st.button("Fetch Pull Requests Now"):
            with st.status("Fetching pull requests...", expanded=True):
                repo_url = registry[active_key]["url"]
                repo_name = repo_url.replace("https://github.com/", "").rstrip("/")
                st.write(f"Querying GitHub API for merged PRs...")
                fetch_result = fetch_prs(repo_name, max_prs=200)
                for w in fetch_result.warnings:
                    st.warning(w)

                prs = fetch_result.prs
                st.write(f"Fetched {len(prs)} PRs. Rebuilding chunks...")

                clone_path = registry[active_key]["clone_path"]
                if not Path(clone_path).exists():
                    git.Repo.clone_from(repo_url, clone_path)
                # Rebuild the same commit range that was originally ingested
                max_commits = registry[active_key].get("max_commits", registry[active_key]["commits"])
                commits = load_commits(clone_path, max_count=max_commits)
                chunks = build_chunks(commits, pull_requests=prs)

                st.write("Saving updated chunks...")
                with open(active_chunks_path, "w") as f:
                    json.dump(chunks, f, indent=2)

                st.write("Updating Pinecone index...")
                store = VectorStore(collection_name=active_key)
                store.ingest(chunks, overwrite=True)
                registry[active_key]["commits"] = len(chunks)

            st.success(f"Done. {len(prs)} PRs fetched. Reloading page...")
            st.rerun()
        st.stop()

    # Stats row
    total_prs = len(pr_map)
    authors   = list(set(v["author"] for v in pr_map.values() if v["author"]))
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f'<div class="stat-card"><div class="stat-label">Total PRs</div><div class="stat-value">{total_prs}</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="stat-card"><div class="stat-label">Contributors</div><div class="stat-value">{len(authors)}</div></div>', unsafe_allow_html=True)
    with col3:
        dates = sorted([v["date"] for v in pr_map.values() if v["date"]])
        date_range = f"{dates[0]} → {dates[-1]}" if dates else "N/A"
        st.markdown(f'<div class="stat-card"><div class="stat-label">Date Range</div><div class="stat-value" style="font-size:1rem">{date_range}</div></div>', unsafe_allow_html=True)

    st.markdown("<div style='margin-top:1.5rem'></div>", unsafe_allow_html=True)

    # PR list — sorted by PR number descending (newest first)
    AUTHOR_COLORS = {
        a: c for a, c in zip(
            authors,
            ["#7F77DD", "#1D9E75", "#E24B4A", "#378ADD", "#D85A30", "#BA7517", "#D4537E"]
        )
    }

    all_pr_html = ""
    for pr_num in sorted(pr_map.keys(), reverse=True):
        pr    = pr_map[pr_num]
        color = AUTHOR_COLORS.get(pr["author"], "#888")
        labels_html = ""
        if pr["labels"]:
            for lbl in pr["labels"].split(","):
                lbl = lbl.strip()
                if lbl:
                    labels_html += f'<span style="background:#1a1a24;border:1px solid #2a2a34;border-radius:20px;padding:2px 8px;font-size:10px;color:#888;margin-left:6px;">{lbl}</span>'

        all_pr_html += f"""<div style="background:#111115;border:1px solid #1e1e24;border-radius:10px;padding:14px 18px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between;"><div style="display:flex;align-items:center;gap:12px;"><span style="color:#7F77DD;font-family:monospace;font-size:13px;font-weight:600;">#{pr_num}</span><span style="color:#e8e6e0;font-size:14px;font-weight:500;">{pr['title']}</span>{labels_html}</div><div style="display:flex;align-items:center;gap:16px;flex-shrink:0;"><span style="display:inline-flex;align-items:center;gap:6px;"><span style="width:8px;height:8px;border-radius:50%;background:{color};display:inline-block;"></span><span style="font-size:12px;color:#666;">{pr['author']}</span></span><span style="font-family:monospace;font-size:11px;color:#444;">{pr['date']}</span><span style="background:#1D9E7522;color:#1D9E75;padding:3px 10px;border-radius:20px;font-size:10px;font-weight:700;letter-spacing:.05em;">MERGED</span></div></div>"""

    st.markdown(all_pr_html, unsafe_allow_html=True)