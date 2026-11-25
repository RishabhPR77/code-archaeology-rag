#!/usr/bin/env bash
# Update the Azure copy to the newest image that passed CI. Touches only the "codearch" Compose project:
# Tejaskrit's containers aren't restarted or changed.
set -euo pipefail
cd "$(dirname "$0")"
docker compose pull
docker compose up -d
docker image prune -f --filter "label=org.opencontainers.image.source=https://github.com/RishabhPR77/code-archaeology-rag" >/dev/null || true
docker compose ps
