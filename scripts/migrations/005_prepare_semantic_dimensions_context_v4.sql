-- Microetapa 5.11-B22
-- Preparacao revisavel do contexto semantico de dimensoes explicitas v4.
--
-- Objetivo:
-- - preservar a versao v3 intacta;
-- - criar uma nova versao derivada somente de registros ativos/permitidos;
-- - adicionar metadata explicita de dimensoes para o planner;
-- - evitar inferencia de coluna por nome de tabela, PK ou key_columns.

BEGIN;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v3'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v4'::text
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
    'v2.0-ducklake-query-generator-semantic-operations-v3'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v4'::text
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
  'v2.0-ducklake-query-generator-semantic-operations-v4',
  'dimension',
  'unidade',
  'unidade',
  'main_gold.gold_unidade_negocio',
  'nk_unide_neg',
  NULL,
  '{
    "source": "versioned_semantic_context",
    "dimension_mapping": {
      "evidence": [
        "gold_unidade_negocio.nk_unide_neg e chave de negocio confirmada no table_catalog v3",
        "gold_unidade_negocio.sk e chave tecnica, nao dimensao de negocio"
      ],
      "planner_contract": "usar somente como metadata explicita de agrupamento; nao inferir por nome de tabela ou PK"
    }
  }',
  5,
  TRUE
),
(
  'v2.0-ducklake-query-generator-semantic-operations-v4',
  'dimension',
  'marca',
  'marca',
  'main_gold.gold_unidade_negocio',
  'marca',
  NULL,
  '{
    "source": "versioned_semantic_context",
    "dimension_mapping": {
      "evidence": [
        "gold_unidade_negocio.marca consta como coluna catalogada"
      ],
      "planner_contract": "usar somente como metadata explicita de agrupamento"
    }
  }',
  5,
  TRUE
)
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v3'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v4'::text
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
    'v2.0-ducklake-query-generator-semantic-operations-v3'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v4'::text
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
    'v2.0-ducklake-query-generator-semantic-operations-v3'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v4'::text
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

-- Rollback manual, se a versao nova precisar ser removida antes de uso:
--
-- BEGIN;
-- DELETE FROM public.ai_ducklake_sql_patterns
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v4';
--
-- DELETE FROM public.ai_ducklake_entity_aliases
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v4';
--
-- DELETE FROM public.ai_ducklake_dre_mapping
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v4';
--
-- DELETE FROM public.ai_ducklake_table_catalog
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v4';
--
-- DELETE FROM public.ai_ducklake_agent_rules
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v4';
-- COMMIT;

COMMIT;
