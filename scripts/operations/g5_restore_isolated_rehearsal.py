#!/usr/bin/env python3
"""G5: gated real restore rehearsal in a disposable, networkless PostgreSQL 17.

--plan only inspects the encrypted archive and local Docker image. --restore
requires separately authorized, local typed confirmation. Untrusted restored
SQL executes ONLY in a memory-backed, unprivileged, no-network, no-host-mount
container. The encrypted archive never mounts into Docker: GPG -> docker exec
pg_restore via anonymous pipes. No raw SQL, schema names, logs or credentials
appear on stdout or in a file.

A PASS here demonstrates that pg_restore completed successfully in this
isolated stock PostgreSQL container; it does NOT validate Supabase extensions,
auth, policies, permissions, Storage, external services or financial parity.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.operations.g5_archive_supabase_source import (  # noqa: E402
    ARCHIVE_DIR, ArchiveBlocked, validate_archive_passphrase,
)
from scripts.operations.g5_inspect_encrypted_source import (  # noqa: E402
    validated_archive,
)

DOCKER_SOCKET = Path("/var/run/docker.sock")
IMAGE_TAG = "postgres:17"                 # Structural tool version, never a tenant value.
IMAGE_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
NAME_PATTERN = re.compile(r"^g5-restore-[0-9a-f]{16}$")
CONTAINER_UID = "999:999"                 # Official PostgreSQL 17 Debian image.
CONTAINER_TMPFS = (
    "/var/lib/postgresql/data:rw,nosuid,nodev,size=768m,uid=999,gid=999,mode=0700",
    "/var/run/postgresql:rw,nosuid,nodev,size=16m,uid=999,gid=999,mode=0770",
    "/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777",
)
RESTORE_TIMEOUT = 3600
DOCKER_TIMEOUT = 30
READY_ATTEMPTS = 40
CATALOG_SQL = (
    "SELECT count(*) FROM pg_catalog.pg_class c "
    "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
    "WHERE c.relkind IN ('r','p') AND n.nspname NOT LIKE 'pg_%' "
    "AND n.nspname <> 'information_schema';"
)


def isolated_docker_env() -> dict[str, str]:
    """Never inherit Docker remote contexts, DB variables or app credentials."""
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": "/nonexistent", "LANG": "C"}


def docker_executable() -> list[str]:
    docker = shutil.which("docker")
    try:
        info = DOCKER_SOCKET.lstat()
    except OSError:
        raise ArchiveBlocked("LOCAL_DOCKER_SOCKET_MISSING") from None
    if (not docker or not stat.S_ISSOCK(info.st_mode)
            or info.st_uid != 0 or not DOCKER_SOCKET.is_absolute()):
        raise ArchiveBlocked("LOCAL_DOCKER_SOCKET_UNSAFE")
    return [docker, "--host=unix:///var/run/docker.sock"]


def docker_query(prefix: list[str], args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            prefix + args, env=isolated_docker_env(),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=False, timeout=DOCKER_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        raise ArchiveBlocked("LOCAL_DOCKER_UNAVAILABLE") from None


def image_id(prefix: list[str]) -> str:
    """Never pull an image implicitly or run a tag that changed after preflight."""
    p = docker_query(prefix, ["image", "inspect", "--format", "{{.Id}}", IMAGE_TAG])
    value = p.stdout.decode("ascii", "ignore").strip()
    if p.returncode != 0 or not IMAGE_SHA.fullmatch(value):
        raise ArchiveBlocked("POSTGRES17_IMAGE_NOT_CACHED")
    return value


def isolated_run_args(image: str, name: str) -> list[str]:
    if not IMAGE_SHA.fullmatch(image) or not NAME_PATTERN.fullmatch(name):
        raise ArchiveBlocked("ISOLATED_CONTAINER_INPUT_INVALID")
    # No -p/-P, -v/--volume, --mount, --privileged or network connection.
    return [
        "run", "--detach", "--rm", "--pull=never",
        "--name=" + name,
        "--label=agente-sql-langgraph.g5=isolated-rehearsal",
        "--network=none", "--read-only",
        "--user=" + CONTAINER_UID,
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit=128", "--memory=1g", "--cpus=1",
        "--log-driver=none",
        *("--tmpfs=" + target for target in CONTAINER_TMPFS),
        "--env=POSTGRES_HOST_AUTH_METHOD=trust",
        image,
        "postgres", "-c", "listen_addresses=",
    ]


def isolated_exec_args(name: str, program: str, *args: str, interactive: bool = False) -> list[str]:
    if not NAME_PATTERN.fullmatch(name) or program not in (
        "pg_isready", "postgres", "pg_restore", "psql",
    ):
        raise ArchiveBlocked("ISOLATED_COMMAND_NOT_ALLOWED")
    return ["exec", *(["--interactive"] if interactive else []),
            "--user=" + CONTAINER_UID, name, program, *args]


def check_container_isolation(prefix: list[str], name: str, image: str) -> None:
    """Fail closed if Docker created volumes, host binds, network, or privileges."""
    response = docker_query(prefix, ["inspect", "--format", "{{json .}}", name])
    if response.returncode != 0 or len(response.stdout) > 150_000:
        raise ArchiveBlocked("CONTAINER_ISOLATION_UNVERIFIED")
    try:
        info = json.loads(response.stdout)
        host = info["HostConfig"]
        config = info["Config"]
        mounts = info.get("Mounts") or []
        cap_drop = host.get("CapDrop") or []
        security = host.get("SecurityOpt") or []
        test = (
            info["Image"] == image
            and host.get("NetworkMode") == "none"
            and host.get("ReadonlyRootfs") is True
            and host.get("Privileged") is False
            and host.get("AutoRemove") is True
            and host.get("UsernsMode") not in ("host",)
            and host.get("PidMode") not in ("host",)
            and "ALL" in cap_drop
            and "no-new-privileges" in security
            and config.get("User") == CONTAINER_UID
            and config.get("Labels", {}).get(
                "agente-sql-langgraph.g5") == "isolated-rehearsal"
            and not host.get("Binds")
            and not host.get("Devices")
            and not host.get("PortBindings")
            and not info.get("NetworkSettings", {}).get("Ports")
            and all(m.get("Type") == "tmpfs" for m in mounts)
        )
    except (TypeError, ValueError, KeyError, AttributeError):
        test = False
    if not test:
        raise ArchiveBlocked("CONTAINER_ISOLATION_UNVERIFIED")


def start_container(prefix: list[str], image: str, name: str) -> None:
    if docker_query(prefix, isolated_run_args(image, name)).returncode != 0:
        raise ArchiveBlocked("ISOLATED_CONTAINER_START_FAILED")
    check_container_isolation(prefix, name, image)
    for _ in range(READY_ATTEMPTS):
        ready = docker_query(
            prefix, isolated_exec_args(
                name, "pg_isready", "-h", "/var/run/postgresql", "-U", "postgres",
            ),
        )
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        raise ArchiveBlocked("ISOLATED_POSTGRES_NOT_READY")
    ver = docker_query(prefix, isolated_exec_args(name, "postgres", "--version"))
    if ver.returncode != 0 or not re.search(rb"PostgreSQL\)\s+17\.", ver.stdout):
        # Some official images output "postgres (PostgreSQL) 17.11".
        if ver.returncode != 0 or not re.search(rb"PostgreSQL\)\s+17\.", ver.stdout):
            raise ArchiveBlocked("ISOLATED_POSTGRES_VERSION_INVALID")


def restore_stream(prefix: list[str], name: str, archive: Path, passphrase: str) -> None:
    """Stream the encrypted source through isolated Docker stdin, never a file."""
    validate_archive_passphrase(passphrase)
    gpg_binary = shutil.which("gpg")
    if not gpg_binary:
        raise ArchiveBlocked("GPG_MISSING")
    secret_read = secret_write = None
    decrypt = restore = None
    try:
        secret_read, secret_write = os.pipe()
        gpg_env = {k: os.environ[k] for k in (
            "HOME", "PATH", "LANG", "GNUPGHOME",
        ) if k in os.environ}
        decrypt = subprocess.Popen(
            [gpg_binary, "--batch", "--no-tty", "--pinentry-mode", "loopback",
             "--no-symkey-cache", "--passphrase-fd", str(secret_read),
             "--decrypt", str(archive)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=gpg_env, pass_fds=(secret_read,),
        )
        os.close(secret_read)
        secret_read = None
        with os.fdopen(secret_write, "wb") as passpipe:
            secret_write = None
            passpipe.write(passphrase.encode("ascii") + b"\n")
        assert decrypt.stdout is not None
        restore = subprocess.Popen(
            prefix + isolated_exec_args(
                name, "pg_restore", "--host=/var/run/postgresql",
                "--username=postgres", "--dbname=postgres",
                "--no-owner", "--no-acl", "--single-transaction",
                "--exit-on-error", interactive=True,
            ),
            stdin=decrypt.stdout, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, env=isolated_docker_env(),
        )
        decrypt.stdout.close()
        try:
            status = restore.wait(timeout=RESTORE_TIMEOUT)
            decrypt_status = decrypt.wait(timeout=30)
        except subprocess.TimeoutExpired:
            raise ArchiveBlocked("ISOLATED_RESTORE_TIMEOUT") from None
        if status != 0:
            raise ArchiveBlocked("ISOLATED_RESTORE_SQL_FAILED")
        if decrypt_status != 0:
            raise ArchiveBlocked("GPG_DECRYPTION_FAILED")
    finally:
        for fd in (secret_read, secret_write):
            if fd is not None:
                os.close(fd)
        for child in (restore, decrypt):
            if child is not None:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=10)


def verify_restored_tables(prefix: list[str], name: str) -> int:
    output = docker_query(
        prefix, isolated_exec_args(
            name, "psql", "-X", "--no-psqlrc", "-q", "-t", "-A",
            "-v", "ON_ERROR_STOP=1", "-h", "/var/run/postgresql",
            "-U", "postgres", "-d", "postgres", "-c", CATALOG_SQL,
        ),
    )
    count = output.stdout.decode("ascii", "ignore").strip()
    if output.returncode != 0 or not count.isdecimal():
        raise ArchiveBlocked("ISOLATED_CATALOG_CHECK_FAILED")
    n = int(count)
    if not 0 < n < 1_000_000:
        raise ArchiveBlocked("ISOLATED_RESTORED_TABLES_EMPTY")
    return n


def cleanup_container(prefix: list[str], name: str) -> bool:
    """Only the random name successfully started by this invocation."""
    docker_query(prefix, ["rm", "--force", name])
    return docker_query(prefix, ["container", "inspect", name]).returncode != 0


def rehearsed_restore(archive: Path, password: str, prefix: list[str],
                      pinned_image: str) -> int:
    if os.geteuid() != 0:
        raise ArchiveBlocked("ROOT_REQUIRED_FOR_ISOLATED_RESTORE")
    name = "g5-restore-" + secrets.token_hex(8)
    started = False
    tables = 0
    failure = None
    cleanup_ok = False
    try:
        args = isolated_run_args(pinned_image, name)
        # If the run process fails, do not remove an unrelated existing container.
        result = docker_query(prefix, args)
        if result.returncode != 0:
            raise ArchiveBlocked("ISOLATED_CONTAINER_START_FAILED")
        started = True
        check_container_isolation(prefix, name, pinned_image)
        for _ in range(READY_ATTEMPTS):
            if docker_query(prefix, isolated_exec_args(
                name, "pg_isready", "-h", "/var/run/postgresql", "-U", "postgres",
            )).returncode == 0:
                break
            time.sleep(1)
        else:
            raise ArchiveBlocked("ISOLATED_POSTGRES_NOT_READY")
        ver = docker_query(prefix, isolated_exec_args(name, "postgres", "--version"))
        if ver.returncode != 0 or not re.search(rb"PostgreSQL\)\s+17\.", ver.stdout):
            raise ArchiveBlocked("ISOLATED_POSTGRES_VERSION_INVALID")
        restore_stream(prefix, name, archive, password)
        tables = verify_restored_tables(prefix, name)
    except Exception as exc:
        failure = exc
    finally:
        if started:
            try:
                cleanup_ok = cleanup_container(prefix, name)
            except Exception:
                cleanup_ok = False
        else:
            cleanup_ok = True
    if not cleanup_ok:
        raise ArchiveBlocked("ISOLATED_CLEANUP_UNVERIFIED")
    if failure is not None:
        if isinstance(failure, ArchiveBlocked):
            raise failure
        raise ArchiveBlocked("ISOLATED_RESTORE_FAILED") from None
    return tables


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--plan", action="store_true")
    action.add_argument("--restore", action="store_true")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-project-ref", required=True)
    parser.add_argument("--archive-dir", type=Path, default=ARCHIVE_DIR)
    args = parser.parse_args()
    print("G5_REHEARSAL_MODE=" + ("PLAN" if args.plan else "RESTORE"))
    try:
        archive = validated_archive(
            args.manifest, args.source_project_ref, args.archive_dir,
        )
        prefix = docker_executable()
        pinned = image_id(prefix)
        print("G5_IMAGE_CACHED=YES")
        if args.plan:
            print("G5_REHEARSAL_READY=YES")
            print("G5_RESTORE_TEST=NOT_PERFORMED")
            return 0
        if not sys.stdin.isatty():
            raise ArchiveBlocked("LOCAL_TTY_REQUIRED")
        confirmation = input(
            "Digite RESTORE-G5-ISOLATED para iniciar ensaio em Docker sem rede: "
        )
        if confirmation != "RESTORE-G5-ISOLATED":
            raise ArchiveBlocked("ISOLATED_RESTORE_NOT_AUTHORIZED")
        passphrase = getpass.getpass("Senha do backup criptografado (sem eco): ")
        tables = rehearsed_restore(archive, passphrase, prefix, pinned)
        print("G5_RESTORED_TABLES=" + str(tables))
        print("G5_ISOLATED_CONTAINER_CLEANUP=PASS")
        print("G5_RESTORE_TEST=PASS")
        print("G5_SUPABASE_FULL_RECOVERY=NOT_ATTESTED")
        return 0
    except Exception as exc:
        print("G5_REHEARSAL_RESULT=BLOCKED")
        print("G5_REHEARSAL_ERROR=" + (
            str(exc) if isinstance(exc, ArchiveBlocked) else type(exc).__name__
        ))
        print("G5_RESTORE_TEST=NOT_VERIFIED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
