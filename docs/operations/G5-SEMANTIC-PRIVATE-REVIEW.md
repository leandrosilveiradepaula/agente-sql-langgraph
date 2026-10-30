# G5 semantic knowledge recovery — offline private review

On 30 October 2026, the VPS operator verified `G5_LINEAGE_RESULT=PASS` for 1,381 source semantic records and 11 versions per catalog. This evidence covers five collections but is **not** a mapping approval or financial parity proof.

## Goal

Recover usable source business evidence without copying hardcoded rules into Python, mixing historical versions, loading SQL examples into a generator, changing tenant or SQL permissions, or reactivating the old Supabase.

The review CLI creates 11 **AES256 GPG-encrypted** version-isolated packets, one per source `agent_version`, after verifying the encrypted recovered archive, original extraction receipt, independent source inventory, independently reconstructed lineage, hashes, and P3 physical snapshot. Each encrypted packet contains unreviewed historical records for rules, entity aliases, DRE mappings, and physical catalog only. The fifth collection, historical SQL patterns (106 records), is excluded entirely from the review packets and stays evaluation-only in the original encrypted recovery archive.

The packet includes technical identifier candidates with `NOT_ATTESTED` accounting equivalence. It contains **no approval, tenant binding, generated context version, imports, database writes, execution, network requests or LLM call**. Its manifest has fingerprints, counts and file digests only. Neither plaintext packets nor their passphrases belong in GitHub, public logs, CI artifacts or model prompts.

## Existing private inputs on the VPS

- G5 receipt: `/root/.local/share/agente-sql-langgraph/semantic-recovery/source-semantic-d777ed069af6f36a.sql.gpg.manifest.json`
- G5 independent inventory: `/root/.local/share/agente-sql-langgraph/semantic-recovery/source-semantic-inventory.json`
- G5 lineage report: `/root/.local/share/agente-sql-langgraph/semantic-recovery/source-semantic-lineage-v1.json`
- G5 private identifier candidates: `/root/.local/share/agente-sql-langgraph/semantic-recovery/source-semantic-identifiers-unapproved-v1.json`
- P3 physical snapshot: `/tmp/p3-source-audit.7DIc9fUP/physical-metadata.json`

After **human merge**, run locally from repository checkout (not CI, never in automated workflow):

```bash
cd /docker/agente-sql-langgraph-repo || exit 1
git fetch -q origin && git checkout -q main && git pull --ff-only -q origin main || exit 1
umask 077
.venv/bin/python -m scripts.operations.g5_semantic_context_review_offline \
 --receipt /root/.local/share/agente-sql-langgraph/semantic-recovery/source-semantic-d777ed069af6f36a.sql.gpg.manifest.json \
 --inventory /root/.local/share/agente-sql-langgraph/semantic-recovery/source-semantic-inventory.json \
 --lineage-report /root/.local/share/agente-sql-langgraph/semantic-recovery/source-semantic-lineage-v1.json \
 --lineage-identifiers /root/.local/share/agente-sql-langgraph/semantic-recovery/source-semantic-identifiers-unapproved-v1.json \
 --p3-snapshot /tmp/p3-source-audit.7DIc9fUP/physical-metadata.json
```

Supply the **existing G5 passphrase locally and without echo**; never share. On PASS the output is a private root-owned directory `g5-private-source-review-v1` with `manifest.json` (0600) and encrypted version packets (0600). For subsequent inspection, use dedicated offline, authenticated, least-privilege reviewer workflow. The tool refuses overwriting prior output and deletes partially created output on error.

Expected counts from the reported SOURCE snapshot: **1,275 non-SQL records sealed + 106 SQL patterns excluded = 1,381**. The number of source versions sealed should be **11**, subject to verification by the real private execution; these values do not by themselves prove finance correctness.

## Required next gate

Review each source version **independently** against the authorized `rivatti_demo_masked` physical inventory and compare the existing 10 `demo_lakehouse` semantic versions. Require explicit mappings for grain, metrics, values/sign, dates, joins, dimensions, DRE and tenant, plus independent accounting evidence and approval. No generation/cutover before this gate and additional parity and authorization checks.

`OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. `ai_ducklake_sql_patterns` stays exclusively in evaluation (not model context). All functional code is structural; no client-specific tables/columns in the motor.
