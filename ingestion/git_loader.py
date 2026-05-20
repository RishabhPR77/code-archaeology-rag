# ingestion/git_loader.py
import git
from datetime import datetime
from dataclasses import dataclass

@dataclass
class CommitRecord:
    sha: str
    message: str
    author: str
    email: str
    timestamp: str
    files_changed: list
    insertions: int
    deletions: int
    diff: str
    parent_shas: list

def load_commits(repo_path: str, max_count: int = 300) -> list[CommitRecord]:
    repo = git.Repo(repo_path)
    records = []

    for commit in repo.iter_commits(max_count=max_count):
        try:
            if commit.parents:
                diff_text = repo.git.diff(
                    commit.parents[0].hexsha,
                    commit.hexsha,
                    unified=3
                )
            else:
                diff_text = repo.git.show(commit.hexsha)

            records.append(CommitRecord(
                sha           = commit.hexsha,
                message       = commit.message.strip(),
                author        = commit.author.name,
                email         = commit.author.email,
                timestamp     = datetime.fromtimestamp(commit.authored_date).isoformat(),
                files_changed = list(commit.stats.files.keys()),
                insertions    = commit.stats.total["insertions"],
                deletions     = commit.stats.total["deletions"],
                diff          = diff_text[:4000],
                parent_shas   = [p.hexsha for p in commit.parents],
            ))
        except Exception as e:
            print(f"Skipping commit {commit.hexsha[:7]}: {e}")
            continue

    print(f"Loaded {len(records)} commits")
    return records