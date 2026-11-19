#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="finally"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not in PATH." >&2
  exit 1
fi

if docker ps -aq --filter "name=^/${CONTAINER_NAME}$" | grep -q .; then
  echo "Stopping and removing container '${CONTAINER_NAME}'..."
  docker rm -f "${CONTAINER_NAME}" >/dev/null
  echo "FinAlly stopped. Persistent data volume 'finally-data' was preserved."
else
  echo "FinAlly container '${CONTAINER_NAME}' is not running."
fi
