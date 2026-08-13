# LangGraph Shadow TEST VPS + Supabase Runbook

This runbook describes the real TEST deployment path for the LangGraph shadow
service. It is an operational plan only: do not deploy, change DNS, change
Vercel, change Hostinger, change Supabase, generate real secrets, apply real
migrations, or run real SQL from this document review step.

## 1. Target Topology

```text
Original Product on Vercel
  -> HTTPS
  -> reverse proxy on Hostinger VPS
  -> Uvicorn bound to 127.0.0.1
  -> LangGraph shadow TEST runtime
  -> Supabase SaaS PostgreSQL over TLS
```

The n8n production flow remains official and unchanged. LangGraph runs on the
same VPS only as a separate service with its own directory, virtualenv, process,
internal port, logs, and secrets.

LangGraph must not run inside n8n, as an n8n node, or in the n8n process.

## 2. VPS Layout

Recommended Linux layout:

```text
/srv/agente-sql-langgraph/current/        # checked out source release
/srv/agente-sql-langgraph/current/.venv/  # Python virtualenv
/etc/agente-sql-langgraph/shadow-test.env # non-versioned environment file
/var/log/agente-sql-langgraph/            # optional log directory if file logs are added later
```

Recommended service identity:

```text
user:  langgraph-shadow
group: langgraph-shadow
shell: /usr/sbin/nologin or equivalent
```

Keep ownership narrow:

```bash
sudo chown -R langgraph-shadow:langgraph-shadow /srv/agente-sql-langgraph
sudo install -d -o root -g langgraph-shadow -m 0750 /etc/agente-sql-langgraph
sudo install -d -o langgraph-shadow -g langgraph-shadow -m 0750 /var/log/agente-sql-langgraph
```

Do not place the service under `/root`, a random home directory, or the n8n
installation directory.

## 3. Python Runtime

Local validated runtime:

```text
CPython 3.12.13
```

Recommended VPS runtime:

```text
Python 3.12.x
```

Runtime dependencies are versioned in `requirements.txt`:

```text
langgraph==1.2.9
psycopg[binary]==3.3.4
uvicorn==0.30.6
```

Create the virtualenv from the release directory:

