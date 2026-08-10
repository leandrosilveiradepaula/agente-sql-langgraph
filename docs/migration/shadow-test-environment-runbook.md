# Shadow TEST Environment Runbook

This runbook prepares a controlled TEST deployment of the LangGraph shadow
service. It does not promote LangGraph to the official path.

## A. Infra

- Install dependencies from `requirements.txt`.
- Provision a PostgreSQL TEST database separated from the original product
  operational database.
- Apply the migration manually to the TEST database:

```powershell
psql "<LANGGRAPH_SHADOW_DATABASE_DSN>" -f scripts/migrations/001_create_langgraph_shadow_runs.sql
```

- Inject secrets externally through the TEST platform.
- Do not put real hosts, users, passwords, or DSNs in source control.

## B. LangGraph

Configure the TEST service:

```text
LANGGRAPH_RUNTIME_MODE=shadow_test
LANGGRAPH_HTTP_HOST=127.0.0.1
LANGGRAPH_HTTP_PORT=8000
LANGGRAPH_SHADOW_PERSISTENCE=postgres
LANGGRAPH_SHADOW_DATABASE_DSN=<secret injected externally>
LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false
```

Start the service:

```powershell
uvicorn app.test_runtime.sql_agent_test_app:create_app --factory --host %LANGGRAPH_HTTP_HOST% --port %LANGGRAPH_HTTP_PORT%
```

Use `0.0.0.0` only when a container or private network requires it. Public
exposure must be controlled by infrastructure; this internal endpoint must not
be published directly to the internet.

Validate:

- `GET /health` returns `runtime_mode=shadow_test`.
- `real_sql_execution` is `false`.
- Gemini, Watson, n8n, DuckLake, and real SQL execution remain off.

## C. Original Product

- Keep `LANGGRAPH_SHADOW_ENABLED=false`.
- Configure `LANGGRAPH_INTERNAL_BASE_URL` only with the internal TEST endpoint.
- Deploy without changing n8n, Watson, auth, policy, or UI behavior.

The browser must not call the LangGraph endpoint. The expected topology is:

```text
Original Product backend -> internal LangGraph TEST endpoint
```

Do not propagate browser cookies, browser Authorization headers, or session
tokens to LangGraph.

## D. Activation

- Enable `LANGGRAPH_SHADOW_ENABLED=true` only in TEST.
- Run one controlled generation case.
- Confirm the official n8n response remains intact.
- Confirm one or more records exist in `public.langgraph_shadow_runs`.

## E. Rollback

Set:

```text
LANGGRAPH_SHADOW_ENABLED=false
```

No n8n rollback is required.

## Production Blocker

Before production, the internal endpoint needs one of:

- private network;
- ingress allowlist;
- service identity;
- an equivalent service-to-service mechanism.

Do not implement a static API key in code for this purpose.
