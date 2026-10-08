#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CASES_FILE="${1:-${ROOT_DIR}/scripts/validation/demo_finance_generalization_cases.json}"
SERVICE_NAME="${SHADOW_SERVICE_NAME:-langgraph-shadow-test}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is required."
  exit 2
fi

CONTAINER="${SHADOW_CONTAINER:-}"
if [[ -z "${CONTAINER}" ]]; then
  CONTAINER="$(docker ps     --filter "label=com.docker.compose.service=${SERVICE_NAME}"     --format '{{.Names}}' | head -n 1)"
fi

if [[ -z "${CONTAINER}" ]]; then
  echo "ERROR: shadow container not found."
  exit 3
fi

if [[ ! -r "${CASES_FILE}" ]]; then
  echo "ERROR: validation cases file not readable: ${CASES_FILE}"
  exit 4
fi

RUNNER="/tmp/run_shadow_semantic_validation.py"
CASES="/tmp/shadow_semantic_validation_cases.json"

docker cp "${ROOT_DIR}/scripts/run_shadow_semantic_validation.py"   "${CONTAINER}:${RUNNER}"
docker cp "${CASES_FILE}" "${CONTAINER}:${CASES}"

cleanup() {
  docker exec "${CONTAINER}" sh -c     "rm -f ${RUNNER} ${CASES}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker exec "${CONTAINER}" python "${RUNNER}" --cases "${CASES}"
