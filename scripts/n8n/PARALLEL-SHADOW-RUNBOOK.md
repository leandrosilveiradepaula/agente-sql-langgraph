# Parallel n8n -> LangGraph Shadow (candidate, not deployed)

This is the **new parallel orchestration candidate** for the real finance
workflow confirmed by the operator on 2026-10-20 (separate 68-node production
workflow). See `docs/audits/n8n-operator-confirmed-official-2026-10-20.md`
for its exact SHA-256, scope, audit findings and open gates.
It is NOT the old 6-node manually triggered correlation fixture.
The real n8n + Gemini workflow remains **OFFICIAL**, unchanged.

## What is built

- A distinct, inactive, Header Auth-protected POST webhook:
  \`/webhook/langgraph-shadow-parallel-v1\`.
- Validate the Product/BFF v1 request envelope and correlation fields.
- Respond HTTP **202** with a small JSON acknowledgement before any LLM or
  database activity; n8n continues after the Respond node.
- Forward only the allowed event to LangGraph:
  \`generate\` or \`execute_approved\`. All SQL intelligence, prompt selection,
  metrics, filters, joins, dialect interpretation and repair stay in LangGraph
  and its versioned tenant context, never in n8n.
- For `generate` only, preserve optional versioned
  `llm_selection` (`provider_key`, `model_key`, `config_version`) as an
  opaque field. Malformed or extra fields fail closed; the workflow never
  chooses a model or silently changes the selection. The LangGraph registry
  must authorize the selection and attest the actual generator identity.
  Phase 1 parity requires Gemini on both paths, not merely HTTP 202.
- The evidence read now specifies the **exact returned `run_id`**:
  `GET /v1/internal/agent-runs/{agent_run_id}/shadow-runs?run_id={run_id}&limit=10`.
  The server filters by run ID and authorized tenant **before** applying
  the presentation limit; an older set of 10+ retries therefore cannot
  hide the accepted attempt. Unknown, duplicate or malformed `run_id`
  parameters fail safely. Inactive workflows imported before this candidate
  are **not** updated automatically; they must remain inactive until a
  separately authorized, reviewed replacement/import.
- Check the LangGraph response, fetch persisted Shadow evidence, and verify
  exact \`agent_run_id\`, \`run_id\`, status, event type and a unique
  \`shadow_record_id\` without returning SQL, tokens or provider raw output.
- Disable n8n execution-data persistence on success, error and manual runs.
  LangGraph persists the correlated sanitized Shadow evidence separately.
- Forward the **optional** authenticated Product `principal.organization_id` as
  an opaque bounded identifier without defaulting, rewriting or inferring it
  from question/SQL. Reject malformed supplied IDs rather than stripping them.
  The currently deployed Demo session has no authoritative organization ID;
  this is forward-compatible transport only. Do **not** activate the
  LangGraph expected-organization scope until Product/BFF identity,
  n8n credential ownership and tenant-scoped deployment have been proved.
- Reconcile LangGraph's **HTTP 503 / `infrastructure_error`** as a terminal
  result only when `agent_run_id`, `run_id`, contract, event type, status
  and a single persisted evidence record correlate exactly. A generic
  503, 500, malformed/truncated response or missing evidence still fails
  closed. This is failure observability, **not** success or SQL parity.

**202 means n8n accepted the request, NOT successful SQL generation or proven
equivalence.** The evidence check runs afterwards. The comparison evaluator
must consume stored official and Shadow records after generation, not append
expected answers/SQL or benchmarks to the LangGraph request.

## Wiring / deploy gates (NOT performed by adding this file to GitHub)

1. Review the workflow and run
   `python3 testar_n8n_parallel_shadow_workflow.py` offline. It compiles all
   Code nodes and executes **synthetic** generate, approved-SQL relay,
   malformed request, mismatched-ID and duplicate-evidence scenarios with
   n8n expressions evaluated in a Node.js sandbox (no HTTP, LLM or SQL).
   The test is also wired into the repository-wide offline CI.
2. In a separate authorized n8n deployment, import the **rendered**
   candidate as a NEW, **inactive** workflow using n8n's
   `import:workflow --input=<private-file>` command and verified
   workflow ownership/project. Never replace, publish over, or edit
   the 68-node official financial workflow. Verify the imported workflow
   has a distinct ID, no credentials bound by the JSON and inactive status.
   Import permission does not authorize activation.
3. Attach a distinct **Webhook Header Auth** credential to
   \`Webhook - Parallel Shadow\` with header \`X-Agent-Shadow-Token\`.
   Create the corresponding secret in the Product backend as
   \`N8N_SHADOW_WEBHOOK_TOKEN\`, not in JSON/Git.
4. Attach a separate **HTTP Header Auth** credential to **both**
   \`Call LangGraph Shadow\` and \`Read Correlated Evidence\` with
   \`Authorization: Bearer <LANGGRAPH_S2S_TOKEN>\`.
5. **Preferred for n8n 2.x:** prepare a private, inactive workflow
   JSON with the trusted internal URL substituted at import time. This
   avoids `$env` expressions and **does not require** configuring
   `LANGGRAPH_SHADOW_INTERNAL_BASE_URL` inside n8n or weakening
   `N8N_BLOCK_ENV_ACCESS_IN_NODE`. From the up-to-date LangGraph repo,
   after an explicitly authorized preparation:
   ```bash
   python3 scripts/n8n/render_parallel_shadow_workflow.py --check-template
   python3 scripts/n8n/render_parallel_shadow_workflow.py \\
     --internal-base-url 'http://<private-docker-service-name>:8000' \\
     --output /tmp/parallel-shadow-inactive-private.json
   ```
   Supply the actual private service DNS verified from the n8n container.
   The renderer rejects public destinations, embedded credentials, URL
   paths/query/fragment and unexpected template changes. Only the two
   HTTP Request URL expressions are rendered; the workflow stays inactive,
   without an ID or attached credentials. The generated file is 0600,
   must remain private and is never committed to Git. Import or activation
   requires **separate operator authorization**. The trusted internal URL
   is structural deployment configuration, not a business hardcode.

   Read-only prerequisite audit:
   ```bash
   bash scripts/n8n/probe_parallel_shadow_prerequisites_readonly.sh
   ```
   **Never turn off n8n's global environment isolation just to enable
   this Shadow workflow.** The renderer does not authorize the new
   workflow's import, credential assignment, webhook publication or
   SQL/LLM calls.
6. Confirm **SHADOW model is Gemini** for apples-to-apples comparison
   with the official n8n Gemini path. The workflow does NOT select an
   LLM; LangGraph's authorized provider config does.
7. Before any live call, verify Shadow runtime
   \`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false\`; verify no SQL/data
   execution permissions, tenant context and approved credentials. Also
   verify n8n S2S auth and private routing. These are runtime gates,
   not claims established by the JSON.
8. Keep the Product flag \`LANGGRAPH_SHADOW_ENABLED=false\` until the
   new webhook, credential, model and isolation are verified and
   activation is explicitly approved.
9. When authorized, switch the **Product backend** to n8n transport:
   \`LANGGRAPH_SHADOW_TRANSPORT=n8n\`;
   \`LANGGRAPH_SHADOW_N8N_WEBHOOK_URL=https://<your-n8n>/webhook/langgraph-shadow-parallel-v1\`;
   \`N8N_SHADOW_WEBHOOK_TOKEN\` from a secret store;
   \`LANGGRAPH_SHADOW_ENABLED=true\`. No Next.js browser secrets.
10. Correlate the same question and authorized principal across the
    official product run and Shadow evidence; examine the SQL meaning
    separately from the renderer. No real financial result equivalence
    until a separate read-only execution authorization is granted.

The \`execute_approved\` path is **evidence-only**: it relays the
previously approved SQL from the Product after the official execution
path, but the LangGraph Shadow must not execute or silently approve it.
Any repaired SQL needs a fresh approval; this workflow cannot call an
execute SQL endpoint. Turn off the flag immediately to stop future
Shadow dispatch (rollback). The current six-node manual test fixture
continues to serve solely as a pre-LLM correlation test.

The current contract lacks a trusted tenant identifier in the BFF
payload; do not claim multiclient isolation until tenant identity,
context authorization and tests are implemented and verified.

## Imported-workflow credential audit (read-only; no publication)

After the operator has **saved** credential assignments on the seven-node
workflow, run this on the authorized n8n Docker host, with the real imported
workflow ID (never the 68-node official ID):

```bash
cd /docker/agente-sql-langgraph-repo
bash scripts/n8n/audit_parallel_shadow_bindings_readonly.sh \
  --workflow-id LwUsMRWi34D2ARWu1YzgV
