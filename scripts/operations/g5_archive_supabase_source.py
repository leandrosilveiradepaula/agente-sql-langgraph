#!/usr/bin/env python3
"""G5: encrypted, read-only logical archive of a retiring Supabase source.

Default --plan never connects to a database. --capture is explicit, local,
requires typed approval, and streams pg_dump directly into OpenPGP encryption.
No plaintext dump, credential, password, host, or SQL is written to disk/logs.
The archive MUST be test-restored in a separate isolated environment before
retirement; checksum verification alone does not qualify as restore evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.operations.g1_readonly_rollout import require_verified_tls_dsn  # noqa: E402

PROJECT = re.compile(r"^[a-z]{20}$")
FINGERPRINT = re.compile(r"^[0-9A-Fa-f]{40}$")
ARCHIVE_NAME = re.compile(r"^source-[a-z]{20}-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{16}\.dump\.gpg$")
ARCHIVE_DIR = Path("/root/.local/share/agente-sql-langgraph/source-archives")
MANIFEST_KEYS = frozenset((
    "version", "project_ref", "captured_at", "archive_name",
    "encrypted_sha256", "encrypted_bytes", "format", "restore_verified",
))
DUMP_TIMEOUT = 3600


class ArchiveBlocked(RuntimeError):
    """Safe, non-sensitive status code only."""


def tools_available() -> bool:
    return bool(shutil.which("pg_dump") and shutil.which("gpg"))


def private_directory(directory: Path, *, create: bool) -> None:
    if os.geteuid() != 0 or not directory.is_absolute():
        raise ArchiveBlocked("ROOT_AND_ABSOLUTE_DIRECTORY_REQUIRED")
    if create:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    s = directory.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o077:
        raise ArchiveBlocked("ARCHIVE_DIRECTORY_UNSAFE")


def check_private_file(path: Path) -> None:
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o077:
        raise ArchiveBlocked("ARCHIVE_FILE_UNSAFE")


def write_exclusive(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def digest_file(path: Path) -> tuple[int, str]:
    check_private_file(path)
    sha = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while part := source.read(1024 * 1024):
            size += len(part)
            sha.update(part)
    return size, sha.hexdigest()


def recipient_exists(fingerprint: str) -> bool:
    if not FINGERPRINT.fullmatch(fingerprint):
        raise ArchiveBlocked("GPG_FINGERPRINT_INVALID")
    try:
        result = subprocess.run(
            ["gpg", "--batch", "--no-tty", "--with-colons",
             "--fingerprint", "--list-keys", fingerprint],
            capture_output=True, timeout=15, check=False, text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    return any(
        fields[0] == "fpr" and len(fields) > 9
        and fields[9].upper() == fingerprint.upper()
        for line in result.stdout.splitlines()
        if (fields := line.split(":"))
    )


def pg_environment(dsn: str, project_ref: str) -> dict[str, str]:
    """No DSN/password in argv; libpq receives narrowly scoped environment."""
    require_verified_tls_dsn(dsn, "postgres", project_ref)
    parsed = urlparse(dsn)
    if not parsed.hostname or parsed.password is None or not parsed.username:
        raise ArchiveBlocked("SOURCE_DSN_INVALID")
    opts = parse_qs(parsed.query, keep_blank_values=True)
    permitted = {"sslmode", "sslrootcert", "channel_binding"}
    if set(opts) - permitted:
        raise ArchiveBlocked("SOURCE_DSN_OPTIONS_UNSUPPORTED")
    env = {k: os.environ[k] for k in (
        "HOME", "PATH", "LANG", "PGSSLROOTCERT",
    ) if k in os.environ}
    env.update({
        "PGHOST": parsed.hostname,
        "PGPORT": str(parsed.port or 5432),
        "PGDATABASE": "postgres",
        "PGUSER": unquote(parsed.username),
        "PGPASSWORD": unquote(parsed.password),
        "PGSSLMODE": "verify-full",
        "PGOPTIONS": "-c default_transaction_read_only=on",
        "PGAPPNAME": "g5_source_archive",
    })
    if "sslrootcert" in opts:
        root = opts["sslrootcert"]
        if len(root) != 1 or not root[0].startswith("/"):
            raise ArchiveBlocked("SOURCE_CA_PATH_INVALID")
        env["PGSSLROOTCERT"] = root[0]
    if "channel_binding" in opts:
        binding = opts["channel_binding"]
        if binding != ["require"]:
            raise ArchiveBlocked("SOURCE_CHANNEL_BINDING_INVALID")
        env["PGCHANNELBINDING"] = "require"
    return env


def encrypted_capture(path: Path, recipient: str, pg_env: dict[str, str]) -> None:
    """Two child processes and a pipe: no plaintext intermediate file."""
    pg_dump = shutil.which("pg_dump")
    gpg = shutil.which("gpg")
    if not pg_dump or not gpg:
        raise ArchiveBlocked("TOOLS_MISSING")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    producer = consumer = None
    try:
        with os.fdopen(fd, "wb") as output:
            producer = subprocess.Popen(
                [pg_dump, "--format=custom", "--no-owner", "--no-acl",
                 "--lock-wait-timeout=5s"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=pg_env,
            )
            # Intentionally do not inherit PGPASSWORD into the GPG process.
            gpg_env = {k: os.environ[k] for k in (
                "HOME", "PATH", "LANG", "GNUPGHOME",
            ) if k in os.environ}
            consumer = subprocess.Popen(
                [gpg, "--batch", "--no-tty", "--trust-model", "always",
                 "--recipient", recipient, "--encrypt"],
                stdin=producer.stdout, stdout=output,
                stderr=subprocess.DEVNULL, env=gpg_env,
            )
            assert producer.stdout is not None
            producer.stdout.close()
            try:
                gpg_rc = consumer.wait(timeout=DUMP_TIMEOUT)
                pg_rc = producer.wait(timeout=30)
            except subprocess.TimeoutExpired:
                raise ArchiveBlocked("ARCHIVE_TIMEOUT") from None
            if pg_rc != 0 or gpg_rc != 0:
                raise ArchiveBlocked("ENCRYPTED_DUMP_FAILED")
            output.flush()
            os.fsync(output.fileno())
    finally:
        for child in (consumer, producer):
            if child is not None and child.poll() is None:
                child.kill()
                child.wait(timeout=15)


def capture(project_ref: str, directory: Path, recipient: str) -> Path:
    if not PROJECT.fullmatch(project_ref):
        raise ArchiveBlocked("SOURCE_PROJECT_REF_INVALID")
    private_directory(directory, create=True)
    if not tools_available():
        raise ArchiveBlocked("TOOLS_MISSING")
    if not recipient_exists(recipient):
        raise ArchiveBlocked("GPG_RECIPIENT_NOT_FOUND")
    if not sys.stdin.isatty():
        raise ArchiveBlocked("LOCAL_TTY_REQUIRED")
    answer = input("Digite ARCHIVE-SOURCE-READONLY para autorizar backup criptografado: ")
    if answer != "ARCHIVE-SOURCE-READONLY":
        raise ArchiveBlocked("CAPTURE_NOT_AUTHORIZED")
    dsn = getpass.getpass("DSN admin SOURCE (sem eco): ")
    try:
        env = pg_environment(dsn, project_ref)
    except Exception:
        raise ArchiveBlocked("SOURCE_DSN_INVALID") from None
    del dsn
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"source-{project_ref}-{timestamp}-{secrets.token_hex(8)}.dump.gpg"
    if not ARCHIVE_NAME.fullmatch(filename):
        raise ArchiveBlocked("ARCHIVE_FILENAME_INVALID")
    final = directory / filename
    temporary = directory / (filename + ".partial")
    manifest = directory / (filename + ".manifest.json")
    committed = False
    final_created = False
    try:
        encrypted_capture(temporary, recipient.upper(), env)
        size, sha = digest_file(temporary)
        if size == 0:
            raise ArchiveBlocked("EMPTY_ARCHIVE")
        # Hard link fails if the final path exists, even in the unlikely event
        # of a name collision; no overwrite of previous retention evidence.
        os.link(temporary, final, follow_symlinks=False)
        final_created = True
        temporary.unlink()
        check_private_file(final)
        receipt = {
            "version": 1,
            "project_ref": project_ref,
            "captured_at": timestamp,
            "archive_name": filename,
            "encrypted_sha256": sha,
            "encrypted_bytes": size,
            "format": "pg_dump_custom_openpgp",
            "restore_verified": False,
        }
        write_exclusive(
            manifest,
            (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        )
        committed = True
        return manifest
    finally:
        temporary.unlink(missing_ok=True)
        if not committed and final_created:
            final.unlink(missing_ok=True)


def verify(project_ref: str, directory: Path, manifest: Path) -> None:
    if not PROJECT.fullmatch(project_ref):
        raise ArchiveBlocked("SOURCE_PROJECT_REF_INVALID")
    private_directory(directory, create=False)
    if manifest.parent != directory or not manifest.name.endswith(".manifest.json"):
        raise ArchiveBlocked("MANIFEST_PATH_UNSAFE")
    check_private_file(manifest)
    if manifest.stat().st_size > 4096:
        raise ArchiveBlocked("MANIFEST_INVALID")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError):
        raise ArchiveBlocked("MANIFEST_INVALID") from None
    if not isinstance(data, dict) or set(data) != MANIFEST_KEYS:
        raise ArchiveBlocked("MANIFEST_INVALID")
    name = data["archive_name"]
    if (data["version"] != 1 or data["project_ref"] != project_ref
            or not isinstance(name, str) or not ARCHIVE_NAME.fullmatch(name)
            or manifest.name != name + ".manifest.json"
            or not name.startswith("source-" + project_ref + "-" + data["captured_at"] + "-")
            or data["format"] != "pg_dump_custom_openpgp"
            or data["restore_verified"] is not False
            or not isinstance(data["encrypted_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", data["encrypted_sha256"])
            or type(data["encrypted_bytes"]) is not int
            or data["encrypted_bytes"] <= 0
            or not isinstance(data["captured_at"], str)
            or not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", data["captured_at"])):
        raise ArchiveBlocked("MANIFEST_INVALID")
    size, sha = digest_file(directory / name)
    if size != data["encrypted_bytes"] or sha != data["encrypted_sha256"]:
        raise ArchiveBlocked("ENCRYPTED_ARCHIVE_DIGEST_MISMATCH")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--capture", action="store_true")
    mode.add_argument("--verify", type=Path, metavar="MANIFEST_PATH")
    parser.add_argument("--source-project-ref", required=True)
    parser.add_argument("--recipient-fingerprint", default=None)
    parser.add_argument("--archive-dir", type=Path, default=ARCHIVE_DIR)
    args = parser.parse_args()
    print("G5_ARCHIVE_MODE=" + (
        "PLAN" if args.plan else "CAPTURE" if args.capture else "VERIFY"
    ))
    try:
        if not PROJECT.fullmatch(args.source_project_ref):
            raise ArchiveBlocked("SOURCE_PROJECT_REF_INVALID")
        if args.plan:
            print("G5_ARCHIVE_TOOLS=" + ("READY" if tools_available() else "MISSING"))
            print("G5_ARCHIVE_CAPTURED=NO")
            print("G5_RESTORE_TEST=NOT_PERFORMED")
            return 0 if tools_available() else 2
        if args.capture:
            if not args.recipient_fingerprint:
                raise ArchiveBlocked("GPG_FINGERPRINT_REQUIRED")
            manifest = capture(
                args.source_project_ref, args.archive_dir, args.recipient_fingerprint,
            )
            print("G5_ARCHIVE_RESULT=ENCRYPTED_CAPTURED")
            print("G5_ARCHIVE_MANIFEST=" + str(manifest))
            print("G5_ARCHIVE_RESTORE=NOT_VERIFIED")
            return 0
        verify(args.source_project_ref, args.archive_dir, args.verify)
        print("G5_ARCHIVE_RESULT=ENCRYPTED_DIGEST_PASS")
        print("G5_ARCHIVE_RESTORE=NOT_VERIFIED")
        return 0
    except Exception as exc:
        print("G5_ARCHIVE_RESULT=BLOCKED")
        print("G5_ARCHIVE_ERROR=" + (
            str(exc) if isinstance(exc, ArchiveBlocked) else type(exc).__name__
        ))
        print("G5_ARCHIVE_RESTORE=NOT_VERIFIED")
        return 2


if __name__ == "__main__":
    sys.exit(main())
