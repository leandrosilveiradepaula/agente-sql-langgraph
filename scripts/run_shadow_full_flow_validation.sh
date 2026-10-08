#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CASES_FILE="${1:-${ROOT_DIR}/scripts/validation/demo_finance_generalization_cases.json}"
CONTAINER="${SHADOW_CONTAINER:-agente-sql-langgraph-shadow-test-langgraph-shadow-test-1}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is required."
  exit 2
fi

if [[ ! -r "${CASES_FILE}" ]]; then
  echo "ERROR: validation cases file not readable: ${CASES_FILE}"
  exit 3
fi

if ! docker inspect "${CONTAINER}" >/dev/null 2>&1; then
  echo "ERROR: shadow container not found: ${CONTAINER}"
  exit 4
fi

REAL_SQL_FLAG="$(docker inspect "${CONTAINER}"   --format '{{range .Config.Env}}{{println .}}{{end}}'   | sed -n 's/^LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=//p'   | tail -n 1)"

if [[ "${REAL_SQL_FLAG}" != "false" ]]; then
  echo "ABORTED: LANGGRAPH_ALLOW_REAL_SQL_EXECUTION must be false."
  exit 5
fi

RUNNER="/tmp/run_shadow_full_flow_validation.py"
SMOKE="/tmp/smoke_local_llm_provider.py"
CASES="/tmp/shadow_full_flow_validation_cases.json"

docker cp "${ROOT_DIR}/scripts/smoke_local_llm_provider.py"   "${CONTAINER}:${SMOKE}"

echo "PRECHECK: local OpenAI-compatible provider"
if ! docker exec -w /app -e PYTHONPATH=/app   -e LOCAL_LLM_SMOKE_ENABLED=true   "${CONTAINER}" python "${SMOKE}"; then
  echo "ABORTED: local provider preflight failed; full-flow cases were not executed."
  docker exec "${CONTAINER}" sh -c "rm -f ${SMOKE}" >/dev/null 2>&1 || true
  exit 6
fi


docker cp "${ROOT_DIR}/scripts/run_shadow_full_flow_validation.py"   "${CONTAINER}:${RUNNER}"
docker cp "${CASES_FILE}" "${CONTAINER}:${CASES}"

cleanup() {
  docker exec "${CONTAINER}" sh -c     "rm -f ${RUNNER} ${SMOKE} ${CASES}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker exec -w /app -e PYTHONPATH=/app   "${CONTAINER}" python "${RUNNER}" --cases "${CASES}"
