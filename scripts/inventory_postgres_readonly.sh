#!/usr/bin/env bash
set -euo pipefail

: "${INVENTORY_POSTGRES_DSN:?INVENTORY_POSTGRES_DSN must be set outside Git/chat/logs}"

LABEL="${INVENTORY_LABEL:-database}"

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql is required."
  exit 2
fi

echo "INVENTORY_LABEL=${LABEL}"
echo "MODE=read_only"

psql "${INVENTORY_POSTGRES_DSN}" -X -v ON_ERROR_STOP=1 <<'SQL'
BEGIN READ ONLY;

SELECT
  current_user AS connected_as,
  current_database() AS database_name,
  current_schema() AS current_schema,
  current_setting('search_path') AS search_path,
  current_setting('server_version') AS server_version;

SELECT
  schema_name
FROM information_schema.schemata
WHERE schema_name NOT LIKE 'pg_%'
  AND schema_name <> 'information_schema'
ORDER BY schema_name;

SELECT
  t.table_schema,
  t.table_name,
  COALESCE(s.n_live_tup, 0)::bigint AS estimated_rows,
  pg_total_relation_size(
    format('%I.%I', t.table_schema, t.table_name)::regclass
  ) AS total_bytes
FROM information_schema.tables t
LEFT JOIN pg_stat_user_tables s
  ON s.schemaname = t.table_schema
 AND s.relname = t.table_name
WHERE t.table_type = 'BASE TABLE'
  AND t.table_schema NOT LIKE 'pg_%'
  AND t.table_schema <> 'information_schema'
ORDER BY t.table_schema, t.table_name;

SELECT
  n.nspname AS schema_name,
  COUNT(*) FILTER (WHERE c.relkind = 'r') AS tables,
  COUNT(*) FILTER (WHERE c.relkind = 'v') AS views,
  COUNT(*) FILTER (WHERE c.relkind = 'm') AS materialized_views
FROM pg_namespace n
LEFT JOIN pg_class c
  ON c.relnamespace = n.oid
WHERE n.nspname NOT LIKE 'pg_%'
  AND n.nspname <> 'information_schema'
GROUP BY n.nspname
ORDER BY n.nspname;

SELECT
  extname,
  extversion
FROM pg_extension
ORDER BY extname;

ROLLBACK;
SQL

echo "INVENTORY_COMPLETE=true"
