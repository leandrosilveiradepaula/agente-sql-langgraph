-- Microetapa semantic-period-coverage-v8
-- Amplia cobertura temporal da intent generica sem alterar thresholds,
-- benchmark, Python ou SQL pronta.

BEGIN;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v7'::text AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v8-period-coverage'::text AS target_version
)
INSERT INTO public.ai_ducklake_agent_rules (
  agent_version, rule_group, rule_name, rule_content, applies_to_intents,
  validation_hint, severity, priority, is_active
)
SELECT
  versions.target_version, source.rule_group, source.rule_name,
  source.rule_content, source.applies_to_intents, source.validation_hint,
  source.severity, source.priority, source.is_active
FROM public.ai_ducklake_agent_rules source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v7'::text AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v8-period-coverage'::text AS target_version
)
INSERT INTO public.ai_ducklake_entity_aliases (
  agent_version, entity_type, user_term, canonical_value, target_table,
  target_column, sql_filter_hint, business_rule, priority, is_active
)
SELECT
  versions.target_version, source.entity_type, source.user_term,
  source.canonical_value, source.target_table, source.target_column,
  source.sql_filter_hint, source.business_rule, source.priority,
  source.is_active
FROM public.ai_ducklake_entity_aliases source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
  AND NOT (
    source.entity_type = 'intent_definition'
    AND source.canonical_value = 'metric_total_by_period'
  )
ON CONFLICT DO NOTHING;

