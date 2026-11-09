# evals/bug_reports.py
"""Who broke it? on real bug reports.

A fix here is a commit whose pull request (or message) closes a GitHub issue, which is a much clearer sign
of a real bug fix than a message containing "fix". Bug origins traces what each such fix changed back to the
commit that last wrote it, and that commit is the answer. The report is the issue itself, its title and
description the way a user would paste them, not the fix's one-line commit message.

    cd backend
    python -m evals.bug_reports                    # pallets/click, pallets/flask, encode/httpx
    python -m evals.bug_reports --commits 500

Runs on this machine with local embeddings, like run_eval, and never touches Pinecone, the database or
email. GitHub is read with GITHUB_TOKEN from backend/.env when there is one: public, read-only requests for
pull request lists and the linked issues, cached in data/eval-cache. Writes evals/RESULTS-bug-reports.md.
"""
from evals import run_eval as base   # sets the isolated environment before anything reads the settings

import argparse          # noqa: E402
import dataclasses       # noqa: E402
import functools         # noqa: E402
import json              # noqa: E402
import sys               # noqa: E402
import time              # noqa: E402
from datetime import date, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402
from evals.cases import closing_issues, issue_report, rank_of, suspect_cases  # noqa: E402
from ingestion.bug_origins import find_bug_origins  # noqa: E402
from ingestion.chunker import build_chunks  # noqa: E402
from ingestion.git_loader import load_commits  # noqa: E402
from ingestion.github_enricher import PRRecord, fetch_prs  # noqa: E402
from retrieval.suspects import WEIGHTS, mentioned_files, origin_counts, rank_suspects  # noqa: E402
from storage import vector_store  # noqa: E402
from storage.vector_store import VectorStore  # noqa: E402

K = base.SUSPECT_K
APP = "App weights (search 0.5, files 0.3, risk 0.2)"
VARIANTS = {
    "Search only": {"search": 1.0, "files": 0.0, "risk": 0.0},
    "No risk (0.7, 0.3, 0)": {"search": 0.7, "files": 0.3, "risk": 0.0},
    "More files (0.4, 0.5, 0.1)": {"search": 0.4, "files": 0.5, "risk": 0.1},
    "More risk (0.4, 0.3, 0.3)": {"search": 0.4, "files": 0.3, "risk": 0.3},
}
MESSAGE = "App weights, fix message as the report"
NEWEST = "Newest commit first"


