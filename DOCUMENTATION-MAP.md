# DOCUMENTATION-MAP.md

## Purpose

This map defines documentation precedence for the LangGraph repository and prevents historical documents from being mistaken for current product or orchestration decisions.

## Canonical Precedence

1. **Explicit latest operator decisions**, including phase order and deployment gates.
2. **`AGENTS.md` + `CHATGPT-PROJECT-INSTRUCTIONS.md`**: permanent
   agent working rules, hardcode policy and cross-chat continuity.
3. **`docs/architecture/PORTABILITY-AND-CUTOVER-CONTRACT.md`** +
   **`ORCHESTRATION-STRATEGY.md`**: normative multi-tenant acceptance
   criteria and component responsibility boundaries.
4. **`PROJECT-STATUS.md`**, always checking the dated latest update and
   corroborating live GitHub/VPS evidence; stale snapshots are historical.
5. Current technical contracts in `docs/migration/`.
6. Audit packages and historical baselines.

`docs/codex/CURRENT_TASK.md` controls only its **explicit, still-applicable
task scope**. A historical or unrelated microstep cannot negate a newer
user instruction, allow migration/cutover or supersede architectural gates.
Any conflicting historical document remains preserved but subordinate.

If documents conflict, use the highest-precedence current source.

## Canonical Documents

### `ORCHESTRATION-STRATEGY.md`

Primary architecture document. It defines coexistence between the original product, n8n, and LangGraph; two-stage flow; BFF compatibility; shadow mode; identity boundaries; Watson/Gemini boundaries; run correlation; promotion stages; and benchmark posture.

### `PROJECT-STATUS.md`

Short temporal status document. It records current branch/HEAD, current official path, shadow posture, closed decisions, risks, and next stage.

### `DOCUMENTATION-MAP.md`

This document. It defines precedence and status labels.

### `AGENTS.md`

Mandatory repository instructions for coding agents and ChatGPT. Its
2026-10-19 mission block has current precedence over older phase-specific
sections of the same file.

### `CHATGPT-PROJECT-INSTRUCTIONS.md`

Copy-ready, session-independent instructions for the **Agente Financeiro**
ChatGPT Project. Defines the operator's three phases, multiclient
portability, hardcode elimination, evidence and gates. These instructions
must also be placed in the ChatGPT Project settings by an operator;
versioning them in GitHub alone **does not update ChatGPT settings**.

### `docs/architecture/PORTABILITY-AND-CUTOVER-CONTRACT.md`

Authoritative completion contract (G1–G6): retire the *legacy intelligent
path* n8n + Gemini only after parity and a human cutover, while keeping
n8n operational orchestration. Defines the future Gemini versus Infodive
LLM test, hardcode inventory and multiclient proof.

## Technical Contracts

The documents under `docs/migration/` remain technical contracts for specific capabilities unless a higher-precedence document narrows their operational meaning.

Important current contracts include:

- `docs/migration/google-gemini-sql-generator-contract.md`
- `docs/migration/google-gemini-sql-repairer-contract.md`
- `docs/migration/http-entry-adapter-contract.md`
- `docs/migration/http-auth-boundary-contract.md`
- `docs/migration/watson-flow-contracts.md` (historical/legacy only)
- `docs/migration/watson-flow-live-adapters.md` (historical/legacy only)
- `docs/migration/run-persistence-audit-observability-contract.md`
- `docs/migration/application-service-use-case-contract.md`
- `docs/migration/application-response-contract.md`

## Historical Or Superseded Documents

### Watson/IBM IAM and earlier intent of preserving legacy generation

The old Watson technical contracts and documentation describing *indefinite*
coexistence are historical. The 2026-10-19 operator explicitly targets
**replacement of legacy n8n-embedded SQL intelligence** after Shadow parity;
this does **not** retire n8n. IBM Cloud hosting of a private model does not
make Watson a supported provider dependency.

### `PROJECT-STATUS.md` dated 2026-10-07 sections

Preserved as dated history below the current operative update. Do not use
the pre-v9/v10 63-case baseline or older provider deployment notes as current
acceptance or evidence of recent parity.

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