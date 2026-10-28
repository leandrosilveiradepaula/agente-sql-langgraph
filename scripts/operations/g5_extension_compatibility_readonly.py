#!/usr/bin/env python3
"""G5: compare encrypted archive extensions with cached PostgreSQL images.

Read-only PRECHECK, never a recovery certificate. Docker uses only the local
Unix socket and approved PostgreSQL 17 references. Each candidate image is
pinned by local SHA; an ephemeral non-root networkless read-only process lists
extension control filenames without mounting the real archive or starting a
database. Separately, GPG/pg_restore --list identifies required extensions
from a fully decrypted in-memory pipe. Only validated extension identifiers
are printed; no SQL, data, DSNs, or raw TOC.
"""
from __future__ import annotations

import argparse
import getpass
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.operations.g5_archive_supabase_source import ARCHIVE_DIR, ArchiveBlocked  # noqa: E402
from scripts.operations.g5_inspect_encrypted_source import (  # noqa: E402
    decrypt_and_check_toc, pg_restore_binary, validated_archive,
)
from scripts.operations.g5_restore_isolated_rehearsal import (  # noqa: E402
    docker_executable, docker_query, IMAGE_SHA,
)

IMAGE_REF = re.compile(r"^(?:postgres:17|supabase/postgres:17\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,4})$")
CONTROL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,62}$")
MAX_IMAGES = 3
MAX_OUTPUT_BYTES = 32768

CONTROL_PROBE = """set -eu
sharedir="$(pg_config --sharedir)"
case "$sharedir" in /*) ;; *) exit 2 ;; esac
for file in "$sharedir"/extension/*.control; do
  [ -f "$file" ] || continue
  # PostgreSQL has both primary foo.control and secondary foo--version.control.
  # Only primary files establish the presence of an installable extension.
  # Version-specific controls may include dots and must not be counted as
  # separate extension names (PostgreSQL 17 extension packaging contract).
  case "$file" in *--*.control) continue ;; esac
  basename "$file" .control
done
"""


def cached_image_id(prefix: list[str], image_ref: str) -> str:
    if not IMAGE_REF.fullmatch(image_ref):
        raise ArchiveBlocked("IMAGE_REFERENCE_NOT_APPROVED")
    result = docker_query(
        prefix, ["image", "inspect", "--format", "{{.Id}}", image_ref],
    )
    image_sha = result.stdout.decode("ascii", "ignore").strip()
    if result.returncode != 0 or not IMAGE_SHA.fullmatch(image_sha):
        raise ArchiveBlocked("POSTGRES17_IMAGE_NOT_CACHED")
    return image_sha


def available_control_files(prefix: list[str], image_sha: str) -> set[str]:
    if not IMAGE_SHA.fullmatch(image_sha):
        raise ArchiveBlocked("IMAGE_ID_INVALID")
    cmd = [
        "run", "--rm", "--pull=never",
        "--network=none", "--read-only", "--user=65534:65534",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit=32", "--memory=128m", "--cpus=0.25",
        "--log-driver=none",
        "--tmpfs=/var/lib/postgresql/data:rw,nosuid,nodev,noexec,size=8m,mode=0700",
        "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=8m,mode=1777",
        "--entrypoint=/bin/sh", image_sha, "-c", CONTROL_PROBE,
    ]
    # No archive, secret, host bind, database connection or exposed port.
    # docker_query suppresses stderr. Raw stdout is not echoed to the user.
    try:
        result = docker_query(prefix, cmd)
        payload = result.stdout
    except (OSError, ValueError, subprocess.SubprocessError):
        raise ArchiveBlocked("IMAGE_EXTENSION_PROBE_FAILED") from None
    if result.returncode != 0 or not isinstance(payload, bytes):
        raise ArchiveBlocked("IMAGE_EXTENSION_PROBE_FAILED")
    # Fixed, non-sensitive codes allow diagnosing image layout without
    # copying raw control filenames, stderr, or paths into operator logs.
    if not payload:
        raise ArchiveBlocked("IMAGE_EXTENSION_PROBE_NO_PRIMARY_CONTROLS")
    if len(payload) > MAX_OUTPUT_BYTES:
        raise ArchiveBlocked("IMAGE_EXTENSION_PROBE_OUTPUT_LIMIT")
    try:
        names = [x for x in payload.decode("ascii").splitlines() if x]
    except UnicodeError:
        raise ArchiveBlocked("IMAGE_EXTENSION_PROBE_NON_ASCII") from None
    if not names:
        raise ArchiveBlocked("IMAGE_EXTENSION_PROBE_NO_PRIMARY_CONTROLS")
    if any(not CONTROL_NAME.fullmatch(name) for name in names):
        raise ArchiveBlocked("IMAGE_EXTENSION_PROBE_UNEXPECTED_PRIMARY_NAME")
    return set(names)


