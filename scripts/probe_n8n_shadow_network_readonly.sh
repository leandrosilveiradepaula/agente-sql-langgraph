#!/usr/bin/env bash
set -euo pipefail

# Read-only network probe from the n8n container to LangGraph Shadow.
# Never reads or prints env/secrets; no workflow imports, POST, SQL or LLM.
SHADOW_CONTAINER="${SHADOW_CONTAINER:-agente-sql-langgraph-shadow-test-langgraph-shadow-test-1}"
N8N_CONTAINER="${N8N_CONTAINER:-}"

if ! docker inspect "$SHADOW_CONTAINER" >/dev/null 2>&1; then
  echo "SHADOW_CONTAINER=NOT_FOUND"
  exit 2
fi
health="$(docker inspect "$SHADOW_CONTAINER" --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}')"
if [[ "$health" != "healthy" ]]; then
  echo "SHADOW_HEALTH=NOT_HEALTHY"
  exit 3
fi

if [[ -z "$N8N_CONTAINER" ]]; then
  mapfile -t candidates < <(
    docker ps --format '{{.Names}} {{.Image}}' |
      awk 'tolower($1) ~ /n8n/ || tolower($2) ~ /n8n/ {print $1}'
  )
  if [[ "${#candidates[@]}" != 1 ]]; then
    echo "N8N_CONTAINER_COUNT=${#candidates[@]}"
    echo "N8N_SELECTION=REQUIRES_EXPLICIT_CONTAINER"
    exit 4
  fi
  N8N_CONTAINER="${candidates[0]}"
fi
if [[ "$(docker inspect "$N8N_CONTAINER" --format '{{.State.Running}}' 2>/dev/null || true)" != "true" ]]; then
  echo "N8N_CONTAINER=NOT_RUNNING"
  exit 5
fi

mapfile -t shared_networks < <(
  comm -12     <(docker inspect "$N8N_CONTAINER" --format '{{range $key, $_ := .NetworkSettings.Networks}}{{println $key}}{{end}}' | LC_ALL=C sort)     <(docker inspect "$SHADOW_CONTAINER" --format '{{range $key, $_ := .NetworkSettings.Networks}}{{println $key}}{{end}}' | LC_ALL=C sort)
)
echo "SHADOW_HEALTH=PASS"
echo "N8N_CONTAINER=DETECTED"
echo "SHARED_NETWORK_COUNT=${#shared_networks[@]}"
if [[ "${#shared_networks[@]}" == 0 ]]; then
  echo "N8N_TO_SHADOW_DIRECT_NETWORK=UNAVAILABLE"
  echo "NOTE=Direct Docker network unavailable; authenticated ingress may be an alternative."
  exit 6
fi

# Node is part of n8n's own runtime. Run a GET health probe only.
# A timeout prevents this check from delaying any official orchestration.
if ! docker exec   -e "SHADOW_PROBE_URL=http://${SHADOW_CONTAINER}:8000/health"   "$N8N_CONTAINER" node -e '
    (async () => {
      try {
        const response = await fetch(process.env.SHADOW_PROBE_URL, {
          method: "GET",
          signal: AbortSignal.timeout(5000),
        });
        const health = await response.json();
        if (
          response.status !== 200 ||
          health.status !== "ok" ||
          health.real_sql_execution !== false
        ) {
          process.stdout.write("N8N_TO_SHADOW_HTTP=FAIL\\n");
          process.exitCode = 1;
          return;
        }
        process.stdout.write("N8N_TO_SHADOW_HTTP=PASS\\n");
        process.stdout.write("REAL_SQL_EXECUTION=false\\n");
        process.stdout.write("LLM_CALLS=0\\n");
      } catch (_) {
        process.stdout.write("N8N_TO_SHADOW_HTTP=FAIL\\n");
        process.exitCode = 1;
      }
    })();
  '; then
  echo "N8N_TO_SHADOW_CONNECTIVITY=NOT_VERIFIED"
  exit 7
fi

echo "N8N_TO_SHADOW_CONNECTIVITY=PASS"
echo "OFFICIAL_N8N_WORKFLOW_MODIFIED=false"
