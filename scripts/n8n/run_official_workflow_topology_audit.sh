#!/usr/bin/env bash
set -euo pipefail

# Read-only: n8n workflow export, sanitized in the n8n container.
# No credentials exported. No workflow is imported, activated or updated.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTAINER="${N8N_CONTAINER:-n8n-n8n-1}"
AUDIT_ID="${N8N_AUDIT_WORKFLOW_ID:-}"

if [[ -n "$AUDIT_ID" && ! "$AUDIT_ID" =~ ^[A-Za-z0-9_-]{1,128}$ ]]; then
  echo "N8N_TOPOLOGY_AUDIT=INVALID_WORKFLOW_ID"
  exit 2
fi

if [[ "$(docker inspect "$CONTAINER" --format '{{.State.Running}}' 2>/dev/null || true)" != "true" ]]; then
  echo "N8N_TOPOLOGY_AUDIT=CONTAINER_UNAVAILABLE"
  exit 3
fi

# The temporary directory is private to the n8n OS user. Never copy an
# unredacted workflow export to the VPS, GitHub, or this conversation.
TEMP_DIR="/tmp/n8n-topology-audit-$$"
EXPORT_FILE="$TEMP_DIR/workflows.json"
INSPECTOR_FILE="$TEMP_DIR/inspector.js"

cleanup() {
  docker exec -u node "$CONTAINER" rm -f \
    "$EXPORT_FILE" "$INSPECTOR_FILE" >/dev/null 2>&1 || true
  docker exec -u node "$CONTAINER" rmdir \
    "$TEMP_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! docker exec -u node "$CONTAINER" mkdir -m 700 "$TEMP_DIR" >/dev/null 2>&1; then
  echo "N8N_TOPOLOGY_AUDIT=TEMP_DIR_FAILED"
  exit 4
fi
if ! docker cp \
  "$ROOT_DIR/scripts/n8n/audit_official_workflow_topology.js" \
  "$CONTAINER:$INSPECTOR_FILE" >/dev/null 2>&1; then
  echo "N8N_TOPOLOGY_AUDIT=INSPECTOR_COPY_FAILED"
  exit 5
fi

if [[ -n "$AUDIT_ID" ]]; then
  if ! docker exec -u node "$CONTAINER" n8n export:workflow \
    "--id=$AUDIT_ID" "--output=$EXPORT_FILE" >/dev/null 2>&1; then
    echo "N8N_TOPOLOGY_AUDIT=EXPORT_FAILED"
    exit 6
  fi
else
  if ! docker exec -u node "$CONTAINER" n8n export:workflow \
    --all "--output=$EXPORT_FILE" >/dev/null 2>&1; then
    echo "N8N_TOPOLOGY_AUDIT=EXPORT_FAILED"
    exit 6
  fi
fi

# Only white-listed workflow IDs, counts, node categories and numeric edges
# are emitted by the inspector. Raw JSON and node parameters never leave n8n.
docker exec -u node "$CONTAINER" node \
  "$INSPECTOR_FILE" "$EXPORT_FILE" "$AUDIT_ID"
