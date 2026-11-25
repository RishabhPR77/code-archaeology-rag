#!/usr/bin/env bash
# One-time setup of ~/codearch on the VM: the deploy files, the database password (generated here, on the
# VM), and every setting that isn't a secret. Safe to re-run: settings files that exist are kept.
#   usage: ./setup.sh <domain>      for example ./setup.sh codearch.20-2-69-168.sslip.io
set -euo pipefail
DOMAIN="${1:?usage: setup.sh <domain>}"
DIR="${CODEARCH_DIR:-$HOME/codearch}"
RAW=https://raw.githubusercontent.com/RishabhPR77/code-archaeology-rag/main/deploy/azure

mkdir -p "$DIR" && cd "$DIR"
for f in docker-compose.yml update.sh move-database.sh Caddyfile.site; do
  curl -fsSL -o "$f" "$RAW/$f"
done
chmod +x update.sh move-database.sh
umask 077

if [ ! -f db.env ]; then
  printf 'POSTGRES_USER=codearch\nPOSTGRES_DB=codearch\nPOSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 24)" > db.env
fi
password=$(sed -n 's/^POSTGRES_PASSWORD=//p' db.env)

if [ ! -f codearch.env ]; then
  cat > codearch.env <<EOF
# Filled in by setup.sh
DATABASE_URL=postgresql://codearch:${password}@codearch-db:5432/codearch
FRONTEND_URL=https://${DOMAIN}
PINECONE_INDEX=code-archaeologist-llama
EMBEDDING_PROVIDER=pinecone
EMAIL_DELIVERY=brevo

# Paste each value after its = sign, from Render -> code-archaeologist -> Environment.
# SECRET_KEY and ENCRYPTION_KEY must be exactly the same as on Render: the copied database holds
# API keys encrypted with ENCRYPTION_KEY.
SECRET_KEY=
ENCRYPTION_KEY=
PINECONE_API_KEY=
GITHUB_TOKEN=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_APP_SLUG=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
BREVO_API_KEY=
EMAIL_FROM=
CONTACT_EMAIL=
ADMIN_EMAILS=
EOF
fi

if [ ! -f move-database.env ]; then
  printf "# Paste Render's DATABASE_URL after the = sign. It's only read from. Delete this file after the copy.\nOLD_DATABASE_URL=\n" > move-database.env
fi

echo "Set up $DIR for https://$DOMAIN"
echo "Next: fill in the empty values in codearch.env and move-database.env."