```bash
cd /srv/agente-sql-langgraph/current
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Do not install ad hoc runtime dependencies outside `requirements.txt`.

## 4. Environment File

Use a non-versioned system env file:

```text
/etc/agente-sql-langgraph/shadow-test.env
```

Recommended permissions:

```bash
sudo chown root:langgraph-shadow /etc/agente-sql-langgraph/shadow-test.env
sudo chmod 0640 /etc/agente-sql-langgraph/shadow-test.env
```

Required variables:

```text
LANGGRAPH_RUNTIME_MODE=shadow_test
LANGGRAPH_HTTP_HOST=127.0.0.1
LANGGRAPH_HTTP_PORT=<LANGGRAPH_INTERNAL_PORT>
LANGGRAPH_SHADOW_PERSISTENCE=postgres
LANGGRAPH_SHADOW_DATABASE_DSN=<Supabase runtime Postgres DSN; include sslmode=require>
LANGGRAPH_S2S_TOKEN=<generated outside Git and chat>
LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false
```

Optional safe version metadata:

```text
LANGGRAPH_VERSION=<release version>
LANGGRAPH_COMMIT=<git commit>
```

Classification:

| Variable | Class |
| --- | --- |
| `LANGGRAPH_RUNTIME_MODE` | CONFIG |
| `LANGGRAPH_HTTP_HOST` | CONFIG |
| `LANGGRAPH_HTTP_PORT` | CONFIG |
| `LANGGRAPH_SHADOW_PERSISTENCE` | CONFIG |
| `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION` | CONFIG |
| `LANGGRAPH_VERSION` | CONFIG |
| `LANGGRAPH_COMMIT` | CONFIG |
| `LANGGRAPH_SHADOW_DATABASE_DSN` | SECRET |
| `LANGGRAPH_S2S_TOKEN` | SECRET |

`LANGGRAPH_HTTP_HOST` should stay `127.0.0.1` when the reverse proxy runs on the
same VPS. Do not bind Uvicorn to `0.0.0.0` for this TEST deployment.

## 5. S2S Authentication

The Original Product BFF sends:

```text
Authorization: Bearer <LANGGRAPH_S2S_TOKEN>
```

LangGraph validates the Bearer secret in Python. Nginx must forward the
`Authorization` header but must not validate the token and must not store a copy
of the S2S secret.

Caller service:

```text
product_original_bff
```

Payload `principal.id`, `principal.email`, and `principal.profile` remain audit
context. They are not service identity.

Generate the future TEST secret outside Git/chat/logs with a shell command such
as:

```bash
openssl rand -hex 48
```

Hex output is compatible with the strict Bearer parser and gives 384 bits of
entropy. Store the same generated value only in Vercel TEST env and the VPS env
file.

Current rotation model supports one secret. Rotation is coordinated:

1. Put the new secret in the VPS env file.
2. Restart the LangGraph service in a planned shadow maintenance window.
3. Update the Vercel TEST secret.
4. Redeploy the Original Product TEST environment.
5. Validate negative and positive auth.

Small shadow-only interruption is acceptable in TEST. Future hardening should
add dual-secret rotation.

## 6. Startup Command

The project entrypoint is:

```text
app.test_runtime.sql_agent_test_app:create_app
```

The compatible Uvicorn command is:

```bash
.venv/bin/python -m uvicorn app.test_runtime.sql_agent_test_app:create_app --factory --host "${LANGGRAPH_HTTP_HOST}" --port "${LANGGRAPH_HTTP_PORT}"
```

For initial TEST, use one Uvicorn worker. This is enough for controlled shadow
validation and avoids introducing a process manager stack beyond systemd.

## 7. systemd

Recommended process manager: systemd.

Versioned template:

```text
deploy/systemd/agente-sql-langgraph-shadow-test.service.example
```

Future install procedure:

```bash
sudo cp deploy/systemd/agente-sql-langgraph-shadow-test.service.example /etc/systemd/system/agente-sql-langgraph-shadow-test.service
sudo systemctl daemon-reload
sudo systemctl enable agente-sql-langgraph-shadow-test
sudo systemctl start agente-sql-langgraph-shadow-test
sudo systemctl status agente-sql-langgraph-shadow-test
```

Use logs without printing environment variables:

```bash
sudo journalctl -u agente-sql-langgraph-shadow-test -n 100 --no-pager
```

Do not use commands that dump service environment values.

## 8. Reverse Proxy and HTTPS

Recommended reverse proxy for this VPS plan: Nginx, unless VPS discovery proves
the existing n8n stack uses another proxy that should be preserved.

Versioned template:

```text
deploy/nginx/langgraph-shadow-test.conf.example
```

External HTTP must redirect to HTTPS. External plain HTTP must not expose the
internal API. TLS terminates at the reverse proxy.

Recommended hostname:

```text
langgraph-test.<owned-domain>
```

Do not assume or reuse the n8n hostname. A dedicated hostname reduces routing
risk.

The Nginx route should:

- proxy the dedicated hostname to `http://127.0.0.1:<LANGGRAPH_INTERNAL_PORT>`;
- preserve `Host`, `X-Forwarded-For`, `X-Forwarded-Proto`, and request ID;
- forward `Authorization`;
- avoid forwarding browser cookies from Vercel because the BFF client does not
  send them;
- keep `client_max_body_size 1m`;
- use conservative timeouts: connect `2s`, send/read `5s`.

The Original Product defaults to a short shadow timeout. The proxy timeout must
not be lower than the BFF timeout, but should also avoid long-running public
requests.

Optional TEST rate limiting can be added at Nginx after the first validation.
It is not a replacement for S2S auth and is not required for the first smoke.

## 9. Firewall

Recommended future firewall posture:

- SSH follows the existing VPS management policy.
- Ports `80` and `443` are open only as required for TLS setup and HTTPS.
- The Uvicorn port is not public.
- No local Postgres port is needed.
- Existing n8n ports and routes are not changed without backup and discovery.

Do not execute firewall changes during this microstep.

## 10. Supabase Architecture

LangGraph connects directly from the VPS to Supabase PostgreSQL over TLS:

```text
VPS LangGraph -> internet/TLS -> Supabase PostgreSQL
```

The connection does not pass through the Original Product and does not pass
through n8n. Do not use a Supabase browser/public key. Use a server-side
Postgres connection string stored only in the VPS env file.

Connection mode is not decided by the repo. During deploy, confirm whether the
Supabase project should use direct Postgres or a Supabase pooler endpoint:

