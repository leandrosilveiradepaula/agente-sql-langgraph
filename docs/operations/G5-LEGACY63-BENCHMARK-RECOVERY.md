# G5 legacy 63-question benchmark recovery (private, offline)

## Scope and evidence

The original n8n workflow reads questions from `public.ai_ducklake_benchmarks`
and stores its completed per-case evaluation in
`public.ai_ducklake_benchmark_runs`. This recovery operates on a **verified,
encrypted SOURCE archive** already held on the VPS. The SOURCE Supabase is not
reactivated. No official n8n workflow, Product route, semantic catalog,
financial database, or runtime is changed.

This is an **evaluation-only** adapter for a legacy source format, not a
business rule in LangGraph. Neither historical SQL, required filters,
expected intent nor benchmark correctness hints may enter the generator.

## Review and use (after human merge)

The G5 archive must be root-owned in the existing private archive directory.
The PostgreSQL 17 Docker image must be cached. The CLI verifies archive SHA-256,
uses a pinned local image, drops all Linux capabilities, disables the network,
uses no host mounts and stores the container database in anonymous tmpfs.
It selects **only the two benchmark tables** from the archive. The passphrase
is read via local terminal `getpass`, never via ChatGPT, argv, env or logs.

Run from the checkout on the VPS:

```bash
cd /docker/agente-sql-langgraph-repo || exit 1
git fetch -q origin && git checkout -q main && git pull --ff-only origin main
.venv/bin/python -m scripts.operations.g5_recover_legacy_benchmark_offline \
  --plan --source-project-ref nywxpvzhlpqjtcafpdfe
```

The plan only verifies encrypted archive digest and local image; it does not
inspect decrypted tables or prove the 63 cases exist. If multiple G5 manifests
exist, use `--manifest` with a prevalidated absolute owner-only archive
manifest from the same private directory.

After the plan passes and the authorized operator has reviewed the PR, run:

```bash
cd /docker/agente-sql-langgraph-repo || exit 1
.venv/bin/python -m scripts.operations.g5_recover_legacy_benchmark_offline \
  --recover --source-project-ref nywxpvzhlpqjtcafpdfe
```

Type `RECOVER-LEGACY-BENCHMARK-63` and the existing G5 archive passphrase **in
the VPS terminal only**. Do not paste the passphrase, SQL or historical
answers into ChatGPT or GitHub. No external network requests or real financial
SQL execution are made. If the selected-table restore fails (e.g. dependencies
not in the two tables), fail closed; do not switch to a full restore silently.

The script requires 63 active, unique benchmark questions within **one source
version** and one exactly covering 63-record historical run in the same
version. It chooses the latest **complete** run by recorded timestamp, never
by approval rate; tied latest timestamps fail closed. A historical result may
have no SQL: it is preserved as missing evidence, not fabricated.

## Outputs

Owner-only files under:
`/root/.local/share/agente-sql-langgraph/benchmark-private/legacy63-<digest>/`

- `official-baseline.json`: historical n8n SQL and intent when actually present.
  The **original** n8n agent run ID is kept in `historical-witness.json`, not
  misrepresented as the ID of a future LangGraph attempt.
- `questions-only.json`: exactly `case_id` and `question` for each case;
  neither historical SQL, expected intent, required filters, golden answers
  nor source run identity appears here.
- `freeze-receipt.json`: fingerprints for integrity. Store it under
  independently verified pre-generation custody before claiming a frozen
  benchmark; generation of this receipt alone does not prove that custody.
- `historical-witness.json`: PRIVATE source rows and original n8n evaluation,
  including any expected filters, SQL and responses. Evaluation use ONLY.

All files are created with POSIX `0600`, in a root-only `0700` directory,
without overwrite. A repeated identical recovery refuses to overwrite.
The script prints only status codes, row counts and the private output path,
never question bodies, SQL, scores, secrets or source credentials.

The existing `scripts/blind_shadow_benchmark.py` can consume the baseline in
its **prepare** phase. Its existing **evaluate** phase still expects matching
new Shadow run identity and authenticated principal in the baseline; it cannot
assume a historical n8n `agent_run_id` is the same as a future Shadow run.
Before a full cross-run comparison, add a separately frozen post-generation
case-to-Shadow-run correlation record; do not silently rewrite or reuse the
historical run IDs. The 63 baseline questions are the regression benchmark,
not proof of generalization to new client questions.

