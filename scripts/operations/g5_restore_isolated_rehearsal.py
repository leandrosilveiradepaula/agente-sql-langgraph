#!/usr/bin/env python3
"""G5: gated real restore rehearsal in a disposable, networkless PostgreSQL 17.

--plan only inspects the encrypted archive and local Docker image. --restore
requires separately authorized, local typed confirmation. Untrusted restored
SQL executes ONLY in a memory-backed, unprivileged, no-network, no-host-mount
container. The encrypted archive never mounts into Docker: GPG -> docker exec
pg_restore via anonymous pipes. No raw SQL, schema names, logs or credentials
appear on stdout or in a file.

--boot-test for an explicitly SHA-pinned Supabase Postgres 17 image performs
only rootless initdb, pg_isready and cleanup in anonymous tmpfs; it never reads
or restores the real encrypted backup. The Supabase image default entrypoint
and bundled init migrations are intentionally bypassed: they are not needed
to attest an isolated PostgreSQL engine, and may demand external secrets.
A full restore (with a fresh human gate) may still fail because the raw
pg_dump contains Supabase-managed internal objects/roles or Vault secrets.

A PASS for a future isolated restore does NOT validate Supabase Auth, Vault
key continuity, Storage, external services, tenant parity or retirement.
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
import stat
import subprocess
import sys
import threading
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
IMAGE_TAG = "postgres:17"                 # Legacy community image.
IMAGE_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
IMAGE_REF = re.compile(
    r"^(?:postgres:17|supabase/postgres:17\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,4})$"
)
POSTGRES_UID = re.compile(rb"^[1-9][0-9]{0,5}$")
NAME_PATTERN = re.compile(r"^g5-restore-[0-9a-f]{16}$")
CONTAINER_UID = "999:999"                 # Official PostgreSQL 17 Debian image.
CONTAINER_TMPFS = (
    "/var/lib/postgresql/data:rw,nosuid,nodev,size=768m,uid=999,gid=999,mode=0700",
    "/var/run/postgresql:rw,nosuid,nodev,size=16m,uid=999,gid=999,mode=0770",
    "/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777",
)
# Runtime boot is deliberately not a full Supabase initialization. All paths
# are memory-backed, and shell statements below are static structural logic.
SUPABASE_POSTGRES_BOOT = (
    "set -eu; "
    "initdb -D /var/lib/postgresql/data --username=postgres "
    "--auth-local=trust --auth-host=reject --no-instructions "
    ">/dev/null 2>&1; "
    "exec postgres -D /var/lib/postgresql/data "
    "-c listen_addresses= "
    "-c unix_socket_directories=/var/run/postgresql "
    "-c ssl=off"
)

def supabase_tmpfs(uid: int, gid: int) -> tuple[str, ...]:
    if not (1 <= uid <= 65534 and 1 <= gid <= 65534):
        raise ArchiveBlocked("ISOLATED_IMAGE_UID_INVALID")
    return (
        "/var/lib/postgresql/data:rw,nosuid,nodev,size=768m,"
        + f"uid={uid},gid={gid},mode=0700",
        "/var/run/postgresql:rw,nosuid,nodev,size=16m,"
        + f"uid={uid},gid={gid},mode=0770",
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

# Only these operator-safe classification labels may leave process memory.
# The raw pg_restore/Docker stderr can contain SQL, roles, identifiers and data.
RESTORE_FAILURE_CATEGORIES = frozenset((
    "EXTENSION_UNAVAILABLE", "EXTENSION_LIBRARY_UNAVAILABLE",
    "ROLE_MISSING", "OBJECT_DEPENDENCY_MISSING", "PERMISSION_DENIED",
    "OBJECT_CONFLICT", "RESOURCE_LIMIT", "SERVER_SETTING_UNSUPPORTED",
    "ARCHIVE_INVALID", "SQL_SYNTAX_UNSUPPORTED", "UNCLASSIFIED",
))


class IsolatedRestoreSQLFailure(ArchiveBlocked):
    def __init__(self, category: str) -> None:
        self.category = (
            category if category in RESTORE_FAILURE_CATEGORIES else "UNCLASSIFIED"
        )
        super().__init__("ISOLATED_RESTORE_SQL_FAILED")


def classify_restore_stderr(fragment: bytes) -> str | None:
    """Return a fixed category from an ephemeral error fragment, never raw text."""
    line = fragment[:8192].lower()
    if b"error:" not in line and b"fatal:" not in line:
        return None
    if (b"extension control file" in line
            or (b"extension" in line and b"is not available" in line)):
        return "EXTENSION_UNAVAILABLE"
    if (b"could not access file" in line
            or (b"shared object" in line and b"no such file" in line)):
        return "EXTENSION_LIBRARY_UNAVAILABLE"
    if ((b"role" in line and b"does not exist" in line)
            or b"must be member of role" in line):
        return "ROLE_MISSING"
    if (b"permission denied" in line or b"must be superuser" in line
            or b"must be owner of" in line or b"insufficient privilege" in line):
        return "PERMISSION_DENIED"
    if (b"does not exist" in line and any(
            kind in line for kind in (
                b"schema", b"function", b"type", b"relation", b"operator",
                b"collation", b"language", b"sequence", b"table",
            ))):
        return "OBJECT_DEPENDENCY_MISSING"
    if b"already exists" in line or b"duplicate key value" in line:
        return "OBJECT_CONFLICT"
    if (b"no space left on device" in line or b"out of memory" in line
            or b"disk full" in line or b"could not resize shared memory" in line):
        return "RESOURCE_LIMIT"
    if (b"unrecognized configuration parameter" in line
            or b"cannot change run-time parameter" in line):
        return "SERVER_SETTING_UNSUPPORTED"
    if (b"not a valid archive" in line
            or b"does not appear to be a valid archive" in line
            or b"unsupported version" in line
            or b"could not read from input file" in line):
        return "ARCHIVE_INVALID"
    if b"syntax error at or near" in line:
        return "SQL_SYNTAX_UNSUPPORTED"
    return None


def consume_restore_stderr(pipe, categories: list[str]) -> None:
    """Drain all stderr on a separate thread; persist ONLY the first safe label."""
    try:
        for chunk in iter(lambda: pipe.readline(8192), b""):
            category = classify_restore_stderr(chunk)
            if category is not None and not categories:
                categories.append(category)
    except (OSError, ValueError):
        return


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


def image_id(prefix: list[str], image_ref: str = IMAGE_TAG) -> str:
    """Only cached allowlisted images; pin to immutable SHA before use."""
    if not IMAGE_REF.fullmatch(image_ref):
        raise ArchiveBlocked("ISOLATED_IMAGE_REF_INVALID")
    p = docker_query(prefix, ["image", "inspect", "--format", "{{.Id}}", image_ref])
    value = p.stdout.decode("ascii", "ignore").strip()
    if p.returncode != 0 or not IMAGE_SHA.fullmatch(value):
        raise ArchiveBlocked("POSTGRES17_IMAGE_NOT_CACHED")
    return value


def supabase_image_user(prefix: list[str], image_sha: str) -> str:
    """Read image's real postgres UID/GID, no root or fixed Debian UID assumptions."""
    if not IMAGE_SHA.fullmatch(image_sha):
        raise ArchiveBlocked("ISOLATED_IMAGE_ID_INVALID")
    result = docker_query(prefix, [
        "run", "--rm", "--pull=never", "--network=none", "--read-only",
        "--user=65534:65534", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--pids-limit=24",
        "--memory=128m", "--cpus=0.25", "--log-driver=none",
        "--entrypoint=/bin/sh", image_sha, "-ceu",
        "command -v initdb >/dev/null; command -v postgres >/dev/null; "
        "id -u postgres; id -g postgres",
    ])
    if result.returncode != 0:
        raise ArchiveBlocked("ISOLATED_IMAGE_UID_PROBE_FAILED")
    parts = result.stdout.splitlines()
    if len(parts) != 2 or any(POSTGRES_UID.fullmatch(v) is None for v in parts):
        raise ArchiveBlocked("ISOLATED_IMAGE_UID_INVALID")
    uid, gid = (int(part) for part in parts)
    supabase_tmpfs(uid, gid)  # Validate supported non-root numeric identity.
    return f"{uid}:{gid}"


