#!/usr/bin/env bash
set -euo pipefail

# Read-only, one-off candidate validation. Does not change the active
# SEMANTIC_AGENT_VERSION, provider, n8n flow or running Shadow service.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:?Usage: $0 SEMANTIC_AGENT_VERSION [cases.json]}"
CASES_FILE="${2:-${ROOT_DIR}/scripts/validation/demo_finance_generalization_cases.json}"
CONTAINER="${SHADOW_CONTAINER:-agente-sql-langgraph-shadow-test-langgraph-shadow-test-1}"

if [[ ! -r "${CASES_FILE}" ]]; then
  echo "ERROR: evaluation cases file cannot be read."
  exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is required."
  exit 3
fi
if ! docker inspect "${CONTAINER}" >/dev/null 2>&1; then
  echo "ERROR: Shadow container is unavailable."
  exit 4
fi
REAL_SQL_FLAG="$(
  docker inspect "${CONTAINER}" \
    --format '{{range .Config.Env}}{{println .}}{{end}}' \
    | sed -n 's/^LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=//p' \
    | tail -n 1
)"
if [[ "${REAL_SQL_FLAG}" != "false" ]]; then
  echo "ABORTED: LANGGRAPH_ALLOW_REAL_SQL_EXECUTION must be false."
  exit 5
fi

RUNNER="/tmp/shadow_context_candidate_readonly_$$.py"
CASES="/tmp/shadow_context_candidate_cases_$$.json"
cleanup() {
  docker exec "${CONTAINER}" sh -c \
    "rm -f '${RUNNER}' '${CASES}'" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker cp "${ROOT_DIR}/scripts/run_shadow_context_candidate_readonly.py" \
  "${CONTAINER}:${RUNNER}"
docker cp "${CASES_FILE}" "${CONTAINER}:${CASES}"

docker exec -w /app -e PYTHONPATH=/app "${CONTAINER}" \
  python "${RUNNER}" --version "${VERSION}" --cases "${CASES}"
