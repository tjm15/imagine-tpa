#!/usr/bin/env bash
set -euo pipefail

# Convenience wrapper around `psql` inside the OSS compose DB container.
#
# Why this exists:
# - `docker compose exec -T ... psql` can appear to "freeze" when Postgres prompts for a password.
# - This script uses the container's POSTGRES_* env vars and forces TCP (`-h 127.0.0.1`).
#
# Examples:
#   ./scripts/db_psql_oss.sh -c '\\dt'
#   ./scripts/db_psql_oss.sh -c 'select count(*) from chunks;'

COMPOSE_FILE="${TPA_COMPOSE_FILE:-docker/compose.oss.yml}"
DB_SERVICE="${TPA_DB_SERVICE:-tpa-db}"

docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" sh -lc \
  'PGPASSWORD="${POSTGRES_PASSWORD:-tpa}" psql -h 127.0.0.1 -U "${POSTGRES_USER:-tpa}" -d "${POSTGRES_DB:-tpa}" "$@"' \
  sh "$@"

