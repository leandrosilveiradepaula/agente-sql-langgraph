-- Candidate-only context evolution: demo-finance-v10 -> demo-finance-v11.
-- Adds generic temporal planning metadata without changing v9/v10 or runtime.
-- No benchmark expectation, SQL template or threshold introduced.
-- Requires the structural temporal planner contract before activation.

BEGIN;
SET LOCAL search_path TO :"context_schema";

DO 'BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ai_ducklake_agent_rules
    WHERE agent_version = ''demo-finance-v10'' AND is_active = TRUE
  ) THEN
    RAISE EXCEPTION ''demo-finance-v10 source context is missing'';
  END IF;
  IF EXISTS (
    SELECT 1 FROM ai_ducklake_agent_rules WHERE agent_version = ''demo-finance-v11''
  ) OR EXISTS (
    SELECT 1 FROM ai_ducklake_entity_aliases WHERE agent_version = ''demo-finance-v11''
  ) OR EXISTS (
    SELECT 1 FROM ai_ducklake_sql_patterns WHERE agent_version = ''demo-finance-v11''
  ) OR EXISTS (
    SELECT 1 FROM ai_ducklake_table_catalog WHERE agent_version = ''demo-finance-v11''
  ) OR EXISTS (
    SELECT 1 FROM ai_ducklake_dre_mapping WHERE agent_version = ''demo-finance-v11''
  ) THEN
    RAISE EXCEPTION ''demo-finance-v11 already exists; immutable context not modified'';
  END IF;
END';

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


-- The temporal planner contract is structural; business metadata belongs
-- to this immutable, versioned candidate (not to Python or the n8n workflow).
-- V10 catalog evidence confirms competencia on both realized and budget
-- metric sources, while realized also declares data_lancamento. The proposed
-- accounting period reference for DRE and realized/budget comparison is
-- explicitly versioned below: never infer from the available date columns.
-- Operational analysis by posting date is a distinct semantic reference;
-- this configuration does not authorize silently substituting one for another.
-- This is candidate metadata only; it does not approve activation.
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
    'date_binding_strategy', 'configured_metric_source_date',
    'date_bindings', jsonb_build_array(
      jsonb_build_object(
        'metric_concept', 'amount',
        'target_table', 'demo_lakehouse.gold_orcamento',
        'target_column', 'competencia'
      ),
      jsonb_build_object(
        'metric_concept', 'amount',
        'target_table', 'demo_lakehouse.gold_lancamentos_contabeis',
        'target_column', 'competencia'
      )
    ),
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
  jsonb_build_array('trend'),
  NULL,
  'error',
  20,
  TRUE
);


-- Transactional integrity gate. A partial clone or an unsupported declared
-- date binding is never committed; no existing context version is modified.
DO $v11_candidate_integrity$
DECLARE
  section record;
  copied_source bigint;
  copied_target bigint;
  temporal_cfg jsonb;
  configured_date jsonb;
  source_matches bigint;
  catalog_matches bigint;
  cloned_payload_differs boolean;
  unbound_metric_sources bigint;
  duplicated_temporal_sources bigint;
