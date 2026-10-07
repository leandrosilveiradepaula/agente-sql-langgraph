# ORCHESTRATION-STRATEGY.md

## Purpose

This document defines the canonical orchestration strategy for coexistence between the original product, n8n, and LangGraph.

The goal is not to replace n8n in this phase. The goal is to introduce LangGraph as a reasoning core that works alongside the existing operational product and n8n path.

## Current Product Architecture

The original product is the operational system. It is a Next.js UI/BFF with existing user workflows and backend routes.

Current product responsibilities include:

- browser UI;
- Next.js BFF routes;
- authentication and session handling;
- users, levels/profiles, and policies;
- current endpoints `/api/generate-sql` and `/api/execute-sql`;
- n8n orchestration;
- approved SQL execution path via n8n;
- persistence in the product run/user/policy/audit tables;
- local and persisted history;
- admin areas;
- CSV/PDF exports;
- WhatsApp, Teams, and other operational integrations adjacent to the product.

Previous audit conclusions that described persona, interface, UX, auth, history, or admin as undefined were scoped only to this LangGraph repository and must not be read as product-level facts.

## LangGraph Role

LangGraph is the SQL reasoning core. Its natural responsibilities are:

- context;
- intent;
- planner;
- SQL generation;
- SQL repair;
- SQL security;
- contract validation;
- preflight;
- normalization;
- controlled lifecycle and internal validation.

LangGraph is not the browser UI, product admin, user management system, visual history, report exporter, bot layer, or replacement operational workflow system in this phase.

## Responsibility Boundaries

| CAPABILITY | PRODUCT ORIGINAL | N8N | LANGGRAPH | NOTES |
|---|---|---|---|---|
| UI/browser | Owner | None | None | Do not create second UI here. |
| BFF/API compatibility | Owner | Consumer/provider behind BFF | Internal service behind BFF | Current UI endpoints remain. |
| Auth/session | Owner | Receives context only | Receives normalized principal | No second user store now. |
| Users/profiles/policies | Owner | Receives context | Applies SQL-domain controls | Product remains authority during stabilization. |
| Generate SQL official path | Owns endpoint | Official initial path | Shadow initially | LangGraph may be promoted later. |
| Execute approved SQL official path | Owns endpoint | Official initial path | Shadow validation initially | No duplicate SQL execution. |
| Context/intent/planning | Supplies/correlates | Existing baseline | Owner target | Shadow captures evidence first. |
| SQL repair | Coordinates through official path | Existing baseline | Owner target provider | Gemini Repairer exists offline. |
| Security/contract gates | Product policy still applies | Existing workflow checks | SQL-domain gates | Boundaries must be mapped. |
| Preflight | Coordinates | Official initial path | Offline initially | Future TEST integrations require explicit authorization. |
| Gemini | Not direct UI concern | Baseline remains | Direct provider allowed | Does not replace n8n. |
| Persistence/history | Owner | May pass ids/status | Separate shadow store plus future adapters | Do not use metadata as primary shadow store. |
| Admin/CSV/PDF/bots | Owner | Operational integrations where applicable | None | Do not reimplement here. |

## Two-Stage Flow

The product has a required human pause. LangGraph must preserve it formally.

### A. GENERATE SQL

Purpose: generate SQL in a revisable format.

Canonical flow:

```text
Browser UI
-> Next.js /api/generate-sql
-> product auth/session/profile/policy checks
-> official n8n generation path
-> official response to user
-> asynchronous LangGraph offline shadow generation
-> separate shadow evidence capture
```

LangGraph must provide a formal backend use case or entrypoint for generation-only work. The generated SQL from LangGraph must remain available in a revisable form for shadow evidence and future promotion, even when not shown to the user initially.

### B. EXECUTE APPROVED SQL

Purpose: process the user-approved SQL execution event without collapsing it into generation.

Canonical flow:

```text
Browser UI
-> Next.js /api/execute-sql
-> product auth/session/profile/policy/ownership checks
-> official n8n approved-SQL execution path
-> official response to user
-> asynchronous LangGraph offline shadow event for approved SQL
-> no real SQL execution in initial shadow
-> separate shadow evidence capture
```

LangGraph must provide a formal backend use case or entrypoint for approved-SQL execution events. It receives the SQL exactly as approved by the user and may run gates, validations, and offline preflight.

If LangGraph detects that repair is needed, the repaired SQL loses the approved status. The repaired SQL may be stored as evidence or as a proposal for comparison, but any future execution of that repaired SQL requires new human approval. LangGraph must never automatically execute a SQL statement modified after the original approval.

In the current offline shadow, repair may be analyzed and recorded for comparison, but it is not treated as approved SQL and no real SQL execution is performed.

## BFF / Compatibility Layer

The Next.js BFF is the compatibility boundary.