def isolated_run_args(image: str, name: str, runtime_user: str | None = None) -> list[str]:
    if not IMAGE_SHA.fullmatch(image) or not NAME_PATTERN.fullmatch(name):
        raise ArchiveBlocked("ISOLATED_CONTAINER_INPUT_INVALID")
    if runtime_user is None:
        user = CONTAINER_UID
        tmpfs = CONTAINER_TMPFS
    else:
        if not re.fullmatch(r"[1-9][0-9]{0,5}:[1-9][0-9]{0,5}", runtime_user):
            raise ArchiveBlocked("ISOLATED_IMAGE_UID_INVALID")
        uid, gid = [int(x) for x in runtime_user.split(":")]
        user = runtime_user
        tmpfs = supabase_tmpfs(uid, gid)
    # No -p/-P, -v/--volume, --mount, --privileged or network connection.
    cmd = [
        "run", "--detach", "--rm", "--pull=never",
        "--name=" + name,
        "--label=agente-sql-langgraph.g5=isolated-rehearsal",
        "--network=none", "--read-only",
        "--user=" + user,
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit=128", "--memory=1g", "--memory-swap=1g",
        "--cpus=1", "--log-driver=none",
        *("--tmpfs=" + target for target in tmpfs),
    ]
    if runtime_user is not None:
        # Bypass Supabase's managed initialization/migrations on the image.
        # Init a synthetic scratch cluster only; no project roles/keys are used.
        return cmd + [
            "--env=HOME=/tmp",
            "--entrypoint=/bin/sh", image, "-ceu", SUPABASE_POSTGRES_BOOT,
        ]
    return cmd + [
        "--env=POSTGRES_HOST_AUTH_METHOD=trust", image,
        "postgres", "-c", "listen_addresses=",
    ]