BEGIN
  FOR section IN
    SELECT * FROM (VALUES
      ('ai_ducklake_agent_rules', 'is_active'),
      ('ai_ducklake_entity_aliases', 'is_active'),
      ('ai_ducklake_dre_mapping', 'is_active'),
      ('ai_ducklake_sql_patterns', 'is_active'),
      ('ai_ducklake_table_catalog', 'is_allowed')
    ) AS records(table_name, active_column)
  LOOP
    EXECUTE format(
      'SELECT COUNT(*) FROM %I WHERE agent_version = $1 AND %I = TRUE',
      section.table_name, section.active_column
    ) INTO copied_source USING 'demo-finance-v10';
    EXECUTE format(
      'SELECT COUNT(*) FROM %I WHERE agent_version = $1 AND %I = TRUE',
      section.table_name, section.active_column
    ) INTO copied_target USING 'demo-finance-v11';

    -- Only one new rule is expected: the candidate temporal configuration.
    IF section.table_name = 'ai_ducklake_agent_rules' THEN
      copied_target := copied_target - 1;
    END IF;
    IF copied_source = 0 OR copied_source <> copied_target THEN
      RAISE EXCEPTION
        'Candidate v11 clone integrity mismatch in % (transaction rolled back)',
        section.table_name;
    END IF;

    -- Counting rows cannot detect a changed field or a silent conflict.
    -- Compare both directions including duplicate multiplicities; strip only
    -- agent_version and exclude the single new v11 temporal configuration.
    EXECUTE format(
      'WITH original AS (
         SELECT to_jsonb(s) - ''agent_version'' AS payload
         FROM %I AS s
         WHERE s.agent_version = $1 AND s.%I = TRUE
       ), cloned AS (
         SELECT to_jsonb(t) - ''agent_version'' AS payload
         FROM %I AS t
         WHERE t.agent_version = $2 AND t.%I = TRUE %s
       ), differences AS (
         (SELECT payload FROM original EXCEPT ALL SELECT payload FROM cloned)
         UNION ALL
         (SELECT payload FROM cloned EXCEPT ALL SELECT payload FROM original)
       )
       SELECT EXISTS (SELECT 1 FROM differences)',
      section.table_name,
      section.active_column,
      section.table_name,
      section.active_column,
      CASE
        WHEN section.table_name = 'ai_ducklake_agent_rules'
        THEN 'AND NOT (t.rule_group = ''component_config'' AND t.rule_name = ''temporal_planning_config'')'
        ELSE ''
      END
    ) INTO cloned_payload_differs
    USING 'demo-finance-v10', 'demo-finance-v11';
    IF cloned_payload_differs THEN
      RAISE EXCEPTION
        'Candidate v11 clone payload mismatch in % (transaction rolled back)',
        section.table_name;
    END IF;
  END LOOP;

  IF (
    SELECT COUNT(*)
    FROM ai_ducklake_agent_rules
    WHERE agent_version = 'demo-finance-v11'
      AND rule_group = 'component_config'
      AND rule_name = 'temporal_planning_config'
      AND is_active = TRUE
  ) <> 1 THEN
    RAISE EXCEPTION
      'Candidate v11 must contain exactly one temporal planning configuration';
  END IF;

  SELECT rule_content::jsonb INTO temporal_cfg
  FROM ai_ducklake_agent_rules
  WHERE agent_version = 'demo-finance-v11'
    AND rule_group = 'component_config'
    AND rule_name = 'temporal_planning_config'
    AND is_active = TRUE;

  IF temporal_cfg->>'date_binding_strategy' <> 'configured_metric_source_date'
     OR jsonb_typeof(temporal_cfg->'date_bindings') <> 'array'
     OR jsonb_array_length(temporal_cfg->'date_bindings') = 0 THEN
    RAISE EXCEPTION 'Candidate v11 date binding metadata is missing';
  END IF;

  -- A configured source cannot have two competing reference dates; a
  -- missing source must not be silently rescued by another source.
  SELECT COUNT(*) INTO duplicated_temporal_sources
  FROM (
    SELECT
      LOWER(BTRIM(value->>'metric_concept')) AS metric_concept,
      LOWER(BTRIM(value->>'target_table')) AS target_table
    FROM jsonb_array_elements(temporal_cfg->'date_bindings')
    GROUP BY 1, 2
    HAVING COUNT(*) > 1
  ) duplicates;
  IF duplicated_temporal_sources <> 0 THEN
    RAISE EXCEPTION 'Candidate v11 temporal date bindings are ambiguous';
  END IF;

  SELECT COUNT(*) INTO unbound_metric_sources
  FROM ai_ducklake_entity_aliases e
  WHERE e.agent_version = 'demo-finance-v11'
    AND e.entity_type = 'metric_binding'
    AND e.is_active = TRUE
    AND NOT EXISTS (
      SELECT 1
      FROM jsonb_array_elements(temporal_cfg->'date_bindings') AS d(value)
      WHERE LOWER(BTRIM(d.value->>'metric_concept')) =
        LOWER(BTRIM(COALESCE(
          e.business_rule::jsonb->'metric_binding'->>'metric_concept',
          e.canonical_value
        )))
        AND LOWER(BTRIM(d.value->>'target_table')) =
          LOWER(BTRIM(COALESCE(
            NULLIF(e.business_rule::jsonb->'metric_binding'->>'target_table', ''),
            e.target_table
          )))
    );
  IF unbound_metric_sources <> 0 THEN
    RAISE EXCEPTION 'Candidate v11 metric sources lack explicit temporal bindings';
  END IF;

  FOR configured_date IN
    SELECT value
    FROM jsonb_array_elements(temporal_cfg->'date_bindings')
  LOOP
    IF NULLIF(BTRIM(configured_date->>'metric_concept'), '') IS NULL
       OR NULLIF(BTRIM(configured_date->>'target_table'), '') IS NULL
       OR NULLIF(BTRIM(configured_date->>'target_column'), '') IS NULL THEN
      RAISE EXCEPTION 'Candidate v11 contains an incomplete date binding';
    END IF;

    SELECT COUNT(*) INTO source_matches
    FROM ai_ducklake_entity_aliases e
    WHERE e.agent_version = 'demo-finance-v11'
      AND e.entity_type = 'metric_binding'
      AND e.is_active = TRUE
      AND COALESCE(
        e.business_rule::jsonb->'metric_binding'->>'metric_concept',
        e.canonical_value
      ) = configured_date->>'metric_concept'
      AND COALESCE(
        NULLIF(e.business_rule::jsonb->'metric_binding'->>'target_table', ''),
        e.target_table
      ) = configured_date->>'target_table';

    IF source_matches <> 1 THEN
      RAISE EXCEPTION
        'Candidate v11 temporal metric binding is missing or ambiguous';
    END IF;

    SELECT COUNT(*) INTO catalog_matches
    FROM ai_ducklake_table_catalog t
    WHERE t.agent_version = 'demo-finance-v11'
      AND t.is_allowed = TRUE
      AND (t.schema_name || '.' || t.table_name)
        = configured_date->>'target_table'
      AND EXISTS (
        SELECT 1
        FROM jsonb_array_elements(
          COALESCE(to_jsonb(t.date_columns), '[]'::jsonb)
        ) AS declared(value)
        WHERE declared.value = to_jsonb(configured_date->>'target_column')
           OR declared.value->>'name' = configured_date->>'target_column'
      );

    IF catalog_matches <> 1 THEN
      RAISE EXCEPTION
        'Candidate v11 temporal date is not authorized by the catalog';
    END IF;
  END LOOP;
END
$v11_candidate_integrity$;

COMMIT;
