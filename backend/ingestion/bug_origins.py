# ingestion/bug_origins.py
"""Trace each bug-fix commit back to the commits that most likely introduced the bug.

This is the SZZ method (Śliwerski, Zimmermann and Zeller, 2005): the lines a fix removed
or changed were part of the bug, so `git blame` on the fix's parent shows which earlier
commits wrote them. It reads history only — no LLM, and the repository's code never runs.
"""
import re
from collections import Counter
from datetime import datetime
from statistics import median

import git

from retrieval.analytics import commit_type

MAX_FILES_PER_FIX = 20
MAX_LINES_PER_FILE = 100
MAX_LINES_PER_FIX = 300
TOP_ORIGINS = 3

_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")
_TEST_NAME = re.compile(r"(^test_|^conftest\.py$|_test\.|\.test\.|\.spec\.|_spec\.)")
_TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "testing"}
_DOC_EXT = (".md", ".rst", ".txt", ".adoc", ".lock")
_DOC_NAMES = {"changelog", "changes", "history", "news", "authors", "license", "contributing"}


def _skip_path(path: str) -> bool:
    """Docs and tests can change in a fix without having been part of the bug."""
    p = path.lower()
    *dirs, name = p.split("/")
    if name.endswith(_DOC_EXT) or name.split(".")[0] in _DOC_NAMES:
        return True
    return bool(_TEST_DIRS.intersection(dirs) or _TEST_NAME.search(name))


def _is_comment(text: str) -> bool:
    return text.startswith(("#", "//", "/*", "*/", "<!--")) or text == "*" or text.startswith("* ")


def _deleted_lines(repo: git.Repo, parent: str, sha: str) -> dict[str, list[int]]:
    """Line numbers, in the parent's version of each file, that the fix removed or changed."""
    diff = repo.git.diff(parent, sha, "-U0", "--no-renames", "--no-color", "--no-ext-diff")
    found: dict[str, list[int]] = {}
    path, in_header, old_no, total = None, False, 0, 0
    for raw in diff.split("\n"):
        if raw.startswith("diff --git "):
            path, in_header = None, True
            continue
        if in_header:
            # Header lines like "--- a/x" look like removed lines, so they're handled before any hunk
            if raw.startswith("--- "):
                name = raw[4:].rstrip("\t")
                # "/dev/null" means the file is new, so nothing older to blame; quoted paths are skipped
                path = name[2:] if name.startswith("a/") else None
                if path and (_skip_path(path) or len(found) >= MAX_FILES_PER_FIX):
                    path = None
            if not raw.startswith("@@"):
                continue
            in_header = False
        m = _HUNK.match(raw)
        if m:
            old_no = int(m.group(1))
            continue
        if path and raw.startswith("-"):
            text = raw[1:].strip()
            bucket = found.setdefault(path, [])
            if text and not _is_comment(text) and len(bucket) < MAX_LINES_PER_FILE and total < MAX_LINES_PER_FIX:
                bucket.append(old_no)
                total += 1
            old_no += 1
    return {p: nums for p, nums in found.items() if nums}


def _ranges(nums: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for n in sorted(set(nums)):
        if out and n == out[-1][1] + 1:
            out[-1] = (out[-1][0], n)
        else:
            out.append((n, n))
    return out


def _blame(repo: git.Repo, parent: str, path: str, nums: list[int]) -> list[tuple[str, dict]]:
    """(commit, details) for each line, ignoring whitespace-only changes."""
    args = ["-w", "--line-porcelain"]
    for start, end in _ranges(nums):
        args += ["-L", f"{start},{end}"]
    out = repo.git.blame(*args, parent, "--", path)
    lines, sha, info = [], None, {}
    for row in out.split("\n"):
        if row.startswith("\t"):
            if sha:
                lines.append((sha, info))
            sha, info = None, {}
        elif sha is None:
            sha = row.split(" ", 1)[0] or None
        else:
            key, _, value = row.partition(" ")
            info[key] = value
    return lines


def _when(epoch: str) -> str:
    # Same convention as git_loader: local time, ISO format
    return datetime.fromtimestamp(int(epoch)).isoformat() if epoch else ""


def find_bug_origins(repo_path: str, commits, is_fix=None) -> list[dict]:
    """Every non-merge bug fix among `commits`, newest first, with its likely origins.
    `is_fix(commit)` decides which commits count as fixes; by default, ones whose message reads like a fix."""
    repo = git.Repo(repo_path)
    ingested = {c.sha for c in commits}
    is_fix = is_fix or (lambda c: commit_type(c.message) == "fix")
    fixes = []
    for c in commits:
        if not is_fix(c) or len(c.parent_shas) != 1:
            continue
        fix = {"sha": c.sha[:7], "message": c.message.split("\n")[0][:200], "author": c.author,
               "timestamp": c.timestamp, "status": "traced", "origins": [], "older_lines": 0, "days": None}
        try:
            deleted = _deleted_lines(repo, c.parent_shas[0], c.sha)
            counts, details = Counter(), {}
            for path, nums in deleted.items():
                for sha, info in _blame(repo, c.parent_shas[0], path, nums):
                    if "boundary" in info:
                        # Written before the oldest cloned commit: real, but out of reach
                        fix["older_lines"] += 1
                        continue
                    counts[sha] += 1
                    details.setdefault(sha, info)
            fix["origins"] = [{
                "sha": sha[:7], "message": details[sha].get("summary", "")[:200],
                "author": details[sha].get("author", ""), "timestamp": _when(details[sha].get("author-time", "")),
                "lines": n, "ingested": sha in ingested,
            } for sha, n in counts.most_common(TOP_ORIGINS)]
            if not deleted:
                fix["status"] = "nothing_to_trace"
            elif not fix["origins"]:
                fix["status"] = "older"
        except git.GitCommandError:
            fix["status"] = "error"
        if fix["origins"] and fix["origins"][0]["timestamp"]:
            lived = datetime.fromisoformat(c.timestamp) - datetime.fromisoformat(fix["origins"][0]["timestamp"])
            fix["days"] = max(0, lived.days)
        fixes.append(fix)
    return fixes


def summarize(fixes: list[dict]) -> dict:
    traced = [f for f in fixes if f["origins"]]
    days = [f["days"] for f in traced if f["days"] is not None]
    # Commits that sit behind more than one fix are worth a second look
    behind = Counter(sha for f in traced for sha in {o["sha"] for o in f["origins"]})
    first_seen = {o["sha"]: o for f in traced for o in f["origins"]}
    return {
        "fixes": len(fixes),
        "traced": len(traced),
        "older": sum(f["status"] == "older" for f in fixes),
        "nothing_to_trace": sum(f["status"] == "nothing_to_trace" for f in fixes),
        "median_days": median(days) if days else None,
        "repeat_origins": [
            {k: v for k, v in first_seen[sha].items() if k != "lines"} | {"fixes": n}
            for sha, n in behind.most_common(5) if n >= 2
        ],
    }
