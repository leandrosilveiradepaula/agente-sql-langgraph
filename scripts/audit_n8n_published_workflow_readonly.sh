#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Manual, local, READ-ONLY inspection of one PUBLISHED n8n workflow.
# No webhook execution, API key, SQL, prompt or raw export is printed.
# Raw JSON lives in restricted ephemeral files removed before output.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER="${N8N_CONTAINER:-}"
WORKFLOW_ID=""
BASELINE=""
PRIVATE_DIR=""
REMOTE_DIR=""

reject() {
  printf 'N8N_PUBLISHED_AUDIT=REJECTED\nREASON=%s\n' "$1" >&2
  exit 2
}

usage() {
  cat <<'HELP'
Usage: bash scripts/audit_n8n_published_workflow_readonly.sh \
  --workflow-id WORKFLOW_ID [--container CONTAINER] [--compare-to PRIVATE_EXPORT_PATH]

Requires Docker and Python 3. Requires n8n CLI --published support.
Reports only sanitized hashes, node-type metadata and version drift.
Does not execute the workflow or call a model, database or webhook.
HELP
}

while (( $# > 0 )); do
  case "$1" in
    --workflow-id)
      (( $# >= 2 )) || reject "MISSING_WORKFLOW_ID"
      WORKFLOW_ID="$2"
      shift 2 ;;
    --container)
      (( $# >= 2 )) || reject "MISSING_CONTAINER"
      CONTAINER="$2"
      shift 2 ;;
    --compare-to)
      (( $# >= 2 )) || reject "MISSING_BASELINE"
      BASELINE="$2"
      shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      reject "UNKNOWN_ARGUMENT" ;;
  esac
done

[[ "$WORKFLOW_ID" =~ ^[A-Za-z0-9_-]{1,128}$ ]] || reject "WORKFLOW_ID_INVALID"
[[ -z "$CONTAINER" || "$CONTAINER" =~ ^[A-Za-z0-9_.-]{1,180}$ ]] || reject "CONTAINER_INVALID"
[[ -z "$BASELINE" || ( -f "$BASELINE" && -r "$BASELINE" ) ]] || reject "BASELINE_NOT_READABLE"
command -v docker >/dev/null 2>&1 || reject "DOCKER_NOT_AVAILABLE"
command -v python3 >/dev/null 2>&1 || reject "PYTHON_NOT_AVAILABLE"

if [[ -z "$CONTAINER" ]]; then
  mapfile -t CANDIDATES < <(
    docker ps --format '{{.Names}} {{.Image}}' |
      awk 'tolower($2) ~ /(^|\/)n8n([:@]|$)/ {print $1}'
  )
  (( ${#CANDIDATES[@]} == 1 )) || reject "REQUIRES_EXPLICIT_N8N_CONTAINER"
  CONTAINER="${CANDIDATES[0]}"
fi
[[ "$(docker inspect "$CONTAINER" --format '{{.State.Running}}' 2>/dev/null || true)" == "true" ]] ||
  reject "CONTAINER_NOT_RUNNING"

PRIVATE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/n8n-published-audit.XXXXXXXX")" ||
  reject "PRIVATE_TEMP_CREATE_FAILED"

cleanup() {
  if [[ -n "$REMOTE_DIR" && "$REMOTE_DIR" == /tmp/n8n-published-audit.* ]]; then
    docker exec -u node "$CONTAINER" sh -c \
      'rm -f -- "$1/workflow.json"; rmdir -- "$1"' \
      sh "$REMOTE_DIR" >/dev/null 2>&1 || true
  fi
  if [[ -n "$PRIVATE_DIR" && "$PRIVATE_DIR" == */n8n-published-audit.* ]]; then
    rm -rf -- "$PRIVATE_DIR" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# Fail closed: a draft may not substitute for the published active version.
if ! docker exec -u node "$CONTAINER" n8n export:workflow --help \
  >"$PRIVATE_DIR/help.out" 2>"$PRIVATE_DIR/help.err"; then
  reject "N8N_CLI_HELP_FAILED"
fi
grep -q -- '--published' "$PRIVATE_DIR/help.out" ||
  reject "PUBLISHED_EXPORT_UNSUPPORTED"

REMOTE_DIR="$(
  docker exec -u node "$CONTAINER" sh -c \
    'umask 077; mktemp -d /tmp/n8n-published-audit.XXXXXXXX' \
    2>"$PRIVATE_DIR/temp.err"
)" || reject "N8N_PRIVATE_TEMP_CREATE_FAILED"
[[ "$REMOTE_DIR" =~ ^/tmp/n8n-published-audit\.[A-Za-z0-9]{8}$ ]] ||
  reject "N8N_PRIVATE_TEMP_INVALID"

if ! docker exec -u node "$CONTAINER" n8n export:workflow \
  "--id=$WORKFLOW_ID" --published "--output=$REMOTE_DIR/workflow.json" \
  >"$PRIVATE_DIR/export.out" 2>"$PRIVATE_DIR/export.err"; then
  reject "PUBLISHED_WORKFLOW_EXPORT_FAILED"
fi
if ! docker cp "$CONTAINER:$REMOTE_DIR/workflow.json" \
  "$PRIVATE_DIR/workflow.json" >/dev/null 2>"$PRIVATE_DIR/copy.err"; then
  reject "PUBLISHED_WORKFLOW_COPY_FAILED"
fi

# The export must contain exactly the explicitly named workflow.
if ! python3 - "$PRIVATE_DIR/workflow.json" "$WORKFLOW_ID" \
  >"$PRIVATE_DIR/id.out" 2>"$PRIVATE_DIR/id.err" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    workflow = json.load(stream)
if isinstance(workflow, list):
    if len(workflow) != 1:
        raise ValueError("not one workflow")
    workflow = workflow[0]
if not isinstance(workflow, dict) or workflow.get("id") != sys.argv[2]:
    raise ValueError("workflow ID differs")
PY
then
  reject "PUBLISHED_WORKFLOW_IDENTITY_INVALID"
fi

ARGS=(--workflow "$PRIVATE_DIR/workflow.json")
if [[ -n "$BASELINE" ]]; then
  ARGS+=(--compare-to "$BASELINE")
fi
if ! python3 "$ROOT/scripts/audit_n8n_workflow_export_readonly.py" \
  "${ARGS[@]}" >"$PRIVATE_DIR/summary.json" 2>"$PRIVATE_DIR/audit.err"; then
  reject "WORKFLOW_INVENTORY_FAILED"
fi

# Do not print any report until cleanup of the raw export is confirmed.
if ! docker exec -u node "$CONTAINER" sh -c \
  'rm -f -- "$1/workflow.json"; rmdir -- "$1"' \
  sh "$REMOTE_DIR" >"$PRIVATE_DIR/clean.out" 2>"$PRIVATE_DIR/clean.err"; then
  reject "CONTAINER_EXPORT_CLEANUP_UNCONFIRMED"
fi
REMOTE_DIR=""

python3 - "$PRIVATE_DIR/summary.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    result = json.load(stream)
result["published_export_selected"] = True
result["official_webhook_route_verified"] = False
result["real_sql_execution"] = False
result["workflow_executed"] = False
result["provider_calls"] = 0
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
PY
