#!/usr/bin/env python3
"""Guarded Shadow TEST evidence DSN switch with verified TLS and rollback.

No financial SQL, n8n changes, image builds, or LLM invocations. All business
identity and deployment choices are operator-supplied, never inferred.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import quote, urlencode, urlunsplit

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb

IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
PROJECT = re.compile(r"^[a-z]{20}$")
ORGANIZATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class SwitchBlocked(Exception):
    """Only bounded, non-secret diagnostic codes are exposed."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise SwitchBlocked(code)


def run(args: list[str], *, stdin: str | None = None, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    # stdout/stderr can contain database URLs, so callers must never dump them.
    return subprocess.run(args, input=stdin, text=True, capture_output=True, timeout=timeout, check=False)


def docker(*args: str, stdin: str | None = None, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return run(["docker", *args], stdin=stdin, timeout=timeout)


def compose(deploy_dir: Path, *args: str, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return run(["docker", "compose", "-f", str(deploy_dir / "compose.yaml"), *args], timeout=timeout)


def read_password(path: Path) -> str:
    require(os.geteuid() == 0, "ROOT_REQUIRED")
    require(not path.is_symlink(), "PASSWORD_FILE_SYMLINK")
    data = path.lstat()
    require(stat.S_ISREG(data.st_mode) and data.st_uid == 0 and not data.st_mode & 0o077, "PASSWORD_FILE_PERMISSIONS")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        value = handle.read().strip()
    require(len(value) >= 40 and not any(ch.isspace() for ch in value), "PASSWORD_INVALID")
    return value


def validate_target(context: str, project_ref: str, role: str) -> str:
    options = conninfo_to_dict(context)
    host = options.get("host", "").lower().rstrip(".")
    user = options.get("user", "")
    require(options.get("dbname") == "postgres", "DATABASE_NOT_POSTGRES")
    if host == f"db.{project_ref}.supabase.co":
        require(bool(user), "CONTEXT_IDENTITY_MISSING")
        return role
    if host.endswith(".pooler.supabase.com") and user.endswith("." + project_ref):
        return f"{role}.{project_ref}"
    raise SwitchBlocked("CONTEXT_NOT_TARGET_PROJECT")


def candidate_uri(context: str, *, role_login: str, password: str, ca: str) -> str:
    """Produce a Docker env-safe URI, not a space-delimited libpq conninfo."""
    trial = make_conninfo(
        context, user=role_login, password=password, sslmode="verify-full", sslrootcert=ca,
    )
    d = conninfo_to_dict(trial)
    host = d.pop("host")
    port = d.pop("port", "")
    database = d.pop("dbname")
    user = d.pop("user")
    pw = d.pop("password")
    d.pop("passfile", None)
    require(database == "postgres", "DATABASE_NOT_POSTGRES")
    netloc = f"{quote(user, safe='')}:{quote(pw, safe='')}@{host}"
    if port:
        netloc += f":{port}"
    return urlunsplit(("postgresql", netloc, "/postgres", urlencode(d), ""))


def check_login(conninfo: str, role: str, organization_id: str, *, smoke: bool) -> None:
    with psycopg.connect(conninfo, connect_timeout=12) as connection:
        require(connection.execute("SELECT session_user, current_database()").fetchone() == (role, "postgres"), "LOGIN_ROLE_WRONG")
        require(connection.execute(
            "SELECT organization_id FROM langgraph_internal.shadow_role_tenants"
        ).fetchall() == [(organization_id,)], "LOGIN_TENANT_SCOPE_WRONG")
        require(connection.execute(
            "SELECT count(*) FROM public.langgraph_shadow_runs WHERE (principal->>'organization_id') IS DISTINCT FROM %s",
            (organization_id,),
        ).fetchone() == (0,), "CROSS_TENANT_EVIDENCE_VISIBLE")
        require(connection.execute(
            "SELECT has_table_privilege(current_user,'public.langgraph_shadow_runs','DELETE')"
        ).fetchone() == (False,), "DELETE_PRIVILEGE_FOUND")
        if not smoke:
            return
        identifier = "shadow-tls-smoke-" + uuid.uuid4().hex
        insert = """INSERT INTO public.langgraph_shadow_runs
            (shadow_record_id, agent_run_id, run_id, event_type, contract_version,
             status, created_at, principal, evidence_fingerprint)
            VALUES (%s,%s,%s,'generate','1','started',now(),%s,%s)"""
        try:
            connection.execute(insert, (
                identifier, identifier, identifier,
                Jsonb({"organization_id": organization_id}), identifier,
            ))
            require(connection.execute(
                "UPDATE public.langgraph_shadow_runs SET updated_at=now() WHERE shadow_record_id=%s",
                (identifier,),
            ).rowcount == 1, "EVIDENCE_UPDATE_NOT_ALLOWED")
            blocked = False
            try:
                with connection.transaction():
                    connection.execute(insert, (
                        identifier + "-foreign", identifier, identifier,
                        Jsonb({"organization_id": organization_id + "-foreign"}), identifier,
                    ))
            except psycopg.Error:
                blocked = True
            require(blocked, "CROSS_TENANT_INSERT_ALLOWED")
        finally:
            # Smoke must never persist synthetic rows in DEMO.
            connection.rollback()


def check_inside_container(container: str, uri: str, *, role: str, organization_id: str) -> None:
    code = """import sys,psycopg
try:
    with psycopg.connect(sys.stdin.read(), connect_timeout=12) as db:
        identity = db.execute('SELECT session_user').fetchone()[0]
        scope = db.execute('SELECT organization_id FROM langgraph_internal.shadow_role_tenants').fetchall()
        assert identity == sys.argv[1] and scope == [(sys.argv[2],)]
        db.execute('SELECT count(*) FROM public.langgraph_shadow_runs').fetchone()
except Exception:
    sys.exit(2)
"""
    result = docker("exec", "-i", container, "python", "-c", code, role, organization_id, stdin=uri, timeout=20)
    require(result.returncode == 0, "CONTAINER_TLS_LOGIN_FAILED")


def validated_candidate(context: str, *, container: str, project_ref: str,
                        role: str, password: str, organization_id: str) -> str:
    role_login = validate_target(context, project_ref, role)
    existing_ca = conninfo_to_dict(context).get("sslrootcert")
    cas = dict.fromkeys([existing_ca, "system", "/etc/ssl/certs/ca-certificates.crt"])
    for ca in cas:
        if not ca:
            continue
        try:
            uri = candidate_uri(context, role_login=role_login, password=password, ca=ca)
            # Both shells MUST verify certificate+hostname before switching.
            check_login(uri, role, organization_id, smoke=True)
            check_inside_container(container, uri, role=role, organization_id=organization_id)
            return uri
        except (psycopg.Error, SwitchBlocked, ValueError, OSError, subprocess.TimeoutExpired):
            continue
    raise SwitchBlocked("VERIFY_FULL_NOT_AVAILABLE_ON_BOTH_HOST_AND_CONTAINER")


def env_value(lines: list[str], key: str, *, required: bool = True) -> str | None:
    raw = [line.partition("=")[2] for line in lines if line.startswith(key + "=")]
    require(len(raw) == 1 if required else len(raw) < 2, "ENV_KEY_INVALID")
    if not raw:
        return None
    v = raw[0]
    return v[1:-1] if len(v) > 1 and v[0] in {"'", '"'} and v[-1] == v[0] else v


def patched_env(lines: list[str], uri: str, organization_id: str) -> str:
    require(env_value(lines, "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") == "false", "REAL_SQL_FLAG_NOT_FALSE")
    env_value(lines, "LANGGRAPH_SHADOW_DATABASE_DSN")
    existing_tenant = env_value(lines, "LANGGRAPH_EXPECTED_ORGANIZATION_ID", required=False)
    require(existing_tenant in {None, organization_id}, "EXISTING_TENANT_PIN_DRIFT")
    replaced = list(lines)
    for key, value in (
        ("LANGGRAPH_SHADOW_DATABASE_DSN", uri),
        ("LANGGRAPH_EXPECTED_ORGANIZATION_ID", organization_id),
    ):
        found = [i for i, line in enumerate(replaced) if line.startswith(key + "=")]
        require(len(found) < 2, "DUPLICATE_ENV_KEY")
        if found:
            replaced[found[0]] = key + "=" + value
        else:
            replaced.append(key + "=" + value)
    return "\n".join(replaced) + "\n"


def atomic_replace_env(path: Path, content: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".shadow-evidence-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def healthy(container: str, *, timeout_seconds: int) -> bool:
    for _ in range(max(1, timeout_seconds // 2)):
        res = docker("inspect", container, "--format", "{{if .State.Health}}{{.State.Health.Status}}{{end}}")
        if res.returncode == 0 and res.stdout.strip() == "healthy":
            return True
        time.sleep(2)
    return False


def verify_api(container: str, organization_id: str) -> None:
    code = """import os,sys,json,uuid,urllib.request
assert os.environ.get('LANGGRAPH_ALLOW_REAL_SQL_EXECUTION')=='false'
assert os.environ.get('LANGGRAPH_EXPECTED_ORGANIZATION_ID')==sys.argv[1]
base='http://127.0.0.1:'+os.getenv('LANGGRAPH_HTTP_PORT','8000')
url=base+'/v1/internal/agent-runs/shadow-switch-'+uuid.uuid4().hex+'/shadow-runs?limit=1'
req=urllib.request.Request(url,headers={'Authorization':'Bearer '+os.environ['LANGGRAPH_S2S_TOKEN']})
with urllib.request.urlopen(req,timeout=12) as response:
    assert response.status==200 and json.load(response).get('items')==[]
"""
    result = docker("exec", container, "python", "-c", code, organization_id, timeout=20)
    require(result.returncode == 0, "CORRELATED_EVIDENCE_READ_FAILED")


def switch(*, deploy_dir: Path, service: str, container: str, envfile: Path,
           uri: str, organization_id: str, original_lines: list[str]) -> str:
    require(os.geteuid() == 0, "ROOT_REQUIRED")
    require(envfile.is_file() and not envfile.is_symlink(), "ENV_FILE_UNSAFE")
    require((deploy_dir / "compose.yaml").is_file(), "COMPOSE_NOT_FOUND")
    image = docker("inspect", container, "--format", "{{.Config.Image}}")
    expected = compose(deploy_dir, "config", "--images")
    require(image.returncode == 0 and expected.returncode == 0, "IMAGE_INSPECTION_FAILED")
    require(expected.stdout.strip().splitlines() == [image.stdout.strip()], "IMAGE_DRIFT")

    backup_dir = Path(tempfile.mkdtemp(prefix="shadow-env-backup.", dir="/root"))
    original = backup_dir / "shadow-test.env"
    shutil.copy2(envfile, original)
    original.chmod(0o600)
    changed = False
    try:
        atomic_replace_env(envfile, patched_env(original_lines, uri, organization_id))
        changed = True
        print("SHADOW_ENV_UPDATED=PASS", flush=True)
        validate = compose(deploy_dir, "config", "--quiet", timeout=20)
        require(validate.returncode == 0, "COMPOSE_CONFIG_INVALID")
        up = compose(deploy_dir, "up", "-d", "--no-deps", "--no-build", "--force-recreate", service)
        require(up.returncode == 0, "SHADOW_RECREATE_FAILED")
        require(healthy(container, timeout_seconds=90), "SHADOW_HEALTH_FAILED")
        verify_api(container, organization_id)
        changed = False
        return str(backup_dir)
    except Exception:
        if changed:
            shutil.copy2(original, envfile)
            restored = compose(deploy_dir, "up", "-d", "--no-deps", "--no-build", "--force-recreate", service)
            print("ROLLBACK=" + ("VERIFIED" if restored.returncode == 0 and healthy(container, timeout_seconds=90) else "FAILED"), flush=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-ref", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--login-role", required=True)
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--deploy-dir", type=Path, required=True)
    parser.add_argument("--shadow-container", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--apply", action="store_true", help="Authorized, rollback-protected recreation of Shadow TEST")
    args = parser.parse_args()
    try:
        require(PROJECT.fullmatch(args.project_ref) is not None, "PROJECT_REF_INVALID")
        require(ORGANIZATION.fullmatch(args.organization_id) is not None, "ORGANIZATION_ID_INVALID")
        require(IDENTIFIER.fullmatch(args.login_role) is not None, "LOGIN_ROLE_INVALID")
        require(IDENTIFIER.fullmatch(args.service.replace('-', '_')) is not None, "SERVICE_INVALID")
        envfile = args.deploy_dir / "shadow-test.env"
        require(os.geteuid() == 0 and envfile.is_file() and not envfile.is_symlink(), "SHADOW_ENV_MISSING")
        original_lines = envfile.read_text(encoding="utf-8").splitlines()
        patched_env(original_lines, "placeholder", args.organization_id)  # strict flag and pin preflight
        password = read_password(args.password_file)
        state = docker("inspect", args.shadow_container, "--format", "{{json .Config.Env}}")
        require(state.returncode == 0, "SHADOW_CONTAINER_MISSING")
        runtime_env = dict(item.split("=", 1) for item in json.loads(state.stdout) if "=" in item)
        require(runtime_env.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") == "false", "ACTIVE_REAL_SQL_FLAG_NOT_FALSE")
        candidate = validated_candidate(
            runtime_env["CONTEXT_POSTGRES_DSN"],
            container=args.shadow_container, project_ref=args.project_ref,
            role=args.login_role, password=password, organization_id=args.organization_id,
        )
        print("RESTRICTED_LOGIN=PASS")
        print("TENANT_RLS_SMOKE=PASS_ROLLBACK_ONLY")
        print("TLS_VERIFY_FULL=PASS_ON_HOST_AND_CONTAINER")
        if not args.apply:
            print("SHADOW_SWITCH=DRY_RUN_ONLY")
            print("LLM_CALLS_THIS_PROCEDURE=0")
            print("REAL_FINANCIAL_SQL_EXECUTED=false")
            return 0
        backup = switch(
            deploy_dir=args.deploy_dir, service=args.service, container=args.shadow_container,
            envfile=envfile, uri=candidate, organization_id=args.organization_id,
            original_lines=original_lines,
        )
        print("SHADOW_SWITCH=PASS")
        print("CORRELATED_EVIDENCE_READ=PASS")
        print("SHADOW_TEST=HEALTHY")
        print("REAL_SQL_EXECUTION=false")
        print("N8N_OFFICIAL_MODIFIED=false")
        print("LLM_CALLS_THIS_PROCEDURE=0")
        print("BACKUP_DIR=" + backup)
        return 0
    except Exception as exc:
        # DB and Docker exceptions may include credentials. Never print them.
        print("SHADOW_SWITCH=BLOCKED")
        code = str(exc) if isinstance(exc, SwitchBlocked) else type(exc).__name__
        print("REASON=" + code)
        return 2


if __name__ == "__main__":
    sys.exit(main())
