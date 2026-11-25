#!/usr/bin/env bash
# Copy the database used by Render into this copy's own PostgreSQL container, once, before the app's
# first start. Render's database is only READ (pg_dump), so Render keeps working unchanged.
#   usage: sudo ./move-database.sh      (needs OLD_DATABASE_URL in move-database.env)
set -euo pipefail
cd "$(dirname "$0")"

old=$(sed -n 's/^OLD_DATABASE_URL=//p' move-database.env 2>/dev/null || true)
new=$(sed -n 's/^DATABASE_URL=//p' codearch.env)
if [ -z "$old" ]; then
  echo "Paste Render's DATABASE_URL into move-database.env first." >&2
  exit 1
fi

docker compose up -d db
for _ in $(seq 1 30); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' codearch-db-1 2>/dev/null)" = healthy ] && break
  sleep 2
done

# The URLs go to the tools through a private temporary file, never on a command line
umask 077
urls=$(mktemp)
trap 'rm -f "$urls"' EXIT
printf 'OLD=%s\nNEW=%s\n' "$old" "$new" > "$urls"

docker run --rm --network codearch_default --env-file "$urls" postgres:18-alpine sh -euc '
  tables=$(psql "$NEW" -Atc "select count(*) from information_schema.tables where table_schema = '"'"'public'"'"'")
  if [ "$tables" != 0 ]; then
    echo "The new database already has tables, so nothing was copied (this protects it). To start over:" >&2
    echo "  docker compose down -v   (deletes only this copy'"'"'s database)" >&2
    exit 1
  fi
  echo "Reading the current database (read-only)..."
  pg_dump --no-owner --no-privileges --format=custom --file=/tmp/db.dump "$OLD"
  echo "Writing the copy..."
  pg_restore --no-owner --no-privileges --dbname="$NEW" /tmp/db.dump || true
  echo
  echo "Rows per table, old -> new (they should match):"
  for t in users repos repo_data conversations queries provider_credentials; do
    o=$(psql "$OLD" -Atc "select count(*) from $t")
    n=$(psql "$NEW" -Atc "select count(*) from $t")
    printf "  %-22s %6s -> %6s %s\n" "$t" "$o" "$n" "$([ "$o" = "$n" ] && echo ok || echo DIFFERENT)"
  done
'
echo
echo "Done. Now delete move-database.env: it holds Render's database password."