```

The audit uses n8n's **draft** `export:workflow --id` only to inspect the
*inactive candidate*; it does **not** use `--published` and is **not** the
official-workflow audit. The raw export, which may contain node parameters
and credential reference names, stays in private ephemeral files, is deleted
before reporting success, and must **never** be shared or committed.

A `G1_BINDINGS=PASS` confirms: seven expected nodes and topology, private
rendered LangGraph URL without n8n `$env` access, inactive state, disabled
execution-data storage, Webhook Header Auth binding, separate LangGraph
Header Auth binding shared by both HTTP nodes, and no functional drift from the reviewed
workflow. n8n-generated node IDs must be unique and well formed but need
not equal the portable template IDs. n8n 2.x may omit the default `GET`
method on **Read Correlated Evidence**: only that one missing field is
interpreted as `GET`; an explicit non-GET method or any other parameter
change is rejected. Only fixed status labels are printed. A rejection is **not**
authorization to reimport, activate, weaken security or overwrite credentials.

**This audit does not read/decrypt secrets, validate credential values, make
authenticated calls, execute SQL/LLM, publish the workflow, or prove
correlation/parity.** Credential references can be attached but invalid.
After `PASS`, separately run the existing GET-only network/auth-denial probe:

```bash
bash scripts/probe_n8n_shadow_network_readonly.sh
```

Keep `LANGGRAPH_SHADOW_ENABLED=false` and the workflow unpublished.
A real authenticated request and persisted evidence correlation require a
separately authorized, controlled activation/test window. Never infer G1
completion from credential bindings, network health or HTTP 202 alone.

## Integrated offline contract rehearsal

Before any new authorized activation of the separate seven-node workflow:

```bash
python testar_n8n_langgraph_offline_bridge.py
```

Unlike tests of isolated JSON fixtures, this executes the actual n8n
Code-node JavaScript against a structurally valid Product-like v1 envelope,
then sends its forwarded request into the real S2S-protected LangGraph ASGI
routing and checks the persisted in-memory evidence through the exact
`run_id` reader. It covers generation and approved-SQL Shadow events,
thirteen older attempts and mismatched organization identity, without
an LLM or a financial database. This rehearsal does **not** activate
anything or prove the official Next.js `after()` delivery lifecycle.
The real deployment still requires G1 correlation between the Product
official receipt, the deployed n8n workflow and stored LangGraph evidence.


## G1 real-PostgreSQL integrated rehearsal (CI only)

The additional step in `.github/workflows/shadow-evidence-integrity-postgres.yml`
now runs `scripts/validation/test_n8n_langgraph_shadow_bridge_postgres.py`
against the workflow's **actual n8n Code-node JavaScript**, the actual
S2S-protected LangGraph ASGI HTTP router, the existing PostgreSQL 16
`langgraph_shadow_runs` schema and the genuine PostgreSQL evidence
repository. It checks exact returned `run_id`, both separate event types,
thirteen older attempts, evidence signatures, tenant-bound SQL reads,
foreign-tenant denial and post-generation comparison. The official SQL
is never supplied to the generator, and the comparison uses only a
synthetic self-consistency input.

The script has the same GitHub Actions + loopback-only + synthetic DB
environment guard as the already approved G4 disposable PostgreSQL test.
No runtime credentials, real Gemini calls, financial SQL execution,
Vercel deployment or n8n activation. This is a stronger **offline** G1
integration proof, **not** the missing Product official run receipt ↔
live n8n webhook ↔ live persisted LangGraph evidence correlation.
