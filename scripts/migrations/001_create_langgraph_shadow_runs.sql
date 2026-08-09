CREATE TABLE IF NOT EXISTS public.langgraph_shadow_runs (
  shadow_record_id text PRIMARY KEY,
  agent_run_id text NOT NULL,
  run_id text NOT NULL,
  event_type text NOT NULL CHECK (
    event_type IN ('generate', 'execute_approved_shadow')
  ),
  contract_version text NOT NULL,
  status text NOT NULL CHECK (
    status IN ('started', 'success', 'rejected', 'infrastructure_error')
  ),
  created_at timestamptz NOT NULL,
  completed_at timestamptz,
  question text,
  approved_sql_original text,
  generated_sql text,
  repaired_sql_proposal text,
  requires_reapproval boolean NOT NULL DEFAULT false,
  principal jsonb NOT NULL DEFAULT '{}'::jsonb,
  correlation_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  options jsonb NOT NULL DEFAULT '{}'::jsonb,
  semantic_context jsonb NOT NULL DEFAULT '{}'::jsonb,
  n8n_baseline jsonb NOT NULL DEFAULT '{}'::jsonb,
  langgraph_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  execution_future jsonb NOT NULL DEFAULT '{}'::jsonb,
  fingerprints jsonb NOT NULL DEFAULT '{}'::jsonb,
  lineage jsonb NOT NULL DEFAULT '{}'::jsonb,
  langgraph_version text,
  langgraph_commit text,
  evidence_fingerprint text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_langgraph_shadow_runs_agent_run_id
  ON public.langgraph_shadow_runs (agent_run_id);

CREATE INDEX IF NOT EXISTS idx_langgraph_shadow_runs_run_id
  ON public.langgraph_shadow_runs (run_id);

CREATE INDEX IF NOT EXISTS idx_langgraph_shadow_runs_event_created
  ON public.langgraph_shadow_runs (event_type, created_at);
