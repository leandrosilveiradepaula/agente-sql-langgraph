#!/usr/bin/env python3
"""P3: preflight and *separately authorized* tenant-scoped Shadow PostgreSQL login.

Default mode reads metadata only; --apply creates exactly one login/binding
after local typed confirmation. Credentials stay in a root-only private file.
It NEVER edits LangGraph environment, n8n, financial data or existing evidence.
Do not infer organization_id from historic Shadow records or an LLM.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.operations.g1_readonly_rollout import (  # noqa: E402
    require_verified_tls_dsn,
    scram_verifier,
)

ORG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
PROJECT_PATTERN = re.compile(r"^[a-z]{20}$")
PRIVATE_DIR = Path("/root/.local/share/agente-sql-langgraph/shadow-logins")
EXPECTED_POLICIES = {
    ("public", "langgraph_shadow_runs", "shadow_runtime_select", "SELECT"),
    ("public", "langgraph_shadow_runs", "shadow_runtime_insert", "INSERT"),
    ("public", "langgraph_shadow_runs", "shadow_runtime_update", "UPDATE"),
    ("langgraph_internal", "shadow_role_tenants", "shadow_role_tenants_self_select", "SELECT"),
}
ALLOWED_RELATIONS = {
    ("public", "langgraph_shadow_runs"),
    ("langgraph_internal", "shadow_role_tenants"),
}


class ProvisionBlocked(RuntimeError):
    """Only nonsensitive error codes may be emitted to terminal."""


def validate_project_and_org(project_ref: str, organization_id: str) -> None:
    if not PROJECT_PATTERN.fullmatch(project_ref):
        raise ProvisionBlocked("PROJECT_REF_INVALID")
    if not ORG_PATTERN.fullmatch(organization_id):
        raise ProvisionBlocked("ORGANIZATION_ID_INVALID")


def login_role_for(organization_id: str) -> str:
    if not ORG_PATTERN.fullmatch(organization_id):
        raise ProvisionBlocked("ORGANIZATION_ID_INVALID")
    return "lgshadow_" + hashlib.sha256(organization_id.encode("utf-8")).hexdigest()[:20]


def login_dsn_for(admin_dsn: str, project_ref: str, role: str, password: str) -> str:
    require_verified_tls_dsn(admin_dsn, "postgres", project_ref)
    parsed = urlparse(admin_dsn)
    host = parsed.hostname
    if not host or not parsed.port:
        raise ProvisionBlocked("ADMIN_DSN_HOST_INVALID")
    username = f"{role}.{project_ref}" if host.endswith(".pooler.supabase.com") else role
    netloc = (
        f"{quote(username, safe='')}:{quote(password, safe='')}@"
        f"{host}:{parsed.port}"
    )
    # Retain verify-full and optional CA/channel binding from admin DSN.
    # No admin username or admin password is carried over.
    return urlunparse((parsed.scheme, netloc, "/postgres", "", parsed.query, ""))


def preflight(admin: psycopg.Connection, *, organization_id: str, role: str,
              require_absent: bool = True) -> tuple[int, str]:
    # Authenticated administrative identity and exact structural contract.
    identity = admin.execute("SELECT current_user,current_database()").fetchone()
    if identity != ("postgres", "postgres"):
        raise ProvisionBlocked("WRONG_DATABASE_OR_ADMIN_ROLE")
    group = admin.execute("""
        SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolbypassrls
        FROM pg_roles WHERE rolname='langgraph_shadow'
    """).fetchone()
    if group != (False, False, False, False, False):
        raise ProvisionBlocked("SHADOW_GROUP_UNSAFE_OR_MISSING")
    schema = admin.execute("""
        SELECT
          to_regclass('public.langgraph_shadow_runs') IS NOT NULL,
          to_regclass('langgraph_internal.shadow_role_tenants') IS NOT NULL,
          (SELECT relrowsecurity FROM pg_class
           WHERE oid='public.langgraph_shadow_runs'::regclass),
          (SELECT relrowsecurity FROM pg_class
           WHERE oid='langgraph_internal.shadow_role_tenants'::regclass),
          has_table_privilege('langgraph_shadow','public.langgraph_shadow_runs','DELETE'),
          has_table_privilege('langgraph_shadow','langgraph_internal.shadow_role_tenants','INSERT'),
          has_database_privilege('langgraph_shadow','postgres','CREATE'),
          has_database_privilege('langgraph_shadow','postgres','TEMPORARY'),
          has_schema_privilege('langgraph_shadow','public','CREATE'),
          has_schema_privilege('langgraph_shadow','langgraph_internal','CREATE'),
          has_table_privilege('anon','public.langgraph_shadow_runs','SELECT'),
          has_table_privilege('authenticated','public.langgraph_shadow_runs','SELECT'),
          has_table_privilege('finance_g1_readonly','public.langgraph_shadow_runs','SELECT')
    """).fetchone()
    if schema != (True, True, True, True, False, False, False, False,
                  False, False, False, False, False):
        raise ProvisionBlocked("SHADOW_SCHEMA_PRIVILEGES_UNSAFE")
    observed = set(admin.execute("""
        SELECT schemaname,tablename,policyname,cmd FROM pg_policies
        WHERE (schemaname='public' AND tablename='langgraph_shadow_runs')
           OR (schemaname='langgraph_internal' AND tablename='shadow_role_tenants')
    """).fetchall())
    if observed != EXPECTED_POLICIES:
        raise ProvisionBlocked("SHADOW_RLS_POLICIES_DRIFTED")
    # Effective PUBLIC grants matter: group membership must not expose other
    # finance/customer relations, even in unanticipated client schemas.
    visible = set(admin.execute("""
        SELECT n.nspname,c.relname FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind IN ('r','p','v','m','f','S')
          AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
          AND n.nspname NOT LIKE 'pg_%'
          AND has_schema_privilege('langgraph_shadow',n.oid,'USAGE')
          AND (
            has_table_privilege('langgraph_shadow',c.oid,'SELECT') OR
            has_table_privilege('langgraph_shadow',c.oid,'INSERT') OR
            has_table_privilege('langgraph_shadow',c.oid,'UPDATE') OR
            has_table_privilege('langgraph_shadow',c.oid,'DELETE')
          )
    """).fetchall())
    if visible != ALLOWED_RELATIONS:
        raise ProvisionBlocked("SHADOW_GROUP_OUTSIDE_RELATIONS")
    dangerous_funcs = admin.execute("""
        SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname NOT IN ('pg_catalog','information_schema')
          AND n.nspname NOT LIKE 'pg_%'
          AND p.prosecdef
          AND has_schema_privilege('langgraph_shadow',n.oid,'USAGE')
          AND has_function_privilege('langgraph_shadow',p.oid,'EXECUTE')
    """).fetchone()[0]
    if dangerous_funcs:
        raise ProvisionBlocked("SHADOW_GROUP_CAN_CALL_PRIVILEGED_FUNCTION")
    if require_absent:
        existing_role = admin.execute(
            "SELECT count(*) FROM pg_roles WHERE rolname=%s", (role,)
        ).fetchone()[0]
        existing_binding = admin.execute(
            "SELECT count(*) FROM langgraph_internal.shadow_role_tenants "
            "WHERE role_name=%s OR organization_id=%s", (role, organization_id)
        ).fetchone()[0]
        if existing_role or existing_binding:
            raise ProvisionBlocked("ROLE_OR_BINDING_ALREADY_EXISTS")
    # Do not fetch or print question/SQL/tenant payloads.
    data = admin.execute("""
        SELECT count(*) AS n,
          md5(string_agg(md5(to_jsonb(t)::text),'' ORDER BY shadow_record_id))
        FROM public.langgraph_shadow_runs t
    """).fetchone()
    return int(data[0]), str(data[1] or "")


def provision_in_transaction(admin: psycopg.Connection, *, role: str,
                             organization_id: str, password: str) -> None:
    if role != login_role_for(organization_id):
        raise ProvisionBlocked("ROLE_ORGANIZATION_MISMATCH")
    if len(password) < 32:
        raise ProvisionBlocked("PASSWORD_TOO_SHORT")
    with admin.transaction():
        preflight(admin, organization_id=organization_id, role=role)
        verifier = scram_verifier(password)
        admin.execute(
            sql.SQL("CREATE ROLE {} LOGIN INHERIT NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 3 "
                    "PASSWORD {}").format(sql.Identifier(role), sql.Literal(verifier))
        )
        admin.execute(
            sql.SQL("GRANT langgraph_shadow TO {} WITH INHERIT TRUE, SET FALSE")
            .format(sql.Identifier(role))
        )
        admin.execute(
            sql.SQL("GRANT CONNECT ON DATABASE postgres TO {}")
            .format(sql.Identifier(role))
        )
        admin.execute(
            "INSERT INTO langgraph_internal.shadow_role_tenants "
            "(role_name,organization_id) VALUES (%s,%s)", (role, organization_id)
        )
        for setting, value in (
            ("statement_timeout", "15s"),
            ("lock_timeout", "5s"),
            ("idle_in_transaction_session_timeout", "15s"),
            ("search_path", "pg_catalog"),
        ):
            admin.execute(
                sql.SQL("ALTER ROLE {} SET {} = {}").format(
                    sql.Identifier(role), sql.Identifier(setting), sql.Literal(value)
                )
            )


def verify_login(login_dsn: str, role: str, organization_id: str) -> None:
    """Real authenticated login and rollback-only read/write RLS smoke."""
    with psycopg.connect(login_dsn, connect_timeout=15) as conn:
        identity = conn.execute("SELECT current_user,session_user").fetchone()
        if identity != (role, role):
            raise ProvisionBlocked("REAL_LOGIN_ROLE_MISMATCH")
        bindings = conn.execute(
            "SELECT organization_id FROM langgraph_internal.shadow_role_tenants"
        ).fetchall()
        if bindings != [(organization_id,)]:
            raise ProvisionBlocked("REAL_LOGIN_TENANT_BINDING_MISMATCH")
        other = conn.execute("""
            SELECT count(*) FROM public.langgraph_shadow_runs
            WHERE (principal->>'organization_id') IS DISTINCT FROM %s
        """, (organization_id,)).fetchone()[0]
        if other:
            raise ProvisionBlocked("REAL_LOGIN_CROSS_TENANT_READ")
        if conn.execute(
            "SELECT has_table_privilege(current_user,'public.langgraph_shadow_runs','DELETE')"
        ).fetchone()[0]:
            raise ProvisionBlocked("REAL_LOGIN_DELETE_GRANT")
        probe = "shadow-credential-smoke-" + uuid.uuid4().hex
        parameters = (
            probe, probe, probe, Jsonb({"organization_id": organization_id}), probe,
        )
        query = """
            INSERT INTO public.langgraph_shadow_runs
            (shadow_record_id,agent_run_id,run_id,event_type,contract_version,
             status,created_at,principal,evidence_fingerprint)
            VALUES (%s,%s,%s,'generate','1','started',now(),%s,%s)
        """
        conn.execute(query, parameters)
        if conn.execute(
            "SELECT count(*) FROM public.langgraph_shadow_runs WHERE shadow_record_id=%s",
            (probe,)
        ).fetchone() != (1,):
            raise ProvisionBlocked("REAL_LOGIN_INSERT_NOT_VISIBLE")
        if conn.execute(
            "UPDATE public.langgraph_shadow_runs SET updated_at=now() "
            "WHERE shadow_record_id=%s", (probe,)
        ).rowcount != 1:
            raise ProvisionBlocked("REAL_LOGIN_UPDATE_DENIED")
        # A role must not be able to insert evidence for another organization.
        try:
            with conn.transaction():  # savepoint inside outer transaction
                conn.execute(query, (
                    probe+"-foreign", probe, probe,
                    Jsonb({"organization_id": organization_id + "-foreign"}),
                    probe,
                ))
                raise ProvisionBlocked("CROSS_TENANT_INSERT_ALLOWED")
        except psycopg.Error:
            pass
        # Test data MUST NEVER be committed to DEMO.
        conn.rollback()
    with psycopg.connect(login_dsn, connect_timeout=15) as check:
        if check.execute(
            "SELECT count(*) FROM public.langgraph_shadow_runs WHERE shadow_record_id=%s",
            (probe,)
        ).fetchone() != (0,):
            raise ProvisionBlocked("PROBE_ROLLBACK_FAILED")


def private_file_path(directory: Path, role: str) -> Path:
    return directory / (role + ".json")


def ensure_private_directory(directory: Path) -> None:
    if os.geteuid() != 0:
        raise ProvisionBlocked("ROOT_REQUIRED_FOR_SECRET_STORAGE")
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    s = directory.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.geteuid() or s.st_mode & 0o077:
        raise ProvisionBlocked("SECRET_DIRECTORY_UNSAFE")


def create_private_file(path: Path, data: dict[str, str]) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
        handle.flush()
        os.fsync(handle.fileno())


def read_private_file(path: Path) -> dict[str, str]:
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid() or s.st_mode & 0o077:
        raise ProvisionBlocked("SECRET_FILE_UNSAFE")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"role", "organization_id", "dsn"}:
        raise ProvisionBlocked("SECRET_FILE_INVALID")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-ref", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    private_path = None
    role_created = False
    try:
        if args.apply and args.verify:
            raise ProvisionBlocked("MODES_MUTUALLY_EXCLUSIVE")
        validate_project_and_org(args.project_ref, args.organization_id)
        role = login_role_for(args.organization_id)
        private_path = private_file_path(PRIVATE_DIR, role)
        if args.verify:
            ensure_private_directory(PRIVATE_DIR)
            saved = read_private_file(private_path)
            if saved["role"] != role or saved["organization_id"] != args.organization_id:
                raise ProvisionBlocked("SECRET_IDENTITY_MISMATCH")
            require_verified_tls_dsn_for_login(saved["dsn"], args.project_ref, role)
            verify_login(saved["dsn"], role, args.organization_id)
            print("P3_SHADOW_LOGIN_VERIFY=PASS")
            return 0

        admin_dsn = getpass.getpass("DSN admin DEMO (sem eco): ")
        require_verified_tls_dsn(admin_dsn, "postgres", args.project_ref)
        with psycopg.connect(admin_dsn, autocommit=True, connect_timeout=15) as admin:
            count, digest = preflight(
                admin, organization_id=args.organization_id, role=role
            )
            print("P3_SHADOW_LOGIN_PREFLIGHT=PASS")
            print("P3_ARCHIVE_RECORDS=" + str(count))
            print("P3_ARCHIVE_FINGERPRINT=" + digest)
            print("P3_PLANNED_LOGIN_ROLE=" + role)
            if not args.apply:
                print("P3_SHADOW_ROLE_CREATED=NO")
                print("P3_DSN_CUTOVER=NOT_PERFORMED")
                return 0
            ensure_private_directory(PRIVATE_DIR)
            if private_path.exists() or private_path.is_symlink():
                raise ProvisionBlocked("PRIVATE_SECRET_ALREADY_EXISTS")
            answer = input("Para criar LOGIN restrito, digite CREATE-SHADOW-LOGIN: ")
            if answer != "CREATE-SHADOW-LOGIN":
                raise ProvisionBlocked("OPERATOR_CONFIRMATION_REQUIRED")
            pwd = secrets.token_urlsafe(48)
            dsn = login_dsn_for(admin_dsn, args.project_ref, role, pwd)
            create_private_file(private_path, {
                "role": role, "organization_id": args.organization_id, "dsn": dsn,
            })
            provision_in_transaction(
                admin, role=role, organization_id=args.organization_id, password=pwd
            )
            role_created = True
            # A connection through a real LOGIN is necessary to prove RLS.
            verify_login(dsn, role, args.organization_id)
            count_after, digest_after = preflight(
                admin, organization_id=args.organization_id, role=role,
                require_absent=False,
            )
            if (count, digest) != (count_after, digest_after):
                raise ProvisionBlocked("ARCHIVE_CHANGED_DURING_PROVISION")
        print("P3_SHADOW_ROLE_CREATED=YES")
        print("P3_SHADOW_LOGIN_AUTH=PASS")
        print("P3_SHADOW_LOGIN_RLS=PASS")
        print("P3_SHADOW_PROBE_ROLLBACK=PASS")
        print("P3_SECRET_PATH=" + str(private_path))
        print("P3_DSN_CUTOVER=NOT_PERFORMED")
        print("P3_REAL_FINANCIAL_SQL=NOT_PERFORMED")
        return 0
    except Exception as exc:
        # Driver exceptions may include credentials: NEVER render their text.
        if private_path is not None and not role_created:
            try:
                private_path.unlink(missing_ok=True)
            except OSError:
                pass
        print("P3_SHADOW_LOGIN_RESULT=BLOCKED")
        if isinstance(exc, ProvisionBlocked):
            print("P3_SHADOW_LOGIN_ERROR=" + str(exc))
        else:
            print("P3_SHADOW_LOGIN_ERROR=" + type(exc).__name__)
        print("P3_DSN_CUTOVER=NOT_PERFORMED")
        if role_created:
            print("P3_ROLE_STATE=CREATED_REQUIRES_RECONCILIATION")
        return 2


def require_verified_tls_dsn_for_login(dsn: str, project_ref: str,
                                       role: str) -> None:
    parsed = urlparse(dsn)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise ProvisionBlocked("LOGIN_DSN_INVALID")
    if parsed.path != "/postgres" or not parsed.password:
        raise ProvisionBlocked("LOGIN_DSN_INVALID")
    if not parsed.query or "sslmode=verify-full" not in parsed.query:
        raise ProvisionBlocked("LOGIN_DSN_TLS_REQUIRED")
    if parsed.hostname and parsed.hostname.endswith(".pooler.supabase.com"):
        if parsed.username != role + "." + project_ref:
            raise ProvisionBlocked("LOGIN_DSN_PROJECT_OR_ROLE_MISMATCH")
    elif parsed.hostname != f"db.{project_ref}.supabase.co" or parsed.username != role:
        raise ProvisionBlocked("LOGIN_DSN_PROJECT_OR_ROLE_MISMATCH")


if __name__ == "__main__":
    sys.exit(main())
