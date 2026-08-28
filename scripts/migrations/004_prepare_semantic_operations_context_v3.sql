-- Microetapa 5.11-B15
-- Preparacao revisavel do contexto semantico de operacoes analiticas v3.
--
-- Objetivo:
-- - preservar a versao v2 intacta;
-- - criar uma nova versao derivada somente de registros ativos/permitidos;
-- - neutralizar orientacao fisica invalida para gold_gestor_cc.responsavel;
-- - reforcar chaves fisicas corretas de gold_unidade_negocio sem replace global.

BEGIN;

WITH versions AS (
  SELECT
    'v2.0-ducklake-query-generator-semantic-operations-v2'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v3'::text
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
    THEN concat_ws(
      E'\n',
      NULLIF(replace(
        replace(
          source.rule_content,
          'gold_gestor_cc.responsavel',
          'mapeamento fisico de responsavel indisponivel'
        ),
        'gcc.responsavel',
        'mapeamento fisico de responsavel indisponivel'
      ), ''),
      'Regra adicional v3: responsavel continua como conceito semantico cadastral, mas nenhuma coluna fisica de responsavel esta confirmada para gold_gestor_cc; nao projetar nem filtrar coluna fisica de responsavel.'
    )
    ELSE source.rule_content
  END,
  source.applies_to_intents,
  CASE
    WHEN source.rule_group = 'responsavel_centro_custo'
    THEN concat_ws(
      E'\n',
      NULLIF(replace(
        replace(
          source.validation_hint,
          'gold_gestor_cc.responsavel',
          'mapeamento fisico de responsavel indisponivel'
        ),
        'gcc.responsavel',
        'mapeamento fisico de responsavel indisponivel'
      ), ''),
      'Hint adicional v3: se a pergunta exigir nome de responsavel, retornar rejeicao controlada por contexto insuficiente ate existir mapping fisico confirmado.'
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
    'v2.0-ducklake-query-generator-semantic-operations-v2'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v3'::text
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
    THEN concat_ws(
      E'\n',
      NULLIF(replace(
        replace(
          source.business_rule,
          'gold_gestor_cc.responsavel',
          'mapeamento fisico de responsavel indisponivel'
        ),
        'gcc.responsavel',
        'mapeamento fisico de responsavel indisponivel'
      ), ''),
      'Regra adicional v3: alias semantico preservado; target_column permanece NULL porque nao ha coluna fisica confirmada para responsavel.'
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
    'v2.0-ducklake-query-generator-semantic-operations-v2'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v3'::text
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
    'v2.0-ducklake-query-generator-semantic-operations-v2'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v3'::text
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
    THEN concat_ws(
      E'\n',
      NULLIF(regexp_replace(
        replace(source.sql_pattern, 'gold_gestor_cc.responsavel', ''),
        E'(?m)^.*gcc\\.responsavel.*\\n?',
        '',
        'g'
      ), ''),
      'Orientacao adicional v3: preservar centro de custo, unidade, joins e filtros cadastrais autorizados; como nao ha coluna fisica confirmada para responsavel, nao projetar nem filtrar responsavel e rejeitar de forma controlada quando a resposta exigir esse atributo.'
    )
    ELSE source.sql_pattern
  END,
  CASE
    WHEN source.intent_name = 'responsavel_centro_custo'
      AND source.pattern_name = 'lookup_responsavel_por_centro_e_unidade'
    THEN concat_ws(
      E'\n',
      NULLIF(replace(
        replace(
          source.notes,
          'gold_gestor_cc.responsavel',
          'mapeamento fisico de responsavel indisponivel'
        ),
        'gcc.responsavel',
        'mapeamento fisico de responsavel indisponivel'
      ), ''),
      'Nota adicional v3: responsavel permanece conceito semantico, sem coluna fisica autorizada nesta versao.'
    )
    WHEN source.intent_name = 'orcado_vs_realizado'
      OR source.intent_name = 'estouro_orcamento'
    THEN concat_ws(
      E'\n',
      NULLIF(source.notes, ''),
      'Nota adicional v3: quando gold_unidade_negocio estiver envolvida, usar un.sk para join tecnico e un.nk_unide_neg para chave de negocio/filtro; nao usar un.sk_unid_neg nem un_dest.sk_unid_neg nessa tabela.'
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
    'v2.0-ducklake-query-generator-semantic-operations-v2'::text
      AS source_version,
    'v2.0-ducklake-query-generator-semantic-operations-v3'::text
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
    THEN concat_ws(
      E'\n',
      NULLIF(replace(
        replace(
          source.ai_hint,
          'A coluna do responsável é gcc.responsavel.',
          ''
        ),
        'gcc.responsavel',
        'mapeamento fisico de responsavel indisponivel'
      ), ''),
      'Addendum v3: nao ha coluna fisica responsavel confirmada em gold_gestor_cc; nao inventar, projetar ou filtrar coluna de responsavel. gcc.nk_unid_neg e un.nk_unide_neg sao campos de tabelas diferentes.'
    )
    WHEN source.table_name = 'gold_unidade_negocio'
    THEN concat_ws(
      E'\n',
      NULLIF(source.ai_hint, ''),
      'Addendum v3: colunas fisicas autorizadas desta tabela incluem sk e nk_unide_neg. Use sk para join tecnico e nk_unide_neg para chave de negocio/filtro. Nao usar sk_unid_neg nem nk_unid_neg nesta tabela.'
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
--   'v2.0-ducklake-query-generator-semantic-operations-v3';
--
-- DELETE FROM public.ai_ducklake_entity_aliases
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v3';
--
-- DELETE FROM public.ai_ducklake_dre_mapping
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v3';
--
-- DELETE FROM public.ai_ducklake_table_catalog
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v3';
--
-- DELETE FROM public.ai_ducklake_agent_rules
-- WHERE agent_version =
--   'v2.0-ducklake-query-generator-semantic-operations-v3';
-- COMMIT;

COMMIT;
