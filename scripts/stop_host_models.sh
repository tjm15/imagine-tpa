#!/usr/bin/env bash
set -euo pipefail

# stop_host_models.sh — Stop vLLM and other model servers running on the host

echo "==> Searching for vLLM processes..."
VLLM_PIDS=$(ps aux | grep -E "vllm serve|vllm.entrypoints" | grep -v grep | awk '{print $2}' || true)

if [ -z "$VLLM_PIDS" ]; then
  echo "    No vLLM processes found"
else
  echo "    Found vLLM processes: $VLLM_PIDS"
  echo "    Stopping vLLM processes..."
  for pid in $VLLM_PIDS; do
    sudo kill -TERM "$pid" 2>/dev/null || true
    echo "    Sent SIGTERM to PID $pid"
  done
  
  # Wait a moment for graceful shutdown
  sleep 2
  
  # Force kill if still running
  for pid in $VLLM_PIDS; do
    if ps -p "$pid" > /dev/null 2>&1; then
      echo "    Force killing PID $pid"
      sudo kill -9 "$pid" 2>/dev/null || true
    fi
  done
fi

echo ""
echo "==> Checking for other model server processes..."
OTHER_PIDS=$(ps aux | grep -E "(text-embeddings-inference|text-generation-inference|tei-server)" | grep -v grep | awk '{print $2}' || true)

if [ -z "$OTHER_PIDS" ]; then
  echo "    No other model servers found"
else
  echo "    Found other model servers: $OTHER_PIDS"
  echo "    Stopping..."
  for pid in $OTHER_PIDS; do
    sudo kill -TERM "$pid" 2>/dev/null || true
    echo "    Sent SIGTERM to PID $pid"
  done
  
  sleep 2
  
  for pid in $OTHER_PIDS; do
    if ps -p "$pid" > /dev/null 2>&1; then
      echo "    Force killing PID $pid"
      sudo kill -9 "$pid" 2>/dev/null || true
    fi
  done
fi

echo ""
echo "✓ All host-level model servers stopped"
echo ""
echo "GPU memory should now be freed. Check with: nvidia-smi"
