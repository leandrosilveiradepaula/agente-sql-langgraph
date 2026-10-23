#!/usr/bin/env python3
"""G1 bridge rehearsal with real disposable PostgreSQL 16 persistence.

Executes the checked-in candidate's n8n Code nodes under Node.js and the
actual S2S ASGI application in memory, with the genuine PostgreSQL evidence
repository. No n8n daemon, real LLM, financial datasource, benchmark, Vercel
traffic, official response or live deployment is accessed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import psycopg

from app.domain.shadow_evidence_types import validate_shadow_run_record
from app.infrastructure.persistence.postgres_shadow_evidence_repository import (
    PostgresShadowEvidenceRepository,
)
from app.test_runtime.composition import create_shadow_test_runtime
from app.test_runtime.offline_adapters import (
    ShadowTestContextRepository,
    ShadowTestSqlGenerator,
    ShadowTestSqlRepairer,
)
from scripts.validation.test_shadow_evidence_integrity_postgres import (
    _install_real_schema,
    _require_disposable_environment,
)
from testar_internal_shadow_read_v1_http_handler import _env, _run_asgi
from testar_n8n_langgraph_offline_bridge import (
    AGENT_RUN_ID,
    QUESTION,
    SYNTHETIC_ORGANIZATION,
    _n8n_code,
    _process_cycle,
    _product_envelope,
    _synthetic_old_record,
)

TABLE = "public.langgraph_shadow_runs"


def _count(dsn: str) -> int:
    with psycopg.connect(dsn) as conn, conn.cursor() as cursor:
        cursor.execute(f"SELECT count(*) FROM {TABLE}")
        return int(cursor.fetchone()[0])


def _stored_attempt(dsn: str, record_id: str) -> tuple:
    with psycopg.connect(dsn) as conn, conn.cursor() as cursor:
        cursor.execute(
            f"SELECT agent_run_id, run_id, event_type, evidence_fingerprint "
            f"FROM {TABLE} WHERE shadow_record_id = %s",
            (record_id,),
        )
        row = cursor.fetchone()
    assert row is not None
    return tuple(row)


def test_correlated_generate_approved_and_compare(dsn: str) -> None:
    # Real PostgreSQL repository, but isolated synthetic context/LLM
    # adapters. The runtime has no financial executor.
    repo = PostgresShadowEvidenceRepository(
        dsn=dsn, expected_organization_id=SYNTHETIC_ORGANIZATION,
    )
    # More than ten historical attempts must not hide the current attempt
    # behind n8n's presentation limit.
    for i in range(13):
        result = repo.create(_synthetic_old_record(f"old-run-{i:03d}"))
        assert result["status"] == "created"
    assert _count(dsn) == 13

    generator = ShadowTestSqlGenerator()
    env = _env()
    env["LANGGRAPH_EXPECTED_ORGANIZATION_ID"] = SYNTHETIC_ORGANIZATION
    runtime = create_shadow_test_runtime(
        env,
        shadow_repository_override=repo,
        context_repository_override=ShadowTestContextRepository(),
        sql_generator_override=generator,
        sql_repairer_override=ShadowTestSqlRepairer(),
    )
    assert runtime.config.allow_real_sql_execution is False

    _, generated, generate_receipt = _process_cycle(runtime, "generate")
    assert generator.calls == 1
    _, approved, execute_receipt = _process_cycle(runtime, "execute_approved")
    assert generator.calls == 1
    assert generated["run_id"] != approved["run_id"]
    assert generate_receipt["shadow_record_id"] != execute_receipt["shadow_record_id"]
    assert _count(dsn) == 15

    for event, response, receipt in (
        ("generate", generated, generate_receipt),
        ("execute_approved", approved, execute_receipt),
    ):
        record_id = receipt["shadow_record_id"]
        stored = repo.fetch_by_shadow_record_id(record_id)
        assert stored["status"] == "ok"
        record = validate_shadow_run_record(stored["record"])
        assert record["agent_run_id"] == AGENT_RUN_ID
        assert record["run_id"] == response["run_id"]
        assert record["principal"]["organization_id"] == SYNTHETIC_ORGANIZATION
        assert record["event_type"] == (
            "generate" if event == "generate" else "execute_approved_shadow"
        )
        assert _stored_attempt(dsn, record_id) == (
            AGENT_RUN_ID, response["run_id"], record["event_type"],
            record["evidence_fingerprint"],
        )
        selected = repo.list_bounded_by_agent_run_id(
            AGENT_RUN_ID,
            run_id=response["run_id"],
            limit=1,
            expected_organization_id=SYNTHETIC_ORGANIZATION,
        )
        assert selected["status"] == "ok"
        assert [r["shadow_record_id"] for r in selected["records"]] == [record_id]

    # The post-generation comparator is evaluation-only and uses the signed,
    # persisted SQL. This is a *self-consistency fixture*, not official SQL
    # or a proof of functional/financial parity.
    comparison_request = {
        "contract_version": "1",
        "agent_run_id": AGENT_RUN_ID,
        "shadow_record_id": generate_receipt["shadow_record_id"],
        "question": QUESTION,
        "official_sql": generated["sql"],
        "principal": {
            "id": "synthetic-user",
            "organization_id": SYNTHETIC_ORGANIZATION,
        },
    }
    status, result = _run_asgi(
        runtime.app, "POST",
        "/v1/internal/sql-agent/compare-shadow-sql",
        comparison_request,
    )
    assert status == 200 and result["status"] == "success"
    view = result["metadata"]["comparison"]
    assert view["shadow_record_id"] == generate_receipt["shadow_record_id"]
    assert view["tenant_identity_attested"] is True
    assert view["real_sql_executed"] is False
    assert view["financial_parity_proven"] is False
    assert view["same_data_snapshot_attested"] is False
    assert generated["sql"] not in json.dumps(result)
    assert _count(dsn) == 15  # Read/compare never writes to evidence store.

    # Mismatching identity cannot reach the LLM or persist evidence even
    # when the n8n JavaScript successfully forwards the foreign principal.
    prepared = _n8n_code(
        "Validate Shadow Envelope",
        {"body": _product_envelope("generate", organization="foreign-tenant")},
    )
    before = _count(dsn)
    code, forbidden = _run_asgi(
        runtime.app, "POST", prepared["target_path"],
        prepared["shadow_request"],
    )
    assert code in (401, 403, 422)
    assert forbidden.get("status") != "success"
    assert "sql" not in forbidden or not forbidden["sql"]
    assert _count(dsn) == before
    assert generator.calls == 1

    # Database-layer isolation is independent of the ASGI principal gate.
    foreign_repo = PostgresShadowEvidenceRepository(
        dsn=dsn, expected_organization_id="foreign-tenant",
    )
    for receipt in (generate_receipt, execute_receipt):
        assert foreign_repo.fetch_by_shadow_record_id(
            receipt["shadow_record_id"],
        )["status"] == "not_found"
    assert foreign_repo.list_bounded_by_agent_run_id(
        AGENT_RUN_ID, limit=10, expected_organization_id="foreign-tenant",
    )["records"] == []


def main() -> None:
    # This denies local/production runs before ANY network/database activity.
    dsn = _require_disposable_environment()
    _install_real_schema(dsn)
    test_correlated_generate_approved_and_compare(dsn)
    print("G1_N8N_ASGI_REAL_POSTGRES_CORRELATION=PASS")


if __name__ == "__main__":
    main()
