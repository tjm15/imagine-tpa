#!/usr/bin/env bash
set -euo pipefail

# Reset the OSS Postgres volume (drops all DB data).
#
# This is useful after schema changes (new init SQL) or when you want a clean slate.
#
# Safety:
# - Only removes the Postgres data volume.
# - Does NOT remove MinIO data or model caches.
#
# Examples:
#   ./scripts/db_reset_oss.sh
#   TPA_COMPOSE_PROJECT=myproj ./scripts/db_reset_oss.sh

COMPOSE_FILE="${TPA_COMPOSE_FILE:-docker/compose.oss.yml}"
PROJECT="${TPA_COMPOSE_PROJECT:-tpa-oss}"
DB_VOLUME="${PROJECT}_tpa_db_data"

echo "Stopping DB service (project=${PROJECT})…" >&2
docker compose -f "$COMPOSE_FILE" stop tpa-db >/dev/null 2>&1 || true

echo "Removing DB container (project=${PROJECT})…" >&2
docker compose -f "$COMPOSE_FILE" rm -f tpa-db >/dev/null 2>&1 || true

echo "Cleaning any stray containers holding volume ${DB_VOLUME}…" >&2
docker ps -a --filter "volume=${DB_VOLUME}" -q | xargs -r docker rm -f >/dev/null 2>&1 || true

echo "Removing volume: ${DB_VOLUME}…" >&2
docker volume rm -f "$DB_VOLUME"

echo "Starting DB service…" >&2
docker compose -f "$COMPOSE_FILE" up -d tpa-db

echo "Done. If other services were running, restart them with:" >&2
echo "  docker compose -f $COMPOSE_FILE up -d" >&2
