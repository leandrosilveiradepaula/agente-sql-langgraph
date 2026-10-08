-- Evolucao versionada do contexto semantico DEMO.
-- Origem: demo-finance-v1
-- Destino: demo-finance-v2
--
-- Objetivos:
-- - preservar integralmente a v1;
-- - ampliar cobertura temporal de forma generica;
-- - tornar operacoes de ranking resolviveis pelo planner;
-- - nao alterar thresholds, benchmark, runtime ativo ou SQL pronta.
--
-- Esta migration apenas prepara uma nova versao de contexto. Ela nao altera
-- SEMANTIC_AGENT_VERSION e nao executa SQL analitica.

BEGIN;

SET LOCAL search_path TO :"context_schema";

WITH versions AS (
  SELECT
    'demo-finance-v1'::text AS source_version,
    'demo-finance-v2'::text AS target_version
)
INSERT INTO ai_ducklake_agent_rules (
  agent_version, rule_group, rule_name, rule_content, applies_to_intents,
  validation_hint, severity, priority, is_active
)
SELECT
  versions.target_version, source.rule_group, source.rule_name,
  source.rule_content, source.applies_to_intents, source.validation_hint,
  source.severity, source.priority, source.is_active
FROM ai_ducklake_agent_rules source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'demo-finance-v1'::text AS source_version,
    'demo-finance-v2'::text AS target_version
)
INSERT INTO ai_ducklake_entity_aliases (
  agent_version, entity_type, user_term, canonical_value, target_table,
  target_column, sql_filter_hint, business_rule, priority, is_active
)
SELECT
  versions.target_version, source.entity_type, source.user_term,
  source.canonical_value, source.target_table, source.target_column,
  source.sql_filter_hint, source.business_rule, source.priority,
  source.is_active
FROM ai_ducklake_entity_aliases source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'demo-finance-v1'::text AS source_version,
    'demo-finance-v2'::text AS target_version
)
INSERT INTO ai_ducklake_dre_mapping (
  agent_version, dre_code, nivel_1_bi, business_description, sign_convention,
  category, is_revenue, is_deduction, is_cost, is_opex,
  is_financial_result, sql_filter_hint, sort_order, is_active
)
SELECT
  versions.target_version, source.dre_code, source.nivel_1_bi,
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
  SELECT
    'demo-finance-v1'::text AS source_version,
    'demo-finance-v2'::text AS target_version
)
INSERT INTO ai_ducklake_sql_patterns (
  agent_version, intent_name, pattern_name, business_question_examples,
  required_tables, required_rules, sql_pattern, notes, priority, is_active
)
SELECT
  versions.target_version, source.intent_name, source.pattern_name,
  source.business_question_examples, source.required_tables,
  source.required_rules, source.sql_pattern, source.notes,
  source.priority, source.is_active
FROM ai_ducklake_sql_patterns source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'demo-finance-v1'::text AS source_version,
    'demo-finance-v2'::text AS target_version
)
INSERT INTO ai_ducklake_table_catalog (
  agent_version, table_name, schema_name, table_type, description, grain,
  primary_key, key_columns, metric_columns, date_columns, join_rules,
  ai_hint, priority, is_allowed
)
SELECT
  versions.target_version, source.table_name, source.schema_name,
  source.table_type, source.description, source.grain, source.primary_key,
  source.key_columns, source.metric_columns, source.date_columns,
  source.join_rules, source.ai_hint, source.priority, source.is_allowed
FROM ai_ducklake_table_catalog source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_allowed = TRUE
ON CONFLICT DO NOTHING;

-- O planner ja conhece ranking e comparison como operacoes estruturais.
-- A v1 possuia aliases apenas para comparison. A v2 torna os termos genericos
-- de ranking resolviveis pelo mesmo contrato de analytical_operation.
INSERT INTO ai_ducklake_entity_aliases (
  agent_version, entity_type, user_term, canonical_value, target_table,
  target_column, sql_filter_hint, business_rule, priority, is_active
)
VALUES
(
  'demo-finance-v2', 'analytical_operation', 'ranking', 'ranking',
  NULL, NULL, NULL,
  '{"operation":{"operation_type":"ranking","direction":"descending","requested_limit":null,"binding_cardinality":{"mode":"single","minimum":1,"maximum":1,"same_metric_concept":true,"distinct_bindings":true}}}'::jsonb,
  70, TRUE
),
(
  'demo-finance-v2', 'analytical_operation', 'maior', 'ranking',
  NULL, NULL, NULL,
  '{"operation":{"operation_type":"ranking","direction":"descending","requested_limit":null,"binding_cardinality":{"mode":"single","minimum":1,"maximum":1,"same_metric_concept":true,"distinct_bindings":true}}}'::jsonb,
  80, TRUE
),
(
  'demo-finance-v2', 'analytical_operation', 'maiores', 'ranking',
  NULL, NULL, NULL,
  '{"operation":{"operation_type":"ranking","direction":"descending","requested_limit":null,"binding_cardinality":{"mode":"single","minimum":1,"maximum":1,"same_metric_concept":true,"distinct_bindings":true}}}'::jsonb,
  90, TRUE
),
(
  'demo-finance-v2', 'analytical_operation', 'top', 'ranking',
  NULL, NULL, NULL,
  '{"operation":{"operation_type":"ranking","direction":"descending","requested_limit":null,"binding_cardinality":{"mode":"single","minimum":1,"maximum":1,"same_metric_concept":true,"distinct_bindings":true}}}'::jsonb,
  100, TRUE
),
(
  'demo-finance-v2', 'analytical_operation', 'principais', 'ranking',
  NULL, NULL, NULL,
  '{"operation":{"operation_type":"ranking","direction":"descending","requested_limit":null,"binding_cardinality":{"mode":"single","minimum":1,"maximum":1,"same_metric_concept":true,"distinct_bindings":true}}}'::jsonb,
  110, TRUE
),
(
  'demo-finance-v2', 'analytical_operation', 'menor', 'ranking',
  NULL, NULL, NULL,
  '{"operation":{"operation_type":"ranking","direction":"ascending","requested_limit":null,"binding_cardinality":{"mode":"single","minimum":1,"maximum":1,"same_metric_concept":true,"distinct_bindings":true}}}'::jsonb,
  120, TRUE
),
(
  'demo-finance-v2', 'analytical_operation', 'menores', 'ranking',
  NULL, NULL, NULL,
  '{"operation":{"operation_type":"ranking","direction":"ascending","requested_limit":null,"binding_cardinality":{"mode":"single","minimum":1,"maximum":1,"same_metric_concept":true,"distinct_bindings":true}}}'::jsonb,
  130, TRUE
)
ON CONFLICT DO NOTHING;

