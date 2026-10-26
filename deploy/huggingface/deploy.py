"""Deploy this project to a Hugging Face Docker Space in one command.

    python deploy/huggingface/deploy.py <username>/<space-name>
    python deploy/huggingface/deploy.py <username>/<space-name> --dry-run

It creates the Space if needed, copies settings from backend/.env into the
Space's private secrets and variables (after showing you their names and
asking), then uploads the source code. The first run asks for a Hugging Face
token with WRITE access.

Only an explicit allowlist of source files is uploaded, so .env files, local
databases, virtualenvs and node_modules never end up in the Space.
"""
import argparse
import sys
from pathlib import Path

from huggingface_hub import HfApi, get_token, login
from huggingface_hub.utils import filter_repo_objects

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / "backend" / ".env"

# fnmatch patterns: "*" also matches "/", so "dir/*.py" covers every depth
ALLOW = [
    "Dockerfile",
    "backend/requirements.txt",
    "backend/alembic.ini",
    "backend/migrations/*.py",
    "backend/migrations/script.py.mako",
    "backend/app/*.py",
    "backend/ingestion/*.py",
    "backend/storage/*.py",
    "backend/retrieval/*.py",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/index.html",
    "frontend/tsconfig.json",
    "frontend/vite.config.ts",
    "frontend/public/*",
    "frontend/src/*",
]
NEVER = ["**/.env*", "**/__pycache__/**", "**/node_modules/**", "**/.venv/**", "**/data/**"]

REQUIRED_SECRETS = ["SECRET_KEY", "ENCRYPTION_KEY", "DATABASE_URL"]
OPTIONAL_SECRETS = ["PINECONE_API_KEY", "GITHUB_TOKEN", "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"]
COPIED_VARIABLES = ["PINECONE_INDEX", "ADMIN_EMAILS", "MAX_COMMITS", "MAX_REPOS_PER_USER",
                    "MAX_INGESTS_PER_DAY", "REPO_TTL_HOURS", "MAX_CONCURRENT_INGESTS"]


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def space_url(repo_id: str) -> str:
    owner, name = repo_id.split("/")
    return f"https://{owner}-{name}".lower().replace("_", "-").replace(".", "-") + ".hf.space"


def plan(env: dict[str, str], repo_id: str):
    secrets = {k: env[k] for k in REQUIRED_SECRETS + OPTIONAL_SECRETS if env.get(k)}
    variables = {k: env[k] for k in COPIED_VARIABLES if env.get(k)}
    variables |= {"ENVIRONMENT": "production", "FRONTEND_URL": space_url(repo_id),
                  # The slim image uses hosted embeddings, which need their own 1024-dim index
                  "EMBEDDING_PROVIDER": "pinecone", "PINECONE_INDEX": "code-archaeologist-llama"}

    problems, warnings = [], []
    for key in REQUIRED_SECRETS:
        if not env.get(key):
            problems.append(f"{key} is missing from backend/.env")
    db = env.get("DATABASE_URL", "")
    if db.startswith("sqlite") or not db:
        problems.append("DATABASE_URL must be a hosted Postgres URL (e.g. Neon) - a Space's disk is wiped on restart")
    if "ep-xxxx" in db or "YOUR_PASSWORD" in db:
        problems.append("DATABASE_URL is still the example placeholder - paste your real Neon string")
    if not env.get("PINECONE_API_KEY"):
        warnings.append("PINECONE_API_KEY is empty: vectors would live on the Space's disk and vanish on restart")
    if not env.get("GITHUB_TOKEN"):
        warnings.append("GITHUB_TOKEN is empty: pull requests may be skipped by GitHub's anonymous rate limit")
    return secrets, variables, problems, warnings


def files_to_upload() -> list[str]:
    files = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
             if p.is_file() and "/.git/" not in f"/{p.relative_to(ROOT).as_posix()}"]
    return sorted(filter_repo_objects(filter_repo_objects(files, allow_patterns=ALLOW), ignore_patterns=NEVER))


def main():
    parser = argparse.ArgumentParser(description="Deploy to a Hugging Face Docker Space")
    parser.add_argument("repo_id", help="<username>/<space-name>, e.g. rishabhptdr/code-archaeologist")
    parser.add_argument("--dry-run", action="store_true", help="show what would happen, contact nothing")
    parser.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    parser.add_argument("--code-only", action="store_true", help="upload code, leave Space settings alone")
    args = parser.parse_args()
    if args.repo_id.count("/") != 1:
        parser.error("repo_id must look like <username>/<space-name>")

    env = read_env(ENV_FILE) if ENV_FILE.exists() else {}
    secrets, variables, problems, warnings = plan(env, args.repo_id)
    files = files_to_upload()

    print(f"Space      : https://huggingface.co/spaces/{args.repo_id}")
    print(f"App URL    : {variables['FRONTEND_URL']}")
    print(f"Code       : {len(files)} source files (no .env, data or dependencies)")
    if not args.code_only:
        print(f"Secrets    : {', '.join(secrets)}   (values are never printed)")
        print(f"Variables  : {', '.join(f'{k}={v}' for k, v in variables.items())}")
        for w in warnings:
            print(f"  ! {w}")
        if problems:
            for p in problems:
                print(f"  x {p}")
            sys.exit("\nFix backend/.env and run again.")

    if args.dry_run:
        print("\nDry run - nothing was sent.")
        return

    if not get_token():
        print("\nPaste a Hugging Face token with WRITE access (create one at https://huggingface.co/settings/tokens).")
        login()
    api = HfApi()
    me = api.whoami()
    owner = args.repo_id.split("/")[0]
    allowed = {me["name"], *(o["name"] for o in me.get("orgs", []))}
    if owner not in allowed:
        sys.exit(f"\nYou're logged in as '{me['name']}', which can't create Spaces under '{owner}'.")

    if not args.yes:
        what = "upload the code" if args.code_only else "save the secrets above to it and upload the code"
        if input(f"\nCreate/update the Space, {what}? [y/N] ").strip().lower() != "y":
            sys.exit("Cancelled - nothing was sent.")

    api.create_repo(args.repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
    if not args.code_only:
        # Settings go in first so the very first build starts with them
        for key, value in secrets.items():
            api.add_space_secret(args.repo_id, key, value)
        for key, value in variables.items():
            api.add_space_variable(args.repo_id, key, value)
        print(f"Saved {len(secrets)} secrets and {len(variables)} variables.")

    api.upload_folder(
        repo_id=args.repo_id, repo_type="space", folder_path=ROOT,
        allow_patterns=ALLOW, ignore_patterns=NEVER,
        # Remove files deleted locally since the last deploy
        delete_patterns=["backend/**", "frontend/**"],
        commit_message="Deploy from local source",
    )
    api.upload_file(
        repo_id=args.repo_id, repo_type="space",
        path_or_fileobj=ROOT / "deploy" / "huggingface" / "README.md", path_in_repo="README.md",
        commit_message="Update Space card",
    )
    print(f"\nDeployed. The first build takes ~10 minutes.")
    print(f"Build logs : https://huggingface.co/spaces/{args.repo_id}?logs=build")
    print(f"Open app   : {variables['FRONTEND_URL']}")


if __name__ == "__main__":
    main()
