# PROJECT-STATUS.md

Date: 2026-09-27

Branch: `main`

HEAD: `bed49790aa94106a846a3a1d243172f5d67a3e36`

## Current State

LangGraph has not replaced n8n.

The original product remains the operational product. It lives outside this repository at:

`C:\Users\Leandro Silveira\Documents\Codex\2026-06-25\new-chat`

The original product already has a real Next.js UI/BFF, authentication, session handling, users, levels/profiles, policies, history, admin screens, CSV/PDF export, WhatsApp/Teams adjacent integrations, and the operational two-stage flow used by users.

This repository contains the LangGraph SQL agent backend work. It is not a second product UI and must not redefine the product experience.

## Operational Authority

The initial official path remains n8n.

The target initial architecture is:

```text
Original Product / Next.js BFF
+ n8n as official operational path
+ LangGraph as reasoning core in offline asynchronous shadow
```

The browser/UI must not call LangGraph directly. The current UI endpoints remain:

- `/api/generate-sql`
- `/api/execute-watson`

Next.js will call the separate Python LangGraph service through internal HTTP when integration is implemented.

## LangGraph Role

LangGraph is the reasoning core for the SQL lifecycle:

- context loading;
- intent resolution;
- deterministic planning;
- SQL generation;
- SQL repair;
- Security Gate;
- Contract Gate;
- offline preflight;
- internal validations;
- result normalization and controlled lifecycle contracts.

The graph currently models an end-to-end lifecycle, but the canonical product flow requires two formal backend use cases:

1. Generate SQL.
2. Execute approved SQL.

The separation must exist in LangGraph/backend entrypoints, not only in the Next.js BFF.

## Gemini Status

Offline Gemini SQL Generator and Gemini SQL Repairer providers have been implemented as explicit LangGraph providers. They do not replace n8n, do not make LangGraph official, do not authorize live Watson usage, and do not create benchmark execution.

## Planned Filters Status

Microetapa 7 was completed and merged through PR `#18` after microetapa 6.

- `main`: `bed49790aa94106a846a3a1d243172f5d67a3e36`
- Post-merge CI: `Offline validation` green
- Scope: offline only
- Deploy: not authorized
- Supabase: not changed
- n8n: not changed
- Runtime activation: not authorized

The offline `planned_filters` flow now supports semantic obligations,
separate `resolved_filter_bindings`, generator request separation, Contract
Gate enforcement, structural `join_path` proof and generic multi-value `IN`
bindings. Multi-value bindings accept only non-empty homogeneous simple literal
collections; SQL order does not change equivalence, while subqueries,
expressions, mixed types and `OR` remain fail-closed. Existing scalar bindings
remain compatible. The `join_path` validation resolves SQL aliases, checks
table/column/operator, accepts inverted operands and keeps comparisons isolated
per `JOIN ... ON`.

The DEMO v8 delta remains unapplied:

- `semantic_context/demo_planned_filters_v8.delta.json` is still an offline
  proposal;
- `automatic_apply=false`;
- `activation.allowed=false`.

`dre_receita` has a versioned read-only evidence manifest and a complete
binding for `demo-dre-receita-v1`. `dre_custos` remains
`BLOCKING_FAIL_CLOSED`, and `dre_despesas_operacionais` remains
`BLOCKING_FAIL_CLOSED`. Lucro, margem, ROL and derived concepts remain
unresolved and must not be inferred from the completed Receita binding.

## Shadow Status

Initial shadow is 100% offline:

- no Watson TEST real;
- no real SQL execution;
- no user-visible result;
- no rollback or interruption of the official n8n path;
- asynchronous dispatch required to avoid user-perceived latency.

Every official n8n SQL generation must trigger an asynchronous LangGraph shadow run. Every approved-SQL execution event must trigger the corresponding asynchronous LangGraph shadow event, still without real SQL execution initially.

Shadow persistence must use a separate structure, not `ai_agent_runs.metadata` as the primary store. It should capture all technically allowed evidence needed for full reconstruction and future benchmark, while never storing secrets, credentials, tokens, cookies, or data prohibited by policy/compliance.

## Closed Decisions

- n8n is not being replaced in this phase.
- n8n remains the official initial flow.
- LangGraph begins in offline asynchronous shadow.
- The original product remains authority for authentication, sessions, users, profiles, levels, and policies during stabilization.
- Browser/UI does not call LangGraph directly.
- Next.js calls LangGraph via internal HTTP.
- LangGraph runs as a separate Python service.
- `/v1/sql-agent/query` is not exposed directly to the UI in this phase.
- `agent_run_id` identifies the original product run.
- `run_id` identifies the LangGraph run.
- Correlation between them may be 1:N.
- Compatibility layer contract starts at v1.
- Shadow storage is separate and long-retention, with no purge policy defined now.
- Benchmark is postponed, but evidence capture starts in Stage 1.
- Do not create `PRODUCT.md` in this repository in this phase.

## Remaining Risks

- LangGraph still lacks full integration parity with the original product layers.
- Two-stage backend use cases still need implementation.
- Internal HTTP service/runtime topology is not implemented here.
- Shadow persistence schema and queue/async mechanism are future implementation decisions.
- Policy mapping from the original product into LangGraph SQL gates still needs implementation design.
- Future live Watson TEST and real SQL execution require separate explicit authorization.
- DEMO planned filters v8 is prepared but not applied or activated.
- `dre_custos` remains `BLOCKING_FAIL_CLOSED` and still needs explicit evidence/versioning before any binding.
- `dre_despesas_operacionais` remains `BLOCKING_FAIL_CLOSED`. The generic multi-group mechanism now exists, but a versioned semantic rule and evidence-backed binding are still required before any DEMO binding or activation.
- `sql_filter_hint` and `nivel_1_bi` remain TRANSITIONAL evidence only, not generation or binding contracts.

## Semantic Decision Update — 2026-10-01

A material requirement decision was approved through the AI Product Factory Control Plane: `dre_custos` is CMV-only in this explicitly versioned context.

Microstage 8 versions the existing read-only CMV evidence into offline binding `demo-dre-custos-v1`. This does not activate the v8 delta, does not modify n8n/Supabase/Watson, does not authorize cutover and does not run the postponed 63-question benchmark.

The approved scope does not promote `gasto/gastos`, `custo operacional` or `custo de vendas`. `dre_despesas_operacionais` remains `BLOCKING_FAIL_CLOSED`.

## Next Stage

Stage 1: n8n remains official while the Next.js BFF dispatches asynchronous offline LangGraph shadow runs. Every official n8n SQL generation must trigger shadow, and every approved-SQL execution event must trigger its corresponding shadow event.

No cutover is claimed.

Benchmark remains postponed.

The generic multi-group design has been completed in microetapa 7 without activating any financial concept.

The next semantic work remains evidence/configuration, not a generic engine gap:

1. decide explicitly whether `dre_custos` should mean CMV-only for the relevant context; or
2. create versioned semantic evidence and a concrete binding for `dre_despesas_operacionais` using the now-supported generic multi-value contract.

Neither path authorizes activation, Supabase changes, deploy, benchmark execution or cutover.
