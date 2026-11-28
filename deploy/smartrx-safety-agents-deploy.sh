#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-smartrx-safety-agents:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-smartrx-safety-agents-prod}"
HOST_PORT="${HOST_PORT:-8080}"
HEALTH_URL="http://127.0.0.1:${HOST_PORT}/health"

require_secret() {
  local name="$1"
  local min_len="${2:-16}"
  local val="${!name:-}"
  if [[ -z "${val}" ]]; then
    echo "ERROR: Required environment variable ${name} is unset or empty." >&2
    exit 1
  fi
  if (( ${#val} < min_len )); then
    echo "ERROR: ${name} must be at least ${min_len} characters in production." >&2
    exit 1
  fi
}

echo "[1/5] Validating required production secrets..."
require_secret "MCP_API_KEY" 16
require_secret "PLAN_SIGNING_SECRET" 16
require_secret "SMARTRX_SAFETY_AGENTS_WEBHOOK_SECRET" 16
require_secret "GEMINI_API_KEY" 8

echo "[2/5] Checking Docker daemon health..."
docker info >/dev/null 2>&1 || {
  echo "ERROR: Docker daemon is not reachable." >&2
  exit 1
}

mkdir -p ./data ./audit_logs

echo "[3/5] Building production image (${IMAGE_NAME})..."
docker build -t "${IMAGE_NAME}" .

echo "[4/5] Launching production stack..."
if docker compose version >/dev/null 2>&1; then
  docker compose -f docker-compose.prod.yml up -d
else
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  docker run -d \
    --name "${CONTAINER_NAME}" \
    --restart unless-stopped \
    --memory 2048m \
    --read-only \
    --tmpfs /tmp:rw,noexec,nosuid,size=64m \
    --security-opt no-new-privileges:true \
    -p "${HOST_PORT}:8080" \
    -v "${PWD}/data:/app/data" \
    -v "${PWD}/audit_logs:/app/audit_logs" \
    -e ENVIRONMENT=production \
    -e REQUIRE_AUTH=true \
    -e MCP_API_KEY="${MCP_API_KEY}" \
    -e PLAN_SIGNING_SECRET="${PLAN_SIGNING_SECRET}" \
    -e SMARTRX_SAFETY_AGENTS_WEBHOOK_SECRET="${SMARTRX_SAFETY_AGENTS_WEBHOOK_SECRET}" \
    -e GEMINI_API_KEY="${GEMINI_API_KEY}" \
    -e GEMINI_MODEL_NAME="${GEMINI_MODEL_NAME:-gemini-3.8-flash-high}" \
    -e SMARTRX_DB_PATH=/app/data/smartrx_ledger.db \
    -e AUDIT_LOG_DIR=/app/audit_logs \
    "${IMAGE_NAME}"
fi

echo "[5/5] Polling ${HEALTH_URL} for HTTP 200..."
for attempt in $(seq 1 20); do
  if curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "SUCCESS: SmartRx production service is healthy at ${HEALTH_URL}."
    exit 0
  fi
  sleep 2
done

echo "ERROR: Health check failed after 20 attempts." >&2
docker logs --tail 30 "${CONTAINER_NAME}" || true
exit 1
