#!/usr/bin/env bash
set -euo pipefail
# Only run against ephemeral CI-local PostgreSQL, never client or runtime databases.
if [[ "$V11_DISPOSABLE_POSTGRES_TEST" != "true" || "$PGHOST" != "127.0.0.1" || "$PGPORT" != "5432" || "$PGDATABASE" != "synthetic_ci" || "$LANGGRAPH_ALLOW_REAL_SQL_EXECUTION" != "false" ]]; then
  echo "ABORTED: CI-local disposable PostgreSQL and disabled SQL execution required"
  exit 2
fi
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FIXTURE="$ROOT/scripts/validation/v11_synthetic_postgres_fixture.sql"
MIGRATION="$ROOT/scripts/migrations/021_prepare_demo_finance_context_v11.sql"
psql_safe() { psql -X -q -v ON_ERROR_STOP=1 "$@"; }
count_target() {
 local schema="$1"
 psql -X -A -t -v ON_ERROR_STOP=1 -c "
 SELECT (
 SELECT COUNT(*) FROM \"$schema\".ai_ducklake_agent_rules WHERE agent_version='demo-finance-v11'
 ) + (
 SELECT COUNT(*) FROM \"$schema\".ai_ducklake_entity_aliases WHERE agent_version='demo-finance-v11'
 ) + (
 SELECT COUNT(*) FROM \"$schema\".ai_ducklake_dre_mapping WHERE agent_version='demo-finance-v11'
 ) + (
 SELECT COUNT(*) FROM \"$schema\".ai_ducklake_sql_patterns WHERE agent_version='demo-finance-v11'
 ) + (
 SELECT COUNT(*) FROM \"$schema\".ai_ducklake_table_catalog WHERE agent_version='demo-finance-v11'
 );" | tr -d '[:space:]'
}
assert_count() {
 local actual
 actual="$(count_target "$1")"
 if [[ "$actual" != "$2" ]]; then
   echo "FAIL: $1 target rows $actual expected $2"
   exit 1
 fi
}
init_case() { psql_safe -v context_schema="$1" -f "$FIXTURE" >/dev/null; }
apply_case() { psql_safe -v context_schema="$1" -f "$MIGRATION" >/dev/null; }
expected_failure() {
 if apply_case "$1" >/dev/null 2>&1; then
   echo "FAIL: $1 unexpectedly succeeded"
   exit 1
 fi
 assert_count "$1" 0
 echo "PASS: $1 atomic rollback"
}

init_case test_v11_good
apply_case test_v11_good
assert_count test_v11_good 8
echo "PASS: valid synthetic candidate"
if apply_case test_v11_good >/dev/null 2>&1; then
 echo "FAIL: duplicate candidate accepted"
 exit 1
fi
assert_count test_v11_good 8
echo "PASS: replay rejected without mutation"

# Validate the migration through the actual PostgreSQL context repository and
# versioned parity policy, not only through synthetic row-count SQL assertions.
# The audit uses a separate SELECT-only role with no mutation permissions.
psql_safe -c "CREATE ROLE synthetic_parity_reader LOGIN PASSWORD 'example';"
psql_safe -c "GRANT USAGE ON SCHEMA test_v11_good TO synthetic_parity_reader;"
psql_safe -c "GRANT SELECT ON ALL TABLES IN SCHEMA test_v11_good TO synthetic_parity_reader;"
permissions="$(psql -X -A -t -v ON_ERROR_STOP=1 -c "
 SELECT COUNT(*) = 5 AND COALESCE(bool_and(
    has_table_privilege('synthetic_parity_reader', format('%I.%I', schemaname, tablename), 'SELECT')
    AND NOT has_table_privilege('synthetic_parity_reader', format('%I.%I', schemaname, tablename), 'INSERT')
    AND NOT has_table_privilege('synthetic_parity_reader', format('%I.%I', schemaname, tablename), 'UPDATE')
    AND NOT has_table_privilege('synthetic_parity_reader', format('%I.%I', schemaname, tablename), 'DELETE')
 ), false)
 FROM pg_tables WHERE schemaname = 'test_v11_good';
