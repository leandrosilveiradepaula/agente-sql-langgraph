#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Read-only verification of one 7-node n8n Shadow workflow.
# DEFAULT audits inactive draft. --active-published exports strict published
# with --published. --active-version-match is EXPLICIT for n8n 2.4.8 only:
# export current; require active=true + matching current/active version UUIDs.
# No fallback: divergent versions remain blocked. No mode modifies n8n,
# executes SQL/LLM or reads credential values.
# No HTTP POST, SQL, model call; raw exports remain private.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
N8N_CONTAINER="${N8N_CONTAINER:-}"
WORKFLOW_ID=""
ACTIVE_PUBLISHED=false
ACTIVE_VERSION_MATCH=false
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
    --active-version-match)
      ACTIVE_VERSION_MATCH=true
      shift ;;
    -h|--help)
      echo 'Usage: bash scripts/n8n/audit_parallel_shadow_bindings_readonly.sh --workflow-id ID [--container NAME] [--active-published | --active-version-match]'
      echo 'Default: inactive draft. --active-published: CLI --published; --active-version-match: n8n 2.4.8 only, require identical current/active version IDs.'
      exit 0 ;;
    *) reject "UNKNOWN_ARGUMENT" ;;
  esac
done
if [[ "$ACTIVE_PUBLISHED" == true && "$ACTIVE_VERSION_MATCH" == true ]]; then
  reject "AUDIT_MODES_MUTUALLY_EXCLUSIVE"
fi
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

# On n8n@2.4.8, export:workflow supports no --published and exports the
# CURRENT WorkflowRepository record. Source-verified 2.4.8 only:
# a current version is equivalent to published iff versionId == activeVersionId.
# Any other n8n version needs its own reviewed contract.
if [[ "$ACTIVE_VERSION_MATCH" == true ]]; then
  VERSION="$(docker exec -u node "$N8N_CONTAINER" n8n --version 2>"$PRIVATE_DIR/version.err" | head -n 1)" ||
    reject "N8N_VERSION_UNVERIFIED"
  [[ "$VERSION" == "2.4.8" ]] || reject "N8N_VERSION_UNSUPPORTED_FOR_IDENTITY_CHECK"
fi

# Prefer a genuine --published export on newer supported n8n versions.
# Never silently fall back to draft on a missing flag or failed export.
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
if [[ "$ACTIVE_PUBLISHED" == true || "$ACTIVE_VERSION_MATCH" == true ]]; then
  VERIFY_ARGS+=(--expect-active)
fi
if [[ "$ACTIVE_VERSION_MATCH" == true ]]; then
  VERIFY_ARGS+=(--require-active-version-match)
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
if [[ "$ACTIVE_VERSION_MATCH" == true ]]; then
  echo 'G1_N8N_248_PUBLISHED_IDENTITY_MATCH=true'
fi
echo 'G1_CORRELATED_EXECUTION=NOT_TESTED'
echo 'N8N_WORKFLOW_MODIFIED=false'
echo 'LLM_CALLS=0'
echo 'REAL_SQL_EXECUTION=false'
