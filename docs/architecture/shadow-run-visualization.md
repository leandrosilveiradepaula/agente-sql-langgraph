# Shadow Run Visualization

## Objective

This document defines the local deterministic visualization of LangGraph shadow
runs from `ShadowRunRecord` evidence. It is not LangSmith, not a UI, and not an
operational database reader.

## Topology Versus Run Path

`docs/architecture/generated/langgraph-graph.mmd` shows the possible graph
topology. Shadow run visualization shows only the path supported by one
persisted evidence record.

If a node is present in the topology but not supported by the run evidence, it
is not rendered as executed. Missing execution detail is marked as evidence not
recorded.

## Evidence Sources

The mapper consumes the domain contract from
`app.domain.shadow_evidence_types.ShadowRunRecord`.

Current safe evidence includes:

- `shadow_record_id`, `agent_run_id`, `run_id`, `event_type`, `status`;
- `created_at`, `completed_at`;
- fingerprints for question, original generated SQL, approved SQL, repaired
  proposal, response, and evidence payload;
- `langgraph_evidence` summaries for intent, plan, gates, preflight, repair
  history, warnings, errors, final status, timings, and provider metadata;
- lineage fields such as context, SQL, gate, contract, and preflight
  fingerprints.

The visualization does not read Postgres and does not depend on repository
implementation details.

## Generate Runs

For `event_type=generate`, the mapper renders recorded evidence for:

```text
receive_question -> load_context -> classify_intent -> build_plan
-> generate_sql -> security_gate -> contract_gate -> engine_preflight
-> final
```

When `repair_history` exists, the path includes every recorded repair cycle.
Each cycle is explicitly numbered and no repair is invented when the history is
empty:

```text
engine_preflight -> repair_sql -> security_gate -> contract_gate
-> engine_preflight
```

Security or contract rejection stops at the recorded failed gate and then
renders `final`.

## Execute Approved Runs

For `event_type=execute_approved_shadow`, the mapper starts from:

```text
approved_sql_received -> security_gate -> contract_gate
-> engine_preflight -> final
```

It does not render `generate_sql`, `classify_intent`, or `build_plan`, because
those steps are not executed by this use case.

If repair is proposed, the path includes:

```text
engine_preflight -> repair_sql_proposal -> requires_reapproval -> final
```

The repaired SQL is evidence/proposal only and requires new human approval
before any future execution.

## Actual Nodes And Visualization Events

The mapper distinguishes actual LangGraph nodes from semantic visualization
events. Visualization events explain boundaries and terminal decisions in the
rendered evidence; they are not nodes returned by `create_graph()`.

Actual LangGraph nodes can include:

- `load_context`;
- `classify_intent`;
- `build_plan`;
- `generate_sql`;
- `security_gate`;
- `contract_gate`;
- `engine_preflight`;
- `repair_sql`.

Visualization events can include:

- `receive_question`;
- `approved_sql_received`;
- `repair_sql_proposal`;
- `requires_reapproval`;
- `persistence_failure`;
- `evidence_not_recorded`;
- `final`.

## Redaction

Default rendering includes only identifiers, statuses, node names, non-negative
timings, fingerprints, safe error codes, and flags. Metadata is allowlisted
before rendering, and the renderer applies its own defensive allowlist and
escaping.

Default rendering does not include:

- complete SQL;
- complete question text;
- semantic context payload;
- provider raw response;
- results;
- DSN or credentials.

No verbose mode is implemented in this microstep.

## Timeline And Mermaid

`app.domain.shadow_run_visualization` exposes neutral reconstruction:

- `visualize_shadow_run(record)`;
- `correlate_agent_run(records)`;
- `correlate_agent_run(records, agent_run_id=...)`;

`app.application.shadow_run_visualization_renderers` exposes textual rendering:

- `render_mermaid(visualization)`;
- `render_timeline(visualization)`;
- `render_correlation(correlation)`.

`scripts/render_shadow_run.py` can render a safe JSON `ShadowRunRecord` or one
of the synthetic examples. It can also check versioned examples for drift:

```powershell
.\.venv\Scripts\python.exe scripts\render_shadow_run.py --check-examples
```

Versioned examples:

- `docs/architecture/generated/shadow-run-generate-example.mmd`
- `docs/architecture/generated/shadow-run-execute-example.mmd`

## Correlation 1:N

Correlation is represented by `agent_run_id`. One official product run can have
multiple shadow records:

```text
agent_run_id=X
01 event_type=generate shadow_record_id=A run_id=LG1
02 event_type=execute_approved_shadow shadow_record_id=B run_id=LG2
```

This is a structural correlation view only. It does not compare output quality
or benchmark behavior.

## N8N And LangGraph Run View

The official path remains n8n. Shadow evidence is correlated by
`agent_run_id`.

Current view:

```text
Official: n8n run and response
Shadow: LangGraph run visualization
Correlated by: agent_run_id
```

Real comparison against n8n requires a future persisted n8n baseline. This
microstep does not require that baseline.

## Future UI And LangSmith

The model can later feed an admin UI or review screen because it is already a
small neutral structure: run, steps, edges, and flags.

LangSmith, Studio, tracing, API keys, Agent Server, and LangGraph CLI were not
added. They remain future complements requiring explicit operator approval.
