#!/usr/bin/env bash
set -euo pipefail

# One-off read-only semantic preflight, reusing only the existing Shadow's
# context connection. Never export, echo or copy any database credential.
# Load reviewed git source into /tmp, never modifying the live /app or service.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_RELATIVE="${1:-}"
OVERLAY_RELATIVE="${2:-}"
EXPECTED_SOURCE_FINGERPRINT="${3:-}"
SUITE_RELATIVE="${4:-}"
CONTAINER="${SHADOW_CONTAINER:-agente-sql-langgraph-shadow-test-langgraph-shadow-test-1}"

for policy in "$BASE_RELATIVE" "$OVERLAY_RELATIVE"; do
  if [[ ! "$policy" =~ ^semantic_context/[A-Za-z0-9._-]+\.json$ ]]; then
    echo "ABORTED: both policies must be tracked JSON under semantic_context."
    exit 2
  fi
done
if [[ ! "$EXPECTED_SOURCE_FINGERPRINT" =~ ^[0-9a-f]{64}$ ]]; then
  echo "ABORTED: expected v10 source fingerprint is required."
  exit 2
fi
if [[ ! "$SUITE_RELATIVE" =~ ^scripts/validation/[A-Za-z0-9._-]+\.json$ ]]; then
  echo "ABORTED: evaluation suite must be tracked JSON under scripts/validation."
  exit 2
fi
if [[ "$(git -C "$ROOT_DIR" branch --show-current)" != "main" ]]; then
  echo "ABORTED: use reviewed main checkout."
  exit 3
fi
for tracked in "$BASE_RELATIVE" "$OVERLAY_RELATIVE" "$SUITE_RELATIVE"; do
  if ! git -C "$ROOT_DIR" cat-file -e "HEAD:$tracked" 2>/dev/null; then
    echo "ABORTED: reviewed policy or suite missing from main."
    exit 3
  fi
done
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

STAGE="$(docker exec "$CONTAINER" python -c 'import tempfile;print(tempfile.mkdtemp(prefix="semantic_overlay_readonly_"))')"
cleanup() {
  docker exec "$CONTAINER" python -c \
    'import pathlib,shutil,sys; p=pathlib.Path(sys.argv[1]); assert p.parent == pathlib.Path("/tmp") and p.name.startswith("semantic_overlay_readonly_"); shutil.rmtree(p,ignore_errors=True)' \
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
echo "PREVIEW_MODE=read_only_virtual_semantic_overlay"
ARCHIVE_PATHS=(
  app
  scripts/preview_semantic_candidate_readonly.py
  scripts/audit_semantic_candidate_parity_readonly.py
  scripts/preflight_semantic_candidate_readonly.py
  scripts/evaluate_memory_candidate_generalization_readonly.py
  scripts/preview_semantic_overlay_readonly.py
  "$BASE_RELATIVE"
  "$OVERLAY_RELATIVE"
  "$SUITE_RELATIVE"
)

git -C "$ROOT_DIR" archive --format=tar HEAD "${ARCHIVE_PATHS[@]}" \
  | docker exec -i "$CONTAINER" python -c "$EXTRACTOR" "$STAGE"

docker exec -w "$STAGE" \
  -e "PYTHONPATH=$STAGE" \
  -e "PYTHONDONTWRITEBYTECODE=1" \
  "$CONTAINER" python -m scripts.preview_semantic_overlay_readonly \
    --base-policy "$STAGE/$BASE_RELATIVE" \
    --overlay "$STAGE/$OVERLAY_RELATIVE" \
    --cases "$STAGE/$SUITE_RELATIVE" \
    --expected-source-fingerprint "$EXPECTED_SOURCE_FINGERPRINT"
