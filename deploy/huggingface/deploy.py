"""Push this project to a Hugging Face Docker Space.

Usage:
    python deploy/huggingface/deploy.py <username>/<space-name>

Uses your saved Hugging Face login or HF_TOKEN; otherwise it asks for a
write token once and saves it.

Only an explicit allowlist of source files is uploaded, so .env files, local
databases, virtualenvs and node_modules can never end up in the Space.
"""
import sys
from pathlib import Path

from huggingface_hub import HfApi, get_token, login

ROOT = Path(__file__).resolve().parents[2]

# fnmatch patterns: "*" also matches "/", so "dir/*.py" covers every depth
ALLOW = [
    "Dockerfile",
    "backend/requirements.txt",
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


def main():
    if len(sys.argv) != 2 or "/" not in sys.argv[1]:
        sys.exit("usage: python deploy/huggingface/deploy.py <username>/<space-name>")
    repo_id = sys.argv[1]
    if not get_token():
        print("Paste a Hugging Face token with WRITE access (huggingface.co/settings/tokens).")
        login()
    api = HfApi()

    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
    api.upload_folder(
        repo_id=repo_id, repo_type="space", folder_path=ROOT,
        allow_patterns=ALLOW, ignore_patterns=NEVER,
        # Remove files deleted locally since the last deploy
        delete_patterns=["backend/**", "frontend/**"],
        commit_message="Deploy from local source",
    )
    api.upload_file(
        repo_id=repo_id, repo_type="space",
        path_or_fileobj=ROOT / "deploy" / "huggingface" / "README.md", path_in_repo="README.md",
        commit_message="Update Space card",
    )
    owner, name = repo_id.split("/")
    subdomain = f"{owner}-{name}".lower().replace("_", "-").replace(".", "-")
    print(f"\nDeployed. Build logs: https://huggingface.co/spaces/{repo_id}?logs=build")
    print(f"App URL (set FRONTEND_URL to this): https://{subdomain}.hf.space")


if __name__ == "__main__":
    main()
