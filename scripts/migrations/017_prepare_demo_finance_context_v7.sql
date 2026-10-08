-- Evolucao versionada do contexto semantico DEMO.
-- Origem: demo-finance-v6
-- Destino: demo-finance-v7
--
-- Objetivo:
-- - preservar integralmente a v6;
-- - adicionar evidencias auxiliares, derivadas dos aliases versionados,
--   para que o planner receba dimensao, operacao e metrica sem hardcode;
-- - manter score 0 nessas evidencias, sem alterar thresholds ou decisao de intent;
-- - nao usar benchmark, pergunta especifica ou SQL pronta.

BEGIN;
SET LOCAL search_path TO :"context_schema";

WITH versions AS (
  SELECT 'demo-finance-v6'::text AS source_version,
         'demo-finance-v7'::text AS target_version
)
INSERT INTO ai_ducklake_agent_rules (
  agent_version, rule_group, rule_name, rule_content, applies_to_intents,
  validation_hint, severity, priority, is_active
)
SELECT versions.target_version, source.rule_group, source.rule_name,
  source.rule_content, source.applies_to_intents, source.validation_hint,
  source.severity, source.priority, source.is_active
FROM ai_ducklake_agent_rules source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT 'demo-finance-v6'::text AS source_version,
         'demo-finance-v7'::text AS target_version
)
INSERT INTO ai_ducklake_entity_aliases (
  agent_version, entity_type, user_term, canonical_value, target_table,
  target_column, sql_filter_hint, business_rule, priority, is_active
)
SELECT versions.target_version, source.entity_type, source.user_term,
  source.canonical_value, source.target_table, source.target_column,
  source.sql_filter_hint, source.business_rule, source.priority,
  source.is_active
FROM ai_ducklake_entity_aliases source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT 'demo-finance-v6'::text AS source_version,
         'demo-finance-v7'::text AS target_version
)
INSERT INTO ai_ducklake_dre_mapping (
  agent_version, dre_code, nivel_1_bi, business_description, sign_convention,
  category, is_revenue, is_deduction, is_cost, is_opex,
  is_financial_result, sql_filter_hint, sort_order, is_active
)
SELECT versions.target_version, source.dre_code, source.nivel_1_bi,
  source.business_description, source.sign_convention, source.category,
  source.is_revenue, source.is_deduction, source.is_cost, source.is_opex,
  source.is_financial_result, source.sql_filter_hint, source.sort_order,
  source.is_active
FROM ai_ducklake_dre_mapping source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT 'demo-finance-v6'::text AS source_version,
         'demo-finance-v7'::text AS target_version
)
INSERT INTO ai_ducklake_sql_patterns (
  agent_version, intent_name, pattern_name, business_question_examples,
  required_tables, required_rules, sql_pattern, notes, priority, is_active
)
SELECT versions.target_version, source.intent_name, source.pattern_name,
  source.business_question_examples, source.required_tables,
  source.required_rules, source.sql_pattern, source.notes,
  source.priority, source.is_active
FROM ai_ducklake_sql_patterns source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT 'demo-finance-v6'::text AS source_version,
         'demo-finance-v7'::text AS target_version
)
INSERT INTO ai_ducklake_table_catalog (
  agent_version, table_name, schema_name, table_type, description, grain,
  primary_key, key_columns, metric_columns, date_columns, join_rules,
  ai_hint, priority, is_allowed
)
SELECT versions.target_version, source.table_name, source.schema_name,
  source.table_type, source.description, source.grain, source.primary_key,
  source.key_columns, source.metric_columns, source.date_columns,
  source.join_rules, source.ai_hint, source.priority, source.is_allowed
FROM ai_ducklake_table_catalog source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_allowed = TRUE
ON CONFLICT DO NOTHING;

-- Cada alias vira uma regra auxiliar de score zero. Assim:
-- 1) o resolver continua decidindo a intent pelas regras existentes;
-- 2) o planner recebe a evidencia semantica do termo realmente reconhecido;
-- 3) tabela/coluna/operacao continuam vindo do contexto versionado.
WITH projection_aliases AS (
  SELECT
    entity_type,
    user_term,
    CASE entity_type
      WHEN 'dimension' THEN 'dimension_grouping'
      WHEN 'analytical_operation' THEN 'analytical_operation'
      WHEN 'financial_metric' THEN 'financial_metric'
    END AS concept_name,
    'semantic_projection_auxiliary_' ||
      md5(entity_type || '|' || user_term) AS rule_name
  FROM ai_ducklake_entity_aliases
  WHERE agent_version = 'demo-finance-v7'
    AND is_active = TRUE
    AND entity_type IN (
      'dimension',
      'analytical_operation',
      'financial_metric'
    )
    AND NULLIF(trim(user_term), '') IS NOT NULL
),
definitions AS (
  SELECT
    ctid AS row_id,
    business_rule::jsonb AS rule_json
  FROM ai_ducklake_entity_aliases
  WHERE agent_version = 'demo-finance-v7'
    AND is_active = TRUE
    AND entity_type = 'intent_definition'
    AND (business_rule::jsonb) ? 'intent_catalog'
),
auxiliary_rules AS (
  SELECT jsonb_agg(
    jsonb_build_object(
      'rule_name', projection_aliases.rule_name,
      'effect', 'positive_score',
      'concepts', jsonb_build_array(
        jsonb_build_object(
          'concept_name', projection_aliases.concept_name,
          'terms', jsonb_build_array(projection_aliases.user_term),
          'match_mode', 'contains',
          'minimum_term_matches', 1
        )
      ),
      'minimum_concept_matches', 1,
      'score', 0,
      'priority', 999
    )
    ORDER BY projection_aliases.entity_type, projection_aliases.user_term
  ) AS rules
  FROM projection_aliases
),
rewritten AS (
  SELECT
    definitions.row_id,
    jsonb_set(
      definitions.rule_json,
      '{intent_catalog,rules}',
      COALESCE(
        definitions.rule_json -> 'intent_catalog' -> 'rules',
        '[]'::jsonb
      ) || COALESCE(auxiliary_rules.rules, '[]'::jsonb)
    ) AS new_business_rule
  FROM definitions
  CROSS JOIN auxiliary_rules
)
UPDATE ai_ducklake_entity_aliases target
SET business_rule = rewritten.new_business_rule::text
FROM rewritten
WHERE target.ctid = rewritten.row_id;

COMMIT;
