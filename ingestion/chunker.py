# ingestion/chunker.py
from dataclasses import asdict

def build_chunks(commits, pull_requests) -> list[dict]:
    # Map merge SHA → PR
    sha_to_pr = {
        pr.merge_commit_sha: pr
        for pr in pull_requests
        if pr.merge_commit_sha
    }

    chunks = []
    for commit in commits:
        pr = sha_to_pr.get(commit.sha)
        text = _build_text(commit, pr)

        chunks.append({
            "id":   commit.sha,
            "text": text,
            "metadata": {
                "sha":        commit.sha[:7],
                "author":     commit.author,
                "email":      commit.email,
                "timestamp":  commit.timestamp,
                "files":      ", ".join(commit.files_changed[:10]),
                "insertions": commit.insertions,
                "deletions":  commit.deletions,
                "has_pr":     pr is not None,
                "pr_number":  pr.number if pr else 0,
                "pr_labels":  ", ".join(pr.labels) if pr else "",
            }
        })

    print(f"Built {len(chunks)} chunks")
    return chunks

def _build_text(commit, pr=None) -> str:
    parts = [
        f"COMMIT: {commit.message}",
        f"AUTHOR: {commit.author}",
        f"FILES: {', '.join(commit.files_changed[:10])}",
        f"DIFF:\n{commit.diff}",
    ]
    if pr:
        parts.append(f"PR TITLE: {pr.title}")
        if pr.body:
            parts.append(f"PR DESCRIPTION: {pr.body[:1000]}")
        if pr.review_comments:
            parts.append("REVIEW COMMENTS:\n" + "\n".join(pr.review_comments[:3]))
        if pr.review_summaries:
            parts.append("REVIEW SUMMARY:\n" + "\n".join(pr.review_summaries[:2]))
    return "\n\n".join(parts)