# Review G5/P3 via existing Product BFF — disabled-by-default contract

**Phase: code contract tested, NOT deployed or exposed.** This is not another
application or an alternative authentication system. Next.js remains responsible
for login, RBAC, session policies, approval history and auditing; LangGraph
retains versioned financial semantics and read/commit validation. n8n remains
the operational orchestrator and official SQL engine during Shadow.

## Why this boundary exists

The original G5 corpus contains 77 source rows, and P3 has 137 physical metadata
rows covering 48 source references. The owner holds final project authority.
The private TTY works on the VPS, but the assistant's safe audited VPS connector
cannot supply /dev/tty input. The contract below creates a path for an
authenticated Product page to display source context and submit **explicit**
owner decisions without requiring an SSH session.

## Implemented and tested in LangGraph

`scripts/operations/g5_owner_review_http_contract.py` is a pure, unmounted
Python handler: no server bind, socket, DNS, deployment or port is created.
The `ReviewConfig.enabled` flag defaults to **False**; when false, all
operations return a safe 404 without opening the private G5 packet.

An eventual Product-only BFF adapter must enforce the existing logged-in
`admin` profile, tenant authorization, session validity, CSRF and rate limits,
and use a **dedicated G5 review bearer token** (NOT reuse general shadow
evidence credentials). The backend separately requires explicit tenant
identity and role headers, a tenant-pinned private packet config, token of
at least 32 characters, disallows cookies and direct browser Origin, and
never accepts a caller-selected filesystem path, database, SQL or LLM prompt.
Untrusted users and other tenants receive **no source data**.

The handler contract (BFF translates GET query parameters to validated body
parameters; it does NOT allow raw GET bodies):

| Method/path | Behavior |
|---|---|
| GET `/v1/internal/g5-owner-review/status` | Counts only, G5/P3 fingerprints, revision; no source content |
| GET `/v1/internal/g5-owner-review/item` | One source record or P3 physical choices, only for authorized admin |
| POST `/v1/internal/g5-owner-review/decision` | Explicit classification/destinations or physical schema, column, rationale; never approves/activates |

Every read validates sealed G5/P3, 0600/0700 ownership and workbook provenance.
Every mutation uses an exclusive local lock (shared with the TTY), checks an
optimistic SHA-256 state revision, rejects unknown values/changed source,
writes a private **two-phase audit journal** (prepare / atomic session /
commit) and fsyncs before success. On interrupted audit, stale session or
torn update, it fails closed until an operator reconciles the private state.
Audit contains actor ID, kind/index, timestamp and state hashes, not source
content or token. All responses have no-store, nosniff and anti-framing
headers; errors intentionally contain no financial values.

**No approvals:** `accounting_approved=false`,
`context_activated=false`, `sql_executed=false` remain invariant.
The API never emits a financial signature, creates a canonical business
mapping or runs SQL. It only records choices to the existing private,
version-pinned review worksheet. The external independent HMAC approval
gate remains distinct and requires explicit action.

## Missing deployment/acceptance gates

1. Add a Product admin page and BFF route with existing auth/CSRF/tenant/
   audit policy. Do not fetch source content for unauthenticated or
   unauthorized viewers; never use public client-side credentials.
2. Implement an internal HTTP transport adapter for this pure handler with
   dedicated S2S auth and strict network origin, response size and request
   size limits, behind the existing private gateway. Do not mount it on
   the existing SQL/shadow token alone.
3. Confirm restricted private snapshot access, audit durability and recovery
   from half-committed event, then explicit operator authorization to
   enable the separate feature. There is no deployment authorization here.
4. The owner must still review financial meaning and table/column bindings
   against the **real source**. Product cannot approve by guess or auto-fill.
5. Only after signed financial context and second distinct real tenant,
   run novel questions and audited Shadow parity. Any financial SELECT-only
   execution requires a separate human authorization.

## Evidence so far

Nine synthetic tests exercise feature default-off, authorization, tenant
isolation, raw item visibility only to a tokenized admin, private physical
rationale, optimistic conflicts, durable audit, corruption fail-closed and
no SQL/activation. These tests are integrated into Offline validation; they
do **not** prove the Product BFF integration or actual deployed access.

OFFICIAL=n8n+Gemini; SHADOW=n8n+LangGraph+Gemini;
`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.
