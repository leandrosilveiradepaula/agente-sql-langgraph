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
      awk 'tolower($2) ~ /(^|\/)n8n([:@]|$)/ {print $1}'
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

# Validate connectivity and the negative S2S boundary from n8n's Node runtime.
# Does not pass any secret to n8n and makes GET-only requests.
if ! docker exec \
  -e "SHADOW_PROBE_BASE=http://${SHADOW_CONTAINER}:8000" \
  "$N8N_CONTAINER" node -e '
    (async () => {
      const base = process.env.SHADOW_PROBE_BASE;
      try {
        const healthResponse = await fetch(base + "/health", {
          method: "GET",
          signal: AbortSignal.timeout(5000),
        });
        const health = await healthResponse.json();
        if (
          healthResponse.status !== 200 ||
          health.status !== "ok" ||
          health.real_sql_execution !== false
        ) {
          console.log("N8N_TO_SHADOW_HTTP=FAIL");
          process.exitCode = 1;
          return;
        }
        console.log("N8N_TO_SHADOW_HTTP=PASS");

        const deniedResponse = await fetch(
          base + "/v1/internal/shadow-runs/invalid!",
          {method: "GET", signal: AbortSignal.timeout(5000)}
        );
        const deniedBody = await deniedResponse.json();
        if (
          deniedResponse.status !== 401 ||
          deniedBody.error?.code !== "UNAUTHORIZED_SERVICE"
        ) {
          console.log("N8N_TO_SHADOW_AUTH_BOUNDARY=FAIL");
          process.exitCode = 1;
          return;
        }
        console.log("N8N_TO_SHADOW_AUTH_BOUNDARY=DENIED");
        console.log("REAL_SQL_EXECUTION=false");
        console.log("LLM_CALLS=0");
      } catch (_) {
        console.log("N8N_TO_SHADOW_HTTP=FAIL");
        process.exitCode = 1;
      }
    })();
  '; then
  echo "N8N_TO_SHADOW_CONNECTIVITY=NOT_VERIFIED"
  exit 7
fi

echo "N8N_TO_SHADOW_CONNECTIVITY=PASS"
echo "OFFICIAL_N8N_WORKFLOW_MODIFIED=false"
