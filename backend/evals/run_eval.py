# evals/run_eval.py
"""Accuracy check for search and Who broke it?, on real public repositories.

Everything runs on this machine: local BGE embeddings, a throwaway vector store, no database, and no
GitHub token (pull requests come from GitHub's public API, about 7 requests per repository, then
cached). Questions and answers come from each repository's own history; see evals/cases.py.

    cd backend
    python -m evals.run_eval                       # pallets/click, pallets/flask, encode/httpx
    python -m evals.run_eval --repos pallets/click --commits 100

Needs the local embedding model (pip install -r requirements-local.txt). Writes evals/RESULTS.md.
"""
import os
import sys
import tempfile

from cryptography.fernet import Fernet

_SCRATCH = tempfile.mkdtemp(prefix="ca-eval-")
# Environment values win over backend/.env, so set these before anything reads the settings:
# nothing here can reach Pinecone, the real database, email or the server's GitHub token.
os.environ.update({
    "PINECONE_API_KEY": "", "EMBEDDING_PROVIDER": "local", "GITHUB_TOKEN": "", "EMAIL_DELIVERY": "off",
    "DATABASE_URL": f"sqlite:///{_SCRATCH}/unused.db", "DATA_DIR": _SCRATCH,
    "SECRET_KEY": "eval-only-" + "x" * 32, "ENCRYPTION_KEY": Fernet.generate_key().decode(),
})

import argparse          # noqa: E402
import dataclasses       # noqa: E402
import functools         # noqa: E402
import json              # noqa: E402
import shutil            # noqa: E402
import stat              # noqa: E402
import time              # noqa: E402
from datetime import date, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

import git  # noqa: E402
from rank_bm25 import BM25Okapi  # noqa: E402

from app.config import get_settings  # noqa: E402
from evals.cases import rank_of, retrieval_cases, scores, suspect_cases  # noqa: E402
from ingestion.bug_origins import find_bug_origins  # noqa: E402
from ingestion.chunker import build_chunks  # noqa: E402
from ingestion.git_loader import load_commits  # noqa: E402
from ingestion.github_enricher import PRRecord, fetch_prs  # noqa: E402
from retrieval.suspects import WEIGHTS, origin_counts, rank_suspects  # noqa: E402
from storage import vector_store  # noqa: E402
from storage.vector_store import VectorStore  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_REPOS = ["pallets/click", "pallets/flask", "encode/httpx"]
# Keyword side of rank fusion; the app uses vector_store.KEYWORD_WEIGHT
FUSION_WEIGHTS = sorted({0.25, 0.5, 1.0, vector_store.KEYWORD_WEIGHT})
WEIGHT_SETS = {
    "App (search 0.5, files 0.3, risk 0.2)": WEIGHTS,
    "Search only": {"search": 1.0, "files": 0.0, "risk": 0.0},
    "No risk (0.7, 0.3, 0)": {"search": 0.7, "files": 0.3, "risk": 0.0},
    "More risk (0.4, 0.3, 0.3)": {"search": 0.4, "files": 0.3, "risk": 0.3},
}
OLD_SUSPECTS = "App weights, with the search from before"
SEARCH_K = (1, 3, 8)       # the Ask tab reads the top 8 results
SUSPECT_K = (1, 3, 10)     # Who broke it? shows the top 3


def _rmtree(path: Path):
    def _force(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onexc=_force)


def _clone(full_name: str, commits: int, cache: Path) -> Path:
    path = cache / f"{full_name.replace('/', '__')}__{commits}"
    if not (path / ".git").exists():
        print(f"  cloning {full_name}")
        git.Repo.clone_from(f"https://github.com/{full_name}.git", path, depth=commits * 2,
                            single_branch=True, no_tags=True, env={"GIT_TERMINAL_PROMPT": "0"})
    return path


def _prs(full_name: str, commits, cache: Path) -> list[PRRecord]:
    path = cache / f"{full_name.replace('/', '__')}__{len(commits)}.prs.json"
    if path.exists():
        return [PRRecord(**p) for p in json.loads(path.read_text(encoding="utf-8"))]
    print(f"  fetching pull requests for {full_name}")
    oldest = min(datetime.fromisoformat(c.timestamp) for c in commits)
    result = fetch_prs(full_name, max_prs=min(200, len(commits) * 2), token=None, since=oldest)
    for w in result.warnings:
        print(f"  warning: {w}")
    if result.prs:   # don't cache an empty list from a rate limit
        path.write_text(json.dumps([dataclasses.asdict(p) for p in result.prs]), encoding="utf-8")
    return result.prs


