# ingestion/github_enricher.py
import os, re, time
from dataclasses import dataclass
from github import Github, RateLimitExceededException

@dataclass
class PRRecord:
    number: int
    title: str
    body: str
    author: str
    merge_commit_sha: str
    merged_at: str
    labels: list
    linked_issues: list
    review_comments: list
    review_summaries: list
    discussion: list

def fetch_prs(repo_name: str, max_prs: int = 200) -> list[PRRecord]:
    g = Github(os.getenv("GITHUB_TOKEN"))
    repo = g.get_repo(repo_name)
    records = []

    for pr in repo.get_pulls(state="closed", sort="updated"):
        if not pr.merged:
            continue
        if len(records) >= max_prs:
            break
        try:
            records.append(PRRecord(
                number           = pr.number,
                title            = pr.title,
                body             = (pr.body or "")[:2000],
                author           = pr.user.login if pr.user else "unknown",
                merge_commit_sha = pr.merge_commit_sha or "",
                merged_at        = pr.merged_at.isoformat() if pr.merged_at else "",
                labels           = [l.name for l in pr.labels],
                linked_issues    = _extract_issues(pr.body or ""),
                review_comments  = [c.body for c in pr.get_review_comments() if c.body.strip()][:10],
                review_summaries = [r.body for r in pr.get_reviews() if r.body and r.body.strip()][:5],
                discussion       = [c.body for c in pr.get_issue_comments() if c.body.strip()][:10],
            ))
            time.sleep(0.5)
        except Exception as e:
            print(f"Skipping PR #{pr.number}: {e}")
            continue

    print(f"Fetched {len(records)} merged PRs")
    return records

def _extract_issues(body: str) -> list:
    pattern = r'(?:fix(?:es)?|close[sd]?|resolve[sd]?)\s+#(\d+)'
    return [int(n) for n in re.findall(pattern, body, re.IGNORECASE)]