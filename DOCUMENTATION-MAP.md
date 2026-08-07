# DOCUMENTATION-MAP.md

## Purpose

This map defines documentation precedence for the LangGraph repository and prevents historical documents from being mistaken for current product or orchestration decisions.

## Canonical Precedence

1. Explicit current operator decisions.
2. `ORCHESTRATION-STRATEGY.md`.
3. `PROJECT-STATUS.md`.
4. Current technical contracts in `docs/migration/`.
5. Audits and external review packages.
6. Historical baselines and older migration notes.

If documents conflict, use the highest-precedence current source.

## Canonical Documents

### `ORCHESTRATION-STRATEGY.md`

Primary architecture document. It defines coexistence between the original product, n8n, and LangGraph; two-stage flow; BFF compatibility; shadow mode; identity boundaries; Watson/Gemini boundaries; run correlation; promotion stages; and benchmark posture.

### `PROJECT-STATUS.md`

Short temporal status document. It records current branch/HEAD, current official path, shadow posture, closed decisions, risks, and next stage.

### `DOCUMENTATION-MAP.md`

This document. It defines precedence and status labels.

## Technical Contracts

The documents under `docs/migration/` remain technical contracts for specific capabilities unless a higher-precedence document narrows their operational meaning.

Important current contracts include:

- `docs/migration/google-gemini-sql-generator-contract.md`
- `docs/migration/google-gemini-sql-repairer-contract.md`
- `docs/migration/http-entry-adapter-contract.md`
- `docs/migration/http-auth-boundary-contract.md`
- `docs/migration/watson-flow-contracts.md`
- `docs/migration/watson-flow-live-adapters.md`
- `docs/migration/run-persistence-audit-observability-contract.md`
- `docs/migration/application-service-use-case-contract.md`
- `docs/migration/application-response-contract.md`

## Historical Or Superseded Documents

Historical documents are preserved. Do not delete or rewrite them as if their original claims were never true.

### `docs/migration/sql-repair-loop-contract.md`

Status: historical for the statement that no real repair provider existed in that phase.

Current status: Gemini SQL Repairer now exists as an offline explicit provider. The repair loop contract remains useful for domain flow, safety, and retry limits, but its provider-availability statement is superseded.

### `docs/baselines/pre-live-readiness-baseline.md`

Status: historical baseline.

Current status: it predates the current canonical coexistence decisions and the now-documented Gemini Generator/Repairer posture. It remains useful as a point-in-time readiness record, not as current orchestration strategy.

## Audit Interpretation Rule

Audits that inspected only the LangGraph repository must not be read as saying the original product lacks persona, interface, UX, auth, history, admin, or operational workflow.

Correct distinction:

- The original product has those product capabilities.
- This LangGraph repository does not implement full product parity for those capabilities.

## Not Created

`PRODUCT.md` is intentionally not created in this repository during this phase. The product definition belongs to the original product repository. LangGraph documentation should describe its role as reasoning core and integration participant, not redefine the product.