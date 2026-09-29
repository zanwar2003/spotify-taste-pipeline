#!/usr/bin/env bash
# One-time database setup for a hosted Postgres (Neon).
# Usage:  NEON_DIRECT_URL='postgresql://...' ./scripts/setup_neon.sh
# Prints the password it generated for the restricted app role; put that in APP_DATABASE_URL.
set -euo pipefail
: "${NEON_DIRECT_URL:?set NEON_DIRECT_URL to the direct (non-pooled) owner connection string}"
cd "$(dirname "$0")/.."
for f in db/init/*.sql; do
  echo "applying $f"
  psql "$NEON_DIRECT_URL" -v ON_ERROR_STOP=1 -q -f "$f"
done
PW=$(openssl rand -hex 24)
psql "$NEON_DIRECT_URL" -v ON_ERROR_STOP=1 -q -c "ALTER ROLE tastepipe_app PASSWORD '$PW'"
echo
echo "Done. tastepipe_app password (save it, shown once): $PW"
