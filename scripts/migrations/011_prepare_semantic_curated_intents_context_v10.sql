-- Microetapa semantic-curated-intents-v10
-- Persiste no contexto versionado as definicoes semanticas curadas.
-- Nao altera thresholds, benchmark, Python, SQL pronta ou versao ativa.

BEGIN;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v9-period-coverage'::text AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents'::text AS target_version
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
    'v2.0-ducklake-query-generator-semantic-operations-v9-period-coverage'::text AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents'::text AS target_version
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
    AND source.canonical_value IN ('resultado_por_marca', 'opex_por_marca', 'opex_por_centro_custo', 'orcado_vs_realizado', 'estouro_orcamento', 'dre_mensal', 'comparativo_marcas', 'impacto_setor_marca', 'responsavel_centro_custo')
  )
ON CONFLICT DO NOTHING;

INSERT INTO public.ai_ducklake_entity_aliases (
  agent_version, entity_type, user_term, canonical_value, target_table,
  target_column, sql_filter_hint, business_rule, priority, is_active
)
VALUES
(
  'v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents',
  'intent_definition',
  'resultado_por_marca_catalog_v1',
  'resultado_por_marca',
  NULL,
  NULL,
  NULL,
  '{"intent_catalog":{"semantic_description":"Resultado e desempenho por marca sem comparação explícita entre entidades.","rules":[{"rule_name":"require_brand_result","effect":"require","concepts":[{"concept_name":"brand_dimension","terms":["\\bmarc(?:a|as)\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"result_metric","terms":["\\bresultado(?:s)?\\b","\\bresultado liquido\\b","\\brol\\b","\\bmargem\\b","\\bdesempenho\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":2,"score":null,"priority":1},{"rule_name":"exclude_explicit_comparison","effect":"exclude","concepts":[{"concept_name":"comparison_operation","terms":["\\bcompare\\b","\\bcomparar\\b","\\bcomparativo\\b","\\bversus\\b","\\bvs\\b","\\bmelhor desempenho\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"comparison_relation","terms":["\\bcom\\b","\\bou\\b","\\bentre\\b","\\be\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":2,"score":null,"priority":1},{"rule_name":"exclude_opex_focus","effect":"exclude","concepts":[{"concept_name":"opex_metric","terms":["\\bopex\\b","\\bdespesa(?:s)? operacional(?:is)?\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":1,"score":null,"priority":1},{"rule_name":"score_brand_result","effect":"positive_score","concepts":[{"concept_name":"brand_dimension","terms":["\\bmarc(?:a|as)\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"result_metric","terms":["\\bresultado(?:s)?\\b","\\bresultado liquido\\b","\\brol\\b","\\bmargem\\b","\\bdesempenho\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":2,"score":135,"priority":1}]}}'::jsonb,
  1,
  TRUE
),
(
  'v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents',
  'intent_definition',
  'opex_por_marca_catalog_v1',
  'opex_por_marca',
  NULL,
  NULL,
  NULL,
  '{"intent_catalog":{"semantic_description":"OPEX agregado ou proporcional por marca.","rules":[{"rule_name":"require_brand_opex","effect":"require","concepts":[{"concept_name":"brand_dimension","terms":["\\bmarc(?:a|as)\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"opex_metric","terms":["\\bopex\\b","\\bdespesa(?:s)? operacional(?:is)?\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":2,"score":null,"priority":1},{"rule_name":"exclude_sector_breakdown","effect":"exclude","concepts":[{"concept_name":"cost_center_dimension","terms":["\\bcentro(?:s)? de custo\\b","\\bsetor(?:es)?\\b","\\barea(?:s)?\\b","\\bdepartamento(?:s)?\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":1,"score":null,"priority":1},{"rule_name":"score_brand_opex","effect":"positive_score","concepts":[{"concept_name":"brand_dimension","terms":["\\bmarc(?:a|as)\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"opex_metric","terms":["\\bopex\\b","\\bdespesa(?:s)? operacional(?:is)?\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":2,"score":145,"priority":1}]}}'::jsonb,
  2,
  TRUE
),
(
  'v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents',
  'intent_definition',
  'opex_por_centro_custo_catalog_v1',
  'opex_por_centro_custo',
  NULL,
  NULL,
  NULL,
  '{"intent_catalog":{"semantic_description":"OPEX, consumo, controle ou desempenho orçamentário por centro de custo, setor ou área.","rules":[{"rule_name":"require_cost_center","effect":"require","concepts":[{"concept_name":"cost_center_dimension","terms":["\\bcentro(?:s)? de custo\\b","\\bsetor(?:es)?\\b","\\barea(?:s)?\\b","\\bdepartamento(?:s)?\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":1,"score":null,"priority":1},{"rule_name":"score_center_opex","effect":"positive_score","concepts":[{"concept_name":"cost_center_dimension","terms":["\\bcentro(?:s)? de custo\\b","\\bsetor(?:es)?\\b","\\barea(?:s)?\\b","\\bdepartamento(?:s)?\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"opex_metric","terms":["\\bopex\\b","\\bdespesa(?:s)? operacional(?:is)?\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":2,"score":150,"priority":1},{"rule_name":"score_center_budget_control","effect":"positive_score","concepts":[{"concept_name":"cost_center_dimension","terms":["\\bcentro(?:s)? de custo\\b","\\bsetor(?:es)?\\b","\\barea(?:s)?\\b","\\bdepartamento(?:s)?\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"budget_metric","terms":["\\borcamento\\b","\\borcado\\b","\\borcada\\b","\\borcamentari\\w*\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"budget_control","terms":["\\bcontrole\\b","\\bconsum\\w*\\b","\\beconom\\w*\\b","\\bgast\\w* menos\\b","\\babaixo do orcamento\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":3,"score":150,"priority":2},{"rule_name":"score_center_overrun","effect":"positive_score","concepts":[{"concept_name":"cost_center_dimension","terms":["\\bcentro(?:s)? de custo\\b","\\bsetor(?:es)?\\b","\\barea(?:s)?\\b","\\bdepartamento(?:s)?\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"budget_overrun","terms":["\\bestour\\w*\\b","\\bacima do orcamento\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":2,"score":140,"priority":3}]}}'::jsonb,
  3,
  TRUE
),
(
  'v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents',
  'intent_definition',
  'orcado_vs_realizado_catalog_v1',
  'orcado_vs_realizado',
  NULL,
  NULL,
  NULL,
  '{"intent_catalog":{"semantic_description":"Comparação entre orçamento e realizado, variações, desvios ou impacto em grupos DRE.","rules":[{"rule_name":"score_budget_actual","effect":"positive_score","concepts":[{"concept_name":"budget_metric","terms":["\\borcamento\\b","\\borcado\\b","\\borcada\\b","\\borcamentari\\w*\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"actual_metric","terms":["\\brealizado\\b","\\brealizada\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":2,"score":160,"priority":1},{"rule_name":"score_variance_period","effect":"positive_score","concepts":[{"concept_name":"variance_metric","terms":["\\bdesvio(?:s)?\\b","\\bvariac\\w*\\b","\\bvariancia(?:s)?\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"monthly_period","terms":["\\bmes\\b","\\bmensal\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":2,"score":135,"priority":2},{"rule_name":"score_dre_negative_impact","effect":"positive_score","concepts":[{"concept_name":"dre_structure","terms":["\\bdre\\b","\\bdemonstrativo\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"impact_metric","terms":["\\bimpact\\w*\\b","\\bpes\\w*\\b","\\brepresent\\w*\\b","\\bcust\\w*\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"negative_impact","terms":["\\bnegativ\\w*\\b","\\bpior\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":3,"score":155,"priority":3}]}}'::jsonb,
  4,
  TRUE
),
(
  'v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents',
  'intent_definition',
  'estouro_orcamento_catalog_v1',
  'estouro_orcamento',
  NULL,
  NULL,
  NULL,
  '{"intent_catalog":{"semantic_description":"Estouro orçamentário por conta, centro de custo ou localização gerencial.","rules":[{"rule_name":"score_overrun_budget","effect":"positive_score","concepts":[{"concept_name":"budget_overrun","terms":["\\bestour\\w*\\b","\\bacima do orcamento\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"budget_metric","terms":["\\borcamento\\b","\\borcado\\b","\\borcada\\b","\\borcamentari\\w*\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":2,"score":165,"priority":1},{"rule_name":"score_overrun_account","effect":"positive_score","concepts":[{"concept_name":"budget_overrun","terms":["\\bestour\\w*\\b","\\bacima do orcamento\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"account_dimension","terms":["\\bconta(?:s)?\\b","\\bcontabil\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":2,"score":150,"priority":2},{"rule_name":"score_overrun_period","effect":"positive_score","concepts":[{"concept_name":"budget_overrun","terms":["\\bestour\\w*\\b","\\bacima do orcamento\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"monthly_period","terms":["\\bmes\\b","\\bmensal\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":2,"score":130,"priority":3}]}}'::jsonb,
  5,
  TRUE
),
(
  'v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents',
  'intent_definition',
  'dre_mensal_catalog_v1',
  'dre_mensal',
  NULL,
  NULL,
  NULL,
  '{"intent_catalog":{"semantic_description":"Análise mensal da demonstração de resultado total ou por marca.","rules":[{"rule_name":"score_dre","effect":"positive_score","concepts":[{"concept_name":"dre_structure","terms":["\\bdre\\b","\\bdemonstrativo\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":1,"score":125,"priority":1}]}}'::jsonb,
  7,
  TRUE
),
(
  'v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents',
  'intent_definition',
  'comparativo_marcas_catalog_v1',
  'comparativo_marcas',
  NULL,
  NULL,
  NULL,
  '{"intent_catalog":{"semantic_description":"Comparação explícita entre duas ou mais marcas ou entidades comerciais.","rules":[{"rule_name":"require_comparison_relation","effect":"require","concepts":[{"concept_name":"comparison_operation","terms":["\\bcompare\\b","\\bcomparar\\b","\\bcomparativo\\b","\\bversus\\b","\\bvs\\b","\\bmelhor desempenho\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"comparison_relation","terms":["\\bcom\\b","\\bou\\b","\\bentre\\b","\\be\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":2,"score":null,"priority":1},{"rule_name":"exclude_budget_comparison","effect":"exclude","concepts":[{"concept_name":"budget_metric","terms":["\\borcamento\\b","\\borcado\\b","\\borcada\\b","\\borcamentari\\w*\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"actual_metric","terms":["\\brealizado\\b","\\brealizada\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":1,"score":null,"priority":1},{"rule_name":"score_explicit_comparison","effect":"positive_score","concepts":[{"concept_name":"comparison_operation","terms":["\\bcompare\\b","\\bcomparar\\b","\\bcomparativo\\b","\\bversus\\b","\\bvs\\b","\\bmelhor desempenho\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"comparison_relation","terms":["\\bcom\\b","\\bou\\b","\\bentre\\b","\\be\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":2,"score":170,"priority":1}]}}'::jsonb,
  8,
  TRUE
),
(
  'v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents',
  'intent_definition',
  'impacto_setor_marca_catalog_v1',
  'impacto_setor_marca',
  NULL,
  NULL,
  NULL,
  '{"intent_catalog":{"semantic_description":"Impacto, peso ou representatividade de OPEX por setor dentro de cada marca.","rules":[{"rule_name":"require_sector","effect":"require","concepts":[{"concept_name":"cost_center_dimension","terms":["\\bcentro(?:s)? de custo\\b","\\bsetor(?:es)?\\b","\\barea(?:s)?\\b","\\bdepartamento(?:s)?\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":1,"score":null,"priority":1},{"rule_name":"score_sector_opex_scope","effect":"positive_score","concepts":[{"concept_name":"cost_center_dimension","terms":["\\bcentro(?:s)? de custo\\b","\\bsetor(?:es)?\\b","\\barea(?:s)?\\b","\\bdepartamento(?:s)?\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"opex_metric","terms":["\\bopex\\b","\\bdespesa(?:s)? operacional(?:is)?\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"within_brand_scope","terms":["\\bpor marca\\b","\\bde cada marca\\b","\\bdentro da\\b","\\bdentro de\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":3,"score":180,"priority":1},{"rule_name":"score_sector_impact_brand","effect":"positive_score","concepts":[{"concept_name":"cost_center_dimension","terms":["\\bcentro(?:s)? de custo\\b","\\bsetor(?:es)?\\b","\\barea(?:s)?\\b","\\bdepartamento(?:s)?\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"impact_metric","terms":["\\bimpact\\w*\\b","\\bpes\\w*\\b","\\brepresent\\w*\\b","\\bcust\\w*\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"brand_dimension","terms":["\\bmarc(?:a|as)\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":3,"score":175,"priority":2}]}}'::jsonb,
  9,
  TRUE
),
(
  'v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents',
  'intent_definition',
  'responsavel_centro_custo_catalog_v1',
  'responsavel_centro_custo',
  NULL,
  NULL,
  NULL,
  '{"intent_catalog":{"semantic_description":"Consulta cadastral de responsável ou gestor por centro de custo e unidade.","rules":[{"rule_name":"score_responsibility_center","effect":"positive_score","concepts":[{"concept_name":"responsibility_lookup","terms":["\\bresponsav\\w*\\b","\\bgestor(?:es)?\\b","\\badministra\\w*\\b","\\bresponde\\b","\\bdono\\b"],"match_mode":"regex","minimum_term_matches":1},{"concept_name":"cost_center_dimension","terms":["\\bcentro(?:s)? de custo\\b","\\bsetor(?:es)?\\b","\\barea(?:s)?\\b","\\bdepartamento(?:s)?\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":2,"score":155,"priority":1},{"rule_name":"score_responsibility_lookup","effect":"positive_score","concepts":[{"concept_name":"responsibility_lookup","terms":["\\bresponsav\\w*\\b","\\bgestor(?:es)?\\b","\\badministra\\w*\\b","\\bresponde\\b","\\bdono\\b"],"match_mode":"regex","minimum_term_matches":1}],"minimum_concept_matches":1,"score":120,"priority":2}]}}'::jsonb,
  10,
  TRUE
)
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v9-period-coverage'::text AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents'::text AS target_version
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
    'v2.0-ducklake-query-generator-semantic-operations-v9-period-coverage'::text AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents'::text AS target_version
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
    'v2.0-ducklake-query-generator-semantic-operations-v9-period-coverage'::text AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents'::text AS target_version
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