```text
SUPABASE CONNECTION MODE TO CONFIRM DURING DEPLOY
```

The DSN should require TLS, typically with:

```text
sslmode=require
```

The code uses `psycopg.connect(...)`, so TLS mode is controlled by the DSN.

## 11. Supabase Roles

Use separate credentials:

- migration credential: may have DDL permission for the migration;
- runtime credential: least privilege for the running service.

The runtime repository currently requires:

- `SELECT` on `public.langgraph_shadow_runs`;
- `INSERT` on `public.langgraph_shadow_runs`;
- `UPDATE` on `public.langgraph_shadow_runs`.

`DELETE` is not required by the runtime.

The migration credential applies `scripts/migrations/001_create_langgraph_shadow_runs.sql`.
That migration uses `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`.
It is idempotent for initial object creation, but it is not a schema drift
repair tool.

## 12. Migration Procedure

Future manual migration order:

1. Open the Supabase SQL editor or a trusted admin SQL client.
2. Use the migration credential, not the runtime credential.
3. Review `scripts/migrations/001_create_langgraph_shadow_runs.sql`.
4. Apply the migration once.
5. Re-run only if the target schema is known to be compatible.
6. Confirm table, columns, primary key, checks, and indexes.

Do not execute this migration from this runbook review step.

Safe metadata validation SQL for future use:

```sql
select to_regclass('public.langgraph_shadow_runs') as table_ref;

select column_name, data_type, is_nullable
from information_schema.columns
where table_schema = 'public'
  and table_name = 'langgraph_shadow_runs'
order by ordinal_position;

select indexname, indexdef
from pg_indexes
where schemaname = 'public'
  and tablename = 'langgraph_shadow_runs'
order by indexname;

select conname, contype
from pg_constraint
where conrelid = 'public.langgraph_shadow_runs'::regclass
order by conname;
```

Future runtime permission validation:

- connect with the runtime DSN;
- confirm metadata `SELECT` works;
- confirm controlled synthetic `INSERT` and `UPDATE` work;
- confirm unnecessary `DELETE` is denied, if feasible;
- use synthetic data only.

## 13. Vercel TEST Configuration

The Original Product needs these server-side env vars in the chosen TEST Vercel
environment:

```text
LANGGRAPH_INTERNAL_BASE_URL=https://<LANGGRAPH_TEST_HOSTNAME>
LANGGRAPH_S2S_TOKEN=<same TEST secret as VPS>
LANGGRAPH_SHADOW_ENABLED=true
LANGGRAPH_SHADOW_TIMEOUT_MS=1500
```

`LANGGRAPH_INTERNAL_BASE_URL` should be the HTTPS reverse proxy URL, not the
Uvicorn localhost URL. The client trims trailing slashes, but use no trailing
slash for clarity.

No variable should use `NEXT_PUBLIC_`. The browser must not receive the S2S
credential.

Vercel environment choice remains an operator decision:

```text
VERCEL TEST ENVIRONMENT TO CONFIRM: Preview or Production-backed TEST.
```

Configure Vercel only after Python, HTTPS, negative auth, positive auth, and
Supabase persistence pass independently.

## 14. Validation Flow

Local health on the VPS:

```bash
curl --fail http://127.0.0.1:<LANGGRAPH_INTERNAL_PORT>/health
```

External health:

```bash
curl --fail https://<LANGGRAPH_TEST_HOSTNAME>/health
```

Negative auth examples:

```bash
curl -i -X POST https://<LANGGRAPH_TEST_HOSTNAME>/v1/internal/sql-agent/generate \
  -H 'Content-Type: application/json' \
  --data '<synthetic-json-payload>'

curl -i -X POST https://<LANGGRAPH_TEST_HOSTNAME>/v1/internal/sql-agent/generate \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer test-wrong-token' \
  --data '<synthetic-json-payload>'

curl -i https://<LANGGRAPH_TEST_HOSTNAME>/v1/internal/agent-runs/<synthetic-agent-run-id>/shadow-runs
```

Expected result: `401` with safe S2S error for internal endpoints.

Positive auth without echoing the token:

```bash
set +o history
read -r -s LANGGRAPH_S2S_TOKEN
export LANGGRAPH_S2S_TOKEN
set -o history

curl --fail -X POST https://<LANGGRAPH_TEST_HOSTNAME>/v1/internal/sql-agent/generate \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${LANGGRAPH_S2S_TOKEN}" \
  --data '<synthetic-json-payload>'
```