## Blockers and governance

If no eligible 63-row cohort exists or the archive lacks either table, report
`BENCHMARK_RECOVERY=BLOCKED` and inspect existing n8n execution history or an
already authorized alternate snapshot. Do **not** re-run the 63 questions
against the official n8n, activate SOURCE, expose the benchmark to semantic
context, run Gemini/SQL-InfoDive, or enable real financial SQL by convenience.

`OFFICIAL=n8n`, `SHADOW=LangGraph`,
`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` remain. A future LangGraph batch
needs explicit provider/cost consent; any numeric comparison is a distinct
read-only authorization and must not happen in the Shadow generator.

## 10/11/2026 — historic 63-case archive actually recovered (operator evidence)

The isolated operator run reported `BENCHMARK_RECOVERY=PASS`,
`BENCHMARK_CASES=63`, `BENCHMARK_OFFICIAL_SQL_PRESENT=63`,
`BENCHMARK_ISOLATED_CONTAINER_CLEANUP=PASS`,
`BENCHMARK_FINANCIAL_SQL_EXECUTED=false`, and `BENCHMARK_LLM_CALLS=0`.
The VPS MCP independently verified:
`g5_benchmark_recovery_status(status=pass,cases=63,baseline_case_count=63,history_case_count=63,questions_only=true,freeze_receipt_present=true,official_sql_present=63)`.

The backup is held privately at
`/root/.local/share/agente-sql-langgraph/benchmark-private/legacy63-ea0035e714f64e275b0f/`.
No file from that directory is to be checked into Git or exposed in CI.

A defect was isolated in the legacy recovery stream: its GPG producer exited
with code 2 when the consuming `pg_restore` closed its pipe after successfully
restoring selected tables (exit 0). A one-off, memory-only stream-draining
adapter was used during the successful recovery. The original pinned recovery
module remains unchanged; any persistent correction requires reviewed update
of its hash-pinned MCP contract, not an unreviewed on-host change.

### Blind dispatch preparation (no calls or DB writes)

The recovered private folder contains `questions-only.json`,
`official-baseline.json`, `freeze-receipt.json`, and
`historical-witness.json`. The operator must maintain independent custody
of a copy of the receipt before invoking any generation.

```bash
cd /docker/agente-sql-langgraph-repo || exit 1
PRIVATE=/root/.local/share/agente-sql-langgraph/benchmark-private/legacy63-ea0035e714f64e275b0f
.venv/bin/python -m scripts.blind_shadow_batch prepare \
  --manifest "$PRIVATE/questions-only.json" \
  --receipt "$PRIVATE/freeze-receipt.json" \
  --output "$PRIVATE/dispatch-plan-v1.json"
```

This produces unique *new* `agent_run_id` values for all cases. It **does not**
automatically call an LLM or invoke the webhook. The dispatch plan contains
only the ID, case ID, and original question. It carries **no** historical
SQL, expected intent, historic result, or benchmark answer. It must remain
private and unchanged while the operator-approved Shadow-only generation is
performed.

When a generation batch has been separately authorized and completed, export
the **full, fingerprinted** `ShadowRunRecord` values (not the sanitized
evidence-read projection) to an authorized private
`shadow-records-v1.json` file, with no other run IDs. The database
reader and export mechanisms must uphold tenant and principal isolation.
The existing evidence-read n8n workflow returns a limited safe projection,
**not** sufficient to populate this evaluator; do not fake a full record from
that projection.

```bash
.venv/bin/python -m scripts.blind_shadow_batch bind \
  --manifest "$PRIVATE/questions-only.json" \
  --receipt "$PRIVATE/freeze-receipt.json" \
  --dispatch-plan "$PRIVATE/dispatch-plan-v1.json" \
  --evidence "$PRIVATE/shadow-records-v1.json" \
  --output "$PRIVATE/post-generation-correlation-v1.json"

.venv/bin/python -m scripts.blind_shadow_benchmark evaluate \
  --baseline "$PRIVATE/official-baseline.json" \
  --manifest "$PRIVATE/questions-only.json" \
  --receipt "$PRIVATE/freeze-receipt.json" \
  --dispatch-plan "$PRIVATE/dispatch-plan-v1.json" \
  --correlation "$PRIVATE/post-generation-correlation-v1.json" \
  --evidence "$PRIVATE/shadow-records-v1.json" \
  --output "$PRIVATE/structural-evaluation-v1.json"
```

