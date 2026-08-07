# PROJECT-STATUS.md

Date: 2026-08-07

Branch: `master`

HEAD: `e535870`

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

## Next Stage

Stage 1: n8n remains official while the Next.js BFF dispatches asynchronous offline LangGraph shadow runs. Every official n8n SQL generation must trigger shadow, and every approved-SQL execution event must trigger its corresponding shadow event.

No cutover is claimed.

Benchmark remains postponed.
