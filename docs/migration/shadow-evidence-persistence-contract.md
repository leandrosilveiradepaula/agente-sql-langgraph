# Shadow Evidence Persistence Contract

## Purpose

This contract defines the separated persistence layer for offline LangGraph
shadow evidence. It does not replace n8n, does not write to the original product
store, and does not use `ai_agent_runs.metadata` as the primary shadow store.

## Storage Separation

Shadow evidence is stored in a dedicated `langgraph_shadow_runs` table. The
chosen model is one primary table with explicit correlation/status columns and
structured JSON evidence sections. This keeps the first implementation small
while preserving reconstruction, 1:N correlation, future benchmark inputs, and
future n8n baseline attachment.

## Stored Data

The record supports:

- `shadow_record_id`, `agent_run_id`, `run_id`, `event_type`, status, version,
  and timestamps;
- original question for generate events;
- `approved_sql_original` for approved-SQL shadow events;
- generated SQL and repaired proposal SQL when present;
- normalized principal and safe correlation metadata;
- semantic context, options, intent, plan, gate results, preflight result,
  repair history, warnings, errors, lineage, timings, and fingerprints;
- non-secret LangGraph version/commit and provider metadata when injected;
- future n8n baseline and future execution/benchmark fields.

Full permitted evidence plus fingerprints are stored. Fingerprints are not a
replacement for allowed content.

## Prohibited Data

The sanitizer removes sensitive keys before persistence, including API keys,
passwords, tokens, cookies, authorization headers, DSNs, raw credentials,
secrets, raw headers, and raw provider responses. Evidence must be strict JSON;
NaN, Infinity, non-string object keys, and non-serializable objects are rejected.

No custom encryption is introduced in this phase.

## Correlation

`agent_run_id` is the product run identifier. `run_id` is the LangGraph run
identifier. `shadow_record_id` identifies the dedicated shadow evidence record.
One `agent_run_id` may have many shadow records.

## Retention

Retention is intentionally long. No purge job, TTL, or numeric retention policy
is implemented in this microstep. Expiration policy is a future decision.

## Repository Port

`ShadowEvidenceRepository` exposes explicit operations to create a shadow
record, update evidence, finalize status, fetch by shadow id, and list by
`agent_run_id`. Application/domain layers depend only on this port and neutral
contracts. The concrete PostgreSQL adapter stays in infrastructure.

## Schema And Migration

The offline migration is:

`scripts/migrations/001_create_langgraph_shadow_runs.sql`

It creates `public.langgraph_shadow_runs` and indexes for `agent_run_id`,
`run_id`, and event/time queries. It is not executed in this microstep.

## Future N8N Baseline

The `n8n_baseline` section is reserved for future attachment of n8n SQL,
workflow version, status/error, timing, allowed output, and fingerprints. This
microstep does not call n8n, does not create a webhook, and does not integrate
Next.js.

## Benchmark

Benchmark remains postponed. No score, ranking, comparison, or quality judgment
is calculated now. The persistence shape preserves evidence needed for a future
benchmark.