def _old_search(store: VectorStore, question: str, top_k: int) -> list[dict]:
    """The search the app used before rank fusion, kept here to compare against: 0.6 x cosine +
    0.4 x BM25 (words split on spaces, divided by the best score) over the top_k * 4 commits by meaning."""
    cands = store.backend.query(vector_store._embed_query(question), min(max(top_k * 4, 20), 200), store.namespace, None)
    if not cands:
        return []
    bm = BM25Okapi([m.get("text", "").lower().split() for _, m in cands]).get_scores(question.lower().split())
    top = max(bm) if max(bm) > 0 else 1
    mixed = sorted(((0.6 * d + 0.4 * bm[i] / top, m) for i, (d, m) in enumerate(cands)), key=lambda x: -x[0])
    return [{"metadata": {"sha": m.get("sha", "")}, "score": round(score, 3)} for score, m in mixed[:top_k]]


OLD_SEARCH = "Before: score mix (0.6 dense + 0.4 keywords)"
APP_SEARCH = f"Rank fusion, keyword weight {vector_store.KEYWORD_WEIGHT:g} (the app)"
SEARCHES = {
    OLD_SEARCH: _old_search,
    "Dense only": lambda store, q, k: store.search(q, top_k=k, keyword_weight=0),
    **{(APP_SEARCH if w == vector_store.KEYWORD_WEIGHT else f"Rank fusion, keyword weight {w:g}"):
       (lambda store, q, k, w=w: store.search(q, top_k=k, keyword_weight=w)) for w in FUSION_WEIGHTS},
}


def _eval_search(name: str, chunks: list[dict]) -> dict:
    indexed, titles, descriptions = retrieval_cases(chunks)
    store = VectorStore(f"eval_search_{name}")
    store.ingest(indexed, overwrite=True)
    out = {}
    for kind, cases in (("PR title", titles), ("PR description", descriptions)):
        out[kind] = {"cases": len(cases), "ranks": {}}
        for label, search in SEARCHES.items():
            out[kind]["ranks"][label] = [
                rank_of(c["answers"], [h["metadata"]["sha"] for h in search(store, c["question"], 8)]) for c in cases]
    store.delete_namespace()
    return out


def _eval_suspects(name: str, chunks: list[dict], fixes: list[dict]) -> dict:
    cases = suspect_cases(fixes)
    store = VectorStore(f"eval_suspects_{name}")
    store.ingest(chunks, overwrite=True)
    ranks = {label: [] for label in [*WEIGHT_SETS, OLD_SUSPECTS, "Newest commit first"]}
    used = 0
    for case in cases:
        before = [c for c in chunks if c["metadata"]["timestamp"] < case["before"]]
        visible = {c["metadata"]["sha"] for c in before}
        if case["answer"] not in visible:
            continue  # the cause was committed after the fix (a rebase), so no ranking could find it
        used += 1
        caused = origin_counts(case["earlier_fixes"])

        def ranked(search, weights):
            # Search the whole index, then keep the best 30 that existed when the bug was reported
            hits = [h for h in search(store, case["report"], 200) if h["metadata"]["sha"] in visible][:30]
            found, _ = rank_suspects(case["report"], before, {h["metadata"]["sha"]: h["score"] for h in hits},
                                     caused, top_n=10, weights=weights)
            return rank_of({case["answer"]}, [s["sha"] for s in found])

        for label, weights in WEIGHT_SETS.items():
            ranks[label].append(ranked(SEARCHES[APP_SEARCH], weights))
        ranks[OLD_SUSPECTS].append(ranked(_old_search, WEIGHTS))
        newest = sorted(before, key=lambda c: c["metadata"]["timestamp"], reverse=True)[:10]
        ranks["Newest commit first"].append(rank_of({case["answer"]}, [c["metadata"]["sha"] for c in newest]))
    store.delete_namespace()
    return {"cases": used, "ranks": ranks}


def _pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def _row(label: str, ranks: list, ks: tuple) -> str:
    s = scores(ranks, ks)
    return "| " + " | ".join([label, *[_pct(s[f"@{k}"]) for k in ks], "n/a" if s["mrr"] is None else f"{s['mrr']:.2f}"]) + " |"


def _header(first: str, ks: tuple, word: str) -> list[str]:
    cols = [first, *[f"{word} top {k}" for k in ks], "MRR"]
    return ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] + ["---:"] * (len(cols) - 1)) + "|"]


