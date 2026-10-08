-- Evolucao versionada do contexto semantico DEMO.
-- Origem: demo-finance-v8
-- Destino: demo-finance-v9
--
-- Corrige a regressao da v8 sem alterar thresholds:
-- - operacoes especializadas (ranking/trend) voltam a suprimir o default
--   de cenario realizado durante classificacao;
-- - metric bindings passam a usar os required_rules do pattern como contexto
--   de fonte, preservando o conhecimento no contexto versionado;
-- - mantem metadata de comparison normalizada da v8.

BEGIN;
SET LOCAL search_path TO :"context_schema";

WITH versions AS (
  SELECT 'demo-finance-v8'::text AS source_version,
         'demo-finance-v9'::text AS target_version
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
  SELECT 'demo-finance-v8'::text AS source_version,
         'demo-finance-v9'::text AS target_version
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
  SELECT 'demo-finance-v8'::text AS source_version,
         'demo-finance-v9'::text AS target_version
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
  SELECT 'demo-finance-v8'::text AS source_version,
         'demo-finance-v9'::text AS target_version
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
  SELECT 'demo-finance-v8'::text AS source_version,
         'demo-finance-v9'::text AS target_version
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

-- Restaura a regra de classificacao comprovada na v7:
-- operacao analitica ou trend explicitos impedem que o default realizado
-- concorra com intents especializadas.
WITH transformed AS (
  SELECT ctid AS row_id,
    jsonb_set(
      rule_content::jsonb,
      '{rules}',
      (
        SELECT jsonb_agg(
          CASE
            WHEN rule ->> 'rule_name' =
              'default_realized_scenario_for_financial_metric'
            THEN jsonb_set(
              rule,
              '{when_absent}',
              (
                SELECT jsonb_agg(to_jsonb(term) ORDER BY term)
                FROM (
                  SELECT DISTINCT term
                  FROM (
                    SELECT jsonb_array_elements_text(
                      COALESCE(rule -> 'when_absent', '[]'::jsonb)
                    ) AS term
                    UNION ALL SELECT 'analytical_operation'
                    UNION ALL SELECT 'trend'
                  ) expanded
                ) deduped
              )
            )
            ELSE rule
          END
          ORDER BY ordinality
        )
        FROM jsonb_array_elements(
          (rule_content::jsonb) -> 'rules'
        ) WITH ORDINALITY AS rules(rule, ordinality)
      )
    ) AS new_rule_content
  FROM ai_ducklake_agent_rules
  WHERE agent_version = 'demo-finance-v9'
    AND rule_group = 'component_config'
    AND rule_name = 'semantic_defaults_config'
    AND (rule_content::jsonb) ->> 'component' = 'semantic_defaults'
)
UPDATE ai_ducklake_agent_rules target
SET rule_content = transformed.new_rule_content::text
FROM transformed
WHERE target.ctid = transformed.row_id;

-- Metric bindings deixam de depender do default de classificacao.
-- As condicoes passam a referenciar required_rules versionadas do pattern.
WITH target AS (
  SELECT ctid AS row_id, business_rule::jsonb AS rule_json
  FROM ai_ducklake_entity_aliases
  WHERE agent_version = 'demo-finance-v9'
    AND entity_type = 'metric_binding'
    AND (business_rule::jsonb) ? 'metric_binding'
),
rewritten AS (
  SELECT row_id,
    jsonb_set(
      jsonb_set(
        rule_json,
        '{metric_binding,when_present}',
        COALESCE(
          (
            SELECT jsonb_agg(
              to_jsonb(
                CASE value
                  WHEN 'realized_scenario' THEN 'realized_source'
                  WHEN 'budget_scenario' THEN 'budget_source'
                  ELSE value
                END
              )
              ORDER BY ordinality
            )
            FROM jsonb_array_elements_text(
              COALESCE(rule_json -> 'metric_binding' -> 'when_present', '[]'::jsonb)
            ) WITH ORDINALITY AS values(value, ordinality)
          ),
          '[]'::jsonb
        )
      ),
      '{metric_binding,when_absent}',
      COALESCE(
        (
          SELECT jsonb_agg(
            to_jsonb(
              CASE value
                WHEN 'realized_scenario' THEN 'realized_source'
                WHEN 'budget_scenario' THEN 'budget_source'
                ELSE value
              END
            )
            ORDER BY ordinality
          )
          FROM jsonb_array_elements_text(
            COALESCE(rule_json -> 'metric_binding' -> 'when_absent', '[]'::jsonb)
          ) WITH ORDINALITY AS values(value, ordinality)
        ),
        '[]'::jsonb
      )
    ) AS new_business_rule
  FROM target
)
UPDATE ai_ducklake_entity_aliases target
SET business_rule = rewritten.new_business_rule::text
FROM rewritten
WHERE target.ctid = rewritten.row_id;

COMMIT;
