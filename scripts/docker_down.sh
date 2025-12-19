#!/usr/bin/env bash
set -euo pipefail

# docker_down.sh — Take down all TPA containers and optionally remove images

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

# Parse arguments
REMOVE_IMAGES=false
REMOVE_VOLUMES=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --images|-i)
      REMOVE_IMAGES=true
      shift
      ;;
    --volumes|-v)
      REMOVE_VOLUMES=true
      shift
      ;;
    --all|-a)
      REMOVE_IMAGES=true
      REMOVE_VOLUMES=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--images|-i] [--volumes|-v] [--all|-a]"
      exit 1
      ;;
  esac
done

echo "==> Taking down OSS profile containers (all profiles)..."
COMPOSE_ARGS=""
if [ "$REMOVE_VOLUMES" = true ]; then
  COMPOSE_ARGS="$COMPOSE_ARGS -v"
fi
if [ "$REMOVE_IMAGES" = true ]; then
  COMPOSE_ARGS="$COMPOSE_ARGS --rmi all"
fi

# Stop all profile containers (base + optional profiles)
docker compose -f docker/compose.oss.yml \
  --profile ui-dev \
  --profile web \
  --profile vision \
  --profile llm \
  --profile vlm \
  --profile embeddings \
  --profile reranker \
  --profile models-auto \
  down $COMPOSE_ARGS

echo ""
echo "==> Taking down Azure profile containers (if any)..."
docker compose -f docker/compose.azure.yml down $COMPOSE_ARGS 2>/dev/null || echo "    (no Azure containers found)"

echo ""
echo "==> Removing dangling TPA containers (if any)..."
docker ps -a --filter "name=tpa-" --format "{{.ID}}" | xargs -r docker rm -f || true

if [ "$REMOVE_IMAGES" = true ]; then
  echo ""
  echo "==> Removing TPA images..."
  docker images --filter "reference=tpa-*" --format "{{.Repository}}:{{.Tag}}" | xargs -r docker rmi -f || true
fi

echo ""
echo "==> Checking for ghost containers in containerd..."
if command -v ctr &> /dev/null; then
  GHOST_COUNT=$(sudo ctr -n moby containers ls -q 2>/dev/null | wc -l || echo "0")
  if [ "$GHOST_COUNT" -gt 0 ]; then
    echo "    ⚠️  Found $GHOST_COUNT ghost container(s) in containerd (not visible to docker ps)"
    echo "    These are orphaned containers, usually from Docker daemon crashes."
    echo "    Run './scripts/cleanup_ghost_containers.sh' to remove them."
  else
    echo "    No ghost containers found"
  fi
else
  echo "    (ctr command not available; skipping ghost container check)"
fi

echo ""
echo "✓ All TPA containers stopped and removed"
if [ "$REMOVE_IMAGES" = true ]; then
  echo "✓ TPA images removed"
fi
if [ "$REMOVE_VOLUMES" = true ]; then
  echo "✓ Volumes removed"
fi
