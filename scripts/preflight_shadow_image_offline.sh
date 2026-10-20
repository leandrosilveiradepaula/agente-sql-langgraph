#!/usr/bin/env bash
set -Eeuo pipefail

# Checks real Uvicorn startup without exposing ports or contacting any service.
# The isolated container can access only its own loopback interface.
if [[ $# -ne 2 ]]; then
  echo "USAGE: preflight_shadow_image_offline.sh IMAGE_TAG ENV_FILE"
  exit 2
fi
IMAGE_TAG="$1"
ENV_FILE="$2"

if [[ ! -r "$ENV_FILE" ]]; then
  echo "OFFLINE_PREFLIGHT=FAIL env_file_unavailable"
  exit 2
fi
if [[ "$(sed -n 's/^LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=//p' "$ENV_FILE" | tail -n 1)" != "false" ]]; then
  echo "OFFLINE_PREFLIGHT=FAIL real_sql_must_be_disabled"
  exit 2
fi

CANDIDATE_CONTAINER="shadow-image-preflight-$$"
cleanup() {
  docker rm -f "$CANDIDATE_CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run --pull=never -d --name "$CANDIDATE_CONTAINER" \
  --network none --cap-drop ALL --security-opt no-new-privileges \
  --env-file "$ENV_FILE" \
  -e LANGGRAPH_RUNTIME_MODE=shadow_test \
  -e LANGGRAPH_HTTP_HOST=0.0.0.0 \
  -e LANGGRAPH_HTTP_PORT=8000 \
  -e LANGGRAPH_SHADOW_PERSISTENCE=postgres \
  -e LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false \
  "$IMAGE_TAG" >/dev/null

passed=false
for _ in $(seq 1 35); do
  if docker exec -i "$CANDIDATE_CONTAINER" python - <<'PY' >/dev/null 2>&1
import json
import os
import urllib.error
import urllib.request

assert os.geteuid() != 0
assert os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") == "false"
url = "http://127.0.0.1:8000"
with urllib.request.urlopen(url + "/health", timeout=2) as reply:
    health = json.load(reply)
assert health.get("status") == "ok"
assert health.get("runtime_mode") == "shadow_test"
assert health.get("real_sql_execution") is False
try:
    urllib.request.urlopen(url + "/v1/internal/shadow-runs/invalid!", timeout=2)
except urllib.error.HTTPError as error:
    assert error.code == 401
else:
    raise AssertionError("S2S protection missing")
PY
  then
    passed=true
    break
  fi
  if [[ "$(docker inspect "$CANDIDATE_CONTAINER" --format '{{.State.Running}}' 2>/dev/null || true)" != "true" ]]; then
    break
  fi
  sleep 1
done

if [[ "$passed" != true ]]; then
  echo "OFFLINE_PREFLIGHT=FAIL image_cannot_start_or_serve_health"
  exit 1
fi

echo "OFFLINE_PREFLIGHT=PASS isolated_network=none startup=healthy s2s_denied=true sql_real=false llm_calls=0"
