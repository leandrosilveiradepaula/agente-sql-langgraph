-- Disposable metadata-only PostgreSQL schema for CI. No customer data or SQL execution.
-- The only business-labelled identifiers are those already versioned in migration 021.
CREATE SCHEMA :"context_schema";
SET search_path TO :"context_schema";

CREATE TABLE ai_ducklake_agent_rules (
  agent_version text NOT NULL,
  rule_group text NOT NULL,
  rule_name text NOT NULL,
  rule_content text NOT NULL,
  applies_to_intents jsonb,
  validation_hint jsonb,
  severity text,
  priority integer,
  is_active boolean NOT NULL,
  UNIQUE (agent_version, rule_group, rule_name)
);

CREATE TABLE ai_ducklake_entity_aliases (
  agent_version text NOT NULL,
  entity_type text NOT NULL,
  user_term text NOT NULL,
  canonical_value text,
  target_table text,
  target_column text,
  sql_filter_hint jsonb,
  business_rule jsonb,
  priority integer,
  is_active boolean NOT NULL,
  UNIQUE (agent_version, entity_type, user_term)
);

CREATE TABLE ai_ducklake_dre_mapping (
  agent_version text NOT NULL,
  dre_code text NOT NULL,
  nivel_1_bi text,
  business_description text,
  sign_convention text,
  category text,
  is_revenue boolean,
  is_deduction boolean,
  is_cost boolean,
  is_opex boolean,
  is_financial_result boolean,
  sql_filter_hint jsonb,
  sort_order integer,
  is_active boolean NOT NULL,
  UNIQUE (agent_version, dre_code)
);

CREATE TABLE ai_ducklake_sql_patterns (
  agent_version text NOT NULL,
  intent_name text NOT NULL,
  pattern_name text NOT NULL,
  business_question_examples jsonb,
  required_tables jsonb,
  required_rules jsonb,
  sql_pattern text,
  notes text,
  priority integer,
  is_active boolean NOT NULL,
  UNIQUE (agent_version, intent_name, pattern_name)
);

CREATE TABLE ai_ducklake_table_catalog (
  agent_version text NOT NULL,
  table_name text NOT NULL,
  schema_name text NOT NULL,
  table_type text,
  description text,
  grain jsonb,
  primary_key jsonb,
  key_columns jsonb,
  metric_columns jsonb,
  date_columns jsonb,
  join_rules jsonb,
  ai_hint jsonb,
  priority integer,
  is_allowed boolean NOT NULL,
  UNIQUE (agent_version, schema_name, table_name)
);

INSERT INTO ai_ducklake_agent_rules (
  agent_version, rule_group, rule_name, rule_content, applies_to_intents,
  validation_hint, severity, priority, is_active
) VALUES (
  'demo-finance-v10', 'synthetic', 'baseline', '{}', '[]'::jsonb,
  NULL, 'info', 1, TRUE
);

-- These synthetic metric definitions intentionally match the candidate's
-- versioned amount-source metadata. No analytic facts or transactions exist.
INSERT INTO ai_ducklake_entity_aliases (
  agent_version, entity_type, user_term, canonical_value, target_table,
  target_column, sql_filter_hint, business_rule, priority, is_active
) VALUES
(
  'demo-finance-v10', 'metric_binding', 'budget-synthetic', 'amount',
  NULL, NULL, NULL,
  '{"metric_binding":{"metric_concept":"amount","target_table":"demo_lakehouse.gold_orcamento","target_column":"valor_orcado","when_present":["budget_source"]}}'::jsonb,
  1, TRUE
),
(
  'demo-finance-v10', 'metric_binding', 'realized-synthetic', 'amount',
  NULL, NULL, NULL,
  '{"metric_binding":{"metric_concept":"amount","target_table":"demo_lakehouse.gold_lancamentos_contabeis","target_column":"valor","when_present":["realized_source"]}}'::jsonb,
  2, TRUE
);

INSERT INTO ai_ducklake_dre_mapping (
  agent_version, dre_code, nivel_1_bi, business_description,
  sign_convention, category, is_revenue, is_deduction, is_cost, is_opex,
  is_financial_result, sql_filter_hint, sort_order, is_active
) VALUES (
  'demo-finance-v10', 'SYNTHETIC', 'Synthetic', 'Synthetic fixture',
  'none', 'test', FALSE, FALSE, FALSE, FALSE, FALSE,
  NULL, 1, TRUE
);

INSERT INTO ai_ducklake_sql_patterns (
  agent_version, intent_name, pattern_name, business_question_examples,
  required_tables, required_rules, sql_pattern, notes, priority, is_active
) VALUES (
  'demo-finance-v10', 'trend', 'synthetic-trend', '[]'::jsonb,
  '["demo_lakehouse.gold_orcamento"]'::jsonb, '[]'::jsonb,
  '', 'Disposable SQL integration fixture', 1, TRUE
);

INSERT INTO ai_ducklake_table_catalog (
  agent_version, table_name, schema_name, table_type, description, grain,
  primary_key, key_columns, metric_columns, date_columns, join_rules,
  ai_hint, priority, is_allowed
) VALUES
(
  'demo-finance-v10', 'gold_orcamento', 'demo_lakehouse', 'fact',
  'Budget source in synthetic metadata', 'null'::jsonb,
  'null'::jsonb, '[]'::jsonb, '["valor_orcado"]'::jsonb,
  '["competencia"]'::jsonb, '[]'::jsonb, '{}'::jsonb, 1, TRUE
),
(
  'demo-finance-v10', 'gold_lancamentos_contabeis', 'demo_lakehouse', 'fact',
  'Realized source with ambiguous temporal columns in synthetic metadata',
  'null'::jsonb, 'null'::jsonb, '[]'::jsonb, '["valor"]'::jsonb,
  '["data_lancamento","competencia"]'::jsonb,
  '[]'::jsonb, '{}'::jsonb, 2, TRUE
);
