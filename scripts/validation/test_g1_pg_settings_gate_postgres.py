#!/usr/bin/env python3
"""Disposable PostgreSQL regression for the G1 effective-permission gate.

Run only against a local CI database and never against a live tenant or
Supabase. This fixture does not execute any business SQL or paid model.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "operations"))
from g1_readonly_rollout import (
    RolloutConfig,
    RolloutError,
    assert_role_effective_permissions,
    quote_ident,
)

ROLE = "g1_disposable_reader"
SCHEMA = "g1_disposable_allowed"
HIDDEN = "g1_disposable_hidden"
RELATION = "sample_rows"


def assert_rejected(conn: psycopg.Connection, config: RolloutConfig, label: str) -> None:
    try:
        assert_role_effective_permissions(conn, config)
    except RolloutError as exc:
        if "role pode modificar uma relacao" not in str(exc):
            raise AssertionError(label + ": wrong security gate") from None
        return
    raise AssertionError(label + ": forbidden privilege was permitted")


def main() -> None:
    if os.environ.get("G1_DISPOSABLE_POSTGRES_TEST") != "true":
        raise RuntimeError("This test requires an explicitly marked disposable PG database")
    required = ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE")
    if any(not os.environ.get(key) for key in required):
        raise RuntimeError("Disposable PG connection configuration missing")

    database = os.environ["PGDATABASE"]
    if database != "g1_disposable_ci":
        raise RuntimeError("Refusing to test on an unknown database")

    # All credential values come from CI environment and are never printed.
    with psycopg.connect(
        host=os.environ["PGHOST"],
        port=os.environ["PGPORT"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        dbname=database,
        connect_timeout=10,
    ) as conn:
        # A dedicated disposable database, not a product or tenant database.
        conn.execute("REVOKE TEMPORARY ON DATABASE " + quote_ident(database) + " FROM PUBLIC")
        conn.execute("CREATE ROLE " + quote_ident(ROLE) +
                     " LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS")
        conn.execute("CREATE SCHEMA " + quote_ident(SCHEMA))
        conn.execute("CREATE TABLE " + quote_ident(SCHEMA) + "." +
                     quote_ident(RELATION) + " (id integer)")
        conn.execute("CREATE SCHEMA " + quote_ident(HIDDEN))
        conn.execute("CREATE TABLE " + quote_ident(HIDDEN) + "." +
                     quote_ident(RELATION) + " (id integer)")
        conn.execute("GRANT CONNECT ON DATABASE " + quote_ident(database) + " TO " + quote_ident(ROLE))
        conn.execute("GRANT USAGE ON SCHEMA " + quote_ident(SCHEMA) + " TO " + quote_ident(ROLE))
        conn.execute("GRANT SELECT ON " + quote_ident(SCHEMA) + "." +
                     quote_ident(RELATION) + " TO " + quote_ident(ROLE))

        config = RolloutConfig({
            "role_name": ROLE, "database": database,
            "schema": SCHEMA, "relations": [RELATION],
        })
        public_update = conn.execute("""
            SELECT EXISTS(
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid=c.relnamespace
                JOIN LATERAL aclexplode(COALESCE(
                    c.relacl, acldefault('r',c.relowner)
                )) a ON TRUE
                WHERE n.nspname='pg_catalog' AND c.relname='pg_settings'
                  AND c.relkind='v' AND a.grantee=0
                  AND a.privilege_type='UPDATE'
            )
        """).fetchone()[0]
        assert public_update, "PostgreSQL fixture does not reproduce the intrinsic grant"
        assert conn.execute(
            "SELECT has_table_privilege(%s, 'pg_catalog.pg_settings', 'UPDATE')",
            (ROLE,),
        ).fetchone()[0]

        # This is the actual G1 check, not just an assertion on SQL text:
        # pg_settings PUBLIC UPDATE must be the ONLY built-in exception.
        assert_role_effective_permissions(conn, config)
        print("G1_INTRINSIC_PG_SETTINGS=PASS")

        allowed = quote_ident(SCHEMA) + "." + quote_ident(RELATION)
        hidden = quote_ident(HIDDEN) + "." + quote_ident(RELATION)
        conn.execute("GRANT UPDATE ON " + allowed + " TO " + quote_ident(ROLE))
        assert_rejected(conn, config, "allowed relation UPDATE")
        conn.execute("REVOKE UPDATE ON " + allowed + " FROM " + quote_ident(ROLE))
        print("G1_FINANCIAL_DML_STILL_BLOCKED=PASS")

        # No USAGE on this hidden schema, but its DML privilege must still
        # fail: SQL privileges are unsafe even if another grant is needed.
        conn.execute("GRANT UPDATE ON " + hidden + " TO " + quote_ident(ROLE))
        assert_rejected(conn, config, "inaccessible schema UPDATE")
        conn.execute("REVOKE UPDATE ON " + hidden + " FROM " + quote_ident(ROLE))
        print("G1_HIDDEN_SCHEMA_DML_STILL_BLOCKED=PASS")

        # An explicit grant to this reader must not be masked by the builtin
        # PUBLIC grant on pg_settings; only the latter is a structural case.
        conn.execute("GRANT UPDATE ON pg_catalog.pg_settings TO " + quote_ident(ROLE))
        assert_rejected(conn, config, "direct pg_settings UPDATE")
        conn.execute("REVOKE UPDATE ON pg_catalog.pg_settings FROM " + quote_ident(ROLE))
        print("G1_DIRECT_SETTINGS_DML_STILL_BLOCKED=PASS")

        # Insert would still be prohibited even for this exact system view.
        conn.execute("GRANT INSERT ON pg_catalog.pg_settings TO " + quote_ident(ROLE))
        assert_rejected(conn, config, "pg_settings INSERT")
        conn.execute("REVOKE INSERT ON pg_catalog.pg_settings FROM " + quote_ident(ROLE))
        print("G1_SETTINGS_OTHER_DML_STILL_BLOCKED=PASS")

        assert_role_effective_permissions(conn, config)
        print("G1_POSTGRES_REGRESSION=PASS")


if __name__ == "__main__":
    main()