def _github_token() -> str | None:
    """GITHUB_TOKEN from backend/.env, read directly because run_eval blanks it for everything else."""
    env = base.BACKEND / ".env"
    if not env.exists():
        return None
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("GITHUB_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def _prs(full_name: str, commits, cache: Path, token: str | None) -> list[PRRecord]:
    """Merged PRs over the whole window, without review details (not needed here, and costly)."""
    path = cache / f"{full_name.replace('/', '__')}__{len(commits)}.prs-light.json"
    if path.exists():
        return [PRRecord(**p) for p in json.loads(path.read_text(encoding="utf-8"))]
    print(f"  fetching pull requests for {full_name}", flush=True)
    oldest = min(datetime.fromisoformat(c.timestamp) for c in commits)
    result = fetch_prs(full_name, max_prs=len(commits), token=token, since=oldest, details=False)
    for w in result.warnings:
        print(f"  warning: {w}")
    if result.prs:
        path.write_text(json.dumps([dataclasses.asdict(p) for p in result.prs]), encoding="utf-8")
    return result.prs


class _Issues:
    """GitHub issues by number, cached on disk; None for pull requests and missing issues."""

    def __init__(self, full_name: str, cache: Path, token: str | None):
        self.full_name, self.token = full_name, token
        self.path = cache / f"{full_name.replace('/', '__')}.issues.json"
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def _fetch(self, number: int) -> httpx.Response | None:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "code-archaeologist-eval"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        for attempt in range(4):
            try:
                r = httpx.get(f"https://api.github.com/repos/{self.full_name}/issues/{number}", headers=headers,
                              timeout=30)
                if r.status_code < 500:
                    return r
            except httpx.TransportError:
                pass
            time.sleep(2 ** (attempt + 1))   # a slow or dropped connection: wait and try again
        return None

    def get(self, number: int) -> dict | None:
        key = str(number)
        if key not in self.data or (self.data[key] and "labels" not in self.data[key]):
            r = self._fetch(number)
            if r is None:
                print(f"  couldn't fetch issue #{number}; skipping it this run", flush=True)
                return None   # not cached, so a later run tries again
            if r.status_code == 404:
                self.data[key] = None
            else:
                r.raise_for_status()
                issue = r.json()
                # The issues API also returns pull requests; only real issues are bug reports
                self.data[key] = None if "pull_request" in issue else {
                    "title": issue["title"], "body": issue.get("body") or "",
                    "labels": [label["name"] for label in issue.get("labels", [])]}
            self.path.write_text(json.dumps(self.data), encoding="utf-8")
        return self.data[key]


def _linked_issues(full_name: str, commits, chunks: list[dict], prs: list[PRRecord]) -> dict[str, list[int]]:
    """Issue numbers each commit says it closes, through its pull request or its own message."""
    pr_by_number = {p.number: p for p in prs}
    pr_of = {c["metadata"]["sha"]: pr_by_number.get(c["metadata"]["pr_number"]) for c in chunks}
    linked = {}
    for c in commits:
        pr = pr_of.get(c.sha[:7])
        numbers = (pr.linked_issues + closing_issues(f"{pr.title}\n{pr.body}", full_name)) if pr else []
        numbers += closing_issues(c.message, full_name)
        if numbers:
            linked[c.sha[:7]] = list(dict.fromkeys(numbers))
    return linked


def _evaluate(full_name: str, commits_n: int, cache: Path, token: str | None) -> dict:
    name = full_name.replace("/", "_").replace("-", "_").replace(".", "_")
    path = base._clone(full_name, commits_n, cache)
    commits = load_commits(str(path), max_count=commits_n)
    prs = _prs(full_name, commits, cache, token)
    chunks = build_chunks(commits, pull_requests=prs)
    linked = _linked_issues(full_name, commits, chunks, prs)
    print(f"  {len(linked)} commits close an issue; tracing what they changed", flush=True)
    fixes = find_bug_origins(str(path), commits, is_fix=lambda c: c.sha[:7] in linked)
    issues = _Issues(full_name, cache, token)
    store = VectorStore(f"eval_bugs_{name}")
    print(f"  indexing {len(chunks)} commits", flush=True)
    store.ingest(chunks, overwrite=True)

    ranks = {label: [] for label in (APP, *VARIANTS, MESSAGE, NEWEST)}
    counts = {"closing": len(linked), "traced": 0, "cases": 0, "bug_label": 0, "names_a_file": 0}
    used_issues = set()
    for case in suspect_cases(fixes):
        before = [c for c in chunks if c["metadata"]["timestamp"] < case["before"]]
        visible = {c["metadata"]["sha"] for c in before}
        if case["answer"] not in visible:
            continue  # the cause was committed after the fix (a rebase), so no ranking could find it
        counts["traced"] += 1
        # One case per issue: several commits of one pull request can close the same issue
        number, issue = next(((n, i) for n in linked[case["fix"]] if n not in used_issues
                              and (i := issues.get(n)) and i["title"].strip()), (None, None))
        if issue is None:
            continue
        used_issues.add(number)
        report = issue_report(issue)
        counts["cases"] += 1
        counts["bug_label"] += any("bug" in label.lower() for label in issue["labels"])
        counts["names_a_file"] += bool(mentioned_files(report))
        caused = origin_counts(case["earlier_fixes"])

        @functools.cache
        def hits(text: str) -> dict[str, float]:
            # Search every commit, and keep the best 30 that existed when the bug was reported
            found = [h for h in store.search(text, top_k=len(chunks), chunks=chunks)
                     if h["metadata"]["sha"] in visible][:30]
            return {h["metadata"]["sha"]: h["score"] for h in found}

        def rank(text: str, weights: dict) -> int | None:
            top, _ = rank_suspects(text, before, hits(text), caused, top_n=10, weights=weights)
            return rank_of({case["answer"]}, [s["sha"] for s in top])

        ranks[APP].append(rank(report, WEIGHTS))
        for label, weights in VARIANTS.items():
            ranks[label].append(rank(report, weights))
        ranks[MESSAGE].append(rank(case["report"], WEIGHTS))
        newest = sorted(before, key=lambda c: c["metadata"]["timestamp"], reverse=True)[:10]
        ranks[NEWEST].append(rank_of({case["answer"]}, [c["metadata"]["sha"] for c in newest]))
    store.delete_namespace()
    return {"name": full_name, "head": commits[0].sha[:7], "commits": len(chunks), **counts, "ranks": ranks}


def _report(repos: list[dict], commits: int, seconds: float) -> str:
    pooled = lambda label: [r for repo in repos for r in repo["ranks"][label]]
    cases = sum(r["cases"] for r in repos)
    lines = [
        "# Who broke it? on real bug reports",
        "",
        f"Run on {date.today().isoformat()} with `python -m evals.bug_reports` (local BGE-small embeddings, the last "
        f"{commits} commits of each repository, {seconds / 60:.0f} minutes).",
        "",
        "A fix is a commit whose pull request or message closes a GitHub issue. Bug origins traces what it changed "
        "back to the commit that last wrote those lines, and that commit is the answer. The report is the issue's "
        "title and description, the way a user would paste them. Only commits from before the fix are ranked, and the "
        "\"already caused a bug\" signal only counts earlier fixes. Tracing finds a likely cause rather than a certain "
        "one, so the true accuracy is somewhat higher than measured.",
        "",
        "| Repository | Commits | Close an issue | Traced to an earlier commit | Cases (one per issue) | "
        "Labelled bug | Issue names a file |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *[f"| [{r['name']}](https://github.com/{r['name']}) at `{r['head']}` | {r['commits']} | {r['closing']} | "
          f"{r['traced']} | {r['cases']} | {r['bug_label']} | {r['names_a_file']} |" for r in repos],
        "",
        f"## All {cases} cases",
        "",
        *base._header("Ranking", K, "Cause in"),
        *[base._row(label, pooled(label), K) for label in repos[0]["ranks"]],
        "",
        "### Per repository, app weights",
        "",
        *base._header("Repository", K, "Cause in"),
        *[base._row(f"{r['name']} ({r['cases']} cases)", r["ranks"][APP], K) for r in repos],
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repos", nargs="+", default=base.DEFAULT_REPOS)
    parser.add_argument("--commits", type=int, default=1000)
    parser.add_argument("--cache", type=Path, default=base.BACKEND / "data" / "eval-cache")
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("RESULTS-bug-reports.md"))
    args = parser.parse_args()

    settings = get_settings()
    if settings.pinecone_api_key or settings.embedding_provider != "local":
        sys.exit("Refusing to run: the settings still point at Pinecone.")
    token = _github_token()
    print("GitHub: " + ("using GITHUB_TOKEN from backend/.env" if token else "no token, 60 requests an hour"))
    args.cache.mkdir(parents=True, exist_ok=True)
    vector_store._embed_query = functools.lru_cache(maxsize=None)(vector_store._embed_query)
    vector_store._backend = base._QueryCache(vector_store._get_backend())

    started, results = time.time(), []
    try:
        for full_name in args.repos:
            print(full_name, flush=True)
            results.append(_evaluate(full_name, args.commits, args.cache, token))
    finally:
        base._rmtree(Path(base._SCRATCH))

    report = _report(results, args.commits, time.time() - started)
    args.out.write_text(report, encoding="utf-8")
    print(f"\nWrote {args.out}\n\n{report}")


if __name__ == "__main__":
    main()
