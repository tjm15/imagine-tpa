#!/usr/bin/env bash
set -euo pipefail

# cleanup_ghost_containers.sh — Clean up orphaned containerd containers not visible to Docker

echo "==> Checking for ghost/orphaned containers in containerd..."

# Check if we have access to containerd
if ! command -v ctr &> /dev/null; then
  echo "ERROR: 'ctr' command not found. Install containerd tools."
  exit 1
fi

# List all containers in moby namespace
echo ""
echo "Containers in containerd (moby namespace):"
sudo ctr -n moby containers ls

echo ""
echo "==> Checking for running tasks..."
GHOST_TASKS=$(sudo ctr -n moby task ls -q 2>/dev/null || true)

if [ -z "$GHOST_TASKS" ]; then
  echo "    No running tasks in containerd"
else
  echo "    Found running tasks:"
  sudo ctr -n moby task ls
  
  echo ""
  read -p "Do you want to kill all these tasks? [y/N] " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    for task_id in $GHOST_TASKS; do
      echo "    Killing task: $task_id"
      sudo ctr -n moby task kill -s SIGKILL "$task_id" 2>/dev/null || true
      sudo ctr -n moby task delete "$task_id" 2>/dev/null || true
    done
    echo "    ✓ All tasks killed"
  else
    echo "    Skipped killing tasks"
  fi
fi

echo ""
echo "==> Checking for containers to remove..."
GHOST_CONTAINERS=$(sudo ctr -n moby containers ls -q 2>/dev/null || true)

if [ -z "$GHOST_CONTAINERS" ]; then
  echo "    No containers in containerd"
else
  echo "    Found containers:"
  sudo ctr -n moby containers ls
  
  echo ""
  read -p "Do you want to remove all these containers? [y/N] " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    for container_id in $GHOST_CONTAINERS; do
      echo "    Removing container: $container_id"
      sudo ctr -n moby containers delete "$container_id" 2>/dev/null || true
    done
    echo "    ✓ All containers removed"
  else
    echo "    Skipped removing containers"
  fi
fi

echo ""
echo "✓ Cleanup complete"
echo ""
echo "Note: These were 'ghost' containers not visible to 'docker ps'."
echo "This usually happens after Docker daemon restarts or crashes."
echo "To prevent this, always use 'docker compose down' or 'docker stop' to stop containers properly."