def isolated_exec_args(name: str, program: str, *args: str,
                       interactive: bool = False,
                       runtime_user: str | None = None) -> list[str]:
    if not NAME_PATTERN.fullmatch(name) or program not in (
        "pg_isready", "postgres", "pg_restore", "psql",
    ):
        raise ArchiveBlocked("ISOLATED_COMMAND_NOT_ALLOWED")
    user = runtime_user if runtime_user is not None else CONTAINER_UID
    if not re.fullmatch(r"[1-9][0-9]{0,5}:[1-9][0-9]{0,5}", user):
        raise ArchiveBlocked("ISOLATED_IMAGE_UID_INVALID")
    return ["exec", *(["--interactive"] if interactive else []),
            "--user=" + user, name, program, *args]


def check_container_isolation(prefix: list[str], name: str, image: str,
                              runtime_user: str | None = None) -> None:
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
            and config.get("User") == (
                runtime_user if runtime_user is not None else CONTAINER_UID
            )
            and config.get("Labels", {}).get(
                "agente-sql-langgraph.g5") == "isolated-rehearsal"
            and not host.get("Binds")
            and not host.get("Devices")
            and not host.get("PortBindings")
            # Docker may advertise EXPOSE 5432/tcp with a null binding.
            and all(v in (None, []) for v in
                    (info.get("NetworkSettings", {}).get("Ports") or {}).values())
            and all(m.get("Type") == "tmpfs" for m in mounts)
        )
        if test and runtime_user is not None:
            # The Supabase image must not sneak its default entrypoint,
            # init migrations, host logging, or a persisted PGDATA volume
            # into the scratch-only test. All database files are anonymous.
            uid, gid = [int(x) for x in runtime_user.split(":")]
            expected_tmpfs = {
                t.split(":", 1)[0] for t in supabase_tmpfs(uid, gid)
            }
            tmpfs = host.get("Tmpfs") or {}
            test = (
                config.get("Entrypoint") == ["/bin/sh"]
                and config.get("Cmd") == ["-ceu", SUPABASE_POSTGRES_BOOT]
                and (host.get("LogConfig") or {}).get("Type") == "none"
                and isinstance(tmpfs, dict)
                and set(tmpfs) == expected_tmpfs
                and all(
                    "uid=" + str(uid) in tmpfs.get(mount, "")
                    and "gid=" + str(gid) in tmpfs.get(mount, "")
                    for mount in (
                        "/var/lib/postgresql/data",
                        "/var/run/postgresql",
                    )
                )
                and not host.get("VolumesFrom")
                and not host.get("IpcMode") == "host"
            )
    except (TypeError, ValueError, KeyError, AttributeError):
        test = False
    if not test:
        raise ArchiveBlocked("CONTAINER_ISOLATION_UNVERIFIED")


