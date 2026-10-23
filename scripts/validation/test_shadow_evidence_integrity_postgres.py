#!/usr/bin/env python3
"""Real PostgreSQL 16 integration contract for synthetic Shadow evidence only.

Runs only with the explicitly named disposable GitHub Actions database.
No LLM, n8n, warehouse, benchmark, financial SQL or external connection.
The application SQL executor remains forbidden.
"""
from __future__ import annotations

import os
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import psycopg
from psycopg.conninfo import make_conninfo

from app.application.internal_sql_agent_v1_shared import persist_shadow_record
from app.domain.shadow_evidence_types import build_generate_shadow_record
from app.infrastructure.persistence.postgres_shadow_evidence_repository import (
    PostgresShadowEvidenceRepository,
)

TABLE = "public.langgraph_shadow_runs"
AGENT = "synthetic-agent-run"
TENANT_A = "synthetic-tenant-a"
TENANT_B = "synthetic-tenant-b"


def _require_disposable_environment() -> str:
    required = {
        "CI": "true",
        "GITHUB_ACTIONS": "true",
        "SHADOW_EVIDENCE_DISPOSABLE_POSTGRES_TEST": "true",
        "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "false",
        "PGHOST": "127.0.0.1",
        "PGPORT": "5432",
        "PGDATABASE": "synthetic_ci",
        "PGUSER": "synthetic_ci",
    }
    if any(os.environ.get(k) != v for k, v in required.items()):
        raise RuntimeError("Disposable PostgreSQL CI safeguards are not satisfied.")
    password = os.environ.get("PGPASSWORD", "")
    if not password:
        raise RuntimeError("Disposable PostgreSQL credential is absent.")
    return make_conninfo(
        "", host=required["PGHOST"], port=required["PGPORT"],
        dbname=required["PGDATABASE"], user=required["PGUSER"],
        password=password, connect_timeout=5,
    )


def _install_real_schema(dsn: str) -> None:
    migration = ROOT / "scripts/migrations/001_create_langgraph_shadow_runs.sql"
    statements = [part.strip() for part in migration.read_text(encoding="utf-8").split(";") if part.strip()]
    # This fixture intentionally exercises the real existing schema, not an
    # abbreviated test replacement; do not execute unexpected migrations.
    if len(statements) != 4 or not statements[0].casefold().startswith(
        "create table if not exists public.langgraph_shadow_runs"
    ) or any(
        not statement.casefold().startswith("create index if not exists ")
        for statement in statements[1:]
    ):
        raise RuntimeError("Disposable fixture migration contract drift.")
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)


def _record(
    organization: str,
    record_id: str,
    *,
    run_id: str = "synthetic-run-a",
    sql: str = "SELECT field_one FROM synthetic_schema.synthetic_table",
    agent_run_id: str = AGENT,
) -> dict:
    request = {
        "principal": {
            "id": "synthetic-actor",
            "profile": "synthetic-reader",
            "organization_id": organization,
        },
        "question": "Synthetic test question for evidence integrity",
        "correlation_metadata": {
            "request_id": "synthetic-request",
            "source": "ci",
        },
    }
    state = {
        "current_sql": sql,
        "generated_sql": sql,
        "query_plan": {"intent_name": "synthetic-intent"},
        "final_status": "approved",
        "options": {"shadow_mode": True},
        "engine_preflight_result": {"status": "approved", "executed": False},
    }
    response = {
        "status": "success",
        "agent_run_id": agent_run_id,
        "run_id": run_id,
        "sql": sql,
        "errors": [],
    }
    return build_generate_shadow_record(
        shadow_record_id=record_id,
        agent_run_id=agent_run_id,
        run_id=run_id,
        created_at="2026-10-23T00:00:00+00:00",
        completed_at="2026-10-23T00:00:01+00:00",
        status="success",
        request=request,
        state=state,
        response=response,
        langgraph_version="synthetic-ci",
        langgraph_commit="offline-only",
    )


def _finalization(record: dict) -> dict:
    return {
        "shadow_record_id": record["shadow_record_id"],
        "status": record["status"],
        "completed_at": record["completed_at"],
        "evidence_fingerprint": record["evidence_fingerprint"],
    }


def _snapshot(dsn: str, record_id: str) -> tuple:
    # Check raw committed state rather than trusting in-memory adapters.
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT agent_run_id, run_id, event_type, principal, "
                f"evidence_fingerprint, generated_sql, updated_at "
                f"FROM {TABLE} WHERE shadow_record_id = %s",
                (record_id,),
            )
            row = cursor.fetchone()
    assert row is not None
    return tuple(row)


def _count(dsn: str) -> int:
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT count(*) FROM {TABLE}")
            return int(cursor.fetchone()[0])


