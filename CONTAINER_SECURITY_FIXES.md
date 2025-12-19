# Container Security and Reliability Fixes

## Problems Fixed

### 1. Ghost Containers
**Problem:** Containers became invisible to `docker ps` but kept running, consuming resources (especially GPU memory). This happened after Docker daemon crashes or restarts.

**Root Cause:** `restart: unless-stopped` policy caused containers to restart automatically through containerd, even when Docker CLI couldn't see them.

**Fix:** Changed default restart policy to `restart: "no"` for all services.

### 2. Running as Root
**Problem:** All containers (including model servers) ran as root by default, which is a security issue.

**Fix:** Added `user: "${UID:-1000}:${GID:-1000}"` to model services (tpa-llm, tpa-vlm, tpa-embeddings, tpa-reranker).

### 3. Poor Signal Handling
**Problem:** Containers didn't handle SIGTERM/SIGKILL properly, leading to unclean shutdowns.

**Fix:** Added `init: true` to all services to enable proper signal handling via tini.

## Changes Made

### docker/compose.oss.yml
- Changed `x-service-defaults` restart policy from `unless-stopped` to `"no"`
- Added `init: true` to service defaults
- Added `user: "${UID:-1000}:${GID:-1000}"` to:
  - tpa-llm
  - tpa-vlm
  - tpa-embeddings
  - tpa-reranker
- Added explicit `restart: "no"` and `init: true` to tpa-model-supervisor
- Added documentation comments explaining the security rationale

### .env.example
- Added `UID=1000` and `GID=1000` with explanatory comments

### New Scripts

#### scripts/setup_env.sh
Automatically configures UID/GID in `.env` to match your current user.

Usage:
```bash
./scripts/setup_env.sh
```

#### scripts/cleanup_ghost_containers.sh
Interactive script to find and remove ghost containers from containerd.

Usage:
```bash
./scripts/cleanup_ghost_containers.sh
```

#### scripts/fix_volume_permissions.sh
Fixes ownership of Docker volumes to match your UID/GID.

Usage:
```bash
./scripts/fix_volume_permissions.sh
```

#### scripts/docker_down.sh (updated)
- Now checks all compose profiles (--profile llm, --profile vlm, etc.)
- Detects ghost containers and warns you
- Supports flags: --images, --volumes, --all

Usage:
```bash
./scripts/docker_down.sh              # Stop and remove containers
./scripts/docker_down.sh --images     # Also remove images
./scripts/docker_down.sh --volumes    # Also remove volumes (destructive)
./scripts/docker_down.sh --all        # Remove everything
```

### Documentation Updates

#### DOCKERIZED_IMPLEMENTATION_GUIDE.md
- Added security setup instructions in Step 2.1
- Added new troubleshooting section (Section 12) covering:
  - Ghost containers (symptoms, cause, fix, prevention)
  - Permission errors (symptoms, cause, fix)
  - Model supervisor restart loops (symptoms, cause, fix)

## Migration Guide

If you have existing containers running:

1. **Stop everything cleanly:**
   ```bash
   ./scripts/docker_down.sh --images
   ```

2. **Clean up ghost containers (if any):**
   ```bash
   ./scripts/cleanup_ghost_containers.sh
   ```
   Or if that doesn't work:
   ```bash
   sudo systemctl stop docker.socket docker.service containerd.service
   sudo rm -rf /var/lib/containerd/io.containerd.metadata.v1.bolt/meta.db
   sudo systemctl start containerd.service docker.service
   ```

3. **Set up your environment:**
   ```bash
   ./scripts/setup_env.sh
   ```

4. **Fix volume permissions (if volumes already exist):**
   ```bash
   ./scripts/fix_volume_permissions.sh
   ```

5. **Start containers normally:**
   ```bash
   docker compose -f docker/compose.oss.yml up -d --build
   ```

## What Changed for Day-to-Day Usage

### Before
- Containers automatically restarted (could create ghosts)
- Ran as root (security issue)
- Hard to fully stop (especially with model supervisor)

### After
- Containers stay stopped when you stop them
- Run as your user (better security)
- Clean shutdown every time
- Clear warnings about ghost containers if they occur

### New Workflow
1. Start services: `docker compose -f docker/compose.oss.yml up -d`
2. Stop services: `./scripts/docker_down.sh`
3. Start models on-demand: `docker compose -f docker/compose.oss.yml --profile llm up -d`
4. Check for issues: `./scripts/docker_down.sh` (warns about ghosts)

## Verification

Check that your containers are running as your user:
```bash
docker compose -f docker/compose.oss.yml --profile llm up -d tpa-llm
docker inspect tpa-oss-tpa-llm-1 | jq '.[0].Config.User'
# Should output: "1000:1000" (or your UID:GID)
```

Check restart policy:
```bash
docker inspect tpa-oss-tpa-llm-1 | jq '.[0].HostConfig.RestartPolicy'
# Should output: {"Name": "no", "MaximumRetryCount": 0}
```
