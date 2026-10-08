#!/usr/bin/env bash
set -euo pipefail

: "${SEMANTIC_MIGRATION_POSTGRES_DSN:?SEMANTIC_MIGRATION_POSTGRES_DSN must be set outside Git/chat/logs}"
: "${POSTGRES_CONTEXT_SCHEMA:?POSTGRES_CONTEXT_SCHEMA must be set outside Git/chat/logs}"

SOURCE_VERSION="demo-finance-v7"
TARGET_VERSION="demo-finance-v8"
CONFIRM_VALUE="APLICAR_DEMO_FINANCE_V8"

if [[ ! "${POSTGRES_CONTEXT_SCHEMA}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "ERROR: POSTGRES_CONTEXT_SCHEMA must be a simple PostgreSQL identifier."
  exit 2
fi
if [[ "${CONFIRM_APPLY:-}" != "${CONFIRM_VALUE}" ]]; then
  echo "ABORTED: set CONFIRM_APPLY=${CONFIRM_VALUE} to continue."
  exit 2
fi
if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql is required."
  exit 3
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATION="${ROOT_DIR}/scripts/migrations/018_prepare_demo_finance_context_v8.sql"

count_version() {
  local version="$1"
  psql "${SEMANTIC_MIGRATION_POSTGRES_DSN}" -X -A -t -v ON_ERROR_STOP=1 -v agent_version="${version}" <<SQL
SELECT
  (SELECT COUNT(*) FROM "${POSTGRES_CONTEXT_SCHEMA}".ai_ducklake_agent_rules WHERE agent_version = :'agent_version')
+ (SELECT COUNT(*) FROM "${POSTGRES_CONTEXT_SCHEMA}".ai_ducklake_entity_aliases WHERE agent_version = :'agent_version')
+ (SELECT COUNT(*) FROM "${POSTGRES_CONTEXT_SCHEMA}".ai_ducklake_dre_mapping WHERE agent_version = :'agent_version')
+ (SELECT COUNT(*) FROM "${POSTGRES_CONTEXT_SCHEMA}".ai_ducklake_sql_patterns WHERE agent_version = :'agent_version')
+ (SELECT COUNT(*) FROM "${POSTGRES_CONTEXT_SCHEMA}".ai_ducklake_table_catalog WHERE agent_version = :'agent_version');
SQL
}

source_count="$(count_version "${SOURCE_VERSION}" | tr -d '[:space:]')"
target_count="$(count_version "${TARGET_VERSION}" | tr -d '[:space:]')"
if [[ -z "${source_count}" || "${source_count}" == "0" ]]; then
  echo "ERROR: source semantic version is missing."
  exit 5
fi
echo "PRECHECK: source_records=${source_count} target_records=${target_count}"
if [[ "${target_count}" != "0" ]]; then
  echo "ABORTED: target version already contains records. No write performed."
  exit 6
fi
echo "APPLY: demo-finance-v8"
psql "${SEMANTIC_MIGRATION_POSTGRES_DSN}" -X -v ON_ERROR_STOP=1 -v context_schema="${POSTGRES_CONTEXT_SCHEMA}" -f "${MIGRATION}"
target_after="$(count_version "${TARGET_VERSION}" | tr -d '[:space:]')"
echo "VERIFIED: source_records=${source_count} target_records=${target_after}"
echo "NEXT: validate demo-finance-v8 read-only before changing SEMANTIC_AGENT_VERSION."
