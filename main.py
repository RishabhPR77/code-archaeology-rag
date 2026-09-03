# main.py
import os, json, git
from dotenv import load_dotenv

load_dotenv()

from ingestion.git_loader import load_commits
from ingestion.github_enricher import fetch_prs
from ingestion.chunker import build_chunks
from storage.vector_store import VectorStore

REPO_URL   = os.getenv("REPO_URL")
REPO_NAME  = os.getenv("REPO_NAME")
CLONE_PATH = os.getenv("CLONE_PATH", "./data/repo")
RAW_PATH   = "./data/raw/chunks.json"

def run_ingestion():
    if not os.path.exists(CLONE_PATH):
        print(f"Cloning {REPO_URL}...")
        git.Repo.clone_from(REPO_URL, CLONE_PATH)
    else:
        print("Repo already cloned, skipping.")

    commits = load_commits(CLONE_PATH, max_count=300)

    print("Fetching pull requests...")
    prs = []
    try:
        fetch_result = fetch_prs(REPO_NAME, max_prs=200)
        prs = fetch_result.prs
        for w in fetch_result.warnings:
            print(f"WARNING: {w}")
    except Exception as e:
        print(f"PR fetch failed: {e} — continuing without PR data")

    chunks = build_chunks(commits, prs)

    os.makedirs("./data/raw", exist_ok=True)
    with open(RAW_PATH, "w") as f:
        json.dump(chunks, f, indent=2)
    print(f"Saved {len(chunks)} chunks to {RAW_PATH}")

    store = VectorStore()
    store.ingest(chunks)
    print("Ingestion complete!")


def run_query(question: str):
    from query.engine import ask
    print(f"\nSearching commits for: {question}")
    result = ask(question)
    print("=" * 60)
    print("ANSWER")
    print("=" * 60)
    print(result["answer"])
    print("\n" + "=" * 60)
    print("SOURCES USED")
    print("=" * 60)
    for i, source in enumerate(result["sources"], 1):
        print(f"\n[{i}] {source['author']} — {source['timestamp'][:10]}")
        print(f"    Files:  {source['files'][:80]}")
        print(f"    Score:  {source['score']}")
        print(f"    Has PR: {source['has_pr']}")


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ingest"

    if cmd == "query":
        run_query(" ".join(sys.argv[2:]))

    elif cmd == "timeline":
        from query.engine import timeline_ask
        filename = sys.argv[2] if len(sys.argv) > 2 else "sessions.py"
        result = timeline_ask(filename)
        print(f"\nEvolution of: {filename}\n")
        print("=" * 60)
        print(result["answer"])
        print("\n" + "=" * 60)
        print(f"COMMITS FOUND: {len(result['timeline'])}")
        for entry in result["timeline"]:
            print(f"  {entry['timestamp'][:10]} — {entry['author']:<20} {entry['message'][:60]}")

    elif cmd == "hotfiles":
        from retrieval.graph import CommitGraph
        graph = CommitGraph()
        print("\nMost frequently changed files:\n")
        for item in graph.hottest_files():
            print(f"  {item['change_count']:>3}x  {item['file']}")

    elif cmd == "cochange":
        from retrieval.graph import CommitGraph
        graph = CommitGraph()
        print("\nFiles that change together most often:\n")
        for item in graph.co_change_analysis():
            print(f"  {item['co_changes']:>3}x  {item['files'][0]}")
            print(f"         {item['files'][1]}")

    elif cmd == "authors":
        from retrieval.graph import CommitGraph
        graph = CommitGraph()
        print("\nAuthor analysis:\n")
        for author in graph.author_analysis():
            print(f"  {author['author']} — {author['commits']} commits")
            for f in author["top_files"][:3]:
                print(f"    {f['changes']}x {f['file']}")

    else:
        run_ingestion()