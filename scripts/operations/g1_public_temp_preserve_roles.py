#!/usr/bin/env python3
"""G1/P3: atomically preserve existing roles while removing PUBLIC TEMPORARY.

This does NOT run from LangGraph, n8n or a migration. No business schema,
tenant, metric, or SQL is embedded here. --apply and --rollback are explicit
database-wide privilege operations requiring separate operator authorization.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

from g1_readonly_rollout import (
    RolloutError, canonical_json, load_config, private_snapshot,
    quote_ident, require_verified_tls_dsn,
)

# A database role's OID identifies it across renames. Compare effective
# privileges for ALL existing roles, not merely LOGIN roles: services can
# SET ROLE to NOLOGIN roles, and preserving only logins is insufficient.
ROLE_SQL = """
SELECT r.oid::bigint, r.rolname,
       has_database_privilege(r.oid, %s, 'TEMPORARY'),
       has_database_privilege(r.oid, %s, 'CONNECT'),
       has_database_privilege(r.oid, %s, 'CREATE')
FROM pg_roles r ORDER BY r.oid
"""
DB_ACL_SQL = """
SELECT a.grantee::bigint, a.privilege_type
FROM pg_database d
CROSS JOIN LATERAL aclexplode(
    COALESCE(d.datacl, acldefault('d', d.datdba))
) a
WHERE d.datname=%s
ORDER BY a.grantee, a.privilege_type
"""
DB_ID_SQL = "SELECT current_database()"
VERSION = "g1-public-temp-preserve-existing-roles-v1"


def inventory(conn: Any, database: str) -> dict[str, Any]:
    db = conn.execute(DB_ID_SQL).fetchone()
    if not db or db[0] != database:
        raise RolloutError("database divergente")
    rows = conn.execute(ROLE_SQL, (database, database, database)).fetchall()
    acl = conn.execute(DB_ACL_SQL, (database,)).fetchall()
    if not rows or not acl:
        raise RolloutError("catalogo de roles/ACL incompleto")
    roles = []
    for oid, name, temporary, connect, create in rows:
        if type(oid) is not int or not isinstance(name, str) or not name or not all(
            type(v) is bool for v in (temporary, connect, create)
        ):
            raise RolloutError("estado de role invalido")
        roles.append([oid, name, temporary, connect, create])
    if len({row[0] for row in roles}) != len(roles):
        raise RolloutError("roles duplicadas")
    grants = []
    for grantee, privilege in acl:
        if type(grantee) is not int or not isinstance(privilege, str):
            raise RolloutError("ACL invalida")
        grants.append([grantee, privilege])
    if len({tuple(grant) for grant in grants}) != len(grants):
        raise RolloutError("ACL duplicada")
    return {"roles": roles, "grants": grants}


def _role_map(snapshot: Mapping[str, Any]) -> dict[int, list[Any]]:
    return {row[0]: row for row in snapshot["roles"]}


def _acl_set(snapshot: Mapping[str, Any]) -> set[tuple[int, str]]:
    return {tuple(row) for row in snapshot["grants"]}


def preflight(snapshot: Mapping[str, Any], role_name: str) -> None:
    rights = _acl_set(snapshot)
    if (0, "TEMPORARY") not in rights or (0, "CREATE") in rights:
        raise RolloutError("PUBLIC TEMPORARY/CREATE nao corresponde ao bloqueio G1")
    if any(row[1] == role_name for row in snapshot["roles"]):
        raise RolloutError("role G1 ja existe; nao alterar ACL global")
    if not any(row[2] for row in snapshot["roles"]):
        raise RolloutError("nenhum privilegio TEMPORARY efetivo inventariado")


def validate_after(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    compensated_ids: list[int],
    *,
    allow_target_name: str | None = None,
) -> None:
    original = _role_map(before)
    current = _role_map(after)
    extra = set(current) - set(original)
    if extra:
        if len(extra) != 1 or allow_target_name is None:
            raise RolloutError("novas roles inesperadas; revisao necessaria")
        added = current[next(iter(extra))]
        if added[1] != allow_target_name or added[2] or added[4]:
            raise RolloutError("role G1 nao esta isolada")
    if not all(current.get(oid) == row for oid, row in original.items()):
        raise RolloutError("privilegios existentes mudaram; ROLLBACK automatico da transacao")
    expected = (_acl_set(before) - {(0, "TEMPORARY")}) | {
        (oid, "TEMPORARY") for oid in compensated_ids
    }
    if _acl_set(after) != expected:
        raise RolloutError("mudancas na ACL alem das compensacoes previstas")
    if (0, "TEMPORARY") in _acl_set(after):
        raise RolloutError("PUBLIC ainda possui TEMPORARY")


def preserve_existing_roles(conn: Any, before: Mapping[str, Any], database: str,
                            role_name: str) -> list[int]:
    preflight(before, role_name)
    if inventory(conn, database) != before:
        raise RolloutError("catalogo mudou apos preflight; nenhuma alteracao")
    conn.execute(f"REVOKE TEMPORARY ON DATABASE {quote_ident(database)} FROM PUBLIC")
    without_public = inventory(conn, database)
    old = _role_map(before)
    current = _role_map(without_public)
    if set(old) != set(current):
        raise RolloutError("concorrencia no catalogo de roles")
    # Grant TEMP only to roles that lost it when PUBLIC was revoked. Role
    # names always come from pg_roles, never input/user string interpolation.
    compensated = [oid for oid, row in old.items()
                   if row[2] and not current[oid][2]]
    for oid in compensated:
        conn.execute(
            f"GRANT TEMPORARY ON DATABASE {quote_ident(database)} "
            f"TO {quote_ident(old[oid][1])}"
        )
    after = inventory(conn, database)
    validate_after(before, after, compensated)
    return compensated


def _load_private(path: Path) -> dict[str, Any]:
    if path.is_symlink() or path.parent.is_symlink():
        raise RolloutError("snapshot nao aceita symlinks")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            if os.name != "nt" and stat.S_IMODE(os.fstat(handle.fileno()).st_mode) & 0o077:
                raise RolloutError("snapshot acessivel a terceiros")
            value = json.load(handle)
    except (OSError, ValueError) as exc:
        raise RolloutError("snapshot indisponivel/invalido") from exc
    if not isinstance(value, dict) or value.get("version") != VERSION:
        raise RolloutError("snapshot de outra operacao")
    if not isinstance(value.get("before"), dict) or not isinstance(value.get("compensated"), list):
        raise RolloutError("snapshot incompleto")
    return value


def verify(conn: Any, database: str, target_role: str, record: Mapping[str, Any],
           *, allow_target: bool) -> None:
    if record.get("database") != database or record.get("role_name") != target_role:
        raise RolloutError("snapshot de outro banco/role")
    baseline, compensated = record["before"], record["compensated"]
    if not compensated or len(set(compensated)) != len(compensated) or not all(
        type(x) is int and x in _role_map(baseline) for x in compensated
    ):
        raise RolloutError("snapshot de compensacao invalido")
    validate_after(
        baseline, inventory(conn, database), compensated,
        allow_target_name=target_role if allow_target else None,
    )


def rollback(conn: Any, database: str, target_role: str, record: Mapping[str, Any]) -> None:
    # Any new role may rely on the post-revoke default. Never re-grant PUBLIC
    # with a newly provisioned G1 reader or any other new role present.
    verify(conn, database, target_role, record, allow_target=False)
    before = record["before"]
    conn.execute(f"GRANT TEMPORARY ON DATABASE {quote_ident(database)} TO PUBLIC")
    roles = _role_map(before)
    for oid in record["compensated"]:
        conn.execute(
            f"REVOKE TEMPORARY ON DATABASE {quote_ident(database)} "
            f"FROM {quote_ident(roles[oid][1])}"
        )
    if inventory(conn, database) != before:
        raise RolloutError("rollback nao reproduziu ACL original")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    parser.add_argument("--project-ref", required=True)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("g1_readonly_rollout.json"))
    parser.add_argument("--snapshot", type=Path,
                        default=Path.home() / ".local/state/agente-sql-langgraph/g1-public-temp-acl.json")
    args = parser.parse_args(argv)
    if not args.project_ref.isascii() or not args.project_ref.isalnum() or not 12 <= len(args.project_ref) <= 35:
        raise RolloutError("referencia de projeto invalida")
    config = load_config(args.config)
    database, role_name = config.raw["database"], config.raw["role_name"]
    dsn = getpass.getpass("DSN PostgreSQL admin (sem eco): ")
    require_verified_tls_dsn(dsn, database, args.project_ref)
    try:
        import psycopg
    except ImportError as exc:
        raise RolloutError("psycopg indisponivel") from exc
    with psycopg.connect(dsn, autocommit=True, connect_timeout=15) as conn:
        if args.verify or args.rollback:
            record = _load_private(args.snapshot)
            if args.verify:
                verify(conn, database, role_name, record, allow_target=True)
                print("P3_ACL_VERIFY=PASS")
                return 0
            if input("Digite ROLLBACK-P3-ACL para confirmar: ").strip() != "ROLLBACK-P3-ACL":
                raise RolloutError("rollback nao autorizado")
            with conn.transaction():
                conn.execute("SET LOCAL lock_timeout = '5s'")
                conn.execute("SET LOCAL statement_timeout = '30s'")
                rollback(conn, database, role_name, record)
            print("P3_ACL_ROLLBACK=PASS")
            return 0
        before = inventory(conn, database)
        preflight(before, role_name)
        print("P3_ACL_PLAN=REVIEW_REQUIRED")
        print("P3_ACL_EXISTING_ROLES=" + str(len(before["roles"])))
        print("P3_ACL_PUBLIC_TEMPORARY=TRUE")
        print("P3_ACL_EXISTING_ROLE_PRIVILEGES_WILL_BE_PRESERVED=TRUE")
        print("P3_ACL_NEW_ROLES_REQUIRE_EXPLICIT_TEMP_GRANTS=TRUE")
        if not args.apply:
            print("P3_ACL_MUTATION=FALSE")
            return 0
        if args.snapshot.exists() or args.snapshot.is_symlink():
            raise RolloutError("snapshot anterior: verificar/reconciliar antes de aplicar")
        if input("Digite APPLY-P3-ACL para confirmar a mudanca global: ").strip() != "APPLY-P3-ACL":
            raise RolloutError("alteracao global nao autorizada")
        with conn.transaction():
            conn.execute("SET LOCAL lock_timeout = '5s'")
            conn.execute("SET LOCAL statement_timeout = '30s'")
            compensated = preserve_existing_roles(conn, before, database, role_name)
            if not compensated:
                raise RolloutError("PUBLIC nao era necessario a nenhuma role; revisao")
            private_snapshot(args.snapshot, {
                "version": VERSION, "database": database, "role_name": role_name,
                "before": before, "compensated": compensated,
            })
        print("P3_ACL_MUTATION=COMMITTED")
        print("P3_ACL_COMPENSATED_ROLES=" + str(len(compensated)))
        print("P3_ACL_EXISTING_ROLE_PRIVILEGES_PRESERVED=TRUE")
        print("P3_ACL_NEXT=G1_READONLY_ROLLOUT_DRY_RUN")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RolloutError as exc:
        print("P3_ACL_RESULT=REJECTED", file=sys.stderr)
        print("P3_ACL_ERROR=" + str(exc), file=sys.stderr)
        raise SystemExit(2)
    except Exception:
        # Never print psycopg/n8n exceptions, SQL/role names, DSN or passwords.
        print("P3_ACL_RESULT=ERROR_REQUIRES_RECONCILIATION", file=sys.stderr)
        raise SystemExit(2)
