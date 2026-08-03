# Pre-Live Readiness Baseline

Date: 2026-08-03

Branch: `feat/pre-live-readiness`

Base commit: `6b3cfaaa6c08c0be968bf0ed67a53ce4a9f21ad3`

## Architecture

The local graph loads a versioned context snapshot, resolves one intent,
builds a deterministic query plan, generates SQL through an injected
generator, validates security and contract gates, performs engine preflight
through an injected port, executes controlled SQL through an injected executor,
normalizes and serializes results, finalizes the run, and emits a public
`ApplicationResponse`.

## Watson TEST

Watson TEST is isolated in a composition root that accepts only
`DeploymentEnvironment.TEST`. Live adapters are explicit dependencies and are
not defaults. The dry-run path does not require API key, does not query
secrets, and does not access network.

Watson payload remains limited to one logical key: `sql_query`. No `limit`
field is added by this phase.

## Checks

- `scripts/check_imports.py`
- `scripts/check_no_network.py`
- `scripts/check_workspace_hygiene.py`
- `scripts/check_dependencies.py`
- `scripts/offline_watson_failure_rehearsal.py`
- `scripts/check_all.py`
- `scripts/check_clean_room.py`, executed separately to avoid recursion
- `scripts/check_hardcodes.py`
- `scripts/check_secrets.py`

## Main Tests

- Watson TEST probe, composition, graph, and offline runner tests
- Watson live adapter contract tests with fakes
- HTTP, ASGI, auth, application service, graph, and bootstrap regressions
- Clean-room, network guard, import, workspace hygiene, dependency, CI, CMD,
  and failure rehearsal tests

## Sanitization Contracts

Public contracts must not expose API key, token, Authorization, raw output,
`sql_transport`, provider body, complete SQL outside validated data, GraphState,
or live configuration values.

## Known Risks

- The first live probe is blocked until a new API key is available.
- The first live execution may expose provider contract drift.
- A successful TEST probe is not a PROD promotion signal.
- Manual operator mistakes remain possible if the parent CMD session is not
  cleaned after live use.

## First Probe Criteria

- Working tree clean.
- Offline CI and local checks pass.
- New API key available only in the operator CMD session.
- One attempt only.
- No rows preview on the first live execution.
- No retry, cache, backoff, ASGI live entrypoint, n8n change, or PROD change.

## Success Criteria

- The launcher exits successfully.
- Public output remains sanitized.
- No raw provider payload is persisted.
- Evidence contains only exit code, sanitized status, hashes, and timestamps.

## Stop Criteria

- Missing or invalid configuration.
- Authentication failure.
- Timeout, rate limit, DNS, TLS, invalid JSON, invalid contract, or unexpected
  provider response.
- Any evidence of raw output, token, Authorization, or complete environment
  leakage.

## Do Not Promote To PROD When

- The TEST probe has not completed once successfully.
- Any offline checker fails.
- The provider response requires contract changes.
- There is any manual retry, cache, backoff, or emergency workaround.
