# evals/bug_reports.py
"""Who broke it? on real bug reports.

A fix here is a commit whose pull request (or message) closes a GitHub issue, which is a much clearer sign
of a real bug fix than a message containing "fix". Bug origins traces what each such fix changed back to the
commit that last wrote it, and that commit is the answer. The report is the issue itself, its title and
description the way a user would paste them, not the fix's one-line commit message.

Each case is ranked as of when the issue was opened, as the app would have seen it: only earlier commits,
and only earlier fixes for the "already caused a bug" signal. A traced cause newer than the issue can't be
right, so those cases are dropped. Results are shown for real bug reports (see evals.cases.is_bug_report)
and for every issue, since many issues a pull request closes are feature requests.

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
from evals.cases import closing_issues, is_bug_report, issue_report, rank_of, suspect_cases  # noqa: E402
from ingestion.bug_origins import find_bug_origins  # noqa: E402
from ingestion.chunker import build_chunks  # noqa: E402
from ingestion.git_loader import load_commits  # noqa: E402
from ingestion.github_enricher import PRRecord, fetch_prs  # noqa: E402
from retrieval.suspects import WEIGHTS, mentioned_files, origin_counts, rank_suspects  # noqa: E402
from storage import vector_store  # noqa: E402
from storage.vector_store import VectorStore  # noqa: E402

K = (1, 3, 5, 10)   # top 5 as well, which published work on this task reports
APP = "App ranking"
ANY = "App ranking, any traced cause counts"
# Each signal taken out in turn shows what it adds
VARIANTS = {
    "Without change size": {**WEIGHTS, "size": 0.0},
    "Without code names": {**WEIGHTS, "code": 0.0},
    "Without recency": {**WEIGHTS, "recency": 0.0},
    "Without named files": {**WEIGHTS, "files": 0.0},
    "Earlier weights (search 0.5, files 0.3, type and earlier bugs 0.2)":
        {"search": 0.5, "files": 0.3, "type": 0.12, "caused": 0.08},
    "Search only": {"search": 1.0},
}
MESSAGE = "App ranking, fix message as the report"
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


def _local_time(utc: str) -> str:
    """GitHub's UTC time in the commits' convention (local time, ISO format, no zone), so they compare."""
    return datetime.fromisoformat(utc.replace("Z", "+00:00")).astimezone().replace(tzinfo=None).isoformat()


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
        if key not in self.data or (self.data[key] and "opened" not in self.data[key]):
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
                    "labels": [label["name"] for label in issue.get("labels", [])],
                    "opened": _local_time(issue["created_at"])}
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

    ranks = {label: [] for label in (APP, ANY, *VARIANTS, MESSAGE, NEWEST)}
    counts = {"closing": len(linked), "traced": 0, "after_issue": 0, "cases": 0, "bugs": 0, "names_a_file": 0}
    is_bug, used_issues = [], set()
    by_sha = {f["sha"]: f for f in fixes}
    when = {c["metadata"]["sha"]: c["metadata"]["timestamp"] for c in chunks}
    for case in suspect_cases(fixes):
        if when.get(case["answer"], "9") >= case["before"]:
            continue  # the cause was committed after the fix (a rebase), so no ranking could find it
        counts["traced"] += 1
        # One case per issue: several commits of one pull request can close the same issue
        number, issue = next(((n, i) for n in linked[case["fix"]] if n not in used_issues
                              and (i := issues.get(n)) and i["title"].strip()), (None, None))
        if issue is None:
            continue
        # Rank as of when the issue was opened; a cause newer than the report was traced wrongly
        cutoff = min(issue["opened"], case["before"])
        if when[case["answer"]] >= cutoff:
            counts["after_issue"] += 1
            continue
        used_issues.add(number)
        before = [c for c in chunks if c["metadata"]["timestamp"] < cutoff]
        visible = {c["metadata"]["sha"] for c in before}
        report = issue_report(issue)
        counts["cases"] += 1
        is_bug.append(is_bug_report(issue["labels"], case["report"], report))
        counts["bugs"] += is_bug[-1]
        counts["names_a_file"] += bool(mentioned_files(report))
        caused = origin_counts([f for f in fixes if f["timestamp"] < cutoff])
        traced = {o["sha"] for o in by_sha[case["fix"]]["origins"] if o["ingested"]}

        @functools.cache
        def hits(text: str) -> dict[str, float]:
            # Search every commit, and keep the best 30 that existed when the bug was reported
            found = [h for h in store.search(text, top_k=len(chunks), chunks=chunks)
                     if h["metadata"]["sha"] in visible][:30]
            return {h["metadata"]["sha"]: h["score"] for h in found}

        def rank(text: str, weights: dict, answers: set | None = None) -> int | None:
            top, _ = rank_suspects(text, before, hits(text), caused, top_n=10, weights=weights)
            return rank_of(answers or {case["answer"]}, [s["sha"] for s in top])

        ranks[APP].append(rank(report, WEIGHTS))
        ranks[ANY].append(rank(report, WEIGHTS, traced))
        for label, weights in VARIANTS.items():
            ranks[label].append(rank(report, weights))
        ranks[MESSAGE].append(rank(case["report"], WEIGHTS))
        newest = sorted(before, key=lambda c: c["metadata"]["timestamp"], reverse=True)[:10]
        ranks[NEWEST].append(rank_of({case["answer"]}, [c["metadata"]["sha"] for c in newest]))
    store.delete_namespace()
    return {"name": full_name, "head": commits[0].sha[:7], "commits": len(chunks), **counts, "ranks": ranks,
            "is_bug": is_bug}


def _report(repos: list[dict], commits: int, seconds: float) -> str:
    def pooled(label: str, bugs_only: bool) -> list:
        return [r for repo in repos
                for r, bug in zip(repo["ranks"][label], repo["is_bug"], strict=True) if bug or not bugs_only]

    def table(bugs_only: bool) -> list[str]:
        return [*base._header("Ranking", K, "Cause in"),
                *[base._row(label, pooled(label, bugs_only), K) for label in repos[0]["ranks"]]]

    def per_repo(bugs_only: bool) -> list[str]:
        rows = []
        for r in repos:
            ranks = [x for x, bug in zip(r["ranks"][APP], r["is_bug"], strict=True) if bug or not bugs_only]
            rows.append(base._row(f"{r['name']} ({len(ranks)} cases)", ranks, K))
        return [*base._header("Repository, app ranking", K, "Cause in"), *rows]

    cases, bugs = sum(r["cases"] for r in repos), sum(r["bugs"] for r in repos)
    lines = [
        "# Who broke it? on real bug reports",
        "",
        f"Run on {date.today().isoformat()} with `python -m evals.bug_reports` (local BGE-small embeddings, the last "
        f"{commits} commits of each repository, {seconds / 60:.0f} minutes).",
        "",
        "A fix is a commit whose pull request or message closes a GitHub issue. Bug origins traces what it changed "
        "back to the commit that last wrote those lines, and that commit is the answer. The report is the issue's "
        "title and description, the way a user would paste them. Each case is ranked as of when the issue was "
        "opened: only earlier commits are candidates, and the \"already caused a bug\" signal only counts earlier "
        "fixes. A traced cause newer than the issue can't be right, so those cases are left out.",
        "",
        "Many issues a pull request closes are feature requests, where \"who broke it\" has no answer. An issue "
        "counts as a real bug report if it's labelled as a bug, the commit that closed it is a fix, or it has a "
        "Python traceback. Tracing finds a likely cause rather than a certain one, and a fix can trace to several "
        "commits: the main rows count only the commit that wrote most of the fixed lines, and one row counts any "
        "of them.",
        "",
        "| Repository | Commits | Close an issue | Traced to an earlier commit | Cause newer than the issue | "
        "Cases (one per issue) | Real bug reports | Issue names a file |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        *[f"| [{r['name']}](https://github.com/{r['name']}) at `{r['head']}` | {r['commits']} | {r['closing']} | "
          f"{r['traced']} | {r['after_issue']} | {r['cases']} | {r['bugs']} | {r['names_a_file']} |" for r in repos],
        "",
        f"## Real bug reports ({bugs})",
        "",
        *table(bugs_only=True),
        "",
        *per_repo(bugs_only=True),
        "",
        f"## Every issue ({cases})",
        "",
        *table(bugs_only=False),
        "",
        *per_repo(bugs_only=False),
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
