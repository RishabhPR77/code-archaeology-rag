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
from storage.vector_store import VectorStore
from retrieval.graph import CommitGraph
from query.engine import ask, timeline_ask

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

/* Radio nav — hide the widget label */
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

def ingest_repo(repo_url: str, max_commits: int) -> str:
    key         = repo_key(repo_url)
    clone_path  = f"./data/repos/{key}"
    chunks_path = f"./data/raw/{key}_chunks.json"

    if not Path(clone_path).exists():
        st.write(f"Cloning {repo_url}...")
        git.Repo.clone_from(repo_url, clone_path)
    else:
        st.write("Repo already cloned.")

    st.write(f"Extracting {max_commits} commits...")
    commits = load_commits(clone_path, max_count=max_commits)

    chunks = build_chunks(commits, pull_requests=[])

    Path("./data/raw").mkdir(parents=True, exist_ok=True)
    with open(chunks_path, "w") as f:
        json.dump(chunks, f, indent=2)

    st.write("Embedding and storing in ChromaDB...")
    store = VectorStore(collection_name=key)
    store.ingest(chunks)

    registry = load_registry()
    registry[key] = {
        "url":         repo_url,
        "key":         key,
        "chunks_path": chunks_path,
        "clone_path":  clone_path,
        "commits":     len(chunks)
    }
    save_registry(registry)
    return key

# ---------------------------------------------------------------
# State
# ---------------------------------------------------------------
if "page" not in st.session_state:
    st.session_state.page = "ingest"

registry    = load_registry()
repo_keys   = list(registry.keys())
repo_urls   = [registry[k]["url"] for k in repo_keys]

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
    ("graph",    "Graph"),
    ("hotfiles", "Hot Files"),
    ("cochange", "Co-Change"),
    ("authors",  "Authors"),
]

page_keys   = [k for k, _ in pages]
page_labels = {k: l for k, l in pages}
current_idx = page_keys.index(st.session_state.page) if st.session_state.page in page_keys else 0

logo_col, radio_col = st.columns([2, 6])
with logo_col:
    st.markdown('<div class="nav-logo">code-archaeologist</div>', unsafe_allow_html=True)
with radio_col:
    selected_page = st.radio(
        "nav",
        options=page_keys,
        format_func=lambda k: page_labels[k],
        horizontal=True,
        label_visibility="collapsed",
        index=current_idx,
        key="nav_radio",
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
        max_commits = st.selectbox("Commits", [50, 100, 200, 300, 500, 1000], index=3, label_visibility="collapsed")

    st.caption("50 commits ~ 30s   |   300 commits ~ 3min   |   1000 commits ~ 10min")

    if st.button("Ingest Repository"):
        if not repo_url:
            st.warning("Please enter a GitHub URL.")
        else:
            try:
                with st.status("Ingesting...", expanded=True):
                    key = ingest_repo(repo_url.strip(), max_commits)
                    st.session_state.active_key = key
                st.success("Done. Select Ask from the nav to start querying.")
                st.balloons()
            except Exception as e:
                st.error(f"Failed: {e}")

    if registry:
        st.divider()
        st.markdown("**Previously ingested**")
        for k, v in registry.items():
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"`{v['url']}` — {v['commits']} commits")
            with col2:
                if st.button("Switch", key=f"switch_{k}"):
                    st.session_state.active_key = k
                    st.session_state.page = "ask"
                    st.session_state.nav_radio = "ask"
                    st.rerun()

# ---------------------------------------------------------------
# Page: Ask
# ---------------------------------------------------------------
elif page == "ask":
    st.markdown('<div class="page-title">Ask a Question</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Ask anything about why code was changed in this repository.</div>', unsafe_allow_html=True)

    if not active_key:
        st.warning("No repository ingested yet. Go to Ingest.")
        st.stop()

    question = st.text_input("Question", placeholder="Why was the session interface modified?", label_visibility="collapsed")

    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        top_k = st.slider("Sources", 3, 10, 5)
    with col2:
        only_pr = st.checkbox("PRs only")

    if st.button("Ask"):
        if not question:
            st.warning("Enter a question.")
        else:
            filters = {"has_pr": True} if only_pr else None
            with st.spinner("Retrieving commits and generating answer..."):
                result = ask(question, top_k=top_k, filters=filters, collection_name=active_key)

            st.markdown(f'<div class="answer-box">{result["answer"]}</div>', unsafe_allow_html=True)

            st.markdown("**Sources**")
            for i, s in enumerate(result["sources"], 1):
                st.markdown(f"""
                <div class="source-card">
                    <span class="source-author">{s['author']}</span>
                    <span class="source-score">{s['score']}</span>
                    <div style="color:#555;margin-top:0.3rem;font-size:0.78rem">{s['timestamp'][:10]}</div>
                    <div style="color:#666;margin-top:0.2rem;font-family:'DM Mono',monospace;font-size:0.72rem">{s['files'][:80]}</div>
                </div>
                """, unsafe_allow_html=True)

# ---------------------------------------------------------------
# Page: Timeline
# ---------------------------------------------------------------
elif page == "timeline":
    st.markdown('<div class="page-title">File Timeline</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Trace how any file evolved — with an LLM summary of every change.</div>', unsafe_allow_html=True)

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
elif page == "graph":
    st.markdown('<div class="page-title">Graph Explorer</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Interactive commit graph. Each node is a commit, colored by author. Drag, zoom, explore.</div>', unsafe_allow_html=True)

    if not active_key:
        st.warning("No repository ingested yet.")
        st.stop()

    col1, col2 = st.columns([3, 1])
    with col1:
        filter_file = st.text_input("Filter by file (leave empty for full graph)", placeholder="sessions.py", label_visibility="collapsed")
    with col2:
        if st.button("Generate Graph"):
            graph       = CommitGraph(chunks_path=active_chunks_path)
            output_path = f"./data/{active_key}_graph.html"
            with st.spinner("Generating..."):
                graph.visualize(output_path=output_path, filter_file=filter_file if filter_file else None)
            st.session_state[f"graph_ready_{active_key}"] = output_path

    graph_path = st.session_state.get(f"graph_ready_{active_key}")
    if graph_path and Path(graph_path).exists():
        with open(graph_path, "r", encoding="utf-8") as f:
            st.components.v1.html(f.read(), height=720, scrolling=False)

# ---------------------------------------------------------------
# Page: Hot Files
# ---------------------------------------------------------------
elif page == "hotfiles":
    st.markdown('<div class="page-title">Hot Files</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Files changed most frequently — the core of the codebase.</div>', unsafe_allow_html=True)

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
    st.markdown('<div class="page-sub">File pairs that are almost always changed together — reveals hidden dependencies.</div>', unsafe_allow_html=True)

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
            with st.expander(f"{author_data['author']} — {author_data['commits']} commits"):
                for f in author_data["top_files"]:
                    st.markdown(f"`{f['file']}` — {f['changes']}x")