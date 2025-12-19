#!/usr/bin/env bash
set -euo pipefail

# fix_volume_permissions.sh — Fix ownership of Docker volumes for non-root containers

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

# Load UID/GID from .env
if [ ! -f .env ]; then
  echo "ERROR: .env file not found. Run ./scripts/setup_env.sh first."
  exit 1
fi

source .env

TARGET_UID=${UID:-1000}
TARGET_GID=${GID:-1000}

echo "==> Fixing volume permissions for UID:GID ${TARGET_UID}:${TARGET_GID}"
echo ""

# Get volume mount paths
MODEL_VOLUME=$(docker volume inspect tpa-oss_tpa_models --format '{{ .Mountpoint }}' 2>/dev/null || echo "")

if [ -z "$MODEL_VOLUME" ]; then
  echo "    tpa_models volume does not exist yet (will be created on first use)"
  echo "    Volume will be created with correct ownership when you start model services."
else
  echo "    tpa_models volume: $MODEL_VOLUME"
  echo "    Setting ownership to ${TARGET_UID}:${TARGET_GID}..."
  sudo chown -R "${TARGET_UID}:${TARGET_GID}" "$MODEL_VOLUME"
  echo "    ✓ Ownership updated"
fi

echo ""
echo "✓ Volume permissions configured"
echo ""
echo "Model containers will now be able to read/write as your user."