Use synthetic payloads first. Keep:

```text
LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false
```

Gemini, Watson, n8n, DuckLake, and real SQL remain out of the first remote smoke.

Persistence validation:

1. Send authenticated synthetic generate.
2. Confirm one shadow record in Supabase using metadata-safe queries.
3. Call `GET /v1/internal/agent-runs/{agent_run_id}/shadow-runs`.
4. Call `GET /v1/internal/shadow-runs/{shadow_record_id}/visualization`.
5. Confirm IDs correlate and no real SQL was executed.

## 15. Failure Isolation

After Vercel TEST is configured:

- LangGraph online: official n8n response remains normal and shadow persists.
- LangGraph offline: official n8n response remains normal and shadow dispatch
  fails isolated.
- Wrong S2S token: official n8n response remains normal and shadow fails
  isolated.
- Admin UI with LangGraph offline: official run detail opens and shadow panel
  reports unavailable.

## 16. n8n Protection

Do not alter n8n for this deploy. Before changing reverse proxy configuration
for LangGraph, take a backup of the current proxy config and identify:

- how n8n runs;
- whether it uses systemd, Docker, or another supervisor;
- its hostname;
- its internal port;
- its TLS route;
- its current reverse proxy owner.

LangGraph must use a separate internal port and must not break n8n routing.

## 17. Capacity Checklist

Future read-only VPS checks before deploy:

```bash
uname -a
cat /etc/os-release
python3 --version
free -h
df -h
ss -ltnp
systemctl --type=service --state=running
nginx -v
caddy version
docker version
```

It is acceptable for some commands to be unavailable; record what exists.

Check CPU, RAM, disk, Python availability, listening ports, current reverse
proxy, current n8n service, and whether a safe internal port is free.

## 18. Rollback

TEST rollback order:

1. Set `LANGGRAPH_SHADOW_ENABLED=false` in Vercel TEST.
2. Redeploy the Original Product TEST environment.
3. Stop LangGraph service:
   `sudo systemctl stop agente-sql-langgraph-shadow-test`.
4. Disable LangGraph service if needed:
   `sudo systemctl disable agente-sql-langgraph-shadow-test`.
5. Revert the LangGraph reverse proxy config from the backup.
6. Keep Supabase evidence/table intact by default.
7. Do not touch n8n.

Database rollback requires explicit review. Do not invent or run `DROP TABLE`
as default rollback.

## 19. Deploy Order

1. Audit VPS.
2. Confirm reverse proxy.
3. Confirm hostname/DNS.
4. Prepare Supabase role and DSN.
5. Apply migration.
6. Install LangGraph source.
7. Create env file.
8. Create systemd service.
9. Start only on localhost.
10. Test localhost health.
11. Configure reverse proxy.
12. Configure HTTPS.
13. Test external health.
14. Test negative auth.
15. Test positive synthetic auth.
16. Validate Supabase persistence.
17. Configure Vercel TEST.
18. Redeploy Original Product TEST.
19. Test end-to-end dispatch.
20. Test Read API and admin UI.
21. Test failure isolation.
22. Register result.

## 20. GO / NO-GO Gates

GO GATE A - VPS:

- resources sufficient;
- current proxy identified;
- n8n topology understood;
- internal port free.

GO GATE B - DB:

- migration applied;
- table and indexes validated;
- runtime credential has minimum required permissions.

GO GATE C - Python local:

- systemd starts;
- health OK on localhost;
- negative auth OK;
- positive synthetic auth OK.

GO GATE D - HTTPS:

- certificate valid;
- Uvicorn not public;
- reverse proxy forwards `Authorization`;
- external health OK.

GO GATE E - Vercel:

- server-side secret configured;
- base URL points to HTTPS hostname;
- dispatch works;
- n8n official path unaffected.

GO GATE F - UI:

- shadow read works;
- visualization works;
- failure isolation works.

If any gate fails, stop and fix before moving forward.

## 21. Production Separation

This TEST runbook is not production-ready. Production still needs:

- final service identity decision stronger than single static Bearer;
- ingress hardening;
- operational TLS review;
- rate limiting;
- replay protection;
- migration rollback design;
- runtime/worker process design;
- monitoring and alerting;
- backup and disaster recovery review.