def _report(repos: list[dict], commits: int, seconds: float) -> str:
    search_ranks = lambda kind, label: [r for repo in repos for r in repo["search"][kind]["ranks"][label]]
    suspect_ranks = lambda label: [r for repo in repos for r in repo["suspects"]["ranks"][label]]
    lines = [
        "# Accuracy check",
        "",
        f"Run on {date.today().isoformat()} with `python -m evals.run_eval` (local BGE-small embeddings, "
        f"the last {commits} commits of each repository, {seconds / 60:.0f} minutes). "
        "The live site uses Pinecone's llama-text-embed-v2, so its numbers can differ.",
        "",
        "| Repository | Commits | Linked PRs | Title questions | Description questions | Traced bugs |",
        "|---|---:|---:|---:|---:|---:|",
        *[f"| [{r['name']}](https://github.com/{r['name']}) at `{r['head']}` | {r['commits']} | {r['prs']} | "
          f"{r['search']['PR title']['cases']} | {r['search']['PR description']['cases']} | {r['suspects']['cases']} |"
          for r in repos],
        "",
        *([f"No pull requests were fetched for {', '.join(r['name'] for r in repos if not r['prs'])} (GitHub's "
           "limit for requests without a token ran out), so it only counts toward Who broke it?.", ""]
          if any(not r["prs"] for r in repos) else []),
        "## Search",
        "",
        "Each merged pull request becomes a question: its title, or the first real sentence of its "
        "description. The answer is the commit the PR belongs to. That PR text is removed from the index "
        "first, and the title is also cut from the commit message (which often repeats it word for word), so "
        "the commit has to be found from the rest of its message and its diff.",
        "",
        "Found = the answer is in the top k results. MRR (mean reciprocal rank) is 1 when the answer is always "
        "first, 0.5 when it's always second, and counts a miss outside the top 8 as 0.",
        "",
        "The searches compared: the score mix the app used before; dense (embedding) search alone; and rank "
        "fusion, which merges the dense ranking with a BM25 keyword ranking by position, at several weights for "
        "the keyword side. Rank fusion also matches keywords over every commit rather than only the top 32 by "
        "meaning, and splits code into words properly (`ctx.ensure_object()` gives ctx, ensure, object).",
        "",
    ]
    for kind in ("PR description", "PR title"):
        lines += [f"### {kind} questions, all repositories together", "",
                  *_header("Search", SEARCH_K, "Found in"),
                  *[_row(label, search_ranks(kind, label), SEARCH_K) for label in SEARCHES], ""]
    lines += ["### Per repository, before and now", "",
              *_header("Repository, question, search", SEARCH_K, "Found in"),
              *[_row(f"{r['name']}, {kind.split()[1]}, {'now' if label == APP_SEARCH else 'before'}",
                     r["search"][kind]["ranks"][label], SEARCH_K)
                for r in repos if r["prs"] for kind in ("PR description", "PR title") for label in (OLD_SEARCH, APP_SEARCH)],
              ""]
    lines += [
        "## Who broke it?",
        "",
        "Every bug fix that Bug origins traced to one of the ingested commits becomes a report: the fix's "
        "commit message is the description and the traced commit is the answer. Only commits from before the "
        "fix are candidates, and the \"already caused a bug\" signal only counts fixes made before it. A fix "
        "message is shorter than a real bug report and the traced commit is a likely cause rather than a "
        "certain one, so treat these numbers as a rough guide.",
        "",
        "### All repositories together",
        "",
        *_header("Ranking", SUSPECT_K, "Cause in"),
        *[_row(label, suspect_ranks(label), SUSPECT_K) for label in [*WEIGHT_SETS, OLD_SUSPECTS, "Newest commit first"]],
        "",
        "### Per repository, with the app's weights",
        "",
        *_header("Repository", SUSPECT_K, "Cause in"),
        *[_row(r["name"], r["suspects"]["ranks"][next(iter(WEIGHT_SETS))], SUSPECT_K) for r in repos],
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repos", nargs="+", default=DEFAULT_REPOS)
    parser.add_argument("--commits", type=int, default=200)
    parser.add_argument("--cache", type=Path, default=BACKEND / "data" / "eval-cache",
                        help="clones and pull requests are kept here between runs")
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("RESULTS.md"))
    args = parser.parse_args()

    settings = get_settings()
    if settings.pinecone_api_key or settings.embedding_provider != "local":
        sys.exit("Refusing to run: the settings still point at Pinecone.")
    args.cache.mkdir(parents=True, exist_ok=True)
    # Each question is searched once per method; embed it once
    vector_store._embed_query = functools.lru_cache(maxsize=None)(vector_store._embed_query)

    started, results = time.time(), []
    try:
        for full_name in args.repos:
            print(f"{full_name}")
            name = full_name.replace("/", "_").replace("-", "_").replace(".", "_")
            path = _clone(full_name, args.commits, args.cache)
            commits = load_commits(str(path), max_count=args.commits)
            chunks = build_chunks(commits, pull_requests=_prs(full_name, commits, args.cache))
            fixes = find_bug_origins(str(path), commits)
            print("  searching")
            search = _eval_search(name, chunks)
            print("  ranking suspects")
            suspects = _eval_suspects(name, chunks, fixes)
            results.append({"name": full_name, "head": commits[0].sha[:7], "commits": len(chunks),
                            "prs": len({c["metadata"]["pr_number"] for c in chunks if c["metadata"]["pr_number"]}),
                            "search": search, "suspects": suspects})
    finally:
        _rmtree(Path(_SCRATCH))

    report = _report(results, args.commits, time.time() - started)
    args.out.write_text(report, encoding="utf-8")
    print(f"\nWrote {args.out}\n\n{report}")


if __name__ == "__main__":
    main()
