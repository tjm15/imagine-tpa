#!/usr/bin/env bash
set -euo pipefail

# setup_env.sh — Set up .env file with proper UID/GID for non-root containers

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

if [ -f .env ]; then
  echo "⚠️  .env file already exists"
  read -p "Do you want to update UID/GID in the existing .env? [y/N] " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Skipping .env update"
    exit 0
  fi
fi

# Get current user's UID/GID
CURRENT_UID=$(id -u)
CURRENT_GID=$(id -g)

echo "==> Setting up .env file"
echo "    Your UID: $CURRENT_UID"
echo "    Your GID: $CURRENT_GID"

if [ ! -f .env ]; then
  # Create new .env from example
  cp .env.example .env
  echo "    ✓ Created .env from .env.example"
fi

# Update or add UID/GID
if grep -q "^UID=" .env; then
  sed -i "s/^UID=.*/UID=$CURRENT_UID/" .env
  echo "    ✓ Updated UID=$CURRENT_UID"
else
  echo "UID=$CURRENT_UID" >> .env
  echo "    ✓ Added UID=$CURRENT_UID"
fi

if grep -q "^GID=" .env; then
  sed -i "s/^GID=.*/GID=$CURRENT_GID/" .env
  echo "    ✓ Updated GID=$CURRENT_GID"
else
  echo "GID=$CURRENT_GID" >> .env
  echo "    ✓ Added GID=$CURRENT_GID"
fi

echo ""
echo "✓ .env file configured"
echo ""
echo "This ensures model containers run as your user (not root) for better security."
echo "The tpa_models volume will be owned by UID:GID ${CURRENT_UID}:${CURRENT_GID}."
