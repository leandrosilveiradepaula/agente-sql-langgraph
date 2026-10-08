#!/usr/bin/env bash
set -euo pipefail

SEMANTIC_MIGRATION_ENV_FILE="${SEMANTIC_MIGRATION_ENV_FILE:-/docker/agente-sql-langgraph/semantic-migration.env}"

if [[ -z "${SEMANTIC_MIGRATION_POSTGRES_DSN:-}" && -r "${SEMANTIC_MIGRATION_ENV_FILE}" ]]; then
  mode="$(stat -c '%a' "${SEMANTIC_MIGRATION_ENV_FILE}" 2>/dev/null || true)"
  if [[ "${mode}" != "600" ]]; then
    echo "ERROR: semantic migration env file must have mode 600."
    exit 2
  fi

  dsn_line="$(grep -m1 '^SEMANTIC_MIGRATION_POSTGRES_DSN=' "${SEMANTIC_MIGRATION_ENV_FILE}" || true)"
  schema_line="$(grep -m1 '^POSTGRES_CONTEXT_SCHEMA=' "${SEMANTIC_MIGRATION_ENV_FILE}" || true)"

  if [[ -n "${dsn_line}" ]]; then
    export SEMANTIC_MIGRATION_POSTGRES_DSN="${dsn_line#SEMANTIC_MIGRATION_POSTGRES_DSN=}"
  fi
  if [[ -z "${POSTGRES_CONTEXT_SCHEMA:-}" && -n "${schema_line}" ]]; then
    export POSTGRES_CONTEXT_SCHEMA="${schema_line#POSTGRES_CONTEXT_SCHEMA=}"
  fi
fi

: "${SEMANTIC_MIGRATION_POSTGRES_DSN:?SEMANTIC_MIGRATION_POSTGRES_DSN must be set in the shell or protected local env file}"
: "${POSTGRES_CONTEXT_SCHEMA:?POSTGRES_CONTEXT_SCHEMA must be set in the shell or protected local env file}"
