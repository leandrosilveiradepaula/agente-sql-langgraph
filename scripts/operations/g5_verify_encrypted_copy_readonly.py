#!/usr/bin/env python3
"""G5: independently verify an encrypted backup copy, without decrypting it.

Run on the EXTERNAL destination after the operator has explicitly arranged
a secure transfer. This utility NEVER copies data, connects to Supabase,
reads secrets/SQL, sends network requests, restores a database or modifies
the archive/manifest. Both ciphertext and manifest are verified against the
manifest SHA256 captured independently on the SOURCE host.

A matching copy is *not* proof of actual offsite custody; its physical host,
separate failure domain, encryption key custody and retention policy require
independent operator attestation before the SOURCE retirement gate can pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

SOURCE_REF = re.compile(r"^[a-z]{20}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CAPTURED_TIME = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
ARCHIVE_NAME = re.compile(
    r"^source-[a-z]{20}-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{16}\.dump\.gpg$"
)
MANIFEST_KEYS = frozenset((
    "version", "project_ref", "captured_at", "archive_name",
    "encrypted_sha256", "encrypted_bytes", "format", "restore_verified",
))
MANIFEST_LIMIT = 4096
FORMAT_ALLOWLIST = frozenset((
    "pg_dump_custom_openpgp_symmetric", "pg_dump_custom_openpgp",
))


class CopyBlocked(Exception):
    """Only fixed, non-sensitive diagnostic codes."""


def private_regular_file(path: Path) -> int:
    """No symlink traversal; fail if group/other may access on POSIX."""
    try:
        info = path.lstat()
    except OSError:
        raise CopyBlocked("COPY_FILE_MISSING") from None
    if not stat.S_ISREG(info.st_mode):
        raise CopyBlocked("COPY_FILE_NOT_REGULAR")
    if os.name == "posix" and info.st_mode & 0o077:
        raise CopyBlocked("COPY_FILE_PERMISSIONS_UNSAFE")
    return info.st_size


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_copy(
    manifest: Path, project_ref: str, trusted_manifest_sha256: str,
) -> int:
    if not SOURCE_REF.fullmatch(project_ref):
        raise CopyBlocked("COPY_PROJECT_REF_INVALID")
    if not SHA256.fullmatch(trusted_manifest_sha256):
        raise CopyBlocked("TRUSTED_MANIFEST_SHA256_INVALID")
    if manifest.name.endswith(".dump.gpg.manifest.json") is False:
        raise CopyBlocked("MANIFEST_FILENAME_INVALID")
    if not manifest.is_absolute():
        raise CopyBlocked("COPY_PATH_NOT_ABSOLUTE")
    size = private_regular_file(manifest)
    if not 1 <= size <= MANIFEST_LIMIT:
        raise CopyBlocked("MANIFEST_SIZE_INVALID")
    if file_sha256(manifest) != trusted_manifest_sha256:
        raise CopyBlocked("MANIFEST_TRUST_HASH_MISMATCH")
    try:
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeError):
        raise CopyBlocked("MANIFEST_JSON_INVALID") from None
    if not isinstance(metadata, dict) or set(metadata) != MANIFEST_KEYS:
        raise CopyBlocked("MANIFEST_STRUCTURE_INVALID")
    filename = metadata.get("archive_name")
    captured = metadata.get("captured_at")
    if (
        metadata.get("version") != 1
        or metadata.get("project_ref") != project_ref
        or not isinstance(filename, str)
        or not ARCHIVE_NAME.fullmatch(filename)
        or not isinstance(captured, str)
        or not CAPTURED_TIME.fullmatch(captured)
        or filename != "source-" + project_ref + "-" + captured + "-" +
            filename.rsplit("-", 1)[-1]
        or manifest.name != filename + ".manifest.json"
        or metadata.get("format") not in FORMAT_ALLOWLIST
        or metadata.get("restore_verified") is not False
        or type(metadata.get("encrypted_bytes")) is not int
        or metadata["encrypted_bytes"] <= 0
        or not isinstance(metadata.get("encrypted_sha256"), str)
        or not SHA256.fullmatch(metadata["encrypted_sha256"])
    ):
        raise CopyBlocked("MANIFEST_METADATA_INVALID")
    archive = manifest.with_name(filename)
    actual_size = private_regular_file(archive)
    if actual_size != metadata["encrypted_bytes"]:
        raise CopyBlocked("CIPHERTEXT_SIZE_MISMATCH")
    if file_sha256(archive) != metadata["encrypted_sha256"]:
        raise CopyBlocked("CIPHERTEXT_SHA256_MISMATCH")
    return actual_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-project-ref", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--trusted-manifest-sha256", required=True)
    args = parser.parse_args()
    print("G5_COPY_VERIFICATION_MODE=OFFLINE_READ_ONLY")
    try:
        size = inspect_copy(
            args.manifest, args.source_project_ref, args.trusted_manifest_sha256,
        )
        print("G5_COPY_MANIFEST_SHA256=PASS")
        print("G5_COPY_CIPHERTEXT_SHA256=PASS")
        print("G5_COPY_CIPHERTEXT_BYTES=" + str(size))
        print("G5_COPY_FILESYSTEM_PERMISSIONS=" +
              ("PRIVATE_POSIX" if os.name == "posix" else "NOT_ATTESTED"))
        print("G5_COPY_VERIFICATION=PASS")
        print("G5_OFFSITE_CUSTODY=NOT_ATTESTED")
        print("G5_RESTORE_TEST=NOT_PERFORMED")
        return 0
    except (CopyBlocked, OSError, UnicodeError, ValueError) as error:
        print("G5_COPY_VERIFICATION=BLOCKED")
        print("G5_COPY_ERROR=" + (
            str(error) if isinstance(error, CopyBlocked) else "COPY_IO_ERROR"
        ))
        print("G5_OFFSITE_CUSTODY=NOT_ATTESTED")
        print("G5_RESTORE_TEST=NOT_PERFORMED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
