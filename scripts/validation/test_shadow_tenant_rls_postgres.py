#!/usr/bin/env python3
"""Real, disposable PostgreSQL proof of tenant-bound Shadow evidence access.

Synthetic only. Never connects to DEMO, CRM, production, n8n, LLM or any
external Supabase endpoint. Exercises migrations 001 and 002 as checked in.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb

from app.infrastructure.persistence.postgres_shadow_evidence_repository import (
    PostgresShadowEvidenceRepository,
)
from scripts.validation.test_shadow_evidence_integrity_postgres import _record

TENANT_A = "synthetic-A"
TENANT_B = "synthetic-B"
ROLE_A = "ci_shadow_login_a"
ROLE_B = "ci_shadow_login_b"
ROLE_UNKNOWN = "ci_shadow_unbound"
PASS_A = "ci-role-a-only"
PASS_B = "ci-role-b-only"
PASS_UNKNOWN = "ci-role-unbound-only"


def admin_dsn() -> str:
    expected = {
        "CI": "true",
        "GITHUB_ACTIONS": "true",
        "SHADOW_TENANT_RLS_DISPOSABLE_TEST": "true",
        "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "false",
        "PGHOST": "127.0.0.1",
        "PGPORT": "5432",
        "PGDATABASE": "synthetic_ci",
        "PGUSER": "synthetic_ci",
    }
    if any(os.environ.get(k) != v for k, v in expected.items()):
        raise RuntimeError("NOT_DISPOSABLE_CI")
    pwd = os.environ.get("PGPASSWORD")
    if not pwd:
        raise RuntimeError("MISSING_DISPOSABLE_CI_PASSWORD")
    return make_conninfo(
        "", host="127.0.0.1", port=5432, dbname="synthetic_ci",
        user="synthetic_ci", password=pwd, connect_timeout=5,
    )


def login_dsn(role: str, password: str) -> str:
    return make_conninfo(
        "", host="127.0.0.1", port=5432, dbname="synthetic_ci",
        user=role, password=password, connect_timeout=5,
    )


def expect_access_denied(dsn: str, query: str) -> None:
    with psycopg.connect(dsn) as connection:
        try:
            connection.execute(query)
        except psycopg.Error:
            connection.rollback()
            return
    raise AssertionError("unexpected SQL privilege or tenant access")


def prepare_roles_and_schema(dsn: str) -> None:
    migration1 = (ROOT / "scripts/migrations/001_create_langgraph_shadow_runs.sql").read_text()
    migration2 = (ROOT / "scripts/migrations/002_shadow_tenant_bound_evidence_access.sql").read_text()

    with psycopg.connect(dsn) as admin:
        # Supabase's default public roles are simulated, then explicitly
        # revoked by the real migration. NOLOGIN: cannot use these over TCP.
        for name in ("anon", "authenticated", "service_role", "finance_g1_readonly"):
            admin.execute(f"CREATE ROLE {name} NOLOGIN")
        admin.execute(migration1)
        admin.execute(
            "GRANT SELECT,INSERT,UPDATE ON public.langgraph_shadow_runs "
            "TO anon, authenticated, service_role, finance_g1_readonly"
        )
        seed = """
        INSERT INTO public.langgraph_shadow_runs (
          shadow_record_id,agent_run_id,run_id,event_type,
          contract_version,status,created_at,principal,evidence_fingerprint
        ) VALUES (%s,%s,%s,'generate','1','success',now(),%s,%s)
        """
        for record_id, principal in (
            ("ci-old-unscoped", {}),
            ("ci-old-tenant-a", {"organization_id": TENANT_A}),
            ("ci-old-tenant-b", {"organization_id": TENANT_B}),
        ):
            admin.execute(seed, (record_id, "ci-agent", "ci-run", Jsonb(principal), "ci-fingerprint"))
        admin.execute(migration2)

        # PostgreSQL 16+ membership can inherit table privileges WITHOUT
        # permitting SET ROLE. Each login is permanently bound by session_user.
        for role, password in (
            (ROLE_A, PASS_A), (ROLE_B, PASS_B), (ROLE_UNKNOWN, PASS_UNKNOWN)
        ):
            admin.execute(f"CREATE ROLE {role} LOGIN INHERIT PASSWORD %s", (password,))
            admin.execute(f"GRANT langgraph_shadow TO {role} WITH INHERIT TRUE, SET FALSE")
        admin.execute(
            "INSERT INTO langgraph_internal.shadow_role_tenants "
            "(role_name,organization_id) VALUES (%s,%s),(%s,%s)",
            (ROLE_A, TENANT_A, ROLE_B, TENANT_B),
        )


def prove_rls(dsn: str) -> None:
    a = login_dsn(ROLE_A, PASS_A)
    b = login_dsn(ROLE_B, PASS_B)
    unknown = login_dsn(ROLE_UNKNOWN, PASS_UNKNOWN)

    with psycopg.connect(dsn) as admin:
        public_rights = admin.execute("""
            SELECT relrowsecurity,
              has_table_privilege('anon','public.langgraph_shadow_runs','SELECT'),
              has_table_privilege('authenticated','public.langgraph_shadow_runs','INSERT'),
              has_table_privilege('finance_g1_readonly','public.langgraph_shadow_runs','SELECT')
            FROM pg_class WHERE oid='public.langgraph_shadow_runs'::regclass
        """).fetchone()
        assert public_rights == (True, False, False, False), public_rights

    for role_dsn, expected in ((a, "ci-old-tenant-a"), (b, "ci-old-tenant-b")):
        with psycopg.connect(role_dsn) as conn:
            assert conn.execute("SELECT session_user").fetchone()[0] in (ROLE_A, ROLE_B)
            rows = conn.execute(
                "SELECT shadow_record_id FROM public.langgraph_shadow_runs "
                "WHERE shadow_record_id LIKE 'ci-old-%'"
            ).fetchall()
            assert rows == [(expected,)], rows
            role_tenants = conn.execute(
                "SELECT organization_id FROM langgraph_internal.shadow_role_tenants"
            ).fetchall()
            assert len(role_tenants) == 1
    with psycopg.connect(unknown) as conn:
        assert conn.execute("SELECT count(*) FROM public.langgraph_shadow_runs").fetchone() == (0,)
        assert conn.execute(
            "SELECT count(*) FROM langgraph_internal.shadow_role_tenants"
        ).fetchone() == (0,)

    # An RLS bypass, cross-tenant insertion, session/role substitution,
    # deletion or binding modification must fail.
    expect_access_denied(
        a, "INSERT INTO public.langgraph_shadow_runs "
           "(shadow_record_id,agent_run_id,run_id,event_type,contract_version,"
           "status,created_at,principal,evidence_fingerprint) "
           "VALUES ('foreign-write','ci-agent','ci-run','generate','1','success',"
           "now(),'{\"organization_id\":\"synthetic-B\"}'::jsonb,'ci-fingerprint')"
    )
    expect_access_denied(
        a, "UPDATE public.langgraph_shadow_runs SET principal="
           "'{\"organization_id\":\"synthetic-B\"}'::jsonb "
           "WHERE shadow_record_id='ci-old-tenant-a'"
    )
    expect_access_denied(a, "DELETE FROM public.langgraph_shadow_runs")
    expect_access_denied(a, "UPDATE langgraph_internal.shadow_role_tenants SET organization_id='other'")
    expect_access_denied(a, "SET ROLE langgraph_shadow")
    expect_access_denied(a, "SET SESSION AUTHORIZATION ci_shadow_login_b")

    # Exercise the actual application adapter, including scoped SELECT and
    # create/update/finalize. This is not just static checking of SQL tokens.
    repo_a = PostgresShadowEvidenceRepository(dsn=a, expected_organization_id=TENANT_A)
    repo_b = PostgresShadowEvidenceRepository(dsn=b, expected_organization_id=TENANT_B)
    record = _record(TENANT_A, "ci-runtime-tenant-a")
    assert repo_a.create(record)["status"] == "created"
    assert repo_a.update_evidence(record)["status"] == "updated"
    assert repo_a.finalize({
        "shadow_record_id": record["shadow_record_id"],
        "status": record["status"],
        "completed_at": record["completed_at"],
        "evidence_fingerprint": record["evidence_fingerprint"],
    })["status"] == "finalized"
    assert repo_a.fetch_by_shadow_record_id("ci-runtime-tenant-a")["status"] == "ok"
    assert repo_b.fetch_by_shadow_record_id("ci-runtime-tenant-a")["status"] == "not_found"
    with psycopg.connect(unknown) as conn:
        assert conn.execute("SELECT count(*) FROM public.langgraph_shadow_runs").fetchone() == (0,)
    with psycopg.connect(dsn) as admin:
        assert admin.execute("SELECT count(*) FROM public.langgraph_shadow_runs").fetchone() == (4,)


if __name__ == "__main__":
    dsn = admin_dsn()
    prepare_roles_and_schema(dsn)
    prove_rls(dsn)
    print("SHADOW_TENANT_RLS_DISPOSABLE_POSTGRES=PASS")