INSERT INTO public.ai_ducklake_entity_aliases (
  agent_version, entity_type, user_term, canonical_value, target_table,
  target_column, sql_filter_hint, business_rule, priority, is_active
)
VALUES (
  'v2.0-ducklake-query-generator-semantic-operations-v8-period-coverage',
  'intent_definition',
  'metric_total_by_period_period_coverage_v8',
  'metric_total_by_period',
  NULL,
  NULL,
  NULL,
  '{
    "intent_catalog": {
      "semantic_description": "Resolve perguntas analiticas genericas sobre metricas financeiras por periodos relativos ou explicitos e dimensoes autorizadas pelo contexto.",
      "rules": [
        {
          "rule_name": "metric_period_operation_or_dimension_required_v8",
          "effect": "require",
          "minimum_concept_matches": 3,
          "priority": 1,
          "concepts": [
            {
              "concept_name": "financial_metric",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "receita","receitas","faturamento","rol","opex",
                "despesa","despesas","despesa operacional",
                "despesas operacionais","gasto","gastos","custo","custos",
                "movimentado","movimentacao"
              ]
            },
            {
              "concept_name": "analytical_operation",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "total","quanto","qual foi","quais foram","valor agregado",
                "consolidado","soma","distribuido","distribuidos",
                "distribuicao","concentraram","concentrado",
                "concentracao","maiores"
              ]
            },
            {
              "concept_name": "dimension_grouping",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "por marca","por centro de custo","centro de custo",
                "por unidade","unidade","por conta","conta contabil"
              ]
            },
            {
              "concept_name": "period_reference",
              "match_mode": "regex",
              "minimum_term_matches": 1,
              "terms": [
                "\\bultimo mes\\b",
                "\\bultimo mes fechado\\b",
                "\\bultimo periodo\\b",
                "\\bultimo periodo disponivel\\b",
                "\\bmes passado\\b",
                "\\bmes anterior\\b",
                "\\bperiodo anterior\\b",
                "\\bperiodo passado\\b",
                "\\bno mes\\b",
                "\\b(?:19|20)\\d{2}\\b",
                "\\btrimestre\\b",
                "\\b(?:primeiro|segundo|terceiro|quarto) trimestre\\b",
                "\\bsemestre\\b",
                "\\b(?:primeiro|segundo) semestre\\b",
                "\\bano atual\\b",
                "\\bano passado\\b",
                "\\bano anterior\\b",
                "\\b(?:janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\\b"
              ]
            }
          ]
        },
        {
          "rule_name": "metric_operation_period_score_v8",
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
                "receita","receitas","faturamento","rol","opex",
                "despesa","despesas","despesa operacional",
                "despesas operacionais","gasto","gastos","custo","custos",
                "movimentado","movimentacao"
              ]
            },
            {
              "concept_name": "analytical_operation",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "total","quanto","qual foi","quais foram","valor agregado",
                "consolidado","soma","distribuido","distribuidos",
                "distribuicao","concentraram","concentrado",
                "concentracao","maiores"
              ]
            },
            {
              "concept_name": "period_reference",
              "match_mode": "regex",
              "minimum_term_matches": 1,
              "terms": [
                "\\bultimo mes\\b","\\bultimo mes fechado\\b",
                "\\bultimo periodo\\b","\\bultimo periodo disponivel\\b",
                "\\bmes passado\\b","\\bmes anterior\\b",
                "\\bperiodo anterior\\b","\\bperiodo passado\\b",
                "\\bno mes\\b","\\b(?:19|20)\\d{2}\\b",
                "\\btrimestre\\b",
                "\\b(?:primeiro|segundo|terceiro|quarto) trimestre\\b",
                "\\bsemestre\\b","\\b(?:primeiro|segundo) semestre\\b",
                "\\bano atual\\b","\\bano passado\\b","\\bano anterior\\b",
                "\\b(?:janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\\b"
              ]
            }
          ]
        },
        {
          "rule_name": "metric_dimension_period_score_v8",
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
                "receita","receitas","faturamento","rol","opex",
                "despesa","despesas","despesa operacional",
                "despesas operacionais","gasto","gastos","custo","custos",
                "movimentado","movimentacao"
              ]
            },
            {
              "concept_name": "dimension_grouping",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": [
                "por marca","por centro de custo","centro de custo",
                "por unidade","unidade","por conta","conta contabil"
              ]
            },
            {
              "concept_name": "period_reference",
              "match_mode": "regex",
              "minimum_term_matches": 1,
              "terms": [
                "\\bultimo mes\\b","\\bultimo mes fechado\\b",
                "\\bultimo periodo\\b","\\bultimo periodo disponivel\\b",
                "\\bmes passado\\b","\\bmes anterior\\b",
                "\\bperiodo anterior\\b","\\bperiodo passado\\b",
                "\\bno mes\\b","\\b(?:19|20)\\d{2}\\b",
                "\\btrimestre\\b",
                "\\b(?:primeiro|segundo|terceiro|quarto) trimestre\\b",
                "\\bsemestre\\b","\\b(?:primeiro|segundo) semestre\\b",
                "\\bano atual\\b","\\bano passado\\b","\\bano anterior\\b",
                "\\b(?:janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\\b"
              ]
            }
          ]
        },
        {
          "rule_name": "responsibility_lookup_exclusion_v8",
          "effect": "exclude",
          "minimum_concept_matches": 1,
          "priority": 4,
          "concepts": [
            {
              "concept_name": "responsibility_lookup",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": ["responsavel","quem responde","dono"]
            }
          ]
        },
        {
          "rule_name": "budget_overrun_exclusion_v8",
          "effect": "exclude",
          "minimum_concept_matches": 1,
          "priority": 5,
          "concepts": [
            {
              "concept_name": "budget_overrun",
              "match_mode": "contains",
              "minimum_term_matches": 1,
              "terms": ["estouro","orcamento","orcado","realizado"]
            }
          ]
        }
      ]
    }
  }',
  35,
  TRUE
)
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v7'::text AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v8-period-coverage'::text AS target_version
)
INSERT INTO public.ai_ducklake_dre_mapping (
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
FROM public.ai_ducklake_dre_mapping source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v7'::text AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v8-period-coverage'::text AS target_version
)
INSERT INTO public.ai_ducklake_sql_patterns (
  agent_version, intent_name, pattern_name, business_question_examples,
  required_tables, required_rules, sql_pattern, notes, priority, is_active
)
SELECT
  versions.target_version, source.intent_name, source.pattern_name,
  source.business_question_examples, source.required_tables,
  source.required_rules, source.sql_pattern, source.notes,
  source.priority, source.is_active
FROM public.ai_ducklake_sql_patterns source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v7'::text AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v8-period-coverage'::text AS target_version
)
INSERT INTO public.ai_ducklake_table_catalog (
  agent_version, table_name, schema_name, table_type, description, grain,
  primary_key, key_columns, metric_columns, date_columns, join_rules,
  ai_hint, priority, is_allowed
)
SELECT
  versions.target_version, source.table_name, source.schema_name,
  source.table_type, source.description, source.grain, source.primary_key,
  source.key_columns, source.metric_columns, source.date_columns,
  source.join_rules, source.ai_hint, source.priority, source.is_allowed
FROM public.ai_ducklake_table_catalog source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_allowed = TRUE
ON CONFLICT DO NOTHING;

COMMIT;
