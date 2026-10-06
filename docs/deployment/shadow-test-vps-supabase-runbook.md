# LangGraph Shadow TEST Docker + Traefik Runbook

This runbook adapts the LangGraph shadow TEST deployment to the real Hostinger
VPS discovery from Microetapa 5.8. It is still a preparation artifact only: do
not deploy, change DNS, change Vercel, change Supabase, create real secrets,
run migrations, restart services, or alter existing containers from this step.

## 1. Real Target

Discovered VPS baseline:

```text
OS: Ubuntu 24.04.3 LTS
Docker: 29.1.5
Docker Compose: v5.0.2
Traefik: 3.6.7
Traefik container: n8n-traefik-1
Traefik Docker provider: exposedbydefault=false
EntryPoints: web :80, websecure :443
TLS resolver: mytlschallenge
Shared Docker network: n8n_default
RAM: 3.8 GiB
vCPU: 1
Free disk: about 41 GiB
Swap: 0
UFW: inactive
Reboot flag: required, but out of scope here
```

Target topology:

```text
Original Product on Vercel
  -> HTTPS
  -> existing Traefik on Hostinger VPS
  -> Docker network n8n_default
  -> langgraph-shadow-test container on port 8000
  -> Supabase SaaS PostgreSQL over TLS
```

The n8n production flow remains official and unchanged. LangGraph must not run
inside n8n, as an n8n node, or in the n8n process.

## 2. Protected Existing Resources

Do not alter these resources while preparing LangGraph:

- `/docker/n8n/docker-compose.yml`
- `n8n-n8n-1`
- `n8n-traefik-1`
- existing n8n hostname and Traefik router
- `/docker/commercial-copilot-api-staging`
- `commercial-copilot-api-staging`

The existing Traefik network `n8n_default` is reused by joining it from the
separate LangGraph Compose project. Do not run `docker compose down` in the n8n
project.

## 3. VPS Layout

Recommended deployment directory:

```text
/docker/agente-sql-langgraph/
  compose.yaml
  shadow-test.env
  source-or-image-reference
```

The LangGraph Compose project is separate from n8n:

```text
project: agente-sql-langgraph-shadow-test
service: langgraph-shadow-test
```

Do not add LangGraph to `/docker/n8n/docker-compose.yml`.

## 4. Docker Image

Versioned Dockerfile:

```text
deploy/docker/Dockerfile.shadow-test
```

Runtime decisions:

- base image: `python:3.12-slim`;
- dependency source: `requirements.txt`;
- runtime user: non-root `langgraph`;
- working directory: `/app`;
- copied runtime files: `requirements.txt` and `app/`;
- no `.env`, Git credentials, docs, tests, or local artifacts baked into the image.

Container command:

```bash
python -m uvicorn app.test_runtime.sql_agent_test_app:create_app \
  --factory \
  --host 0.0.0.0 \
  --port 8000
```

Inside the container, `0.0.0.0` is correct. Safety comes from zero host port
publication, Docker network isolation, Traefik, HTTPS, and Python S2S auth.

Use one Uvicorn worker for initial TEST because the VPS has 1 vCPU.

## 5. Docker Ignore

Versioned build context guard:

```text
.dockerignore
```

It excludes `.git`, `.env`, `.env.*`, `.venv`, Python caches, docs, deployment
templates not needed in runtime, tests, scripts, and local artifacts. The
Dockerfile still explicitly copies only `requirements.txt` and `app/`.

## 6. Compose Template

Versioned Compose template:

```text
deploy/docker/compose.shadow-test.yaml.example
```

Required properties:

- project name `agente-sql-langgraph-shadow-test`;
- service `langgraph-shadow-test`;
- `restart: unless-stopped`;
- `env_file: ./shadow-test.env`;
- external network `n8n_default`;
- `expose: "8000"`;
- no `ports`;
- healthcheck against `http://127.0.0.1:8000/health`;
- Traefik labels for `websecure`;
- TLS resolver `mytlschallenge`.

The service must not publish a host port such as `8000:8000`.

## 7. Traefik

The existing Traefik container already uses Docker provider with
`exposedbydefault=false`, so the LangGraph container must opt in with labels:

```text
traefik.enable=true
traefik.docker.network=n8n_default
traefik.http.routers.langgraph-shadow-test.rule=Host(`<LANGGRAPH_TEST_HOSTNAME>`)
traefik.http.routers.langgraph-shadow-test.entrypoints=websecure
traefik.http.routers.langgraph-shadow-test.tls=true
traefik.http.routers.langgraph-shadow-test.tls.certresolver=mytlschallenge
traefik.http.services.langgraph-shadow-test.loadbalancer.server.port=8000
```