The evaluator verifies the **original** frozen baseline and receipt *before*
joining observed **new** run identifiers in memory. Missing runs remain
`sem_evidencia`; duplicates, foreign records and tampering block comparison.
The original baseline and receipt fingerprints are preserved. This proves
neither financial parity nor historical source/provider/model provenance
when those were not captured by the legacy run.

**Still required before any batch**: clear evidence of the actual Gemini
provider/model on both paths, correct LangGraph S2S credential binding for
the active Shadow workflow, exact tenant/auth principal scope, explicit
provider/cost authorization, a bounded dispatch/export transport, and a
post-generation evidence integrity/correlation audit. The approved 63-case
benchmark tests regression against the legacy source; it is **not** a
replacement for novel-question portability tests.

## 10/11/2026 — isolated Gemini quality harness (NOT n8n parity)

The operator verified on the VPS:

- \`GIT_FAST_FORWARD=PASS\` at \`fb22285fba855528643fdaf43fbf214dc3f42857\`, with an unrelated untracked local file preserved.
- \`BLIND_BATCH=PASS\`, 63 unique new run IDs, 0 HTTP/LLM/financial SQL calls.
- \`OFFICIAL_MODEL_ATTESTED=0\`: historic baseline SQLs are available, but no historic Gemini provider/model provenance was captured.
- In an isolated, nonpersistent runtime: \`ISOLATED_GEMINI_RUNTIME=PASS\`, model \`gemini-2.5-flash\`, model metadata HTTP 200 (not proof of successful generation), SQL execution false.
- Existing running Shadow service still defaults to private SQL-InfoDive. **Do not reconfigure it** in order to perform the Gemini quality experiment.

**Important filesystem correction:** The reviewed G5 MCP snapshot reader currently requires exactly four files in the recovered \`legacy63-*\` directory. Adding \`dispatch-plan-v1.json\` inside it triggers \`recovery_snapshot_files_invalid\` although its original four files remain valid. Move only this new dispatch-plan file into a separate root-private working directory. Do not touch the four historical files.

\`\`\`bash
set -Eeuo pipefail
RECOVERY=/root/.local/share/agente-sql-langgraph/benchmark-private/legacy63-ea0035e714f64e275b0f
WORK=/root/.local/share/agente-sql-langgraph/benchmark-private/gemini-quality-working
install -d -m 700 "$WORK"
if [ -f "$RECOVERY/dispatch-plan-v1.json" ]; then
  test ! -e "$WORK/dispatch-plan-v1.json"
  mv -- "$RECOVERY/dispatch-plan-v1.json" "$WORK/dispatch-plan-v1.json"
fi
cd /docker/agente-sql-langgraph-repo
.venv/bin/python -m scripts.operations.run_blind_gemini_shadow_quality preflight \
  --manifest "$RECOVERY/questions-only.json" \
  --receipt "$RECOVERY/freeze-receipt.json" \
  --dispatch-plan "$WORK/dispatch-plan-v1.json" \
  --expected-cases 63
\`\`\`

The preflight is offline, read-only, and **cannot** call an LLM. It verifies the frozen manifest receipt and the 63 unique planned new run IDs.

A separate \`run\` action exists but is **disabled unless** the operator explicitly authorizes the generation API costs, a maximum number of provider calls, the expected model, and a dedicated private result directory. This code is *not* an authorisation to call the model, and no activation is implied by merge. The example below is deliberately non-executable: parameters are illustrative and operator approval is still outstanding.

When separately approved, the runner uses the unchanged running container *only as a process image* through \`docker exec -i\` with overrides visible solely to the new Python process. It never edits the container's original environment, restarts it, or writes to its PostgreSQL Shadow evidence database. It injects a dedicated **in-memory** evidence repository, bounds calls at the HTTP transport, and invokes the **real** LangGraph SQL Generate ASGI handler with real Gemini as configured. Historical SQL/expected answers are not available to this child process at any point. Full signed evidence files are saved in an owner-only output directory. Only **after all cases finish** does the parent read the frozen official baseline, bind signed generation records, and run the existing SQL structural comparator, producing its score report and an explicit notice that the n8n transport and financial results were NOT tested.

The quality harness's principal is a **declared synthetic test principal**, not a Product-authenticated user. It MUST NOT be represented as proof of real n8n/Product-to-LangGraph identity, tenant authorisation, orchestration parity, or full Phase 1 integration. Actual Phase 1 parity still requires real n8n Shadow dispatch, S2S credential bindings, authenticated Product identity, and independent evidence correlation. This harness is preparatory generation-quality evidence only. The historical baseline does not attest the provider/model, so \`corresponde\` must not be inferred from matching SQL alone.

The current MCP \`audit_shadow_evidence_draft_bindings\` is pinned to an obsolete checkout SHA and additionally requires one inactive evidence workflow, whereas the existing evidence-read workflow is active. A read-only audit of the **actual active published** Shadow workflow is needed rather than weakening this obsolete gate.

The live Gemini quality experiment must be explicitly authorized separately from any eventual read-only *financial SQL execution*. No financial query execution, n8n modifications, cutover, permissions changes, or official n8n benchmark reruns are permitted by this runbook.


## Operator correction — replay 63 QUESTIONS through LangGraph, no new Gemini calls

**Latest operator decision, 11 Nov 2026:** The n8n+Gemini path **already answered all 63 questions** and the complete historic SQL answers were recovered. Do **NOT** rerun these questions on Gemini. The work is to feed the same 63 **question-only** entries through LangGraph with the **already configured private SQL model** and compare its proposed SQL with the frozen n8n SQL *after* generation.

The previous \`run_blind_gemini_shadow_quality.py\` was the wrong operational path for this goal. It remains uninvoked and must **not** be used for the recovered 63-case replay. The correct offline preflight command is:

\`\`\`sh
cd /docker/agente-sql-langgraph-repo
RECOVERY=/root/.local/share/agente-sql-langgraph/benchmark-private/legacy63-ea0035e714f64e275b0f
WORK=/root/.local/share/agente-sql-langgraph/benchmark-private/quality-working-legacy63
.venv/bin/python -m scripts.operations.run_blind_langgraph_current_provider preflight \
  --manifest "$RECOVERY/questions-only.json" \
  --receipt "$RECOVERY/freeze-receipt.json" \
  --dispatch-plan "$WORK/dispatch-plan-v1.json" \
  --expected-cases 63
\`\`\`

The preflight **never calls any LLM or SQL**. The separately gated \`run\` action uses exactly the existing \`SHADOW_DEFAULT_LLM_SELECTION_JSON\` private model identity (currently reported by the operator as \`infodive_ibm_cloud / SQL-InfoDive\`), never switches provider, and injects \`GEMINI_API_KEY=\` into that single child process. The provider transport permits only \`openai_compatible_chat_completions\`, imposes a per-run call cap, and refuses a provider or model containing \`gemini\`.

Only original questions + unique new run IDs are sent to LangGraph. A bounded isolated worker executes its *real* Generate ASGI use case with versioned semantic context and an in-memory signed Shadow evidence repository. It does not invoke n8n, does not change the running Shadow container, and does not execute financial SQL. The *original historical SQL* stays inaccessible during generation, is loaded in the parent **after** all cases have completed, and is used solely for structural comparison.

**No phase-one n8n transport parity is established by this isolated quality replay.** The test principal is not Product authentication; tenant identity is checked against the existing configured organization scope. The historical n8n provider/model attribution remains unattested in this archive even though the operator knows it was generated by n8n+Gemini. Structural similarities are not proof of financial parity.

Live invocation remains subject to an **explicit separate approval of provider requests/costs** and requires \`BLIND_LANGGRAPH_LLM_ALLOW_LIVE=true\`, the approval phrase \`RUN-63-LANGGRAPH-PRIVATE-LLM\`, expected organization ID/provider/model, and a new private output directory. Do not infer approval from Git merge. Do not use a synthetic or guessed tenant ID, alter SQL privileges, or activate n8n workflows.
