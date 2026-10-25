#!/usr/bin/env python3
"""Read-only impact inventory for PUBLIC privileges before a G1 rollout.

Shows counts, never role/object names, connection secrets, or query text.
The catalogue cannot prove which applications need temporary tables, and
it does not authorize any REVOKE, role creation or workflow modification.
"""
from __future__ import annotations

import argparse
import getpass
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from g1_readonly_rollout import (
    RolloutError,
    load_config,
    pooler_template_from_admin_dsn,
    require_verified_tls_dsn,
)


# Structural PostgreSQL catalogue queries only: no financial data access.
# Exclude built-in namespaces; all other schemas (including extensions) are
# counted without client-specific names or schema assumptions.
DATABASE_ACL_SQL = """
SELECT COALESCE(bool_or(a.privilege_type='CONNECT'), false),
       COALESCE(bool_or(a.privilege_type='TEMPORARY'), false),
       COALESCE(bool_or(a.privilege_type='CREATE'), false),
       COUNT(DISTINCT a.grantee) FILTER (
           WHERE a.privilege_type='TEMPORARY' AND a.grantee<>0)
FROM pg_database d
LEFT JOIN LATERAL aclexplode(
    COALESCE(d.datacl, acldefault('d',d.datdba))) a ON true
WHERE d.datname=current_database() AND (a.grantee=0 OR a.grantee<>0)
"""
# The database ACL above intentionally collects PUBLIC and role grants in
# one query. Filter the three PUBLIC booleans within aggregates, not WHERE.
DATABASE_ACL_SQL = DATABASE_ACL_SQL.replace(
    "a.privilege_type='CONNECT'),",
    "a.privilege_type='CONNECT' AND a.grantee=0),"
).replace(
    "a.privilege_type='TEMPORARY'),",
    "a.privilege_type='TEMPORARY' AND a.grantee=0),"
).replace(
    "a.privilege_type='CREATE'),",
    "a.privilege_type='CREATE' AND a.grantee=0),"
)

ROLE_ACTIVITY_SQL = """
SELECT (SELECT COUNT(*) FROM pg_roles r WHERE r.rolcanlogin
        AND has_database_privilege(r.oid,current_database(),'CONNECT')),
       (SELECT COUNT(*) FROM pg_stat_activity a
        WHERE a.datname=current_database() AND a.pid<>pg_backend_pid()),
       (SELECT COUNT(*) FROM pg_stat_activity a
        WHERE a.datname=current_database() AND a.pid<>pg_backend_pid()
          AND a.state='active')
"""

SCHEMA_PUBLIC_USAGE_SQL = """
SELECT COUNT(*) FROM pg_namespace n
WHERE LEFT(n.nspname,3)<>'pg_' AND n.nspname<>'information_schema'
AND EXISTS (
  SELECT 1 FROM aclexplode(
      COALESCE(n.nspacl,acldefault('n',n.nspowner))) a
  WHERE a.grantee=0 AND a.privilege_type='USAGE'
)
"""

PUBLIC_RELATIONS_SQL = """
WITH public_schemas AS (
 SELECT n.oid FROM pg_namespace n
 WHERE LEFT(n.nspname,3)<>'pg_' AND n.nspname<>'information_schema'
 AND EXISTS (
  SELECT 1 FROM aclexplode(
      COALESCE(n.nspacl,acldefault('n',n.nspowner))) a
  WHERE a.grantee=0 AND a.privilege_type='USAGE'
 )
)
SELECT COUNT(DISTINCT c.oid) FILTER (
         WHERE c.relkind<>'S' AND a.privilege_type='SELECT'),
       COUNT(DISTINCT c.oid) FILTER (
         WHERE c.relkind<>'S' AND
         a.privilege_type IN ('INSERT','UPDATE','DELETE',
                              'TRUNCATE','REFERENCES','TRIGGER')),
       COUNT(DISTINCT c.oid) FILTER (
         WHERE c.relkind='S' AND
         a.privilege_type IN ('SELECT','USAGE','UPDATE'))
FROM pg_class c JOIN public_schemas s ON s.oid=c.relnamespace
CROSS JOIN LATERAL aclexplode(
   COALESCE(c.relacl,
      acldefault(CASE WHEN c.relkind='S' THEN 'S' ELSE 'r' END,
                 c.relowner))) a
WHERE c.relkind IN ('r','v','m','p','f','S') AND a.grantee=0
"""

PUBLIC_DEFINER_SQL = """
SELECT COUNT(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE p.prosecdef AND LEFT(n.nspname,3)<>'pg_'
  AND n.nspname<>'information_schema'
  AND EXISTS (
    SELECT 1 FROM aclexplode(
        COALESCE(n.nspacl,acldefault('n',n.nspowner))) s
    WHERE s.grantee=0 AND s.privilege_type='USAGE'
  )
  AND EXISTS (
    SELECT 1 FROM aclexplode(
        COALESCE(p.proacl,acldefault('f',p.proowner))) a
    WHERE a.grantee=0 AND a.privilege_type='EXECUTE'
  )
"""

