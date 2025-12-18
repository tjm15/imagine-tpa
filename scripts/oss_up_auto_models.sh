#!/usr/bin/env bash
set -euo pipefail

COMPOSE=(docker compose -f docker/compose.oss.yml)

# The model supervisor is an internal compose service. This URL is used inside the `tpa-api` container.
export TPA_MODEL_SUPERVISOR_URL="${TPA_MODEL_SUPERVISOR_URL:-http://tpa-model-supervisor:8091}"

echo "Bringing up base OSS stack…"
"${COMPOSE[@]}" up -d --build

echo "Creating model containers (one-time)…"
"${COMPOSE[@]}" --profile models create tpa-llm tpa-vlm tpa-embeddings tpa-reranker

echo "Starting model supervisor…"
"${COMPOSE[@]}" --profile models-auto up -d --build tpa-model-supervisor

echo
echo "TPA OSS is up."
echo "- UI:  http://localhost:${TPA_UI_PORT:-3000}"
echo "- API: http://localhost:${TPA_API_PORT:-8000}/healthz"
echo
echo "Models will auto-start/stop as the API needs them (single-GPU friendly)."

