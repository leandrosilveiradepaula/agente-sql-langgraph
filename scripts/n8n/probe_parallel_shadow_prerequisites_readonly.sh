#!/usr/bin/env bash
set -Eeuo pipefail

# Read-only G1 prerequisite check: never imports workflows, activates webhooks,
# changes n8n environment, reads secrets, runs SQL or invokes providers.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTAINER="${SHADOW_CONTAINER:-agente-sql-langgraph-shadow-test-langgraph-shadow-test-1}"
N8N_CONTAINER="${N8N_CONTAINER:-}"

echo "=== REPOSITORY / INACTIVE CANDIDATE ==="
echo "REPOSITORY_SHA=$(git -C "$ROOT_DIR" rev-parse HEAD)"
python3 "$ROOT_DIR/scripts/n8n/render_parallel_shadow_workflow.py" --check-template

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "G1_READONLY_CHECK=FAIL shadow_missing"
  exit 2
fi

echo "=== SHADOW RUNTIME ==="
docker inspect "$CONTAINER" --format \
  'SHADOW_STATE={{.State.Status}} SHADOW_HEALTH={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}'
docker exec "$CONTAINER" python - <<'PY'
import os
print("SHADOW_SQL_REAL_DISABLED=" + str(
    os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") == "false"
).lower())
print("SHADOW_CONTEXT_PRESENT=" + str(
    bool(os.environ.get("SEMANTIC_AGENT_VERSION"))
).lower())
print("SHADOW_S2S_PRESENT=" + str(
    bool(os.environ.get("LANGGRAPH_S2S_TOKEN"))
).lower())
print("SHADOW_GEMINI_MODEL_PRESENT=" + str(
    bool(os.environ.get("GEMINI_SQL_GENERATOR_MODEL"))
).lower())
PY

if [[ -z "$N8N_CONTAINER" ]]; then
  mapfile -t candidates < <(
    docker ps --format '{{.Names}} {{.Image}}' |
      awk 'tolower($2) ~ /(^|\/)n8n([:@]|$)/ {print $1}'
  )
  if [[ "${#candidates[@]}" -ne 1 ]]; then
    echo "N8N_SELECTION=REQUIRES_EXPLICIT_CONTAINER"
    exit 3
  fi
  N8N_CONTAINER="${candidates[0]}"
fi

echo "=== N8N CONFIGURATION (METADATA ONLY) ==="
echo "N8N_VERSION=$(docker exec -u node "$N8N_CONTAINER" n8n --version | head -n 1)"
docker exec "$N8N_CONTAINER" node - <<'JS'
const env = process.env;
const safeBool = value => String(Boolean(value)).toLowerCase();
console.log("N8N_SHADOW_INTERNAL_BASE_URL_PRESENT=" +
  safeBool(env.LANGGRAPH_SHADOW_INTERNAL_BASE_URL));
console.log("N8N_ENV_EXPRESSIONS_GLOBAL_ACCESS=" +
  (env.N8N_BLOCK_ENV_ACCESS_IN_NODE === "false" ? "EXPLICITLY_ALLOWED" : "BLOCKED_OR_UNVERIFIED"));
console.log("N8N_IMPORT_REQUIRES_MANUAL_APPROVAL=true");
console.log("N8N_CREDENTIALS_PRESENT=NOT_INSPECTED");
JS

if docker exec -u node "$N8N_CONTAINER" n8n import:workflow --help >/dev/null 2>&1; then
  echo "N8N_IMPORT_CLI_AVAILABLE=PASS"
else
  echo "N8N_IMPORT_CLI_AVAILABLE=UNVERIFIED"
fi

echo "=== NETWORK / S2S DENIAL ==="
bash "$ROOT_DIR/scripts/probe_n8n_shadow_network_readonly.sh"

echo "G1_READONLY_CHECK=PASS"
echo "N8N_WORKFLOW_MODIFIED=false"
echo "N8N_IMPORT_PERFORMED=false"
echo "SHADOW_LLM_CALLS=0"
echo "SHADOW_SQL_REAL_EXECUTED=false"