ROLE_PRESENT_SQL = "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=%s)"


def inventory(connection: Any, config: Mapping[str, Any]) -> dict[str, str]:
    """Run only catalogue SELECTs within a transaction marked READ ONLY."""
    db_name = config["database"]
    found = connection.execute("SELECT current_database()").fetchone()
    if not found or found[0] != db_name:
        raise RolloutError("database divergente; auditoria bloqueada")

    output: dict[str, str] = {"G1_AUDIT_MODE": "READ_ONLY"}
    fields: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        (DATABASE_ACL_SQL, "G1_DATABASE_ACL", (
            "PUBLIC_CONNECT", "PUBLIC_TEMPORARY", "PUBLIC_CREATE",
            "EXPLICIT_TEMP_GRANTEE_COUNT",
        )),
        (ROLE_ACTIVITY_SQL, "G1_DATABASE_USAGE", (
            "LOGIN_ROLES_WITH_CONNECT", "DB_SESSIONS", "DB_ACTIVE_SESSIONS",
        )),
        (SCHEMA_PUBLIC_USAGE_SQL, "G1_SCHEMA_PUBLIC_USAGE", (
            "PUBLIC_USABLE_SCHEMA_COUNT",
        )),
        (PUBLIC_RELATIONS_SQL, "G1_RELATIONS_PUBLIC_ACL", (
            "PUBLIC_READABLE_RELATION_COUNT", "PUBLIC_WRITABLE_RELATION_COUNT",
            "PUBLIC_SEQUENCE_ACCESS_COUNT",
        )),
        (PUBLIC_DEFINER_SQL, "G1_PUBLIC_DEFINER", (
            "PUBLIC_EXECUTABLE_DEFINER_COUNT",
        )),
    )
    for sql, _, keys in fields:
        row = connection.execute(sql).fetchone()
        if not row or len(row) != len(keys):
            raise RolloutError("resultado de catalogo incompleto")
        for value, key in zip(row, keys):
            if type(value) is bool:
                output[f"G1_{key}"] = str(value).upper()
            elif type(value) is int and value >= 0:
                output[f"G1_{key}"] = str(value)
            else:
                raise RolloutError("resultado de catalogo invalido")
    role = connection.execute(
        ROLE_PRESENT_SQL, (config["role_name"],)
    ).fetchone()
    if not role or len(role) != 1 or type(role[0]) is not bool:
        raise RolloutError("identidade da role nao verificavel")
    output["G1_TARGET_ROLE_EXISTS"] = str(role[0]).upper()
    output["G1_IMPACT_NOTE"] = "CATALOG_ONLY_USAGE_NOT_PROVEN"
    output["G1_AUDIT_RESULT"] = "REVIEW_REQUIRED"
    return output


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path,
                   default=Path(__file__).with_name("g1_readonly_rollout.json"))
    p.add_argument("--project-ref", required=True)
    args = p.parse_args(argv)
    stage = "LOAD_CONFIG"
    dsn = None
    try:
        config = load_config(args.config)
        if not re.fullmatch(r"[a-z0-9]{12,35}", args.project_ref):
            raise RolloutError("referencia de projeto invalida")
        dsn = getpass.getpass("DSN admin PostgreSQL (sem eco): ")
        stage = "DSN_VALIDATION"
        require_verified_tls_dsn(
            dsn, config.raw["database"], args.project_ref
        )
        pooler_template_from_admin_dsn(
            dsn, config, args.project_ref
        )
        stage = "CONNECT"
        import psycopg
        with psycopg.connect(dsn, connect_timeout=15) as connection:
            # Fail closed if transaction isolation cannot be enforced.
            stage = "TX_READ_ONLY"
            connection.execute("SET TRANSACTION READ ONLY")
            stage = "CATALOG_QUERY"
            result = inventory(connection, config.raw)
        for key, value in result.items():
            print(f"{key}={value}")
        return 0
    except Exception as exc:
        # No str(exc), query, connection string, or raw PostgreSQL detail.
        print("G1_AUDIT=FAILED")
        print("G1_FAIL_STAGE=" + stage)
        code = getattr(exc, "sqlstate", None)
        print("G1_SQLSTATE=" + (
            code if isinstance(code,str) and re.fullmatch(r"[A-Z0-9]{5}",code)
            else "NONE"
        ))
        print("G1_ERROR_CATEGORY=" + (
            "POLICY" if isinstance(exc,RolloutError)
            else "DATABASE" if type(exc).__name__.endswith("Error")
            else "OTHER"
        ))
        return 2
    finally:
        dsn = None


if __name__ == "__main__":
    sys.exit(main())
