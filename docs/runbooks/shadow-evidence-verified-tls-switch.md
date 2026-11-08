# Shadow TEST evidence persistence: verified TLS switch

This procedure is only for an authorized TEST evidence DSN change. It never updates n8n, the Product, context tables, financial data, or the official route.

## Root cause

The context connection can be healthy with an older TLS mode. Requiring the context connection itself to use verify-full blocked an independently secured evidence connection. The new tool creates a separate evidence URI with strict TLS, validates login and tenant isolation from VPS and container, and only then permits updating the runtime.

## Preconditions

An operator-authorized tenant-bound restricted Postgres LOGIN exists with SCRAM password saved locally in a root-only 0600 file. The Shadow container runs with LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. Existing Compose image equals deployed image.

## Operation

Default invocation runs read-only and rollback-only synthetic evidence checks, without changing the environment. Run the tool with approved project ref, Product organization ID, login-role name, password-file path, deployment directory, container name, and Compose service name.

A successful preflight prints RESTRICTED_LOGIN=PASS, TENANT_RLS_SMOKE=PASS_ROLLBACK_ONLY and TLS_VERIFY_FULL=PASS_ON_HOST_AND_CONTAINER. Only then, with existing authorization, repeat with --apply to back up the environment and recreate the single Shadow service using the existing image.

The tool preserves the context DSN and blocks attempts to change an existing tenant pin. It never downgrades SSL verification. The status CORRELATED_EVIDENCE_READ=PASS proves that the authenticated evidence API can read from the new repository. It does not establish end-to-end generation or financial parity.

On failure after the environment was changed, it restores the original secret-containing environment and attempts recreation of the original Shadow TEST service. Inspect ROLLBACK status, do not assume restoration from a Compose exit code alone. Never paste secrets into chat.
