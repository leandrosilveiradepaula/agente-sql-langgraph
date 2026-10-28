#!/usr/bin/env python3
"""Synthetic-only real Docker smoke of G5 Supabase PG17 boot isolation.

CI-only: starts an empty rootless PostgreSQL 17 scratch cluster on tmpfs,
checks readiness/version, removes and verifies cleanup. Does NOT open
a real archive, decrypt, restore SQL, log database contents or mount host data.
"""
from pathlib import Path
import os
import sys

from scripts.operations.g5_restore_isolated_rehearsal import (
    ArchiveBlocked,
    docker_executable,
    image_id,
    rehearsed_restore,
    supabase_image_user,
)

EXPECTED_IMAGE = "sha256:f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00"
IMAGE_REF = "supabase/postgres:17.6.1.136"


def main() -> int:
    print("G5_CI_BOOT_MODE=SYNTHETIC_OFFLINE")
    try:
        if os.name != "posix" or os.geteuid() != 0:
            raise ArchiveBlocked("CI_ROOT_REQUIRED")
        prefix = docker_executable()
        image = image_id(prefix, IMAGE_REF)
        if image != EXPECTED_IMAGE:
            raise ArchiveBlocked("CI_IMAGE_SHA_MISMATCH")
        identity = supabase_image_user(prefix, image)
        restored = rehearsed_restore(
            Path("/does-not-exist-no-real-archive"),
            "", prefix, image,
            runtime_user=identity, boot_only=True,
        )
        if restored != 0:
            raise ArchiveBlocked("CI_BOOT_UNEXPECTED_RESULT")
        print("G5_CI_BOOT=PASS")
        print("G5_CI_CONTAINER_CLEANUP=PASS")
        print("G5_CI_REAL_ARCHIVE_ACCESSED=NO")
        print("G5_RESTORE_TEST=NOT_PERFORMED")
        return 0
    except Exception as exc:
        print("G5_CI_BOOT=BLOCKED")
        print("G5_CI_ERROR=" + (
            str(exc) if isinstance(exc, ArchiveBlocked) else type(exc).__name__
        ))
        print("G5_RESTORE_TEST=NOT_PERFORMED")
        return 2


if __name__ == "__main__":
    sys.exit(main())
