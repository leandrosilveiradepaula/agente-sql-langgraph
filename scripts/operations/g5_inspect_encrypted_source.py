#!/usr/bin/env python3
"""Inspect the encrypted G5 SOURCE archive with no disk plaintext or DB access.

Decrypts into an anonymous pipe connected to pg_restore --list. GPG is
consumed through EOF to verify the full encrypted message, even if pg_restore
stops reading after its TOC. Outputs ONLY counts and status codes, not names,
DSNs, SQL, source data, the passphrase, or raw subprocess stderr.

This is NOT a restore rehearsal and NEVER connects to a database. An isolated
PostgreSQL restoration with independent authorization is required before
retiring the source.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.operations.g5_archive_supabase_source import (  # noqa: E402
    ARCHIVE_DIR,
    ArchiveBlocked,
    validate_archive_passphrase,
    verify,
)

TOC_RECORD = re.compile(rb"^\d{1,12};\s")
# Only PostgreSQL extension identifier tokens are retained for a separate
# read-only compatibility audit. Table names, SQL and other TOC records
# are never retained or displayed.
TOC_EXTENSION_RECORD = re.compile(
    rb'^\d{1,12};\s+\d+\s+\d+\s+EXTENSION\s+-\s+'
    rb'(?P<name>[A-Za-z][A-Za-z0-9_-]{0,62})(?:\s|$)'
)
TOC_EXTENSION_CANDIDATE = re.compile(
    rb'^\d{1,12};\s+\d+\s+\d+\s+EXTENSION(?:\s|$)'
)
READ_CHUNK = 64 * 1024
TIMEOUT = 120


def pg_restore_binary() -> str:
    binary = shutil.which("pg_restore")
    if not binary:
        raise ArchiveBlocked("PG_RESTORE_MISSING")
    try:
        result = subprocess.run(
            [binary, "--version"], capture_output=True,
            check=False, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        raise ArchiveBlocked("PG_RESTORE_UNAVAILABLE") from None
    match = re.search(r"pg_restore \(PostgreSQL\)\s+(\d+)", result.stdout)
    if result.returncode != 0 or match is None or int(match.group(1)) < 17:
        raise ArchiveBlocked("PG_RESTORE_VERSION_UNSUPPORTED")
    return binary


def validated_archive(manifest: Path, project_ref: str, directory: Path) -> Path:
    # SHA-256 of ciphertext and owner-only manifest/dir/archive are checked first.
    verify(project_ref, directory, manifest)
    receipt = json.loads(manifest.read_text(encoding="utf-8"))
    if receipt["format"] != "pg_dump_custom_openpgp_symmetric":
        raise ArchiveBlocked("SYMMETRIC_ARCHIVE_REQUIRED")
    return directory / receipt["archive_name"]


def read_toc_counts(pipe, counts: list[int],
                    extensions: set[str] | None = None,
                    invalid_extension: list[bool] | None = None) -> None:
    """Drain TOC; optionally keep ONLY validated extension identifiers."""
    try:
        for line in iter(lambda: pipe.readline(8192), b""):
            if TOC_RECORD.match(line):
                counts[0] += 1
                if extensions is not None and TOC_EXTENSION_CANDIDATE.match(line):
                    match = TOC_EXTENSION_RECORD.match(line)
                    if match is None:
                        if invalid_extension is not None:
                            invalid_extension[0] = True
                    else:
                        extensions.add(match.group("name").decode("ascii"))
    except (OSError, ValueError):
        if invalid_extension is not None:
            invalid_extension[0] = True
        return


def decrypt_and_check_toc(archive: Path, password: str, restore_bin: str,
                          extensions: set[str] | None = None) -> tuple[int, int]:
    """GPG stream -> pg_restore -l; optional safe-only extension inventory."""
    validate_archive_passphrase(password)
    if os.name != "posix" or not hasattr(subprocess, "Popen"):
        raise ArchiveBlocked("POSIX_LOCAL_RUNTIME_REQUIRED")
    gpg_bin = shutil.which("gpg")
    if not gpg_bin:
        raise ArchiveBlocked("GPG_MISSING")
    gpg = restore = counter = None
    secret_read = secret_write = None
    listing = [0]
    invalid_extension = [False]
    plain_bytes = 0
    header = b""
    try:
        secret_read, secret_write = os.pipe()
        gpg_env = {k: os.environ[k] for k in (
            "HOME", "PATH", "LANG", "GNUPGHOME",
        ) if k in os.environ}
        gpg = subprocess.Popen(
            [gpg_bin, "--batch", "--no-tty", "--pinentry-mode", "loopback",
             "--no-symkey-cache", "--passphrase-fd", str(secret_read),
             "--decrypt", str(archive)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            pass_fds=(secret_read,), env=gpg_env,
        )
        os.close(secret_read)
        secret_read = None
        with os.fdopen(secret_write, "wb") as secret_pipe:
            secret_write = None
            secret_pipe.write(password.encode("ascii") + b"\n")
        # Never inherit PG* or an implicit DB connection to pg_restore.
        restore_env = {k: os.environ[k] for k in (
            "HOME", "PATH", "LANG",
        ) if k in os.environ}
        restore = subprocess.Popen(
            [restore_bin, "--list"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=restore_env,
        )
        assert restore.stdout is not None and restore.stdin is not None
        counter = threading.Thread(
            target=read_toc_counts,
            args=(restore.stdout, listing, extensions, invalid_extension),
            daemon=True,
        )
        counter.start()
        assert gpg.stdout is not None
        forwarding = True
        while chunk := gpg.stdout.read(READ_CHUNK):
            plain_bytes += len(chunk)
            if len(header) < 5:
                header += chunk[:5 - len(header)]
            if forwarding:
                try:
                    restore.stdin.write(chunk)
                    restore.stdin.flush()
                except (BrokenPipeError, OSError):
                    forwarding = False
                    try:
                        restore.stdin.close()
                    except (BrokenPipeError, OSError):
                        pass
        if forwarding:
            try:
                restore.stdin.close()
            except (BrokenPipeError, OSError):
                pass
        gpg_code = gpg.wait(timeout=TIMEOUT)
        restore_code = restore.wait(timeout=TIMEOUT)
        counter.join(timeout=TIMEOUT)
        if gpg_code != 0:
            raise ArchiveBlocked("GPG_DECRYPTION_FAILED")
        if header != b"PGDMP" or plain_bytes <= 5:
            raise ArchiveBlocked("PG_DUMP_FORMAT_INVALID")
        if restore_code != 0 or counter.is_alive() or listing[0] == 0:
            raise ArchiveBlocked("PG_RESTORE_TOC_INVALID")
        if invalid_extension[0]:
            raise ArchiveBlocked("ARCHIVE_EXTENSION_METADATA_INVALID")
        return plain_bytes, listing[0]
    finally:
        for fd in (secret_read, secret_write):
            if fd is not None:
                os.close(fd)
        for process in (restore, gpg):
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
                for pipe in (process.stdin, process.stdout):
                    if pipe is not None:
                        pipe.close()
        if counter is not None:
            counter.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-project-ref", required=True)
    parser.add_argument("--archive-dir", type=Path, default=ARCHIVE_DIR)
    args = parser.parse_args()
    print("G5_INSPECT_MODE=OFFLINE_READ_ONLY")
    try:
        archive = validated_archive(
            args.manifest, args.source_project_ref, args.archive_dir,
        )
        restore_bin = pg_restore_binary()
        if not sys.stdin.isatty():
            raise ArchiveBlocked("LOCAL_TTY_REQUIRED")
        password = getpass.getpass("Senha do backup criptografado (sem eco): ")
        bytes_read, objects = decrypt_and_check_toc(archive, password, restore_bin)
        print("G5_ARCHIVE_DECRYPTION=PASS")
        print("G5_PG_RESTORE_TOC=PASS")
        print("G5_PG_RESTORE_TOC_ENTRIES=" + str(objects))
        print("G5_DECRYPTED_ARCHIVE_BYTES=" + str(bytes_read))
        print("G5_RESTORE_TEST=NOT_PERFORMED")
        return 0
    except Exception as exc:
        print("G5_INSPECT_RESULT=BLOCKED")
        print("G5_INSPECT_ERROR=" + (
            str(exc) if isinstance(exc, ArchiveBlocked) else type(exc).__name__
        ))
        print("G5_RESTORE_TEST=NOT_PERFORMED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
