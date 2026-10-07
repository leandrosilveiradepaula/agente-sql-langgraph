# PROJECT-STATUS.md

Date: 2026-10-07

Branch: `main`

HEAD before PR #36: `8160b35da14329f9c6bb369d8812d0881730e0ba`

## Current State

LangGraph has not replaced n8n.

The governed architecture remains hybrid:

```text
Product / Next.js
+ n8n as official operational orchestration
+ LangGraph as semantic/reasoning core in shadow
```

Responsibilities remain separated:

- Product: interface, authentication, authorization, policies, history and observability.
- n8n: webhooks, integrations, deterministic orchestration and operational execution.
- LangGraph: semantic interpretation, intent resolution, context selection, planning, SQL generation/validation, repair proposal and evidence.

No implicit cutover is authorized.

## Operational Authority

Current authority is:

- OFFICIAL = n8n;
- SHADOW = LangGraph;
- real_sql_execution = false for LangGraph shadow.

LangGraph shadow must not alter the official answer and must not execute repaired or modified SQL silently.

Generate SQL, repair proposal and execute-approved remain separate lifecycle stages.

## LLM Status

Gemini remains the comparison provider used by the current benchmark baseline for both OFFICIAL and SHADOW so semantic architecture can be isolated from local-model quality.

Connectivity to the Infodive local provider has been validated separately:

- provider: `infodive_local`;
- model: `sql-infodive`;
- transport: OpenWebUI/Ollama over VPN.

This validates connectivity only. It does not claim semantic parity.

## Benchmark Baseline

The latest measured 63-question benchmark remains the pre-v9/v10 baseline:

- OFFICIAL: 59/63 approved = 93.65%;
- SHADOW technical success: 8/63;
- SHADOW rejected: 55/63.

Primary baseline rejection groups:

- 21 `INTENT_RESOLUTION_MINIMUM_SCORE_NOT_REACHED`;
- 18 `INTENT_RESOLUTION_AMBIGUOUS`;
- 10 `SQL_CONTRACT_JOIN_VIOLATED`;
- 3 `SQL_SECURITY_UNAUTHORIZED_TABLE`;
- 2 `INTERNAL_GENERATE_QUESTION_REQUIRED`;
- 1 `SQL_CONTRACT_AMBIGUOUS_COLUMN`.

This baseline must not be used as generation context or question-to-SQL lookup.

No claim is made yet that v9/v10 improved these counts because the 63-question regression has not been rerun after the new semantic context work.

## Recent Structural Changes

Merged changes include:

- provider failure reasons sanitized for observability;
- multiline/tab/CRLF question contract handling;
- safe intent-resolution and QueryPlan metadata;
- semantic intent coverage inventory;
- safe Security/Contract Gate diagnostics;
- planner join filtering now rejects join rules that reference unselected tables;
- `PLANNER_VERSION = v1.3.0-selected-table-join-filtering`.

The planner join correction is a confirmed structural bug fix. Correlation with historical unauthorized-table failures still requires post-change evidence.

## Semantic Context Versions

### v8 planned-filters

`semantic_context/demo_planned_filters_v8.delta.json` remains declarative and unapplied.

- `automatic_apply=false`;
- `activation.allowed=false`;
- Receita has a versioned binding;
- Custos is explicitly scoped as `CMV_ONLY`, backed by versioned evidence and an approved human decision;
- OPEX / `dre_despesas_operacionais` remains `BLOCKING_FAIL_CLOSED`.

The v8 delta is not the active runtime context.

### v9 period coverage

Migration merged:

`scripts/migrations/010_prepare_semantic_period_coverage_context_v9.sql`

Purpose:

- extend `metric_total_by_period` to explicit years, months, quarters and semesters;
- keep existing resolver scores and thresholds;
- remain context-driven rather than Python hardcode.

The migration is merged in source control but this status does not claim it has been applied to PostgreSQL or activated in Shadow.

### v10 curated intents

Migration merged:

`scripts/migrations/011_prepare_semantic_curated_intents_context_v10.sql`

Purpose:

- derive from v9;
- persist the 9 curated specialized `intent_definition` records from `semantic_context/intent_catalog_curado_v1.json`;
- preserve `metric_total_by_period`;
- remove dependence on a local in-memory overlay for those definitions.

The 9 curated definitions have no physical `target_table`, `target_column` or `sql_filter_hint` contract in the definition itself.

The migration is merged in source control but this status does not claim it has been applied to PostgreSQL or activated in Shadow.

## Intent Catalog Coverage

The curated catalog currently contains 9 specialized intent definitions:

- `resultado_por_marca`;
- `opex_por_marca`;
- `opex_por_centro_custo`;
- `orcado_vs_realizado`;
- `estouro_orcamento`;
- `dre_mensal`;
- `comparativo_marcas`;
- `impacto_setor_marca`;
- `responsavel_centro_custo`.

The generic semantic evolution also contains `metric_total_by_period`.

The live validator now inventories query-pattern intents versus intent-catalog definitions and reports missing coverage rather than silently treating examples as lookup.

## Security and Least Privilege

Shadow governance remains:

- `langgraph_shadow`: only required evidence persistence privileges; no DELETE;
- `langgraph_context_reader`: SELECT-only on authorized semantic context tables; no benchmark access and no writes.

No privilege expansion is authorized by v9/v10.

## Observability

Preserve and correlate:

- `agent_run_id`;
- LangGraph `run_id`;
- `shadow_record_id`;
- fingerprints;
- semantic/context versions;
- provider/model;
- token usage when available;
- status/gates/timeline;
- correlation metadata;
- sanitized provider failure reason;
- intent-resolution diagnostic;
- QueryPlan diagnostic;
- Security/Contract Gate structural diagnostic.

Do not persist or expose secrets, DSNs, authorization headers, cookies, API keys or unnecessary raw provider responses.

## Closed Decisions

- n8n remains strategic and is not being replaced.
- deterministic/operational work stays in n8n.
- semantic/agentic reasoning belongs in LangGraph.
- Product remains authority for UI, authn/authz, policies and history.
- benchmark fields are evaluation-only and must not reach generation prompts.
- business question examples are semantic signals only, never lookup.
- business knowledge belongs in versioned context/configuration, not new Python/TypeScript hardcode.
- repaired SQL loses approval and requires reapproval.
- Shadow remains non-executing until explicit promotion decision.

## Current Risks

- v9/v10 are merged in source control but still require controlled PostgreSQL application and read-only live validation before Shadow can select v10.
- The live catalog validator needed adaptation because v10 persists the curated definitions instead of relying only on overlay; PR #36 addresses this.
- OPEX planned-filter semantics remain fail-closed pending evidence-backed multi-group binding.
- Technical success still does not prove semantic correctness.
- Historical JOIN/security failures must be remeasured after the planner correction and new gate diagnostics.
- Local `sql-infodive` connectivity is validated, but semantic quality remains a separate test phase.

## Next Stage

Proceed in this order:

1. merge and validate PR #36;
2. apply v9 then v10 migrations to the semantic context store without changing OFFICIAL n8n;
3. run the live read-only catalog/context validator against v10;
4. switch only the LangGraph Shadow semantic context version to v10;
5. run a small set of new, semantically varied questions to verify generalization and evidence;
6. only then rerun the 63-question regression for measurement;
7. compare rejection distribution and semantic quality against the recorded baseline;
8. keep `real_sql_execution=false` until a separate explicit promotion decision.

No cutover is claimed.
