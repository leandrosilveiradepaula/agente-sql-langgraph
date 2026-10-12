-- Candidate semantic context v10. Never switch the Shadow runtime implicitly.
-- Business vocabulary and intent compatibility remain versioned in PostgreSQL.
-- No benchmark examples, special-case questions, SQL templates or threshold changes.

BEGIN;
SET LOCAL search_path TO :"context_schema";

WITH versions AS (
  SELECT 'demo-finance-v9'::text AS source_version,
         'demo-finance-v10'::text AS target_version
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
  SELECT 'demo-finance-v9'::text AS source_version,
         'demo-finance-v10'::text AS target_version
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
  SELECT 'demo-finance-v9'::text AS source_version,
         'demo-finance-v10'::text AS target_version
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
  SELECT 'demo-finance-v9'::text AS source_version,
         'demo-finance-v10'::text AS target_version
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
  SELECT 'demo-finance-v9'::text AS source_version,
         'demo-finance-v10'::text AS target_version
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


-- Extend the configured trend concept with general verbal and nominal
-- expressions for longitudinal change; leave all existing terms intact.
WITH target AS (
  SELECT ctid AS row_id, business_rule::jsonb AS doc
  FROM ai_ducklake_entity_aliases
  WHERE agent_version = 'demo-finance-v10'
    AND entity_type = 'intent_definition'
    AND canonical_value = 'trend'
    AND is_active = TRUE
), updated AS (
  SELECT row_id,
    jsonb_set(doc, '{intent_catalog,rules}', (
      SELECT jsonb_agg(
        CASE WHEN rule ->> 'rule_name' = 'trend_primary'
          THEN jsonb_set(rule, '{concepts}', (
            SELECT jsonb_agg(
              CASE WHEN concept ->> 'concept_name' = 'trend'
                THEN jsonb_set(concept, '{terms}', (
                  SELECT jsonb_agg(to_jsonb(term) ORDER BY term)
                  FROM (
                    SELECT DISTINCT term
                    FROM (
                      SELECT jsonb_array_elements_text(
                        COALESCE(concept -> 'terms', '[]'::jsonb)
                      ) AS term
                      UNION ALL SELECT unnest(ARRAY[
                        'variar','variam','variou','variaram','variando',
                        'mudança','mudanças','mudou','mudaram',
                        'oscilação','oscilar','oscilou','oscilaram',
                        'flutuação','flutuar','flutuou','flutuaram'
                      ])
                    ) all_terms
                  ) unique_terms
                ))
                ELSE concept END ORDER BY concept_ordinality
            )
            FROM jsonb_array_elements(rule -> 'concepts')
              WITH ORDINALITY AS concepts(concept, concept_ordinality)
          ))
          ELSE rule END ORDER BY rule_ordinality
      )
      FROM jsonb_array_elements(doc -> 'intent_catalog' -> 'rules')
        WITH ORDINALITY AS rules(rule, rule_ordinality)
    )) AS updated_doc
  FROM target
)
UPDATE ai_ducklake_entity_aliases dest
SET business_rule = updated.updated_doc::text
FROM updated
WHERE dest.ctid = updated.row_id;

-- When an explicit trend operation is present, simple realized analysis
-- must not compete with it: realized is a scenario, trend is the operation.
-- Reuse the v10 trend vocabulary rather than duplicating a hardcoded list.
WITH trend_vocabulary AS (
  SELECT concept -> 'terms' AS terms
  FROM ai_ducklake_entity_aliases src
  CROSS JOIN LATERAL jsonb_array_elements(
    (src.business_rule::jsonb) -> 'intent_catalog' -> 'rules'
  ) AS r(rule)
  CROSS JOIN LATERAL jsonb_array_elements(r.rule -> 'concepts') AS c(concept)
  WHERE src.agent_version = 'demo-finance-v10'
    AND src.entity_type = 'intent_definition'
    AND src.canonical_value = 'trend'
    AND r.rule ->> 'rule_name' = 'trend_primary'
    AND c.concept ->> 'concept_name' = 'trend'
), target AS (
  SELECT ctid AS row_id, business_rule::jsonb AS doc
  FROM ai_ducklake_entity_aliases
  WHERE agent_version = 'demo-finance-v10'
    AND entity_type = 'intent_definition'
    AND canonical_value = 'realized_analysis'
    AND is_active = TRUE
), updated AS (
  SELECT row_id, jsonb_set(doc, '{intent_catalog,rules}',
    COALESCE(doc -> 'intent_catalog' -> 'rules', '[]'::jsonb)
    || jsonb_build_array(
      jsonb_build_object(
        'rule_name', 'realized_trend_operation_exclusion',
        'effect', 'exclude',
        'concepts', jsonb_build_array(
          jsonb_build_object(
            'concept_name', 'trend',
            'terms', trend_vocabulary.terms,
            'match_mode', 'contains',
            'minimum_term_matches', 1
          )
        ),
        'minimum_concept_matches', 1,
        'priority', 1
      )
    )) AS updated_doc
  FROM target CROSS JOIN trend_vocabulary
  WHERE NOT EXISTS (
    SELECT 1 FROM jsonb_array_elements(
      COALESCE(doc -> 'intent_catalog' -> 'rules', '[]'::jsonb)
    ) AS r(rule)
    WHERE r.rule ->> 'rule_name' = 'realized_trend_operation_exclusion'
  )
)
UPDATE ai_ducklake_entity_aliases dest
SET business_rule = updated.updated_doc::text
FROM updated WHERE dest.ctid = updated.row_id;

COMMIT;
