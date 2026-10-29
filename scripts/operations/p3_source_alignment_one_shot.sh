#!/usr/bin/env bash
# Local VPS-only: compare official datasource, context and SELECT-only role.
# Existing n8n and Shadow containers are inspected, NOT changed.
# No financial SQL, LLM, DSN, API key, n8n POST, GRANT or migration.
set -Eeuo pipefail
set +x
umask 077

deny() { printf 'P3_SOURCE_AUDIT=BLOCKED\nP3_REASON=%s\n' "$1" >&2; exit 2; }
usage() {
  echo 'Usage: bash scripts/operations/p3_source_alignment_one_shot.sh --context-version VERSION --source-ref REF --demo-ref REF --n8n-container NAME --shadow-container NAME'
}
VERSION=''; SOURCE=''; DEMO=''; N8N=''; SHADOW=''
while (( $# )); do
  case "$1" in
    --context-version) (( $# >= 2 )) || deny VERSION_REQUIRED; VERSION="$2"; shift 2 ;;
    --source-ref) (( $# >= 2 )) || deny SOURCE_REQUIRED; SOURCE="$2"; shift 2 ;;
    --demo-ref) (( $# >= 2 )) || deny DEMO_REQUIRED; DEMO="$2"; shift 2 ;;
    --n8n-container) (( $# >= 2 )) || deny N8N_REQUIRED; N8N="$2"; shift 2 ;;
    --shadow-container) (( $# >= 2 )) || deny SHADOW_REQUIRED; SHADOW="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) deny UNKNOWN_ARGUMENT ;;
  esac
done
[[ "$VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$ ]] || deny VERSION_INVALID
[[ "$SOURCE" =~ ^[a-z]{20}$ && "$DEMO" =~ ^[a-z]{20}$ && "$SOURCE" != "$DEMO" ]] || deny PROJECT_ID_INVALID
[[ "$N8N" =~ ^[A-Za-z0-9_.-]{1,180}$ && "$SHADOW" =~ ^[A-Za-z0-9_.-]{1,180}$ ]] || deny CONTAINER_INVALID
[[ -t 0 ]] || deny LOCAL_TTY_REQUIRED
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$ROOT/.venv/bin/python"
[[ -x "$PY" ]] || deny PYTHON_VENV_MISSING
command -v docker >/dev/null 2>&1 || deny DOCKER_MISSING
POLICY="$ROOT/scripts/operations/g1_readonly_rollout.json"
[[ -f "$POLICY" ]] || deny POLICY_MISSING
for container_name in "$N8N" "$SHADOW"; do
  [[ "$(docker inspect "$container_name" --format '{{.State.Running}}' 2>/dev/null || true)" == true ]] || deny CONTAINER_NOT_RUNNING
done

PRIVATE="$(mktemp -d /tmp/p3-source-audit.XXXXXXXX)" || deny PRIVATE_DIR_FAILED
chmod 700 "$PRIVATE"
# Retain private metadata for authorized accounting review. Operator
# controls retention; never commit or post these files.
# Keep the read-only audit report even when its result is REVIEW_REQUIRED.
# Final evaluator still blocks. Do not repeat PUT/RECOVER to turn it green.
set +e
"$PY" "$ROOT/scripts/operations/g1_post_put_audit_readonly.py" \
  --n8n-container "$N8N" >"$PRIVATE/g1-proof.txt"
G1_RC=$?
set -e
if (( G1_RC != 0 )); then
  printf 'P3_G1_AUDIT=REVIEW_REQUIRED\n'
fi

WORKFLOW_ID="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["n8n"]["workflow_id"])' "$POLICY")"
# Local prompt is non-secret; collector emits only sanitized status.
"$PY" "$ROOT/scripts/operations/audit_supabase_runtime_dependencies_readonly.py" \
  --source-project-ref "$SOURCE" --demo-project-ref "$DEMO" \
  --shadow-container "$SHADOW" --n8n-container "$N8N" \
  --official-workflow-id "$WORKFLOW_ID" --inspect-n8n-credentials \
  | tee "$PRIVATE/dependency-output.txt" || deny DATASOURCE_AUDIT_FAILED
# n8n confirmation prompt can prefix a status. Extract only known tokens.
grep -oE 'SUPABASE_[A-Z0-9_]+=[A-Za-z0-9_]+' "$PRIVATE/dependency-output.txt" \
  >"$PRIVATE/dependency-proof.txt" || deny DEPENDENCY_PROOF_UNAVAILABLE
rm -f "$PRIVATE/dependency-output.txt"

# Pipe reviewed Python to the existing Shadow container. DSN stays inside
# runtime, only public structural policy crosses docker exec. No financial
# table is queried. Private metadata snapshot remains local and 0600.
docker exec -i -e "P3_PHYSICAL_POLICY_JSON=$(cat "$POLICY")" "$SHADOW" \
  python - --probe-shadow --context-version "$VERSION" \
  < "$ROOT/scripts/operations/p3_source_alignment_readonly.py" \
  > "$PRIVATE/physical-metadata.json" || deny SHADOW_CATALOG_PROBE_FAILED

set +e
"$PY" "$ROOT/scripts/operations/p3_source_alignment_readonly.py" \
  --policy "$POLICY" --context-version "$VERSION" \
  --snapshot "$PRIVATE/physical-metadata.json" \
  --g1-proof "$PRIVATE/g1-proof.txt" \
  --dependency-proof "$PRIVATE/dependency-proof.txt" \
  --private-schema-draft "$PRIVATE/unmapped-schema-draft.json"
RC=$?
set -e
printf 'P3_SOURCE_AUDIT=READ_ONLY\nP3_LLM_CALLS=0\nP3_FINANCIAL_SQL_EXECUTED=false\n'
printf 'P3_PRIVATE_REPORTS_STORED=true\n'
printf 'P3_PRIVATE_REPORTS_DIRECTORY=%s\n' "$PRIVATE"
# Directory path is an operator locator, not evidence or a credential.
# Never print the files' raw contents, SQL, DSNs, URLs or tokens.
exit "$RC"
