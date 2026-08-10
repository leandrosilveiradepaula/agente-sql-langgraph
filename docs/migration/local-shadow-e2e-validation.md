# Local Shadow E2E Validation

This local-only validation proves the original product can dispatch LangGraph shadow requests through HTTP without promoting LangGraph to the official path.

## Topology

Original Product route tests mock the official n8n response and run the `after()` callback. The callback uses the real shadow client to send HTTP only to `127.0.0.1`, where a LangGraph local test server exposes the internal v1 handlers.

```text
Original Product test
-> mocked n8n official response
-> after()
-> real fetch to 127.0.0.1
-> LangGraph local test server
-> InternalSqlAgentV1HttpHandler
-> offline use case
-> FakeShadowEvidenceRepository
```

## Local Server

Run manually only for local validation:

```powershell
$env:LANGGRAPH_LOCAL_TEST_ONLY='1'
$env:LANGGRAPH_LOCAL_TEST_HOST='127.0.0.1'
$env:LANGGRAPH_LOCAL_TEST_PORT='8765'
python -m app.local_testing.internal_sql_agent_v1_local_server
```

The server refuses to start unless `LANGGRAPH_LOCAL_TEST_ONLY=1` is explicitly
set. The flag is not a production switch and does not relax bind restrictions:
the server still binds to localhost only. It uses:

- `FakeContextRepository`
- `FakeSqlGenerator`
- `FakeEnginePreflight`
- `FakeSqlRepairer`
- `FakeShadowEvidenceRepository`

It does not use Postgres, Gemini, Watson, n8n, DuckLake, or any SQL execution engine.

## Scenarios

- Generate shadow request reaches `/v1/internal/sql-agent/generate`.
- Execute approved shadow request reaches `/v1/internal/sql-agent/execute-approved-shadow`.
- The same product `agent_run_id` can create multiple shadow records.
- LangGraph `run_id` values remain separate from the product `agent_run_id`.
- Repair proposals require new approval and never become an approved SQL execution.
- Offline, HTTP 500, and timeout paths keep the official product response unchanged.

## Network Guard

The product E2E test allows real network only for `127.0.0.1` and `localhost`. Official n8n is mocked. Any other host fails the test.

The LangGraph standalone E2E tests also install a process-local socket guard
around the scenarios so any external host attempt fails before a real outbound
connection is opened.

## Limits

This is not a production server, not a fallback path, and not a benchmark. It is a repeatable local harness for verifying wiring and shadow persistence only.
