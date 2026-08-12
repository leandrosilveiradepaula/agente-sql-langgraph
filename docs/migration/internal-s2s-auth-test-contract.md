# Internal S2S Auth TEST Contract

## Purpose

This contract protects the LangGraph internal TEST endpoints called by the
Original Product BFF. It authenticates the caller service, not the browser and
not the final user.

Caller service:

```text
product_original_bff
```

## Bearer Secret

TEST uses:

```text
Authorization: Bearer <test-s2s-secret>
```

The secret name is:

```text
LANGGRAPH_S2S_TOKEN
```

The value must be injected by the runtime platform. It must not be versioned,
logged, placed in a URL, placed in a query string, included in payloads, or
returned in responses.

## Protected Endpoints

S2S Bearer is required for:

- `POST /v1/internal/sql-agent/generate`
- `POST /v1/internal/sql-agent/execute-approved-shadow`
- `GET /v1/internal/shadow-runs/{shadow_record_id}`
- `GET /v1/internal/agent-runs/{agent_run_id}/shadow-runs`
- `GET /v1/internal/shadow-runs/{shadow_record_id}/visualization`

Unauthenticated or malformed requests return `401` with a safe
`UNAUTHORIZED_SERVICE` code and `WWW-Authenticate: Bearer`.

## Health

`GET /health` remains public for TEST liveness and returns only minimal status.
It must not include token, DSN, SQL, provider configuration, credentials, or
headers.

## Principal Context

Payload `principal.id`, `principal.email`, and `principal.profile` remain audit
context supplied by the authenticated BFF. They are not caller authentication.

## Header Parsing

The boundary accepts only a single strict `Authorization: Bearer <credential>`
header. Missing, empty, lowercase scheme, malformed, duplicated, and oversized
Authorization headers are rejected. Cookie does not authenticate the caller.

## Secret Verification

The Python boundary compares credentials with standard-library constant-time
comparison. The configured token is kept out of dataclass repr, health,
observability, errors, and logs.

## Deployment Notes

Real TEST deployment still needs HTTPS plus reverse proxy or managed ingress in
front of Uvicorn. Production should evolve toward platform/workload identity or
a managed gateway identity rather than relying on a static Bearer secret alone.
