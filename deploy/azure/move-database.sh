#!/usr/bin/env bash
# Copy the database into the new Neon project (Singapore) for the Azure copy.
#
# Render's database is only READ (pg_dump): Render keeps using it, unchanged. Run this once, on the VM,
# from this folder, with a file move-database.env next to it holding:
#   OLD_DATABASE_URL=<Render's DATABASE_URL>
#   NEW_DATABASE_URL=<the new Singapore project's connection string>
# The PostgreSQL tools come from a throwaway container, so nothing is installed on the VM.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f move-database.env ]; then
  echo "Create move-database.env with OLD_DATABASE_URL and NEW_DATABASE_URL first (see README.md, step 4)." >&2
  exit 1
fi
chmod 600 move-database.env

docker run --rm --env-file move-database.env postgres:18-alpine sh -euc '
  echo "Reading the current database (read-only)..."
  pg_dump --no-owner --no-privileges --format=custom --file=/tmp/db.dump "$OLD_DATABASE_URL"
  echo "Writing the copy..."
  pg_restore --no-owner --no-privileges --dbname="$NEW_DATABASE_URL" /tmp/db.dump || true
  echo
  echo "Rows per table, old -> new (they should match):"
  for t in users repos repo_data conversations queries provider_credentials; do
    old=$(psql "$OLD_DATABASE_URL" -Atc "select count(*) from $t")
    new=$(psql "$NEW_DATABASE_URL" -Atc "select count(*) from $t")
    printf "  %-22s %6s -> %6s %s\n" "$t" "$old" "$new" "$([ "$old" = "$new" ] && echo ok || echo DIFFERENT)"
  done
'
echo
echo "Done. Now delete move-database.env: it holds both database passwords."
