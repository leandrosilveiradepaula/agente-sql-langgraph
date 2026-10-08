#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_VERSION="${1:-}"
DEPLOY_DIR="${SHADOW_DEPLOY_DIR:-/docker/agente-sql-langgraph}"
SERVICE_NAME="${SHADOW_SERVICE_NAME:-langgraph-shadow-test}"
CONTAINER="${SHADOW_CONTAINER:-agente-sql-langgraph-shadow-test-langgraph-shadow-test-1}"
ENV_FILE="${SHADOW_ENV_FILE:-${DEPLOY_DIR}/shadow-test.env}"
HEALTH_ATTEMPTS="${SHADOW_HEALTH_ATTEMPTS:-30}"
HEALTH_SLEEP_SECONDS="${SHADOW_HEALTH_SLEEP_SECONDS:-2}"

if [[ -z "${TARGET_VERSION}" ]]; then
  echo "USAGE: $0 <semantic-agent-version>"
  exit 2
fi

if [[ ! -d "${DEPLOY_DIR}" ]]; then
  echo "ERROR: shadow deploy directory not found: ${DEPLOY_DIR}"
  exit 3
fi
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: shadow env file not found: ${ENV_FILE}"
  exit 4
fi

CONTEXT_DSN="$(sed -n 's/^CONTEXT_POSTGRES_DSN=//p' "${ENV_FILE}" | tail -n 1)"
CONTEXT_SCHEMA="$(sed -n 's/^POSTGRES_CONTEXT_SCHEMA=//p' "${ENV_FILE}" | tail -n 1)"
if [[ -z "${CONTEXT_DSN}" || -z "${CONTEXT_SCHEMA}" ]]; then
  echo "ABORTED: context reader configuration is incomplete."
  exit 5
fi
if [[ ! "${CONTEXT_SCHEMA}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "ABORTED: POSTGRES_CONTEXT_SCHEMA is invalid."
  exit 5
fi
if ! command -v psql >/dev/null 2>&1; then
  echo "ABORTED: psql is required for semantic version precheck."
  exit 5
fi

TARGET_RECORDS="$(psql "${CONTEXT_DSN}" -X -A -t -v ON_ERROR_STOP=1 -v agent_version="${TARGET_VERSION}" <<SQL
SELECT
  (SELECT COUNT(*) FROM "${CONTEXT_SCHEMA}".ai_ducklake_agent_rules WHERE agent_version = :'agent_version')
+ (SELECT COUNT(*) FROM "${CONTEXT_SCHEMA}".ai_ducklake_entity_aliases WHERE agent_version = :'agent_version')
+ (SELECT COUNT(*) FROM "${CONTEXT_SCHEMA}".ai_ducklake_dre_mapping WHERE agent_version = :'agent_version')
+ (SELECT COUNT(*) FROM "${CONTEXT_SCHEMA}".ai_ducklake_sql_patterns WHERE agent_version = :'agent_version')
+ (SELECT COUNT(*) FROM "${CONTEXT_SCHEMA}".ai_ducklake_table_catalog WHERE agent_version = :'agent_version');
SQL
)"
TARGET_RECORDS="$(printf '%s' "${TARGET_RECORDS}" | tr -d '[:space:]')"
if [[ -z "${TARGET_RECORDS}" || "${TARGET_RECORDS}" == "0" ]]; then
  echo "ABORTED: semantic version ${TARGET_VERSION} has no context records."
  exit 5
fi
echo "PRECHECK: semantic_agent_version=${TARGET_VERSION} records=${TARGET_RECORDS}"

CURRENT_EXECUTION_FLAG="$(sed -n 's/^LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=//p' "${ENV_FILE}" | tail -n 1)"
if [[ "${CURRENT_EXECUTION_FLAG}" != "false" ]]; then
  echo "ABORTED: LANGGRAPH_ALLOW_REAL_SQL_EXECUTION must be false."
  exit 5
fi

BACKUP="${ENV_FILE}.pre-${TARGET_VERSION}-$(date +%Y%m%d-%H%M%S)"
cp -a "${ENV_FILE}" "${BACKUP}"

if grep -q '^SEMANTIC_AGENT_VERSION=' "${ENV_FILE}"; then
  sed -i "s/^SEMANTIC_AGENT_VERSION=.*/SEMANTIC_AGENT_VERSION=${TARGET_VERSION}/" "${ENV_FILE}"
else
  echo "SEMANTIC_AGENT_VERSION=${TARGET_VERSION}" >> "${ENV_FILE}"
fi

echo "PROMOTE: semantic_agent_version=${TARGET_VERSION}"
echo "SAFETY: LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false"

cd "${DEPLOY_DIR}"
docker compose up -d --force-recreate "${SERVICE_NAME}"

healthy="false"
for ((i=1; i<=HEALTH_ATTEMPTS; i++)); do
  status="$(docker inspect "${CONTAINER}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' 2>/dev/null || true)"
  echo "health=${status:-missing}"
  if [[ "${status}" == "healthy" ]]; then
    healthy="true"
    break
  fi
  sleep "${HEALTH_SLEEP_SECONDS}"
done

if [[ "${healthy}" != "true" ]]; then
  echo "ERROR: shadow did not become healthy; restoring previous env file."
  cp -a "${BACKUP}" "${ENV_FILE}"
  cd "${DEPLOY_DIR}"
  docker compose up -d --force-recreate "${SERVICE_NAME}"
  exit 6
fi

ACTIVE_VERSION="$(docker inspect "${CONTAINER}" --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^SEMANTIC_AGENT_VERSION=//p' | tail -n 1)"
ACTIVE_EXECUTION_FLAG="$(docker inspect "${CONTAINER}" --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=//p' | tail -n 1)"

if [[ "${ACTIVE_VERSION}" != "${TARGET_VERSION}" ]]; then
  echo "ERROR: container semantic version mismatch: ${ACTIVE_VERSION}"
  exit 7
fi
if [[ "${ACTIVE_EXECUTION_FLAG}" != "false" ]]; then
  echo "ERROR: container real SQL execution flag is not false."
  exit 8
fi

cd "${ROOT_DIR}"
bash scripts/run_shadow_semantic_validation.sh

echo "DONE: shadow=${TARGET_VERSION} validated with real_sql_execution=false"
