-- Candidate-only context evolution: demo-finance-v10 -> demo-finance-v11.
-- Adds generic temporal planning metadata without changing v9/v10 or runtime.
-- No benchmark expectation, SQL template or threshold introduced.
-- Requires the structural temporal planner contract before activation.

BEGIN;
SET LOCAL search_path TO :"context_schema";

DO $
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ai_ducklake_agent_rules
    WHERE agent_version = 'demo-finance-v10' AND is_active = TRUE
  ) THEN
    RAISE EXCEPTION 'demo-finance-v10 source context is missing';
  END IF;
  IF EXISTS (
    SELECT 1 FROM ai_ducklake_agent_rules WHERE agent_version = 'demo-finance-v11'
  ) OR EXISTS (
    SELECT 1 FROM ai_ducklake_entity_aliases WHERE agent_version = 'demo-finance-v11'
  ) OR EXISTS (
    SELECT 1 FROM ai_ducklake_sql_patterns WHERE agent_version = 'demo-finance-v11'
  ) OR EXISTS (
    SELECT 1 FROM ai_ducklake_table_catalog WHERE agent_version = 'demo-finance-v11'
  ) OR EXISTS (
    SELECT 1 FROM ai_ducklake_dre_mapping WHERE agent_version = 'demo-finance-v11'
  ) THEN
    RAISE EXCEPTION 'demo-finance-v11 already exists; immutable context not modified';
  END IF;
END $;

WITH versions AS (
  SELECT 'demo-finance-v10'::text AS source_version,
         'demo-finance-v11'::text AS target_version
)
INSERT INTO ai_ducklake_agent_rules (
  agent_version, rule_group, rule_name, rule_content, applies_to_intents,
  validation_hint, severity, priority, is_active
)
SELECT versions.target_version, source.rule_group, source.rule_name,
  source.rule_content, source.applies_to_intents, source.validation_hint,
  source.severity, source.priority, source.is_active
FROM ai_ducklake_agent_rules source CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT 'demo-finance-v10'::text AS source_version,
         'demo-finance-v11'::text AS target_version
)
INSERT INTO ai_ducklake_entity_aliases (
  agent_version, entity_type, user_term, canonical_value, target_table,
  target_column, sql_filter_hint, business_rule, priority, is_active
)
SELECT versions.target_version, source.entity_type, source.user_term,
  source.canonical_value, source.target_table, source.target_column,
  source.sql_filter_hint, source.business_rule, source.priority,
  source.is_active
FROM ai_ducklake_entity_aliases source CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT 'demo-finance-v10'::text AS source_version,
         'demo-finance-v11'::text AS target_version
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
FROM ai_ducklake_dre_mapping source CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT 'demo-finance-v10'::text AS source_version,
         'demo-finance-v11'::text AS target_version
)
INSERT INTO ai_ducklake_sql_patterns (
  agent_version, intent_name, pattern_name, business_question_examples,
  required_tables, required_rules, sql_pattern, notes, priority, is_active
)
SELECT versions.target_version, source.intent_name, source.pattern_name,
  source.business_question_examples, source.required_tables,
  source.required_rules, source.sql_pattern, source.notes,
  source.priority, source.is_active
FROM ai_ducklake_sql_patterns source CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT 'demo-finance-v10'::text AS source_version,
         'demo-finance-v11'::text AS target_version
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
FROM ai_ducklake_table_catalog source CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_allowed = TRUE
ON CONFLICT DO NOTHING;


-- The temporal planner contract is structural; intent name and vocabulary are
-- versioned domain context, not Python business conditions. A date field is
-- acceptable only when the selected metric source has one catalog date column.
-- Never substitute an arbitrary field when metadata is missing or ambiguous.
INSERT INTO ai_ducklake_agent_rules (
  agent_version, rule_group, rule_name, rule_content, applies_to_intents,
  validation_hint, severity, priority, is_active
)
VALUES (
  'demo-finance-v11',
  'component_config',
  'temporal_planning_config',
  jsonb_build_object(
    'component', 'temporal_planning',
    'required_intents', jsonb_build_array('trend'),
    'date_binding_strategy', 'unique_metric_source_catalog_date',
    'granularities', jsonb_build_array(
      jsonb_build_object(
        'grain', 'month',
        'terms', jsonb_build_array(
          'mensal', 'mensalmente', 'por mês', 'mês a mês', 'a cada mês'
        )
      ),
      jsonb_build_object(
        'grain', 'quarter',
        'terms', jsonb_build_array(
          'trimestral', 'trimestralmente', 'por trimestre',
          'trimestre a trimestre', 'trimestres'
        )
      ),
      jsonb_build_object(
        'grain', 'year',
        'terms', jsonb_build_array(
          'anualmente', 'por ano', 'ano a ano'
        )
      )
    )
  )::text,
  ARRAY['trend']::text[],
  NULL,
  'error',
  20,
  TRUE
);

COMMIT;
