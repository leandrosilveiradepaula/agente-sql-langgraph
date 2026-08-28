-- Microetapa 5.11-B12
-- Preparacao revisavel do contexto semantico de operacoes analiticas v2.
--
-- Objetivo:
-- - preservar a versao v1 intacta;
-- - criar uma nova versao derivada somente de registros ativos/permitidos;
-- - remover inducao de coluna fisica inexistente para responsavel;
-- - reforcar a chave fisica correta de gold_unidade_negocio.

BEGIN;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v1'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v2'::text
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
  CASE
    WHEN source.rule_group = 'responsavel_centro_custo'
      AND source.rule_name = 'nao_retornar_responsavel_nulo'
    THEN
      concat_ws(
        E'\n',
        NULLIF(source.rule_content, ''),
        'Regra adicional v2: mapeamento fisico de responsavel indisponivel nesta versao. Nao gerar coluna de responsavel ate que o catalogo versionado contenha uma coluna fisica confirmada.'
      )
    ELSE source.rule_content
  END,
  source.applies_to_intents,
  CASE
    WHEN source.rule_group = 'responsavel_centro_custo'
      AND source.rule_name IN (
        'grao_centro_unidade',
        'nao_retornar_responsavel_nulo'
      )
    THEN
      concat_ws(
        E'\n',
        NULLIF(source.validation_hint, ''),
        'Hint adicional v2: sem coluna fisica confirmada para responsavel. Rejeicao controlada por contexto insuficiente e preferivel a inventar coluna.'
      )
    ELSE source.validation_hint
  END,
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
    'v2.0-ducklake-query-generator-semantic-operations-v1'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v2'::text
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
  CASE
    WHEN source.target_table = 'gold_gestor_cc'
      AND source.target_column = 'responsavel'
    THEN NULL
    ELSE source.target_column
  END,
  source.sql_filter_hint,
  CASE
    WHEN source.target_table = 'gold_gestor_cc'
      AND source.target_column = 'responsavel'
    THEN
      concat_ws(
        E'\n',
        NULLIF(source.business_rule, ''),
        'Regra adicional v2: mapeamento fisico de responsavel indisponivel; nao projetar coluna inventada.'
      )
    ELSE source.business_rule
  END,
  source.priority,
  source.is_active
FROM public.ai_ducklake_entity_aliases source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v1'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v2'::text
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
    'v2.0-ducklake-query-generator-semantic-operations-v1'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v2'::text
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
  CASE
    WHEN source.intent_name = 'responsavel_centro_custo'
      AND source.pattern_name = 'lookup_responsavel_por_centro_e_unidade'
    THEN
      concat_ws(
        E'\n',
        NULLIF(source.sql_pattern, ''),
        'Orientacao adicional v2: mapeamento fisico de responsavel indisponivel nesta versao; nao gerar coluna de responsavel ate que o catalogo versionado contenha coluna fisica confirmada.'
      )
    ELSE source.sql_pattern
  END,
  CASE
    WHEN source.intent_name = 'responsavel_centro_custo'
      AND source.pattern_name = 'lookup_responsavel_por_centro_e_unidade'
    THEN
      concat_ws(
        E'\n',
        NULLIF(source.notes, ''),
        'Nota adicional v2: preservar centro de custo e unidade quando houver mapeamento fisico autorizado. Sem coluna fisica confirmada para responsavel, retornar rejeicao controlada por contexto insuficiente.'
      )
    WHEN source.intent_name = 'estouro_orcamento'
      AND source.pattern_name = 'maiores_estouros_conta_ou_centro_custo'
    THEN
      concat_ws(
        E'\n',
        NULLIF(source.notes, ''),
        'Nota adicional v2: quando gold_unidade_negocio estiver envolvida, usar un.nk_unide_neg. Nao extrapolar nk_unid_neg para gold_unidade_negocio. Outras tabelas podem possuir nk_unid_neg legitimamente.'
      )
    ELSE source.notes
  END,
  source.priority,
  source.is_active
FROM public.ai_ducklake_sql_patterns source
CROSS JOIN versions
WHERE source.agent_version = versions.source_version
  AND source.is_active = TRUE
ON CONFLICT DO NOTHING;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v1'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v2'::text
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
  CASE
    WHEN source.table_name = 'gold_gestor_cc'
    THEN
      concat_ws(
        E'\n',
        NULLIF(source.ai_hint, ''),
        'Addendum v2: nao ha coluna fisica responsavel confirmada nesta tabela; nao inventar coluna de responsavel. gcc.nk_unid_neg e un.nk_unide_neg sao campos de tabelas diferentes.'
      )
    WHEN source.table_name = 'gold_unidade_negocio'
    THEN
      concat_ws(
        E'\n',
        NULLIF(source.ai_hint, ''),
        'Addendum v2: chave fisica confirmada nesta tabela = nk_unide_neg. Nao usar nk_unid_neg nesta tabela.'
      )
    ELSE source.ai_hint
  END,
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
--   'v2.0-ducklake-query-generator-semantic-operations-v2';
--
-- DELETE FROM public.ai_ducklake_entity_aliases
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v2';
--
-- DELETE FROM public.ai_ducklake_dre_mapping
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v2';
--
-- DELETE FROM public.ai_ducklake_table_catalog
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v2';
--
-- DELETE FROM public.ai_ducklake_agent_rules
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v2';
-- COMMIT;

COMMIT;
