"""Isolated one-version G5 financial-context review; NEVER imports/activates.

The passphrase is requested from the operator's LOCAL TTY and passed to GPG
via an anonymous OS file descriptor. It is never a CLI argument, environment
variable, file or log value. Plaintext is verified by the sealed manifest
before writing a root-only, unapproved review packet for separate accounting
validation. No DB, benchmark, LLM, SQL execution, tenant activation or n8n I/O.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{64}$")
_MAX_PLAINTEXT = 8_000_000
_MAX_ROWS = 50000


class ReviewBlocked(ValueError):
    """Fail without disclosing raw financial content or passphrases."""


def _hex(value: object) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def select_verified_seal(
    manifest: Mapping[str, Any], version_sha256: str,
) -> dict[str, Any]:
    if not _hex(version_sha256) or not isinstance(manifest, Mapping):
        raise ReviewBlocked("VERSION_OR_MANIFEST_INVALID")
    if (
        manifest.get("approved_for_generation") is not False
        or manifest.get("approved_for_import") is not False
        or manifest.get("financial_sql_executed") is not False
        or manifest.get("context_activated") is not False
    ):
        raise ReviewBlocked("MANIFEST_SAFETY_FLAGS_INVALID")
    versions = manifest.get("versions")
    if not isinstance(versions, list) or not 1 <= len(versions) <= 500:
        raise ReviewBlocked("MANIFEST_VERSIONS_INVALID")
    matches = [
        item for item in versions if isinstance(item, dict)
        and item.get("source_version_sha256") == version_sha256
    ]
    if len(matches) != 1:
        raise ReviewBlocked("VERSION_NOT_UNIQUELY_IN_MANIFEST")
    selected = matches[0]
    if (
        selected.get("file")
        != "source-version-" + version_sha256 + ".json.gpg"
        or not _hex(selected.get("ciphertext_sha256"))
        or not _hex(selected.get("plaintext_sha256"))
        or selected.get("sealed_and_roundtrip_verified") is not True
    ):
        raise ReviewBlocked("SEALED_VERSION_NOT_VERIFIED")
    rows = selected.get("row_counts")
    if (
        not isinstance(rows, dict)
        or not 1 <= len(rows) <= 128
        or not all(
            isinstance(name, str) and 0 < len(name) <= 128
            and type(count) is int and 0 <= count <= _MAX_ROWS
            for name, count in rows.items()
        )
    ):
        raise ReviewBlocked("SEALED_ROW_COUNTS_INVALID")
    return selected


def verify_decrypted_packet(
    content: bytes, seal: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if (
        not isinstance(content, bytes)
        or not 0 < len(content) <= _MAX_PLAINTEXT
        or _digest(content) != seal["plaintext_sha256"]
    ):
        raise ReviewBlocked("DECRYPTED_INTEGRITY_MISMATCH")
    try:
        packet = json.loads(content)
    except (ValueError, TypeError):
        raise ReviewBlocked("DECRYPTED_PACKET_NOT_JSON") from None
    origin = packet.get("origin") if isinstance(packet, dict) else None
    if (
        not isinstance(origin, Mapping)
        or origin.get("source_version_sha256")
        != seal["source_version_sha256"]
        or packet.get("status") != "QUARANTINED_SOURCE_EVIDENCE_UNAPPROVED"
        or packet.get("financial_semantics_equivalence") != "NOT_ATTESTED"
        or packet.get("can_import_into_semantic_catalog") is not False
        or packet.get("can_use_as_llm_or_planner_context") is not False
        or packet.get("can_execute_financial_sql") is not False
        or packet.get("historical_sql_patterns_excluded") is not True
    ):
        raise ReviewBlocked("DECRYPTED_SOURCE_NOT_QUARANTINED")
    collections = packet.get("collections")
    if not isinstance(collections, dict):
        raise ReviewBlocked("DECRYPTED_COLLECTIONS_INVALID")
    rows_by_source = seal["row_counts"]
    counts = {}
    field_names = {}
    row_digests: set[str] = set()
    for name, items in collections.items():
        if name not in rows_by_source or not isinstance(items, list):
            raise ReviewBlocked("DECRYPTED_COLLECTION_NOT_DECLARED")
        if len(items) != rows_by_source[name]:
            raise ReviewBlocked("DECRYPTED_ROW_COUNT_MISMATCH")
        counts[name] = len(items)
        keys: set[str] = set()
        for item in items:
            if not isinstance(item, Mapping):
                raise ReviewBlocked("DECRYPTED_ROW_INVALID")
            row_sha = item.get("source_row_sha256")
            fields = item.get("source_fields_unreviewed")
            if not _hex(row_sha) or not isinstance(fields, Mapping):
                raise ReviewBlocked("DECRYPTED_ROW_PROVENANCE_INVALID")
            if row_sha in row_digests:
                raise ReviewBlocked("DECRYPTED_DUPLICATE_ROW")
            row_digests.add(row_sha)
            keys.update(str(k) for k in fields.keys())
        field_names[name] = sorted(keys)
    if set(rows_by_source) != set(counts):
        raise ReviewBlocked("DECRYPTED_SOURCE_MISSING")
    if packet.get("row_counts") != rows_by_source:
        raise ReviewBlocked("DECRYPTED_PACKET_COUNTS_MISMATCH")
    report = {
        "contract": "g5-targeted-financial-source-review-v1",
        "status": "INTEGRITY_VERIFIED_FINANCIAL_MEANING_UNAPPROVED",
        "version_sha256": seal["source_version_sha256"],
        "packet_plaintext_sha256": _digest(content),
        "collections": dict(sorted(counts.items())),
        "source_field_names": dict(sorted(field_names.items())),
        "source_row_count": len(row_digests),
        "financial_meaning_approved": False,
        "ready_for_generator": False,
        "ready_for_sql_execution": False,
        "benchmark_inputs_included": False,
    }
    return packet, report


def decrypt_local_gpg(cipher: Path, passphrase: str) -> bytes:
    if not passphrase:
        raise ReviewBlocked("LOCAL_TTY_SECRET_REQUIRED")
    read_fd, write_fd = os.pipe()
    process = None
    try:
        process = subprocess.Popen(
            [
                "gpg", "--batch", "--no-tty", "--quiet",
                "--pinentry-mode", "loopback",
                "--passphrase-fd", str(read_fd),
                "--decrypt", str(cipher),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            pass_fds=(read_fd,),
        )
        os.close(read_fd)
        read_fd = -1
        os.write(write_fd, passphrase.encode("utf-8") + b"\n")
        os.close(write_fd)
        write_fd = -1
        assert process.stdout is not None
        content = process.stdout.read(_MAX_PLAINTEXT + 1)
        process.stdout.close()
        result = process.wait(timeout=40)
        if result != 0 or len(content) > _MAX_PLAINTEXT:
            raise ReviewBlocked("SEALED_DECRYPTION_FAILED")
        return content
    except (OSError, subprocess.TimeoutExpired):
        raise ReviewBlocked("SEALED_DECRYPTION_FAILED") from None
    finally:
        if read_fd != -1:
            os.close(read_fd)
        if write_fd != -1:
            os.close(write_fd)
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()


def write_private_once(output: Path, content: bytes) -> None:
    # Windows cannot attest POSIX 0700/0600 modes: refuse persistence.
    # Never weaken the protection to accommodate a CI filesystem.
    if os.name != "posix":
        raise ReviewBlocked("PRIVATE_REVIEW_POSIX_FILESYSTEM_REQUIRED")
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise ReviewBlocked("PRIVATE_REVIEW_OUTPUT_UNSAFE")
    if not output.parent.is_dir() or stat.S_IMODE(
        output.parent.stat().st_mode
    ) & 0o077:
        raise ReviewBlocked("PRIVATE_REVIEW_DIRECTORY_UNSAFE")
    fd = os.open(
        output,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--version-sha256", required=True)
    p.add_argument("--output-dir", required=True, type=Path)
    args = p.parse_args(argv)
    try:
        if os.name != "posix":
            raise ReviewBlocked("G5_REVIEW_POSIX_ONLY")
        manifest_path = args.manifest.resolve(strict=True)
        if manifest_path.is_symlink() or stat.S_IMODE(
            manifest_path.stat().st_mode
        ) & 0o077:
            raise ReviewBlocked("MANIFEST_PERMISSIONS_UNSAFE")
        manifest = json.loads(manifest_path.read_text())
        seal = select_verified_seal(manifest, args.version_sha256)
        cipher = manifest_path.parent / seal["file"]
        if cipher.is_symlink() or not cipher.is_file() or stat.S_IMODE(
            cipher.stat().st_mode
        ) & 0o077:
            raise ReviewBlocked("SEALED_PACKET_PERMISSIONS_UNSAFE")
        if _digest(cipher.read_bytes()) != seal["ciphertext_sha256"]:
            raise ReviewBlocked("SEALED_CIPHERTEXT_HASH_MISMATCH")
        output = args.output_dir
        if not output.is_absolute() or output.exists() or output.is_symlink():
            raise ReviewBlocked("PRIVATE_REVIEW_OUTPUT_DIR_UNSAFE")
        if not sys.stdin.isatty():
            raise ReviewBlocked("LOCAL_INTERACTIVE_TTY_REQUIRED")
        phrase = getpass.getpass("G5 local review passphrase: ")
        try:
            content = decrypt_local_gpg(cipher, phrase)
        finally:
            del phrase
        packet, report = verify_decrypted_packet(content, seal)
        os.mkdir(output, 0o700)
        try:
            write_private_once(
                output / "unapproved-source-packet.json",
                json.dumps(packet, sort_keys=True, ensure_ascii=True).encode()
                + b"\n",
            )
            write_private_once(
                output / "sanitized-review-evidence.json",
                json.dumps(report, sort_keys=True, ensure_ascii=True).encode()
                + b"\n",
            )
        except BaseException:
            for file in output.iterdir():
                if file.is_file() and not file.is_symlink():
                    file.unlink()
            output.rmdir()
            raise
        print("G5_TARGETED_REVIEW=PASS")
        print("G5_VERSION_SHA256=" + seal["source_version_sha256"])
        print("G5_SOURCE_ROW_COUNT=" + str(report["source_row_count"]))
        print("FINANCIAL_MEANING_APPROVED=false")
        print("SQL_EXECUTED=false")
        print("PRIVATE_REVIEW_OUTPUT=" + str(output))
        return 0
    except (ReviewBlocked, OSError, ValueError, TypeError):
        print("G5_TARGETED_REVIEW=BLOCKED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