Rules:

- current endpoints remain `/api/generate-sql` and `/api/execute-sql`;
- browser/UI does not call LangGraph directly;
- Next.js calls LangGraph through internal HTTP;
- LangGraph runs as a separate Python service;
- `/v1/sql-agent/query` is not exposed directly to the UI in this phase;
- compatibility contract must be versioned explicitly from v1;
- the BFF translates product requests/responses to LangGraph internal contracts;
- `agent_run_id` remains the product run identifier;
- `run_id` remains the LangGraph identifier;
- correlation may be 1:N.

Concrete payload fields, queue mechanism, HTTP framework, deploy topology, and schema are implementation work and are not defined here.

## Shadow Architecture

Initial shadow architecture:

- n8n remains official;
- LangGraph runs in parallel;
- dispatch is asynchronous;
- user response is never delayed by shadow completion;
- shadow failures do not interrupt, rollback, or alter the n8n official flow;
- no real external TEST integration by default;
- no real SQL execution;
- no user-visible shadow output;
- every official n8n SQL generation must trigger an asynchronous LangGraph shadow run;
- every approved-SQL execution event must trigger the corresponding asynchronous LangGraph shadow event.

When future real execution is approved, it must start read-only, use separate TEST/shadow credentials, and follow least privilege.

## Shadow Data Capture

Shadow capture must be rich and reconstructable, not only fingerprints.

The separate shadow persistence structure should store everything technically allowed and necessary for complete reconstruction and future benchmark, including:

- original question;
- context;
- full n8n SQL;
- full LangGraph SQL;
- outputs;
- errors;
- timings;
- intermediate decisions;
- intent;
- plan;
- gates;
- repair;
- preflight;
- versions;
- commits;
- workflow version;
- model/provider;
- relevant non-secret configuration;
- future results when real execution is separately authorized.

Do not persist secrets, credentials, tokens, cookies, or data whose retention is prohibited by policy or compliance.

Retention should be long. No numeric purge policy is defined now.

Future admins may inspect shadow data and divergences in the product UI, but that is not implemented now.

## Identity / Authorization Boundary

The original product remains authority for identity, sessions, users, profiles, levels, and policies during stabilization.

LangGraph receives only a normalized principal and non-secret authorization context. It must not create a second user/profile/admin system in this phase.

LangGraph retains its own SQL-domain controls, including Security Gate, Contract Gate, preflight, repair limits, and lifecycle validation. Fine-grained mapping from product policies into LangGraph gates can evolve later.

## Gemini Boundary

Gemini Generator and Repairer may be direct LangGraph providers.

They do not replace n8n. The n8n baseline remains official initially.

Gemini calls must remain behind LangGraph provider boundaries and must not receive secrets, cookies, tokens, raw headers, DSNs, or complete unrelated product state.

## Failure Behavior

Initial shadow failure behavior:

- no user-visible failure;
- no rollback of n8n;
- no interruption of official response;
- no automatic retry that changes external state;
- no fallback to the user because n8n remains official.

Future official LangGraph capabilities may have n8n fallback only where safe and read-only. SQL execution must not have automatic fallback that can duplicate effects.

## Run Correlation

`agent_run_id` is the original product run identifier.

`run_id` is the LangGraph run identifier.

Correlation may be 1:N because one product run can produce multiple LangGraph shadow attempts, retries, replays, or future benchmark records.

## Promotion Stages

### Stage 0: offline implementation

LangGraph capabilities are built and tested offline with fakes and no real external calls.

### Stage 1: n8n official + LangGraph offline shadow

Every official n8n SQL generation must trigger an asynchronous offline LangGraph shadow run. Every approved-SQL execution event must trigger the corresponding asynchronous LangGraph shadow event without real SQL execution.

### Stage 2: LangGraph shadow with authorized TEST integrations

Selected TEST integrations may be enabled only after explicit approval. Any future TEST integration permission does not imply real SQL execution permission.

### Stage 3: authorized read-only real shadow

Real shadow execution may begin only after separate authorization, using TEST/shadow credentials and least privilege.

### Stage 4: selective promotion of capabilities

Specific LangGraph capabilities may become official behind the BFF. This does not imply removal of n8n.

No dates are assigned to these stages.

## Benchmark

Benchmark is postponed.

Evidence capture must begin in Stage 1 so a future benchmark can compare SQL, intent, plan, gates, repair, success rate, errors, repair count, latency, cost, execution results, semantic divergences, and other available evidence.

## Provider Boundary Update — 2026-10-07

Watson and IBM Cloud are no longer part of the target architecture. n8n remains the operational integration/orchestration layer, LangGraph remains the semantic/reasoning core, and LLM providers are selected through versioned product/runtime configuration. SQL execution integrations must stay provider-neutral and preserve the human approval boundary.
