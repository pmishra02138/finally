#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

IMAGE_NAME="finally"
CONTAINER_NAME="finally"
VOLUME_NAME="finally-data"
PORT="8000"
BUILD_FLAG=false
OPEN_BROWSER=false

for arg in "$@"; do
  case "$arg" in
    --build)
      BUILD_FLAG=true
      ;;
    --open)
      OPEN_BROWSER=true
      ;;
    -h|--help)
      echo "Usage: $0 [--build] [--open]"
      echo "  --build  Rebuild the Docker image before starting"
      echo "  --open   Open http://localhost:${PORT} in your default browser"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not in PATH." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Error: Docker daemon is not running. Please start Docker and try again." >&2
  exit 1
fi

cd "${PROJECT_ROOT}"

# Build image if missing or --build was requested
if [[ "${BUILD_FLAG}" == "true" ]] || ! docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
  echo "Building Docker image '${IMAGE_NAME}'..."
  docker build -t "${IMAGE_NAME}" "${PROJECT_ROOT}"
fi

# Handle existing container idempotently
if docker ps -q --filter "name=^/${CONTAINER_NAME}$" | grep -q .; then
  if [[ "${BUILD_FLAG}" == "true" ]]; then
    echo "Restarting '${CONTAINER_NAME}' with rebuilt image..."
    docker rm -f "${CONTAINER_NAME}" >/dev/null
  else
    echo "FinAlly is already running at http://localhost:${PORT}"
    exit 0
  fi
elif docker ps -aq --filter "name=^/${CONTAINER_NAME}$" | grep -q .; then
  docker rm "${CONTAINER_NAME}" >/dev/null
fi

ENV_ARGS=()
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
  ENV_ARGS=(--env-file "${PROJECT_ROOT}/.env")
else
  echo "Note: .env not found in project root; starting with default simulator settings."
fi

echo "Starting FinAlly container '${CONTAINER_NAME}'..."
docker run -d \
  --name "${CONTAINER_NAME}" \
  -v "${VOLUME_NAME}:/app/db" \
  -p "127.0.0.1:${PORT}:8000" \
  "${ENV_ARGS[@]}" \
  "${IMAGE_NAME}" >/dev/null

# Wait for /api/health
echo -n "Waiting for FinAlly to become ready"
READY=false
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
    READY=true
    break
  fi
  echo -n "."
  sleep 1
done
echo ""

if [[ "${READY}" != "true" ]]; then
  echo "Error: FinAlly failed to become healthy within 30s. Recent logs:" >&2
  docker logs --tail 40 "${CONTAINER_NAME}" >&2 || true
  exit 1
fi

echo "FinAlly is running at http://localhost:${PORT}"

if [[ "${OPEN_BROWSER}" == "true" ]]; then
  if command -v open >/dev/null 2>&1; then
    open "http://localhost:${PORT}"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://localhost:${PORT}"
  fi
fi