def test_real_postgres_shadow_integrity(dsn: str) -> None:
    repo_a = PostgresShadowEvidenceRepository(
        dsn=dsn, expected_organization_id=TENANT_A,
    )
    repo_b = PostgresShadowEvidenceRepository(
        dsn=dsn, expected_organization_id=TENANT_B,
    )
    unbound = PostgresShadowEvidenceRepository(dsn=dsn)
    original = _record(TENANT_A, "shadow-synthetic-a")
    assert repo_a.create(original)["status"] == "created"
    assert repo_a.update_evidence(original)["status"] == "updated"
    assert repo_a.finalize(_finalization(original))["status"] == "finalized"
    before = _snapshot(dsn, original["shadow_record_id"])
    assert repo_a.fetch_by_shadow_record_id(original["shadow_record_id"])["record"] == original

    # A retry of the same signed record is idempotent: no UPDATE/finalize.
    assert repo_a.create(original)["status"] == "already_exists"
    persist_shadow_record(repo_a, original)
    assert _snapshot(dsn, original["shadow_record_id"]) == before
    assert _count(dsn) == 1

    # Another SQL payload with the same shadow_record_id must not overwrite.
    changed = _record(
        TENANT_A, original["shadow_record_id"],
        sql="SELECT field_two FROM synthetic_schema.synthetic_table",
    )
    assert changed["evidence_fingerprint"] != original["evidence_fingerprint"]
    assert repo_a.create(changed)["status"] == "rejected"
    assert repo_a.update_evidence(changed)["status"] == "not_found"
    assert repo_a.finalize(_finalization(changed))["status"] == "not_found"
    persist_shadow_record(repo_a, changed)
    assert _snapshot(dsn, original["shadow_record_id"]) == before

    # Tenant B cannot enumerate or modify tenant A's colliding identifier.
    foreign = _record(TENANT_B, original["shadow_record_id"])
    assert repo_b.create(foreign)["status"] == "rejected"
    assert repo_b.update_evidence(foreign)["status"] == "not_found"
    assert repo_b.finalize(_finalization(foreign))["status"] == "not_found"
    assert repo_b.fetch_by_shadow_record_id(original["shadow_record_id"])["status"] == "not_found"
    assert repo_b.list_bounded_by_agent_run_id(
        AGENT, expected_organization_id=TENANT_B, limit=10,
    )["records"] == []
    assert _snapshot(dsn, original["shadow_record_id"]) == before

    # Legacy unbound access cannot treat a cross-tenant collision as replay.
    assert unbound.create(foreign)["status"] == "rejected"
    assert unbound.create(original)["status"] == "already_exists"
    assert _snapshot(dsn, original["shadow_record_id"]) == before

    # Two tenants may have the same agent_run_id but different record IDs.
    own_b = _record(TENANT_B, "shadow-synthetic-b", run_id="synthetic-run-b")
    assert repo_b.create(own_b)["status"] == "created"
    assert repo_b.update_evidence(own_b)["status"] == "updated"
    assert repo_b.finalize(_finalization(own_b))["status"] == "finalized"
    assert _count(dsn) == 2
    result_a = repo_a.list_bounded_by_agent_run_id(
        AGENT, expected_organization_id=TENANT_A, limit=1,
    )
    result_b = repo_b.list_bounded_by_agent_run_id(
        AGENT, expected_organization_id=TENANT_B, limit=1,
    )
    assert result_a["status"] == result_b["status"] == "ok"
    assert [x["shadow_record_id"] for x in result_a["records"]] == [original["shadow_record_id"]]
    assert [x["shadow_record_id"] for x in result_b["records"]] == [own_b["shadow_record_id"]]

    # The exact-attempt SQL predicate must not be applied after a limit.
    assert repo_a.list_bounded_by_agent_run_id(
        AGENT, expected_organization_id=TENANT_A, run_id=original["run_id"], limit=1,
    )["records"][0]["run_id"] == original["run_id"]
    assert repo_a.list_bounded_by_agent_run_id(
        AGENT, expected_organization_id=TENANT_A, run_id=own_b["run_id"], limit=1,
    )["records"] == []

    # A repository/use-case scope misconfiguration is rejected pre-connection.
    try:
        repo_a.list_bounded_by_agent_run_id(
            AGENT, expected_organization_id=TENANT_B, limit=1,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched scoped repository was not rejected")
    assert _snapshot(dsn, original["shadow_record_id"]) == before


def main() -> None:
    dsn = _require_disposable_environment()
    _install_real_schema(dsn)
    test_real_postgres_shadow_integrity(dsn)
    print("SHADOW_EVIDENCE_REAL_POSTGRES_INTEGRITY=PASS")


if __name__ == "__main__":
    main()