-- Amplia apenas regras de catalogo que ja possuam um conceito isolado
-- period_reference. Nao altera score, prioridade, minimum_score ou margem.
-- A transformacao e estrutural: preserva regras/intents existentes e amplia
-- termos relativos, alem de aceitar anos explicitos por regex.
WITH transformed AS (
  SELECT
    ctid AS row_id,
    jsonb_set(
      business_rule,
      '{intent_catalog,rules}',
      (
        SELECT jsonb_agg(
          CASE
            WHEN jsonb_array_length(COALESCE(rule -> 'concepts', '[]'::jsonb)) = 1
             AND rule -> 'concepts' -> 0 ->> 'concept_name' = 'period_reference'
            THEN jsonb_set(
              rule,
              '{concepts}',
              jsonb_build_array(
                jsonb_set(
                  rule -> 'concepts' -> 0,
                  '{terms}',
                  (
                    SELECT jsonb_agg(to_jsonb(term) ORDER BY term)
                    FROM (
                      SELECT DISTINCT term
                      FROM (
                        SELECT jsonb_array_elements_text(
                          COALESCE(rule -> 'concepts' -> 0 -> 'terms', '[]'::jsonb)
                        ) AS term
                        UNION ALL SELECT 'ultimo mes'
                        UNION ALL SELECT 'ultimo mes fechado'
                        UNION ALL SELECT 'mes passado'
                        UNION ALL SELECT 'mes anterior'
                        UNION ALL SELECT 'ultimo periodo'
                        UNION ALL SELECT 'periodo anterior'
                        UNION ALL SELECT 'ano atual'
                        UNION ALL SELECT 'ano passado'
                        UNION ALL SELECT 'ano anterior'
                        UNION ALL SELECT 'semestre'
                        UNION ALL SELECT 'primeiro semestre'
                        UNION ALL SELECT 'segundo semestre'
                        UNION ALL SELECT 'primeiro trimestre'
                        UNION ALL SELECT 'segundo trimestre'
                        UNION ALL SELECT 'terceiro trimestre'
                        UNION ALL SELECT 'quarto trimestre'
                        UNION ALL SELECT 'janeiro'
                        UNION ALL SELECT 'fevereiro'
                        UNION ALL SELECT 'marco'
                        UNION ALL SELECT 'abril'
                        UNION ALL SELECT 'maio'
                        UNION ALL SELECT 'junho'
                        UNION ALL SELECT 'julho'
                        UNION ALL SELECT 'agosto'
                        UNION ALL SELECT 'setembro'
                        UNION ALL SELECT 'outubro'
                        UNION ALL SELECT 'novembro'
                        UNION ALL SELECT 'dezembro'
                      ) terms
                    ) deduped
                  )
                ),
                jsonb_build_object(
                  'concept_name', 'explicit_period_reference',
                  'terms', jsonb_build_array(E'\\b(?:19|20)\\d{2}\\b'),
                  'match_mode', 'regex',
                  'minimum_term_matches', 1
                )
              )
            )
            ELSE rule
          END
          ORDER BY ordinality
        )
        FROM jsonb_array_elements(
          business_rule -> 'intent_catalog' -> 'rules'
        ) WITH ORDINALITY AS rules(rule, ordinality)
      )
    ) AS new_business_rule
  FROM ai_ducklake_entity_aliases
  WHERE agent_version = 'demo-finance-v2'
    AND entity_type = 'intent_definition'
    AND business_rule ? 'intent_catalog'
    AND EXISTS (
      SELECT 1
      FROM jsonb_array_elements(
        business_rule -> 'intent_catalog' -> 'rules'
      ) AS rules(rule)
      WHERE jsonb_array_length(COALESCE(rule -> 'concepts', '[]'::jsonb)) = 1
        AND rule -> 'concepts' -> 0 ->> 'concept_name' = 'period_reference'
    )
)
UPDATE ai_ducklake_entity_aliases target
SET business_rule = transformed.new_business_rule
FROM transformed
WHERE target.ctid = transformed.row_id;

COMMIT;
