#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Read-only verification of one 7-node n8n Shadow workflow.
# DEFAULT audits the inactive draft. --active-published reads strictly
# the n8n --published version and expects active=true. Neither mode
# changes/publishes/activates a workflow or reads credential values.
# No HTTP POST, SQL, model call; raw exports remain private.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
N8N_CONTAINER="${N8N_CONTAINER:-}"
WORKFLOW_ID=""
ACTIVE_PUBLISHED=false
PRIVATE_DIR=""
REMOTE_DIR=""

reject() {
  printf 'G1_BINDINGS=REJECTED\nREASON=%s\n' "$1" >&2
  exit 2
}

while (( $# > 0 )); do
  case "$1" in
    --workflow-id)
      (( $# >= 2 )) || reject "MISSING_WORKFLOW_ID"
      WORKFLOW_ID="$2"
      shift 2 ;;
    --container)
      (( $# >= 2 )) || reject "MISSING_CONTAINER"
      N8N_CONTAINER="$2"
      shift 2 ;;
    --active-published)
      ACTIVE_PUBLISHED=true
      shift ;;
    -h|--help)
      echo 'Usage: bash scripts/n8n/audit_parallel_shadow_bindings_readonly.sh --workflow-id ID [--container NAME] [--active-published]'
      echo 'Default: inactive draft. --active-published: audited active --published export (read-only).'
      exit 0 ;;
    *) reject "UNKNOWN_ARGUMENT" ;;
  esac
done
[[ "$WORKFLOW_ID" =~ ^[A-Za-z0-9_-]{1,128}$ ]] || reject "WORKFLOW_ID_INVALID"
[[ -z "$N8N_CONTAINER" || "$N8N_CONTAINER" =~ ^[A-Za-z0-9_.-]{1,180}$ ]] || reject "CONTAINER_INVALID"
command -v docker >/dev/null 2>&1 || reject "DOCKER_UNAVAILABLE"
command -v python3 >/dev/null 2>&1 || reject "PYTHON_UNAVAILABLE"

if [[ -z "$N8N_CONTAINER" ]]; then
  mapfile -t candidates < <(
    docker ps --format '{{.Names}} {{.Image}}' |
      awk 'tolower($2) ~ /(^|\/)n8n([:@]|$)/ {print $1}'
  )
  (( ${#candidates[@]} == 1 )) || reject "N8N_CONTAINER_AMBIGUOUS"
  N8N_CONTAINER="${candidates[0]}"
fi
[[ "$(docker inspect "$N8N_CONTAINER" --format '{{.State.Running}}' 2>/dev/null || true)" == "true" ]] ||
  reject "N8N_CONTAINER_NOT_RUNNING"

PRIVATE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/n8n-g1-bindings.XXXXXXXX")" ||
  reject "PRIVATE_TEMP_FAILED"
cleanup() {
  if [[ -n "$REMOTE_DIR" && "$REMOTE_DIR" == /tmp/n8n-g1-bindings.* ]]; then
    if ! docker exec -u node "$N8N_CONTAINER" sh -c \
      'rm -f -- "$1/workflow.json"; rmdir -- "$1"' \
      sh "$REMOTE_DIR" >/dev/null 2>&1; then
      printf 'G1_WARNING=REMOTE_PRIVATE_TEMP_CLEANUP_UNCONFIRMED\n' >&2
    fi
  fi
  if [[ -n "$PRIVATE_DIR" && "$PRIVATE_DIR" == */n8n-g1-bindings.* ]]; then
    rm -rf -- "$PRIVATE_DIR" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# An active workflow must be audited from the published version, not a
# potentially newer or different draft. Never silently fall back.
if [[ "$ACTIVE_PUBLISHED" == true ]]; then
  if ! docker exec -u node "$N8N_CONTAINER" n8n export:workflow --help \
    >"$PRIVATE_DIR/help.out" 2>"$PRIVATE_DIR/help.err"; then
    reject "N8N_CLI_HELP_FAILED"
  fi
  if ! grep -q -- '--published' "$PRIVATE_DIR/help.out"; then
    reject "PUBLISHED_EXPORT_UNSUPPORTED"
  fi
fi

REMOTE_DIR="$(
  docker exec -u node "$N8N_CONTAINER" sh -c \
    'umask 077; mktemp -d /tmp/n8n-g1-bindings.XXXXXXXX' \
    2>"$PRIVATE_DIR/temp.err"
)" || reject "REMOTE_PRIVATE_TEMP_FAILED"
[[ "$REMOTE_DIR" =~ ^/tmp/n8n-g1-bindings\.[A-Za-z0-9]{8}$ ]] ||
  reject "REMOTE_PRIVATE_TEMP_INVALID"

EXPORT_ARGS=("--id=$WORKFLOW_ID")
if [[ "$ACTIVE_PUBLISHED" == true ]]; then
  EXPORT_ARGS+=(--published)
fi
EXPORT_ARGS+=("--output=$REMOTE_DIR/workflow.json")
if ! docker exec -u node "$N8N_CONTAINER" n8n export:workflow \
  "${EXPORT_ARGS[@]}" >"$PRIVATE_DIR/export.out" 2>"$PRIVATE_DIR/export.err"; then
  reject "N8N_WORKFLOW_EXPORT_FAILED"
fi
if ! docker cp "$N8N_CONTAINER:$REMOTE_DIR/workflow.json" \
  "$PRIVATE_DIR/workflow.json" >"$PRIVATE_DIR/copy.out" 2>"$PRIVATE_DIR/copy.err"; then
  reject "N8N_DRAFT_COPY_FAILED"
fi
VERIFY_ARGS=(--workflow "$PRIVATE_DIR/workflow.json" --workflow-id "$WORKFLOW_ID")
if [[ "$ACTIVE_PUBLISHED" == true ]]; then
  VERIFY_ARGS+=(--expect-active)
fi
if ! python3 "$ROOT/scripts/n8n/verify_parallel_shadow_bindings_export.py" \
  "${VERIFY_ARGS[@]}" >"$PRIVATE_DIR/report.json" 2>"$PRIVATE_DIR/verify.err"; then
  # Only the verifier's sanitized, machine-generated reason is printed.
  cat "$PRIVATE_DIR/report.json"
  reject "WORKFLOW_BINDING_VERIFICATION_FAILED"
fi

# Verify remote sensitive export deletion BEFORE reporting success.
if ! docker exec -u node "$N8N_CONTAINER" sh -c \
  'rm -f -- "$1/workflow.json"; rmdir -- "$1"' \
  sh "$REMOTE_DIR" >"$PRIVATE_DIR/cleanup.out" 2>"$PRIVATE_DIR/cleanup.err"; then
  reject "REMOTE_PRIVATE_TEMP_CLEANUP_UNCONFIRMED"
fi
REMOTE_DIR=""
# Remove raw export locally before printing the sanitized report.
rm -f -- "$PRIVATE_DIR/workflow.json"
cat "$PRIVATE_DIR/report.json"
echo 'G1_BINDINGS=PASS'
if [[ "$ACTIVE_PUBLISHED" == true ]]; then
  echo 'G1_PUBLISHED_EXPORT_SELECTED=true'
else
  echo 'G1_PUBLISHED_EXPORT_SELECTED=false'
fi
echo 'G1_CORRELATED_EXECUTION=NOT_TESTED'
echo 'N8N_WORKFLOW_MODIFIED=false'
echo 'LLM_CALLS=0'
echo 'REAL_SQL_EXECUTION=false'
