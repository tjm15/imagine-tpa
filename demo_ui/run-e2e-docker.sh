#!/bin/bash
set -e

# Build the Docker image
echo "Building Playwright Docker image..."
docker build -t planner-ux-e2e -f Dockerfile.e2e .

# Run the tests
echo "Running Playwright tests..."
# We mount the current directory to /app so changes are reflected (optional, but good for dev)
# We specifically mount test-results to get the output back
docker run --rm \
  -v $(pwd)/test-results:/app/test-results \
  -v $(pwd)/playwright-report:/app/playwright-report \
  --ipc=host \
  planner-ux-e2e
