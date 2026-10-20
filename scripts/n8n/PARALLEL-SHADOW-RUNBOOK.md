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
- Check the LangGraph response, fetch persisted Shadow evidence, and verify
  exact \`agent_run_id\`, \`run_id\`, status, event type and a unique
  \`shadow_record_id\` without returning SQL, tokens or provider raw output.
- Disable n8n execution-data persistence on success, error and manual runs.
  LangGraph persists the correlated sanitized Shadow evidence separately.

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
2. In a separate authorized n8n deployment, import the candidate as a
   **NEW** workflow. Never replace, publish over, or edit the 68-node
   OFFICIAL financial workflow.
3. Attach a distinct **Webhook Header Auth** credential to
   \`Webhook - Parallel Shadow\` with header \`X-Agent-Shadow-Token\`.
   Create the corresponding secret in the Product backend as
   \`N8N_SHADOW_WEBHOOK_TOKEN\`, not in JSON/Git.
4. Attach a separate **HTTP Header Auth** credential to **both**
   \`Call LangGraph Shadow\` and \`Read Correlated Evidence\` with
   \`Authorization: Bearer <LANGGRAPH_S2S_TOKEN>\`.
5. Set \`LANGGRAPH_SHADOW_INTERNAL_BASE_URL\` in the authorized n8n
   environment to the LangGraph Shadow service base address reachable
   from the n8n container, without a trailing path. Ensure n8n permits
   access to this specific environment variable in node expressions;
   failure to resolve is a stop, not a reason to hardcode a host/token.
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
