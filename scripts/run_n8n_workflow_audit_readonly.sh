#!/usr/bin/env bash
set -euo pipefail

# Exports only n8n workflows into private ephemeral files for structural audit.
# Never exports credentials, prints raw JSON, edits a workflow, or triggers runs.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
N8N_CONTAINER="${N8N_CONTAINER:-n8n-n8n-1}"

if [[ "$(docker inspect "$N8N_CONTAINER" --format '{{.State.Running}}' 2>/dev/null || true)" != "true" ]]; then
  echo "N8N_AUDIT_CONTAINER_NOT_RUNNING"
  exit 2
fi

umask 077
WORKDIR="$(mktemp -d)"
REMOTE="/tmp/n8n-readonly-audit-${WORKDIR##*/}.json"
cleanup() {
  docker exec -u 0 "$N8N_CONTAINER" rm -f "$REMOTE" >/dev/null 2>&1 || true
  if [[ "$WORKDIR" == /tmp/* && -d "$WORKDIR" ]]; then
    rm -rf -- "$WORKDIR"
  fi
}
trap cleanup EXIT

echo "N8N_WORKFLOW_EXPORT=START"
# Explicitly invoke *workflow* export; credentials must never be exported.
# Suppress CLI logs, which are not trusted for safe disclosure.
if ! docker exec -u node "$N8N_CONTAINER" sh -c \
  'umask 077; exec n8n export:workflow --all --output="$1"' \
  sh "$REMOTE" >/dev/null 2>&1; then
  echo "N8N_WORKFLOW_EXPORT=FAIL"
  exit 3
fi

if ! docker cp "$N8N_CONTAINER:$REMOTE" "$WORKDIR/export.json" >/dev/null 2>&1; then
  echo "N8N_WORKFLOW_COPY=FAIL"
  exit 4
fi

echo "N8N_WORKFLOW_EXPORT=PASS"
python3 "$ROOT/scripts/audit_n8n_workflows_readonly.py" \
  --input "$WORKDIR/export.json" "$@"