def restore_stream(prefix: list[str], name: str, archive: Path, passphrase: str,
                   runtime_user: str | None = None) -> None:
    """Stream the encrypted source through isolated Docker stdin, never a file."""
    validate_archive_passphrase(passphrase)
    gpg_binary = shutil.which("gpg")
    if not gpg_binary:
        raise ArchiveBlocked("GPG_MISSING")
    secret_read = secret_write = None
    decrypt = restore = stderr_reader = None
    safe_categories: list[str] = []
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
                runtime_user=runtime_user,
            ),
            stdin=decrypt.stdout, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, env=isolated_docker_env(),
        )
        assert restore.stderr is not None
        stderr_reader = threading.Thread(
            target=consume_restore_stderr,
            args=(restore.stderr, safe_categories),
            daemon=True,
        )
        stderr_reader.start()
        decrypt.stdout.close()
        try:
            status = restore.wait(timeout=RESTORE_TIMEOUT)
            decrypt_status = decrypt.wait(timeout=30)
        except subprocess.TimeoutExpired:
            raise ArchiveBlocked("ISOLATED_RESTORE_TIMEOUT") from None
        stderr_reader.join(timeout=10)
        if stderr_reader.is_alive():
            raise ArchiveBlocked("ISOLATED_RESTORE_STDERR_DRAIN_UNVERIFIED")
        if status != 0:
            raise IsolatedRestoreSQLFailure(
                safe_categories[0] if safe_categories else "UNCLASSIFIED"
            )
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
        if stderr_reader is not None:
            stderr_reader.join(timeout=5)
        if restore is not None and restore.stderr is not None:
            restore.stderr.close()


