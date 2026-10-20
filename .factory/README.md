# AI Product Factory

This repository is onboarded as the first existing-project pilot of the AI Product Factory.

Local repository instructions remain authoritative. In particular:

1. read `AGENTS.md`;
2. read `PROJECT-STATUS.md`;
3. read `ORCHESTRATION-STRATEGY.md`;
4. apply `.factory/project.json` only as orchestration metadata.

The factory must not reinterpret a postponed benchmark as authorization to run it, and must not treat TEST connectivity, real SQL execution, runtime activation, Supabase writes, n8n changes, Watson changes or production changes as implicitly authorized.

For ordinary reversible code changes, the factory may create a branch, implement, run the offline regression, open a PR, inspect CI and merge when no human gate is required.


## Finance Agent current operator governance (2026-10-19)

The Finance Agent project has an explicit **human merge and production
promotion gate**; generic Factory auto-merge permissions do not override
`AGENTS.md`, `CHATGPT-PROJECT-INSTRUCTIONS.md` or
`docs/architecture/PORTABILITY-AND-CUTOVER-CONTRACT.md`.
Its three phases are n8n/Gemini versus n8n/LangGraph/Gemini Shadow parity;
authorized retirement of only the legacy intelligent n8n+Gemini nodes;
then Gemini versus SQL-InfoDive evaluation. Operational n8n stays.
Unreviewed client-specific hardcodes are forbidden in the new engine.
