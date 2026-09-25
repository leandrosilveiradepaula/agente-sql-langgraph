# AI Product Factory

This repository is onboarded as the first existing-project pilot of the AI Product Factory.

Local repository instructions remain authoritative. In particular:

1. read `AGENTS.md`;
2. read `PROJECT-STATUS.md`;
3. read `ORCHESTRATION-STRATEGY.md`;
4. apply `.factory/project.json` only as orchestration metadata.

The factory must not reinterpret a postponed benchmark as authorization to run it, and must not treat TEST connectivity, real SQL execution, runtime activation, Supabase writes, n8n changes, Watson changes or production changes as implicitly authorized.

For ordinary reversible code changes, the factory may create a branch, implement, run the offline regression, open a PR, inspect CI and merge when no human gate is required.