def compare_extensions(required: set[str],
                       image_controls: set[str]) -> tuple[str, ...]:
    if not required:
        raise ArchiveBlocked("ARCHIVE_EXTENSION_REQUIREMENTS_EMPTY")
    if any(not CONTROL_NAME.fullmatch(name) for name in required):
        raise ArchiveBlocked("ARCHIVE_EXTENSION_METADATA_INVALID")
    return tuple(sorted(required - image_controls))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-project-ref", required=True)
    parser.add_argument("--archive-dir", type=Path, default=ARCHIVE_DIR)
    parser.add_argument("--image-ref", action="append", default=None)
    args = parser.parse_args()
    print("G5_EXTENSION_AUDIT_MODE=READ_ONLY")
    try:
        refs = args.image_ref or ["postgres:17"]
        if len(refs) > MAX_IMAGES or len(set(refs)) != len(refs):
            raise ArchiveBlocked("IMAGE_REFERENCE_COUNT_INVALID")
        if any(not IMAGE_REF.fullmatch(ref) for ref in refs):
            raise ArchiveBlocked("IMAGE_REFERENCE_NOT_APPROVED")
        archive = validated_archive(args.manifest, args.source_project_ref, args.archive_dir)
        prefix = docker_executable()
        candidates = [(ref, cached_image_id(prefix, ref)) for ref in refs]
        controls = [available_control_files(prefix, sha) for _, sha in candidates]
        restore_bin = pg_restore_binary()
        if not sys.stdin.isatty():
            raise ArchiveBlocked("LOCAL_TTY_REQUIRED")
        password = getpass.getpass("Senha do backup criptografado (sem eco): ")
        required: set[str] = set()
        _, total = decrypt_and_check_toc(archive, password, restore_bin, extensions=required)
        missing_per_image = [compare_extensions(required, installed) for installed in controls]
        print("G5_ARCHIVE_TOC_ENTRIES=" + str(total))
        print("G5_ARCHIVE_EXTENSION_COUNT=" + str(len(required)))
        print("G5_ARCHIVE_EXTENSION_NAMES=" + ",".join(sorted(required)))
        for idx, ((ref, sha), installed, missing) in enumerate(
            zip(candidates, controls, missing_per_image), start=1
        ):
            label = "G5_IMAGE_" + str(idx) + "_"
            print(label + "REF=" + ref)
            print(label + "SHA=" + sha)
            print(label + "CONTROL_COUNT=" + str(len(installed)))
            print(label + "MISSING_COUNT=" + str(len(missing)))
            print(label + "MISSING=" + ",".join(missing))
            print(label + "EXTENSION_COVERAGE="
                  + ("BLOCKED" if missing else "FILES_PRESENT_NOT_RESTORE_PROOF"))
        print("G5_EXTENSION_AUDIT_RESULT=RECORDED")
        print("G5_RESTORE_TEST=NOT_PERFORMED")
        return 0
    except Exception as exc:
        print("G5_EXTENSION_AUDIT_RESULT=BLOCKED")
        print("G5_EXTENSION_AUDIT_ERROR=" + (
            str(exc) if isinstance(exc, ArchiveBlocked) else type(exc).__name__
        ))
        print("G5_RESTORE_TEST=NOT_PERFORMED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
