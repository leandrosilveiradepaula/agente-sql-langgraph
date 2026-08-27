-- Microetapa 5.11-B4
-- Preparacao revisavel do contexto semantico de operacoes analiticas
-- genericas.
--
-- Objetivo:
-- - preservar a versao atual intacta;
-- - criar uma nova versao de contexto;
-- - copiar a base semantica ativa da versao anterior;
-- - adicionar somente conhecimento configurado para resolver metricas
--   financeiras agregadas por periodo e dimensoes opcionais autorizadas.

BEGIN;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-offline-poc-test-responsavel-cc-intent-catalog-v1'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v1'::text
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
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-offline-poc-test-responsavel-cc-intent-catalog-v1'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v1'::text
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
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-offline-poc-test-responsavel-cc-intent-catalog-v1'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v1'::text
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
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-offline-poc-test-responsavel-cc-intent-catalog-v1'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v1'::text
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
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-offline-poc-test-responsavel-cc-intent-catalog-v1'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v1'::text
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
ON CONFLICT DO NOTHING;

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
VALUES (
  'v2.0-ducklake-query-generator-semantic-operations-v1',
  'semantic_operations',
  'metric_total_by_period_contract',
  '{
    "source": "versioned_semantic_context",
    "requires": [
      "financial_metric",
      "period_reference",
      "analytical_operation_or_dimension"
    ],
    "forbids": [
      "question_specific_lookup",
      "benchmark_lookup"
    ]
  }'::jsonb,
  ARRAY['metric_total_by_period']::text[],
  NULL,
  'error',
  120,
  TRUE
)
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
VALUES (
  'v2.0-ducklake-query-generator-semantic-operations-v1',
  'intent_definition',
  'metric_total_by_period_definition',
  'metric_total_by_period',
  NULL,
  NULL,
  NULL,
  '{
    "intent_catalog": {
      "semantic_description": "Resolve perguntas analiticas genericas que pedem agregacao de metrica financeira por periodo e dimensoes opcionais autorizadas.",
      "rules": [
        {
          "rule_name": "metric_period_operation_or_dimension_required",
          "effect": "require",
          "minimum_concept_matches": 3,
          "priority": 1,
          "concepts": [
            {
              "concept_name": "financial_metric",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "receita",
                "receitas",
                "faturamento",
                "rol",
                "opex",
                "despesa operacional",
                "despesas operacionais",
                "custo",
                "custos"
              ]
            },
            {
              "concept_name": "analytical_operation",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "total",
                "quanto",
                "qual foi",
                "quais foram",
                "valor agregado",
                "consolidado",
                "soma"
              ]
            },
            {
              "concept_name": "dimension_grouping",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "por marca",
                "por centro de custo",
                "por unidade",
                "por conta"
              ]
            },
            {
              "concept_name": "period_reference",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "ultimo mes",
                "ultimo periodo",
                "mes passado",
                "periodo anterior",
                "periodo passado",
                "no mes"
              ]
            }
          ]
        },
        {
          "rule_name": "metric_operation_period_score",
          "effect": "positive_score",
          "minimum_concept_matches": 3,
          "score": 140,
          "priority": 2,
          "concepts": [
            {
              "concept_name": "financial_metric",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "receita",
                "receitas",
                "faturamento",
                "rol",
                "opex",
                "despesa operacional",
                "despesas operacionais",
                "custo",
                "custos"
              ]
            },
            {
              "concept_name": "analytical_operation",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "total",
                "quanto",
                "qual foi",
                "quais foram",
                "valor agregado",
                "consolidado",
                "soma"
              ]
            },
            {
              "concept_name": "period_reference",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "ultimo mes",
                "ultimo periodo",
                "mes passado",
                "periodo anterior",
                "periodo passado",
                "no mes"
              ]
            }
          ]
        },
        {
          "rule_name": "metric_dimension_period_score",
          "effect": "positive_score",
          "minimum_concept_matches": 3,
          "score": 130,
          "priority": 3,
          "concepts": [
            {
              "concept_name": "financial_metric",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "receita",
                "receitas",
                "faturamento",
                "rol",
                "opex",
                "despesa operacional",
                "despesas operacionais",
                "custo",
                "custos"
              ]
            },
            {
              "concept_name": "dimension_grouping",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "por marca",
                "por centro de custo",
                "por unidade",
                "por conta"
              ]
            },
            {
              "concept_name": "period_reference",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "ultimo mes",
                "ultimo periodo",
                "mes passado",
                "periodo anterior",
                "periodo passado",
                "no mes"
              ]
            }
          ]
        },
        {
          "rule_name": "responsibility_lookup_exclusion",
          "effect": "exclude",
          "minimum_concept_matches": 1,
          "priority": 4,
          "concepts": [
            {
              "concept_name": "responsibility_lookup",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "responsavel",
                "quem responde",
                "dono"
              ]
            }
          ]
        },
        {
          "rule_name": "budget_overrun_exclusion",
          "effect": "exclude",
          "minimum_concept_matches": 1,
          "priority": 5,
          "concepts": [
            {
              "concept_name": "budget_overrun",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "estouro",
                "orcamento",
                "orcado",
                "realizado"
              ]
            }
          ]
        }
      ]
    }
  }'::jsonb,
  120,
  TRUE
)
ON CONFLICT DO NOTHING;

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
VALUES (
  'v2.0-ducklake-query-generator-semantic-operations-v1',
  'metric_total_by_period',
  'metric_total_by_period_default',
  ARRAY['Exemplo documental generico; nao usar como lookup de benchmark.']::text[],
  ARRAY[
    'main_gold.gold_lancamentos_contabeis',
    'main_gold.gold_plano_contas'
  ]::text[],
  ARRAY['metric_total_by_period_contract']::text[],
  'Aggregate the configured financial metric over the requested period using authorized accounting and account-plan context.',
  'Generic semantic operation pattern; not tied to a specific question or expected SQL.',
  120,
  TRUE
)
ON CONFLICT DO NOTHING;

UPDATE public.ai_ducklake_dre_mapping
SET sql_filter_hint = COALESCE(sql_filter_hint, '{}'::jsonb)
  || '{"intent_name": "metric_total_by_period"}'::jsonb
WHERE agent_version =
  'v2.0-ducklake-query-generator-semantic-operations-v1'
  AND (
    is_revenue = TRUE
    OR is_cost = TRUE
    OR is_opex = TRUE
  );

-- Rollback manual, se a versao nova precisar ser removida antes de uso:
--
-- BEGIN;
-- DELETE FROM public.ai_ducklake_sql_patterns
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v1';
--
-- DELETE FROM public.ai_ducklake_entity_aliases
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v1';
--
-- DELETE FROM public.ai_ducklake_dre_mapping
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v1';
--
-- DELETE FROM public.ai_ducklake_table_catalog
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v1';
--
-- DELETE FROM public.ai_ducklake_agent_rules
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v1';
-- COMMIT;

COMMIT;
