#!/usr/bin/env bash
set -euo pipefail

: "${POSTGRES_DSN:?POSTGRES_DSN must be set outside Git/chat/logs}"

SOURCE_VERSION="v2.0-ducklake-query-generator-semantic-operations-v7"
V9_VERSION="v2.0-ducklake-query-generator-semantic-operations-v9-period-coverage"
V10_VERSION="v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents"
CONFIRM_VALUE="APLICAR_CONTEXT_V10"

if [[ "${CONFIRM_APPLY:-}" != "${CONFIRM_VALUE}" ]]; then
  echo "ABORTED: set CONFIRM_APPLY=${CONFIRM_VALUE} to continue."
  exit 2
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql is required."
  exit 3
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
V9_SQL="${ROOT_DIR}/scripts/migrations/010_prepare_semantic_period_coverage_context_v9.sql"
V10_SQL="${ROOT_DIR}/scripts/migrations/011_prepare_semantic_curated_intents_context_v10.sql"

for file in "${V9_SQL}" "${V10_SQL}"; do
  if [[ ! -r "${file}" ]]; then
    echo "ERROR: migration file not readable: ${file}"
    exit 4
  fi
done

count_version() {
  local version="$1"
  psql "${POSTGRES_DSN}" -X -A -t -v ON_ERROR_STOP=1     -v agent_version="${version}" <<'SQL'
SELECT
  (SELECT COUNT(*) FROM public.ai_ducklake_agent_rules WHERE agent_version = :'agent_version')
+ (SELECT COUNT(*) FROM public.ai_ducklake_entity_aliases WHERE agent_version = :'agent_version')
+ (SELECT COUNT(*) FROM public.ai_ducklake_dre_mapping WHERE agent_version = :'agent_version')
+ (SELECT COUNT(*) FROM public.ai_ducklake_sql_patterns WHERE agent_version = :'agent_version')
+ (SELECT COUNT(*) FROM public.ai_ducklake_table_catalog WHERE agent_version = :'agent_version');
SQL
}

source_count="$(count_version "${SOURCE_VERSION}" | tr -d '[:space:]')"
v9_count="$(count_version "${V9_VERSION}" | tr -d '[:space:]')"
v10_count="$(count_version "${V10_VERSION}" | tr -d '[:space:]')"

if [[ -z "${source_count}" || "${source_count}" == "0" ]]; then
  echo "ERROR: source semantic version is missing."
  exit 5
fi

echo "PRECHECK: source_records=${source_count} v9_records=${v9_count} v10_records=${v10_count}"

if [[ "${v10_count}" != "0" ]]; then
  echo "ABORTED: v10 already contains records. No write performed."
  exit 6
fi

if [[ "${v9_count}" == "0" ]]; then
  echo "APPLY: v9 period coverage"
  psql "${POSTGRES_DSN}" -X -v ON_ERROR_STOP=1 -f "${V9_SQL}"
else
  echo "SKIP: v9 already exists; preserving existing version."
fi

v9_after="$(count_version "${V9_VERSION}" | tr -d '[:space:]')"
if [[ -z "${v9_after}" || "${v9_after}" == "0" ]]; then
  echo "ERROR: v9 verification failed."
  exit 7
fi

echo "APPLY: v10 curated intents"
psql "${POSTGRES_DSN}" -X -v ON_ERROR_STOP=1 -f "${V10_SQL}"

v10_after="$(count_version "${V10_VERSION}" | tr -d '[:space:]')"
if [[ -z "${v10_after}" || "${v10_after}" == "0" ]]; then
  echo "ERROR: v10 verification failed."
  exit 8
fi

echo "VERIFIED: v9_records=${v9_after} v10_records=${v10_after}"
echo "NEXT: run read-only live validator against v10 before changing SEMANTIC_AGENT_VERSION."
