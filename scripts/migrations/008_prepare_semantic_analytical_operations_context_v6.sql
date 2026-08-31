-- Microetapa 5.11-B49
-- Preparacao revisavel do contexto semantico v6 para operacoes analiticas.
--
-- Objetivo:
-- - preservar a versao v5-dedup intacta;
-- - criar uma nova versao derivada integralmente da v5-dedup ativa/permitida;
-- - acrescentar semantica versionada generica para analytical_operation;
-- - manter conhecimento como contexto versionado, sem alteracao em Python, threshold, benchmark, SQL pronta ou golden answer.

BEGIN;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v5-dedup'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v6'::text
      AS target_version
)
INSERT INTO public.ai_ducklake_agent_rules (
  agent_version,
  rule_group,
  rule_name,
  rule_content,
  applies_to_intents,
  validation_hint,
  severity,
  priority,
  is_active
)
SELECT
  versions.target_version,
  source.rule_group,
  source.rule_name,
  source.rule_content,
  source.applies_to_intents,
  source.validation_hint,
  source.severity,
  source.priority,
  source.is_active
FROM public.ai_ducklake_agent_rules source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v5-dedup'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v6'::text
      AS target_version
)
INSERT INTO public.ai_ducklake_entity_aliases (
  agent_version,
  entity_type,
  user_term,
  canonical_value,
  target_table,
  target_column,
  sql_filter_hint,
  business_rule,
  priority,
  is_active
)
SELECT
  versions.target_version,
  source.entity_type,
  source.user_term,
  source.canonical_value,
  source.target_table,
  source.target_column,
  source.sql_filter_hint,
  source.business_rule,
  source.priority,
  source.is_active
FROM public.ai_ducklake_entity_aliases source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v5-dedup'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v6'::text
      AS target_version
)
INSERT INTO public.ai_ducklake_dre_mapping (
  agent_version,
  dre_code,
  nivel_1_bi,
  business_description,
  sign_convention,
  category,
  is_revenue,
  is_deduction,
  is_cost,
  is_opex,
  is_financial_result,
  sql_filter_hint,
  sort_order,
  is_active
)
SELECT
  versions.target_version,
  source.dre_code,
  source.nivel_1_bi,
  source.business_description,
  source.sign_convention,
  source.category,
  source.is_revenue,
  source.is_deduction,
  source.is_cost,
  source.is_opex,
  source.is_financial_result,
  source.sql_filter_hint,
  source.sort_order,
  source.is_active
FROM public.ai_ducklake_dre_mapping source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v5-dedup'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v6'::text
      AS target_version
)
INSERT INTO public.ai_ducklake_sql_patterns (
  agent_version,
  intent_name,
  pattern_name,
  business_question_examples,
  required_tables,
  required_rules,
  sql_pattern,
  notes,
  priority,
  is_active
)
SELECT
  versions.target_version,
  source.intent_name,
  source.pattern_name,
  source.business_question_examples,
  source.required_tables,
  source.required_rules,
  source.sql_pattern,
  source.notes,
  source.priority,
  source.is_active
FROM public.ai_ducklake_sql_patterns source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v5-dedup'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v6'::text
      AS target_version
)
INSERT INTO public.ai_ducklake_table_catalog (
  agent_version,
  table_name,
  schema_name,
  table_type,
  description,
  grain,
  primary_key,
  key_columns,
  metric_columns,
  date_columns,
  join_rules,
  ai_hint,
  priority,
  is_allowed
)
SELECT
  versions.target_version,
  source.table_name,
  source.schema_name,
  source.table_type,
  source.description,
  source.grain,
  source.primary_key,
  source.key_columns,
  source.metric_columns,
  source.date_columns,
  source.join_rules,
  source.ai_hint,
  source.priority,
  source.is_allowed
FROM public.ai_ducklake_table_catalog source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_allowed = TRUE
ON CONFLICT DO NOTHING;

INSERT INTO public.ai_ducklake_entity_aliases (
  agent_version,
  entity_type,
  user_term,
  canonical_value,
  target_table,
  target_column,
  sql_filter_hint,
  business_rule,
  priority,
  is_active
)
VALUES
(
  'v2.0-ducklake-query-generator-semantic-operations-v6',
  'analytical_operation',
  'maiores',
  'ranking',
  NULL,
  NULL,
  NULL,
  '{"operation":{"operation_type":"ranking","direction":"descending","requested_limit":null}}',
  10,
  TRUE
),
(
  'v2.0-ducklake-query-generator-semantic-operations-v6',
  'analytical_operation',
  'concentraram',
  'ranking',
  NULL,
  NULL,
  NULL,
  '{"operation":{"operation_type":"ranking","direction":"descending","requested_limit":null}}',
  20,
  TRUE
),
(
  'v2.0-ducklake-query-generator-semantic-operations-v6',
  'analytical_operation',
  'menores',
  'ranking',
  NULL,
  NULL,
  NULL,
  '{"operation":{"operation_type":"ranking","direction":"ascending","requested_limit":null}}',
  30,
  TRUE
),
(
  'v2.0-ducklake-query-generator-semantic-operations-v6',
  'analytical_operation',
  'menor',
  'ranking',
  NULL,
  NULL,
  NULL,
  '{"operation":{"operation_type":"ranking","direction":"ascending","requested_limit":null}}',
  40,
  TRUE
)
ON CONFLICT DO NOTHING;
-- Rollback manual, se a versao nova precisar ser removida antes de uso:
--
-- BEGIN;
-- DELETE FROM public.ai_ducklake_sql_patterns
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v6';
--
-- DELETE FROM public.ai_ducklake_entity_aliases
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v6';
--
-- DELETE FROM public.ai_ducklake_dre_mapping
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v6';
--
-- DELETE FROM public.ai_ducklake_table_catalog
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v6';
--
-- DELETE FROM public.ai_ducklake_agent_rules
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v6';
-- COMMIT;

COMMIT;



