# Private n8n Shadow evidence read relay — inactive candidate

Supplies an authenticated Product -> n8n -> private LangGraph read-only
channel without exposing LangGraph directly to public internet.
Separate from both the 68-node official workflow and the seven-node Shadow generator.

## Contract

- POST /webhook/langgraph-shadow-evidence-v1, protected with a dedicated n8n Header Auth
  credential named X-Agent-Shadow-Evidence-Token. Its secret must be NEW and
  not reused from generation's previously exposed Webhook credential.
- Request: contract_version=1, request_id, operation=list|detail|visualization,
  with agent_run_id and integer limit 1..50 for list, shadow_record_id for detail/visualization.
- Inbound arbitrary target_path, URL, SQL, question or other keys are rejected.
- Only n8n -> LangGraph uses Authorization: Bearer and the existing separate S2S token.
- Only safe run IDs, status, dates, flags, bounded numeric graph metadata
  and graph topology are forwarded. No SQL, prompts, raw responses, diagnostics or secrets.
- Product MUST enforce its own session, profile and run ownership before calling
  this privileged backend-only relay. The relay cannot authenticate individual tenants.

## Safety / deployment

Template is INACTIVE and without credentials, pinned data or execution-history
persistence. The generated workflow must use a private destination and GET-only
LangGraph endpoint. No global n8n $env access is required.

Run: python3 testar_n8n_shadow_evidence_read_workflow.py
Render privately: python3 scripts/n8n/render_shadow_evidence_read_workflow.py
  --internal-base-url http://YOUR_PRIVATE_DOCKER_SERVICE:8000
  --output /tmp/YOUR_NEW_UNIQUE_PRIVATE_FILE.json

Import, credential setup, publication, Vercel environment configuration and
connection testing require separate explicit operator approval. Do not alter
the official n8n or the existing Shadow generation workflow.

An HTTP 200 safe read response confirms retrieval only; it does not prove SQL
parity, LLM provider equivalence or financial results.
