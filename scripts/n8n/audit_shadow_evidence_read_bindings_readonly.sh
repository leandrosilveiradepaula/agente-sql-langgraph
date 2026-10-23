#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Read-only inspection of a separately imported, INACTIVE five-node n8n relay.
# No workflow import/publication, SQL, LLM, HTTP requests, credential values,
# secret printing or Vercel changes. The raw n8n export is private and ephemeral.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
N8N_CONTAINER="${N8N_CONTAINER:-}"
WORKFLOW_ID=""
PRIVATE_DIR=""
REMOTE_DIR=""

reject() {
  printf 'EVIDENCE_READ_BINDINGS=REJECTED\nREASON=%s\n' "$1" >&2
  exit 2
}

while (( $# > 0 )); do
  case "$1" in
    --workflow-id)
      (( $# >= 2 )) || reject MISSING_WORKFLOW_ID
      WORKFLOW_ID="$2"; shift 2 ;;
    --container)
      (( $# >= 2 )) || reject MISSING_CONTAINER
      N8N_CONTAINER="$2"; shift 2 ;;
    -h|--help)
      echo 'Usage: bash scripts/n8n/audit_shadow_evidence_read_bindings_readonly.sh --workflow-id ID [--container NAME]'
      exit 0 ;;
    *) reject UNKNOWN_ARGUMENT ;;
  esac
done
[[ "$WORKFLOW_ID" =~ ^[A-Za-z0-9_-]{1,128}$ ]] || reject WORKFLOW_ID_INVALID
[[ -z "$N8N_CONTAINER" || "$N8N_CONTAINER" =~ ^[A-Za-z0-9_.-]{1,180}$ ]] || reject CONTAINER_INVALID
command -v docker >/dev/null 2>&1 || reject DOCKER_UNAVAILABLE
command -v python3 >/dev/null 2>&1 || reject PYTHON_UNAVAILABLE

if [[ -z "$N8N_CONTAINER" ]]; then
  mapfile -t candidates < <(
    docker ps --format '{{.Names}} {{.Image}}' |
      awk 'tolower($2) ~ /(^|\/)n8n([:@]|$)/ {print $1}'
  )
  (( ${#candidates[@]} == 1 )) || reject N8N_CONTAINER_AMBIGUOUS
  N8N_CONTAINER="${candidates[0]}"
fi
[[ "$(docker inspect "$N8N_CONTAINER" --format '{{.State.Running}}' 2>/dev/null || true)" == "true" ]] ||
  reject N8N_CONTAINER_NOT_RUNNING

PRIVATE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/n8n-evidence-bindings.XXXXXXXX")" ||
  reject PRIVATE_TEMP_CREATE_FAILED
cleanup() {
  if [[ -n "$REMOTE_DIR" && "$REMOTE_DIR" == /tmp/n8n-evidence-bindings.* ]]; then
    if ! docker exec -u node "$N8N_CONTAINER" sh -c \
      'rm -f -- "$1/workflow.json"; rmdir -- "$1"' \
      sh "$REMOTE_DIR" >/dev/null 2>&1; then
      printf 'EVIDENCE_WARNING=REMOTE_PRIVATE_TEMP_CLEANUP_UNCONFIRMED\n' >&2
    fi
  fi
  if [[ -n "$PRIVATE_DIR" && "$PRIVATE_DIR" == */n8n-evidence-bindings.* ]]; then
    rm -rf -- "$PRIVATE_DIR" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

REMOTE_DIR="$(
  docker exec -u node "$N8N_CONTAINER" sh -c \
    'umask 077; mktemp -d /tmp/n8n-evidence-bindings.XXXXXXXX' \
    2>"$PRIVATE_DIR/create.err"
)" || reject REMOTE_PRIVATE_TEMP_CREATE_FAILED
[[ "$REMOTE_DIR" =~ ^/tmp/n8n-evidence-bindings\.[A-Za-z0-9]{8}$ ]] ||
  reject REMOTE_PRIVATE_TEMP_INVALID

# Draft export intentionally; publishing is an unauthorized state for audit.
if ! docker exec -u node "$N8N_CONTAINER" n8n export:workflow \
  "--id=$WORKFLOW_ID" "--output=$REMOTE_DIR/workflow.json" \
  >"$PRIVATE_DIR/export.out" 2>"$PRIVATE_DIR/export.err"; then
  reject N8N_DRAFT_EXPORT_FAILED
fi
if ! docker cp "$N8N_CONTAINER:$REMOTE_DIR/workflow.json" \
  "$PRIVATE_DIR/workflow.json" >"$PRIVATE_DIR/copy.out" 2>"$PRIVATE_DIR/copy.err"; then
  reject N8N_DRAFT_COPY_FAILED
fi
if ! python3 "$ROOT/scripts/n8n/verify_shadow_evidence_read_bindings_export.py" \
  --workflow "$PRIVATE_DIR/workflow.json" --workflow-id "$WORKFLOW_ID" \
  >"$PRIVATE_DIR/report.json" 2>"$PRIVATE_DIR/verify.err"; then
  # Only the machine-generated bounded rejection reason is safe to emit.
  cat "$PRIVATE_DIR/report.json"
  reject EVIDENCE_WORKFLOW_BINDINGS_FAILED
fi

# Never announce PASS before both raw export copies are deleted.
if ! docker exec -u node "$N8N_CONTAINER" sh -c \
  'rm -f -- "$1/workflow.json"; rmdir -- "$1"' \
  sh "$REMOTE_DIR" >"$PRIVATE_DIR/cleanup.out" 2>"$PRIVATE_DIR/cleanup.err"; then
  reject REMOTE_PRIVATE_TEMP_CLEANUP_UNCONFIRMED
fi
REMOTE_DIR=""
rm -f -- "$PRIVATE_DIR/workflow.json"
cat "$PRIVATE_DIR/report.json"
echo 'EVIDENCE_READ_BINDINGS=PASS'
echo 'EVIDENCE_READ_RUNTIME_CONNECTIVITY=NOT_TESTED'
echo 'EVIDENCE_READ_TENANT_ISOLATION=NOT_TESTED'
echo 'N8N_WORKFLOW_MODIFIED=false'
echo 'LLM_CALLS=0'
echo 'REAL_SQL_EXECUTION=false'
