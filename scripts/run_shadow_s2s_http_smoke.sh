#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER="${SHADOW_CONTAINER:-agente-sql-langgraph-shadow-test-langgraph-shadow-test-1}"
RUNNER="/tmp/smoke_shadow_s2s_http_readonly_$$.py"
if [[ "$(docker inspect "$CONTAINER" --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}')" != "healthy" ]]; then
  echo "ABORTED: Shadow container unhealthy"
  exit 2
fi
trap 'docker exec -u 0 "$CONTAINER" rm -f "$RUNNER" >/dev/null 2>&1 || true' EXIT
docker cp "$ROOT_DIR/scripts/smoke_shadow_s2s_http_readonly.py" "$CONTAINER:$RUNNER"
docker exec -w /app -e PYTHONPATH=/app "$CONTAINER" python "$RUNNER"
