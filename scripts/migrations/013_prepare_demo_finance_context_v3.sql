-- Evolucao versionada do contexto semantico DEMO.
-- Origem: demo-finance-v2
-- Destino: demo-finance-v3
--
-- Objetivos:
-- - preservar integralmente a v2;
-- - ampliar variacoes linguisticas de operacoes de comparacao no contexto;
-- - evitar que o default de cenario realizado concorra com uma operacao
--   analitica explicita;
-- - nao alterar thresholds, benchmark, runtime ativo ou SQL pronta.
--
-- Esta migration prepara uma nova versao. Ela nao altera
-- SEMANTIC_AGENT_VERSION e nao executa SQL analitica.

BEGIN;

SET LOCAL search_path TO :"context_schema";

WITH versions AS (
  SELECT
    'demo-finance-v2'::text AS source_version,
    'demo-finance-v3'::text AS target_version
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
    'demo-finance-v2'::text AS source_version,
    'demo-finance-v3'::text AS target_version
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
    'demo-finance-v2'::text AS source_version,
    'demo-finance-v3'::text AS target_version
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
    'demo-finance-v2'::text AS source_version,
    'demo-finance-v3'::text AS target_version
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
    'demo-finance-v2'::text AS source_version,
    'demo-finance-v3'::text AS target_version
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

-- Mantem o vocabulario operacional versionado e auditavel.
INSERT INTO ai_ducklake_entity_aliases (
  agent_version, entity_type, user_term, canonical_value, target_table,
  target_column, sql_filter_hint, business_rule, priority, is_active
)
VALUES
  ('demo-finance-v3', 'analytical_operation', 'compare', 'comparison',
   NULL, NULL, NULL,
   '{"operation":{"operation_type":"comparison","binding_cardinality":{"mode":"multiple","minimum":2,"maximum":2,"same_metric_concept":true,"distinct_bindings":true},"presentation":"side_by_side","combination":"aggregate_then_combine","preserve_all_categories":true}}'::jsonb,
   65, TRUE),
  ('demo-finance-v3', 'analytical_operation', 'comparando', 'comparison',
   NULL, NULL, NULL,
   '{"operation":{"operation_type":"comparison","binding_cardinality":{"mode":"multiple","minimum":2,"maximum":2,"same_metric_concept":true,"distinct_bindings":true},"presentation":"side_by_side","combination":"aggregate_then_combine","preserve_all_categories":true}}'::jsonb,
   66, TRUE),
  ('demo-finance-v3', 'analytical_operation', 'comparado', 'comparison',
   NULL, NULL, NULL,
   '{"operation":{"operation_type":"comparison","binding_cardinality":{"mode":"multiple","minimum":2,"maximum":2,"same_metric_concept":true,"distinct_bindings":true},"presentation":"side_by_side","combination":"aggregate_then_combine","preserve_all_categories":true}}'::jsonb,
   67, TRUE),
  ('demo-finance-v3', 'analytical_operation', 'comparada', 'comparison',
   NULL, NULL, NULL,
   '{"operation":{"operation_type":"comparison","binding_cardinality":{"mode":"multiple","minimum":2,"maximum":2,"same_metric_concept":true,"distinct_bindings":true},"presentation":"side_by_side","combination":"aggregate_then_combine","preserve_all_categories":true}}'::jsonb,
   68, TRUE)
ON CONFLICT DO NOTHING;

-- Amplia, no catalogo de intents, apenas conceitos de operacao que ja
-- representam comparacao. Nao cria uma nova intent nem usa pergunta de benchmark.
WITH transformed AS (
  SELECT
    ctid AS row_id,
    jsonb_set(
      business_rule::jsonb,
      '{intent_catalog,rules}',
      (
        SELECT jsonb_agg(
          jsonb_set(
            rule,
            '{concepts}',
            (
              SELECT jsonb_agg(
                CASE
                  WHEN concept ->> 'concept_name' = 'analytical_operation'
                   AND EXISTS (
                     SELECT 1
                     FROM jsonb_array_elements_text(
                       COALESCE(concept -> 'terms', '[]'::jsonb)
                     ) existing(term)
                     WHERE lower(existing.term) IN (
                       'comparar', 'comparacao', 'comparação',
                       'comparativo', 'versus', 'vs'
                     )
                   )
                  THEN jsonb_set(
                    concept,
                    '{terms}',
                    (
                      SELECT jsonb_agg(to_jsonb(term) ORDER BY term)
                      FROM (
                        SELECT DISTINCT term
                        FROM (
                          SELECT jsonb_array_elements_text(
                            COALESCE(concept -> 'terms', '[]'::jsonb)
                          ) AS term
                          UNION ALL SELECT 'compare'
                          UNION ALL SELECT 'comparando'
                          UNION ALL SELECT 'comparado'
                          UNION ALL SELECT 'comparada'
                        ) expanded
                      ) deduped
                    )
                  )
                  ELSE concept
                END
                ORDER BY concept_ordinality
              )
              FROM jsonb_array_elements(
                COALESCE(rule -> 'concepts', '[]'::jsonb)
              ) WITH ORDINALITY AS concepts(concept, concept_ordinality)
            )
          )
          ORDER BY rule_ordinality
        )
        FROM jsonb_array_elements(
          (business_rule::jsonb) -> 'intent_catalog' -> 'rules'
        ) WITH ORDINALITY AS rules(rule, rule_ordinality)
      )
    ) AS new_business_rule
  FROM ai_ducklake_entity_aliases
  WHERE agent_version = 'demo-finance-v3'
    AND entity_type = 'intent_definition'
    AND (business_rule::jsonb) ? 'intent_catalog'
)
UPDATE ai_ducklake_entity_aliases target
SET business_rule = transformed.new_business_rule::text
FROM transformed
WHERE target.ctid = transformed.row_id;

-- O default de cenario realizado permanece valido para perguntas financeiras
-- sem cenario explicito, mas nao deve competir com uma operacao analitica
-- explicitamente reconhecida.
WITH transformed AS (
  SELECT
    ctid AS row_id,
    jsonb_set(
      business_rule::jsonb,
      '{semantic_defaults,rules}',
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
                  ) expanded
                ) deduped
              )
            )
            ELSE rule
          END
          ORDER BY ordinality
        )
        FROM jsonb_array_elements(
          (business_rule::jsonb) -> 'semantic_defaults' -> 'rules'
        ) WITH ORDINALITY AS rules(rule, ordinality)
      )
    ) AS new_business_rule
  FROM ai_ducklake_entity_aliases
  WHERE agent_version = 'demo-finance-v3'
    AND entity_type = 'component_config'
    AND (business_rule::jsonb) ? 'semantic_defaults'
)
UPDATE ai_ducklake_entity_aliases target
SET business_rule = transformed.new_business_rule::text
FROM transformed
WHERE target.ctid = transformed.row_id;

COMMIT;