def verify_restored_tables(prefix: list[str], name: str,
                           runtime_user: str | None = None) -> int:
    output = docker_query(
        prefix, isolated_exec_args(
            name, "psql", "-X", "--no-psqlrc", "-q", "-t", "-A",
            "-v", "ON_ERROR_STOP=1", "-h", "/var/run/postgresql",
            "-U", "postgres", "-d", "postgres", "-c", CATALOG_SQL,
            runtime_user=runtime_user,
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
    # A disconnected daemon cannot be mistaken for a cleaned-up container.
    if docker_query(prefix, ["version", "--format", "{{.Server.Version}}"]).returncode != 0:
        return False
    return docker_query(prefix, ["container", "inspect", name]).returncode != 0


def rehearsed_restore(archive: Path, password: str, prefix: list[str],
                      pinned_image: str, runtime_user: str | None = None,
                      boot_only: bool = False) -> int:
    if os.geteuid() != 0:
        raise ArchiveBlocked("ROOT_REQUIRED_FOR_ISOLATED_RESTORE")
    if not boot_only:
        validate_archive_passphrase(password)
    name = "g5-restore-" + secrets.token_hex(8)
    started = False
    tables = 0
    failure = None
    cleanup_ok = False
    try:
        args = isolated_run_args(pinned_image, name, runtime_user=runtime_user)
        # If the run process fails, do not remove an unrelated existing container.
        result = docker_query(prefix, args)
        if result.returncode != 0:
            raise ArchiveBlocked("ISOLATED_CONTAINER_START_FAILED")
        started = True
        check_container_isolation(
            prefix, name, pinned_image, runtime_user=runtime_user
        )
        for _ in range(READY_ATTEMPTS):
            if docker_query(prefix, isolated_exec_args(
                name, "pg_isready", "-h", "/var/run/postgresql", "-U", "postgres",
                runtime_user=runtime_user,
            )).returncode == 0:
                break
            time.sleep(1)
        else:
            raise ArchiveBlocked("ISOLATED_POSTGRES_NOT_READY")
        ver = docker_query(prefix, isolated_exec_args(
            name, "postgres", "--version", runtime_user=runtime_user,
        ))
        if ver.returncode != 0 or not re.search(rb"PostgreSQL\)\s+17\.", ver.stdout):
            raise ArchiveBlocked("ISOLATED_POSTGRES_VERSION_INVALID")
        if not boot_only:
            if runtime_user is None:
                # Preserve tested community-image call contract.
                restore_stream(prefix, name, archive, password)
                tables = verify_restored_tables(prefix, name)
            else:
                restore_stream(
                    prefix, name, archive, password, runtime_user=runtime_user,
                )
                tables = verify_restored_tables(
                    prefix, name, runtime_user=runtime_user,
                )
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
    action.add_argument("--boot-test", action="store_true",
                        help="scratch PostgreSQL bootstrap and cleanup only; no dump")
    parser.add_argument("--image-ref", default=IMAGE_TAG,
                        help="allowlisted, cached PostgreSQL 17 image")
    parser.add_argument("--expected-image-sha",
                        help="mandatory immutable image ID for non-default images")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-project-ref", required=True)
    parser.add_argument("--archive-dir", type=Path, default=ARCHIVE_DIR)
    args = parser.parse_args()
    mode = "PLAN" if args.plan else "BOOT_TEST" if args.boot_test else "RESTORE"
    print("G5_REHEARSAL_MODE=" + mode)
    try:
        archive = validated_archive(
            args.manifest, args.source_project_ref, args.archive_dir,
        )
        if not IMAGE_REF.fullmatch(args.image_ref):
            raise ArchiveBlocked("ISOLATED_IMAGE_REF_INVALID")
        prefix = docker_executable()
        pinned = image_id(prefix, args.image_ref)
        if args.image_ref != IMAGE_TAG:
            if (not args.expected_image_sha or
                    args.expected_image_sha != pinned):
                raise ArchiveBlocked("ISOLATED_IMAGE_SHA_NOT_ATTESTED")
        elif args.expected_image_sha and args.expected_image_sha != pinned:
            raise ArchiveBlocked("ISOLATED_IMAGE_SHA_NOT_ATTESTED")
        runtime_user = (
            supabase_image_user(prefix, pinned)
            if args.image_ref != IMAGE_TAG else None
        )
        print("G5_IMAGE_CACHED=YES")
        print("G5_IMAGE_ID=" + pinned)
        if args.plan:
            print("G5_REHEARSAL_READY=YES")
            print("G5_RESTORE_TEST=NOT_PERFORMED")
            return 0
        if args.boot_test:
            rehearsed_restore(
                archive, "", prefix, pinned,
                runtime_user=runtime_user, boot_only=True,
            )
            print("G5_BOOT_TEST=PASS")
            print("G5_ISOLATED_CONTAINER_CLEANUP=PASS")
            print("G5_RESTORE_TEST=NOT_PERFORMED")
            return 0
        if not sys.stdin.isatty():
            raise ArchiveBlocked("LOCAL_TTY_REQUIRED")
        token = (
            "RESTORE-G5-SUPABASE-ISOLATED"
            if runtime_user is not None else "RESTORE-G5-ISOLATED"
        )
        confirmation = input(
            "Digite " + token + " para restaurar apenas em Docker sem rede: "
        )
        if confirmation != token:
            raise ArchiveBlocked("ISOLATED_RESTORE_NOT_AUTHORIZED")
        passphrase = getpass.getpass("Senha do backup criptografado (sem eco): ")
        if runtime_user is None:
            tables = rehearsed_restore(archive, passphrase, prefix, pinned)
        else:
            tables = rehearsed_restore(
                archive, passphrase, prefix, pinned, runtime_user=runtime_user,
            )
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
        if isinstance(exc, IsolatedRestoreSQLFailure):
            print("G5_RESTORE_FAILURE_CATEGORY=" + exc.category)
        print("G5_RESTORE_TEST=" + (
            "NOT_PERFORMED" if args.plan or args.boot_test else "NOT_VERIFIED"
        ))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
