# retrieval/analytics.py
"""History analytics computed straight from commit chunks — no LLM or vector calls."""
from collections import Counter, defaultdict
from datetime import datetime


def _files(chunk) -> list[str]:
    return [f.strip() for f in chunk["metadata"]["files"].split(", ") if f.strip()]


def _message(chunk) -> str:
    first = chunk["text"].split("\n")[0]
    # "COMMIT [LABEL]: message" -> "message"
    return first.split("]: ", 1)[1] if "]: " in first else first.replace("COMMIT: ", "")


def commit_type(msg: str) -> str:
    m = msg.lower()
    if any(w in m for w in ["fix", "bug", "patch", "hotfix", "error", "issue", "crash"]):
        return "fix"
    if any(w in m for w in ["feat", "feature", "add", "new", "implement", "create", "introduce"]):
        return "feat"
    if any(w in m for w in ["refactor", "clean", "restructure", "reorganize", "simplify", "extract"]):
        return "refactor"
    if any(w in m for w in ["doc", "readme", "comment", "docstring"]):
        return "docs"
    if any(w in m for w in ["test", "spec", "coverage"]):
        return "test"
    if any(w in m for w in ["chore", "update", "bump", "upgrade", "deps", "merge", "release"]):
        return "chore"
    return "other"


def commit_log(chunks) -> list[dict]:
    rows = []
    for c in sorted(chunks, key=lambda c: c["metadata"]["timestamp"], reverse=True):
        meta, msg = c["metadata"], _message(c)
        rows.append({
            "sha": meta["sha"], "author": meta["author"], "timestamp": meta["timestamp"],
            "message": msg.split("\n")[0][:200], "type": commit_type(msg), "files": _files(c),
            "insertions": meta.get("insertions", 0), "deletions": meta.get("deletions", 0),
            "pr_number": meta.get("pr_number", 0) or None,
        })
    return rows


def overview(chunks) -> dict:
    if not chunks:
        return {"commits": 0, "authors": 0, "files": 0, "prs": 0, "first_commit": None,
                "last_commit": None, "insertions": 0, "deletions": 0, "types": {}, "activity": []}
    times = sorted(c["metadata"]["timestamp"] for c in chunks)
    weekly = Counter()
    for t in times:
        year, week, _ = datetime.fromisoformat(t).isocalendar()
        weekly[f"{year}-W{week:02d}"] += 1
    return {
        "commits":      len(chunks),
        "authors":      len({c["metadata"]["author"] for c in chunks}),
        "files":        len({f for c in chunks for f in _files(c)}),
        "prs":          len({c["metadata"]["pr_number"] for c in chunks if c["metadata"].get("pr_number")}),
        "first_commit": times[0],
        "last_commit":  times[-1],
        "insertions":   sum(c["metadata"].get("insertions", 0) for c in chunks),
        "deletions":    sum(c["metadata"].get("deletions", 0) for c in chunks),
        "types":        dict(Counter(commit_type(_message(c)) for c in chunks)),
        "activity":     [{"week": w, "commits": n} for w, n in sorted(weekly.items())],
    }


def file_timeline(chunks, filename: str) -> list[dict]:
    needle = filename.lower()
    return [row for row in reversed(commit_log(chunks))
            if any(needle in f.lower() for f in row["files"])]


def all_files(chunks) -> list[str]:
    return sorted({f for c in chunks for f in _files(c)})


def hottest_files(chunks, top_n=15) -> list[dict]:
    fc = Counter(f for c in chunks for f in _files(c))
    return [{"file": f, "changes": n} for f, n in fc.most_common(top_n)]


def co_change_analysis(chunks, top_n=10) -> list[dict]:
    pc = Counter()
    for c in chunks:
        files = sorted(set(_files(c)))
        for i in range(len(files)):
            for j in range(i + 1, len(files)):
                pc[(files[i], files[j])] += 1
    return [{"file_a": a, "file_b": b, "co_changes": n} for (a, b), n in pc.most_common(top_n)]


def author_analysis(chunks) -> list[dict]:
    ad = defaultdict(lambda: {"commits": 0, "insertions": 0, "deletions": 0,
                              "files": Counter(), "first": None, "last": None})
    for c in chunks:
        meta = c["metadata"]
        a = ad[meta["author"]]
        a["commits"] += 1
        a["insertions"] += meta.get("insertions", 0)
        a["deletions"] += meta.get("deletions", 0)
        a["files"].update(_files(c))
        ts = meta["timestamp"]
        a["first"] = min(a["first"] or ts, ts)
        a["last"] = max(a["last"] or ts, ts)
    return sorted([{"author": name, "commits": d["commits"], "insertions": d["insertions"],
                    "deletions": d["deletions"], "first_commit": d["first"], "last_commit": d["last"],
                    "top_files": [{"file": f, "changes": n} for f, n in d["files"].most_common(5)]}
                   for name, d in ad.items()], key=lambda x: x["commits"], reverse=True)


def pull_requests(chunks) -> list[dict]:
    prs = {}
    for c in chunks:
        meta = c["metadata"]
        num = meta.get("pr_number", 0)
        if not meta.get("has_pr") or not num or num in prs:
            continue
        title, author = "", ""
        for line in c["text"].split("\n"):
            # "PR #N by author: title"
            if line.startswith(f"PR #{num} by "):
                head, _, title = line.partition(": ")
                author = head.removeprefix(f"PR #{num} by ")
                break
        prs[num] = {"number": num, "title": title.strip() or "Untitled",
                    "author": author or meta["author"], "merged_at": meta["timestamp"],
                    "labels": [l.strip() for l in meta.get("pr_labels", "").split(",") if l.strip()],
                    "commit_sha": meta["sha"], "files": _files(c)}
    return sorted(prs.values(), key=lambda p: p["number"], reverse=True)
