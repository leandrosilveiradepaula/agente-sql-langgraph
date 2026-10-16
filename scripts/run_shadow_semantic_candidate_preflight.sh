#!/usr/bin/env bash
set -euo pipefail

# One-off read-only semantic preflight, reusing only the existing Shadow's
# context connection. Never export, echo or copy any database credential.
# Load reviewed git source into /tmp, never modifying the live /app or service.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POLICY_RELATIVE="${1:-}"
EXPECTED_SOURCE_FINGERPRINT="${2:-}"
CONTAINER="${SHADOW_CONTAINER:-agente-sql-langgraph-shadow-test-langgraph-shadow-test-1}"

if [[ ! "$POLICY_RELATIVE" =~ ^semantic_context/[A-Za-z0-9._-]+\.json$ ]]; then
  echo "ABORTED: supply a tracked versioned policy under semantic_context."
  exit 2
fi
if [[ -n "$EXPECTED_SOURCE_FINGERPRINT" ]] \
    && [[ ! "$EXPECTED_SOURCE_FINGERPRINT" =~ ^[0-9a-f]{64}$ ]]; then
  echo "ABORTED: expected source fingerprint must be a lowercase SHA-256 value."
  exit 2
fi
if [[ "$(git -C "$ROOT_DIR" branch --show-current)" != "main" ]]; then
  echo "ABORTED: run from a reviewed main checkout, not a feature branch."
  exit 3
fi
if ! git -C "$ROOT_DIR" cat-file -e "HEAD:$POLICY_RELATIVE" 2>/dev/null; then
  echo "ABORTED: policy is not present in the reviewed git commit."
  exit 3
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "ABORTED: Docker is unavailable."
  exit 4
fi
if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "ABORTED: the existing Shadow container is unavailable."
  exit 4
fi
RUNNING="$(docker inspect "$CONTAINER" --format '{{.State.Running}}')"
REAL_SQL_FLAG="$(
  docker inspect "$CONTAINER" \
    --format '{{range .Config.Env}}{{println .}}{{end}}' \
    | sed -n 's/^LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=//p' \
    | tail -n 1
)"
if [[ "$RUNNING" != "true" || "$REAL_SQL_FLAG" != "false" ]]; then
  echo "ABORTED: running Shadow with real SQL execution disabled is required."
  exit 5
fi

# Check only that the DSN exists INSIDE the container. Do not read its value.
if ! docker exec "$CONTAINER" python -c \
  'import os,sys; sys.exit(0 if os.environ.get("CONTEXT_POSTGRES_DSN") else 1)' \
  >/dev/null 2>&1; then
  echo "ABORTED: context-reader connection is unavailable in Shadow."
  exit 6
fi

STAGE="$(docker exec "$CONTAINER" python -c 'import tempfile;print(tempfile.mkdtemp(prefix="semantic_candidate_readonly_"))')"
cleanup() {
  docker exec "$CONTAINER" python -c \
    'import pathlib,shutil,sys; p=pathlib.Path(sys.argv[1]); assert p.parent == pathlib.Path("/tmp") and p.name.startswith("semantic_candidate_readonly_"); shutil.rmtree(p,ignore_errors=True)' \
    "$STAGE" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Extract only git-tracked files to a private ephemeral directory, owned by
# the container's unprivileged runtime user. Reject symlinks and traversal.
EXTRACTOR="$(cat <<'PY'
import pathlib
import shutil
import sys
import tarfile

root = pathlib.Path(sys.argv[1])
if not root.is_dir() or (root.stat().st_mode & 0o777) != 0o700:
    raise ValueError("private staging directory required")
with tarfile.open(fileobj=sys.stdin.buffer, mode="r|*") as archive:
    for member in archive:
        relative = pathlib.PurePosixPath(member.name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("invalid archive path")
        if not relative.parts or relative.parts[0] not in {
            "app", "scripts", "semantic_context"
        }:
            raise ValueError("unexpected archive root")
        target = root.joinpath(*relative.parts)
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
        elif member.isfile():
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("missing archived file")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
        else:
            raise ValueError("unsupported archived file type")
# Prevent imports from resolving to an unrelated installed scripts package.
(root / "scripts" / "__init__.py").touch(exist_ok=True)
PY
)"

echo "SOURCE_COMMIT=$(git -C "$ROOT_DIR" rev-parse HEAD)"
echo "PREVIEW_MODE=read_only_ephemeral_source"

git -C "$ROOT_DIR" archive --format=tar HEAD \
  app \
  scripts/preview_semantic_candidate_readonly.py \
  scripts/audit_semantic_candidate_parity_readonly.py \
  scripts/preflight_semantic_candidate_readonly.py \
  "$POLICY_RELATIVE" \
  | docker exec -i "$CONTAINER" python -c "$EXTRACTOR" "$STAGE"

args=(--policy "$STAGE/$POLICY_RELATIVE")
if [[ -n "$EXPECTED_SOURCE_FINGERPRINT" ]]; then
  args+=(--expected-source-fingerprint "$EXPECTED_SOURCE_FINGERPRINT")
fi
docker exec -w "$STAGE" \
  -e "PYTHONPATH=$STAGE" \
  -e "PYTHONDONTWRITEBYTECODE=1" \
  "$CONTAINER" python -m scripts.preview_semantic_candidate_readonly \
  "${args[@]}"