The current Traefik setup already has `web` and `websecure` entrypoints. Use
only `websecure` for the LangGraph router unless discovery later proves an HTTP
router is required. Do not add a middleware that removes `Authorization`, and do
not validate `LANGGRAPH_S2S_TOKEN` in Traefik.

`Authorization` is forwarded by Traefik by default. Python remains responsible
for S2S validation.

## 8. Hostname and TLS

LangGraph TEST hostname is not decided:

```text
LANGGRAPH_TEST_HOSTNAME TO CONFIRM
```

Possible paths:

- `langgraph-test.<owned-domain>`;
- another hostname supported by the domain currently controlled by the operator.

Do not hardcode a real LangGraph hostname in versioned files. Reuse the existing
Traefik ACME resolver:

```text
mytlschallenge
```

Do not install Certbot and do not add Nginx for the current Hostinger target.

## 9. Environment Strategy

Versioned example:

```text
deploy/docker/shadow-test.env.example
```

Real env file on the VPS:

```text
/docker/agente-sql-langgraph/shadow-test.env
```

Required values:

```text
LANGGRAPH_RUNTIME_MODE=shadow_test
LANGGRAPH_HTTP_HOST=0.0.0.0
LANGGRAPH_HTTP_PORT=8000
LANGGRAPH_SHADOW_PERSISTENCE=postgres
LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false
LANGGRAPH_SHADOW_DATABASE_DSN=<secret Supabase runtime DSN with TLS>
LANGGRAPH_S2S_TOKEN=<secret generated outside Git/chat/logs>
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

Do not place secrets in Compose labels, Dockerfile, image layers, Git, chat, or
logs.

## 10. S2S Authentication

The Original Product BFF sends:

```text
Authorization: Bearer <LANGGRAPH_S2S_TOKEN>
```

Caller service:

```text
product_original_bff
```

Payload `principal.id`, `principal.email`, and `principal.profile` remain audit
context. They are not service identity.

Generate the future TEST secret outside Git/chat/logs with:

```bash
openssl rand -hex 48
```

Store the same generated value only in Vercel TEST env and
`/docker/agente-sql-langgraph/shadow-test.env`.

## 11. Image Strategy

Recommended first TEST deployment:

```text
build locally on the VPS from the approved repo commit
```

Reason: it avoids introducing GHCR authentication before the first controlled
smoke. Record the deployed Git commit SHA in the deployment log and set
`LANGGRAPH_COMMIT`.

Future improvement:

```text
GHCR image tagged by immutable commit SHA
```

Do not use a mutable `latest` tag as the traceability mechanism.

## 12. Supabase

LangGraph connects directly from the container to Supabase PostgreSQL over TLS:

```text
langgraph-shadow-test container -> internet/TLS -> Supabase PostgreSQL
```

The connection does not pass through the Original Product, n8n, Traefik, or
Commercial Copilot. Do not use a Supabase browser/public key.

Connection mode is still an operator decision:

```text
SUPABASE CONNECTION MODE TO CONFIRM DURING DEPLOY
```

The runtime DSN should require TLS, typically with `sslmode=require`.

Runtime role:

- `SELECT` on `public.langgraph_shadow_runs`;
- `INSERT` on `public.langgraph_shadow_runs`;
- `UPDATE` on `public.langgraph_shadow_runs`;
- no `DELETE`.

Migration role:

- separate credential with DDL permission;
- apply `scripts/migrations/001_create_langgraph_shadow_runs.sql` manually;
- do not execute the migration in this step.

## 13. Vercel Handoff

No Vercel change happens in this step. After container, HTTPS, auth, and
persistence are validated independently, configure the chosen TEST environment:

```text
LANGGRAPH_INTERNAL_BASE_URL=https://<LANGGRAPH_TEST_HOSTNAME>
LANGGRAPH_S2S_TOKEN=<same TEST secret as container>
LANGGRAPH_SHADOW_ENABLED=true
LANGGRAPH_SHADOW_TIMEOUT_MS=<test-value>
```

No variable should use `NEXT_PUBLIC_`.

## 14. Future Compose Commands

Run only inside `/docker/agente-sql-langgraph` in the future:

```bash
docker compose -f compose.yaml config
docker compose -f compose.yaml build
docker compose -f compose.yaml up -d
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs langgraph-shadow-test
```

Do not run these commands against `/docker/n8n`.

## 15. Validation Flow

Internal health without host port publication:

```bash
docker compose -f compose.yaml exec langgraph-shadow-test \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status)"
```

External health:

```bash
curl --fail https://<LANGGRAPH_TEST_HOSTNAME>/health
```

Negative auth:

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

Expected:

- `/health` returns `200`;
- internal POST/GET without S2S returns `401`;
- wrong Bearer returns `401`.

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

### Optional local SQL provider

After the base Shadow runtime is healthy, the OpenAI-compatible SQL provider can
be enabled only in the LangGraph runtime env:

```text
OPENAI_COMPATIBLE_SQL_ENABLED=true
OPENAI_COMPATIBLE_SQL_PROVIDER_KEY=infodive_local
OPENAI_COMPATIBLE_SQL_CONFIG_VERSION=sql-infodive-demo-v1
OPENAI_COMPATIBLE_SQL_BASE_URL=<private-or-controlled-https-endpoint>
OPENAI_COMPATIBLE_SQL_MODEL=sql-infodive
OPENAI_COMPATIBLE_SQL_API_KEY_SECRET_NAME=OPENAI_COMPATIBLE_SQL_API_KEY
OPENAI_COMPATIBLE_SQL_API_KEY=<runtime-secret>
```

Do not copy these values into n8n, browser configuration, Git, logs, or Product
public payloads. The Product sends only provider_key/model_key/config_version.
The LangGraph runtime resolves endpoint and credentials server-side. Keep
`OPENAI_COMPATIBLE_SQL_ENABLED=false` until the endpoint and runtime secret are
both configured and validated.

If the endpoint is not HTTPS, do not weaken transport validation silently.
Confirm the intended private-network transport separately before changing the
security rule.

Persistence validation:

1. Send authenticated synthetic generate.
2. Confirm one shadow record in Supabase using metadata-safe queries.
3. Call `GET /v1/internal/agent-runs/{agent_run_id}/shadow-runs`.
4. Call `GET /v1/internal/shadow-runs/{shadow_record_id}/visualization`.
5. Confirm IDs correlate and no real SQL was executed.

## 16. Failure Isolation

After Vercel TEST is configured:

- LangGraph online: official n8n response remains normal and shadow persists.
- LangGraph offline: official n8n response remains normal and shadow dispatch
  fails isolated.
- Wrong S2S token: official n8n response remains normal and shadow fails
  isolated.
- Admin UI with LangGraph offline: official run detail opens and shadow panel
  reports unavailable.

## 17. Rollback

TEST rollback order:

1. Set `LANGGRAPH_SHADOW_ENABLED=false` in Vercel TEST.
2. Redeploy the Original Product TEST environment.
3. Stop only the LangGraph Compose project:
   `docker compose -f /docker/agente-sql-langgraph/compose.yaml stop`.
4. If needed, remove only the LangGraph container:
   `docker compose -f /docker/agente-sql-langgraph/compose.yaml down`.
5. The Traefik router disappears with the LangGraph container labels.
6. Keep Supabase evidence/table intact by default.
7. Do not touch n8n, Traefik, or Commercial Copilot containers.

Database rollback requires explicit review. Do not invent or run `DROP TABLE`
as default rollback.

## 18. Reboot Note

The VPS discovery reported `REBOOT_REQUIRED`. Reboot is out of scope for this
microstep. Before any future reboot:

- confirm backups/config snapshots;
- confirm Docker restart policies;
- check n8n and Traefik recovery expectations;
- use a controlled maintenance window.

## 19. Deploy Order

1. Confirm LangGraph TEST hostname/DNS.
2. Prepare Supabase migration and runtime roles.
3. Apply migration manually.
4. Generate S2S secret outside code.
5. Prepare `/docker/agente-sql-langgraph/shadow-test.env`.
6. Obtain source for the approved commit or a commit-tagged image.
7. Create `/docker/agente-sql-langgraph/compose.yaml` from the template.
8. Join external network `n8n_default`.
9. Start container without host ports.
10. Validate internal health from inside Docker.
11. Validate Traefik router.
12. Validate HTTPS.
13. Validate negative auth.
14. Validate positive synthetic auth.
15. Validate Supabase persistence.
16. Configure Vercel TEST.
17. Validate dispatch.
18. Validate Read API and admin UI.
19. Validate failure isolation.

## 20. GO / NO-GO Gates

GO GATE A - Docker:

- Compose project separate from n8n;
- external network `n8n_default` available;
- no host ports published;
- container health OK.

GO GATE B - Traefik:

- labels detected;
- router bound to `websecure`;
- TLS resolver `mytlschallenge`;
- `Authorization` not stripped;
- existing n8n router unaffected.

GO GATE C - DB:

- migration applied manually;
- table and indexes validated;
- runtime credential has minimum permissions.

GO GATE D - Auth:

- `/health` public and minimal;
- internal endpoints return `401` without S2S;
- synthetic positive auth works.

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

## 21. Alternative Templates

The old templates remain versioned only as alternative deployment references:

- `deploy/systemd/agente-sql-langgraph-shadow-test.service.example`;
- `deploy/nginx/langgraph-shadow-test.conf.example`.

They are not the target for the current Hostinger VPS because discovery found
Docker Compose + Traefik as the active deployment pattern.

## 22. Production Separation

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