" | tr -d '[:space:]')"
if [[ "$permissions" != "t" ]]; then
 echo "FAIL: synthetic context reader has unexpected privileges"
 exit 1
fi
run_parity_reader() {
 PGUSER=synthetic_parity_reader PGPASSWORD=example PYTHONPATH="$ROOT" \
   python -m scripts.validation.test_v11_postgres_context_reader_parity --mode "$1"
}
run_parity_reader matching

# Mutate only the disposable v11 metadata while keeping the full record count
# and the temporal config intact, then confirm the reader catches both drifts.
psql_safe -c "UPDATE test_v11_good.ai_ducklake_agent_rules
 SET priority = priority + 1
 WHERE agent_version = 'demo-finance-v11'
 AND rule_group = 'component_config'
 AND rule_name = 'temporal_planning_config';"
run_parity_reader rule_mutation
psql_safe -c "UPDATE test_v11_good.ai_ducklake_entity_aliases
 SET user_term = user_term || '-modified'
 WHERE agent_version = 'demo-finance-v11'
 AND user_term = 'budget-synthetic';"
run_parity_reader entity_mutation
echo "PASS: normalized context parity fails closed on both synthetic drifts"

init_case test_v11_missing_source
psql_safe -c "DELETE FROM test_v11_missing_source.ai_ducklake_agent_rules WHERE agent_version='demo-finance-v10';"
expected_failure test_v11_missing_source

init_case test_v11_missing_binding
psql_safe -c "DELETE FROM test_v11_missing_binding.ai_ducklake_entity_aliases WHERE user_term='budget-synthetic';"
expected_failure test_v11_missing_binding

init_case test_v11_missing_date
psql_safe -c "UPDATE test_v11_missing_date.ai_ducklake_table_catalog SET date_columns='[]'::jsonb WHERE table_name='gold_orcamento';"
expected_failure test_v11_missing_date

# The source and target can have the same number of rows but different
# content. The BEFORE INSERT trigger mutates only copied v11 fixture data.
init_case test_v11_mutated_payload
psql_safe <<'SQL'
CREATE FUNCTION test_v11_mutated_payload.mutate_copied_payload()
RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
 IF NEW.agent_version = 'demo-finance-v11'
    AND NEW.rule_group = 'synthetic' THEN
   NEW.rule_content := '{"tampered":true}';
 END IF;
 RETURN NEW;
END
$body$;
CREATE TRIGGER mutate_copied_payload
BEFORE INSERT ON test_v11_mutated_payload.ai_ducklake_agent_rules
FOR EACH ROW EXECUTE FUNCTION test_v11_mutated_payload.mutate_copied_payload();
SQL
expected_failure test_v11_mutated_payload

# Multiple metric bindings for one concept/source are not an authorized
# choice even when the catalog's temporal column is unique.
init_case test_v11_ambiguous_metric
psql_safe -c "INSERT INTO test_v11_ambiguous_metric.ai_ducklake_entity_aliases (
 agent_version,entity_type,user_term,canonical_value,target_table,target_column,
 sql_filter_hint,business_rule,priority,is_active
) SELECT agent_version,entity_type,'budget-synthetic-duplicate',canonical_value,
 target_table,target_column,sql_filter_hint,business_rule,priority,is_active
 FROM test_v11_ambiguous_metric.ai_ducklake_entity_aliases
 WHERE user_term='budget-synthetic' AND agent_version='demo-finance-v10';"
expected_failure test_v11_ambiguous_metric

init_case test_v11_target_exists
psql_safe -c "INSERT INTO test_v11_target_exists.ai_ducklake_agent_rules SELECT 'demo-finance-v11',rule_group,rule_name,rule_content,applies_to_intents,validation_hint,severity,priority,is_active FROM test_v11_target_exists.ai_ducklake_agent_rules WHERE agent_version='demo-finance-v10';"
if apply_case test_v11_target_exists >/dev/null 2>&1; then
 echo "FAIL: existing target accepted"
 exit 1
fi
assert_count test_v11_target_exists 1
echo "PASS: pre-existing target preserved"
echo "V11_DISPOSABLE_POSTGRES_TEST=PASS"
