"""J2: same LangGraph runtime against two materially different catalogs.

Proves real S2S -> context loading -> semantic resolution -> planner ->
SQL security/contract gates and evidence flow with *injected offline*
providers. These fake SQLs are fixtures, NOT benchmark-derived responses
and do NOT prove LLM quality or cross-client financial equivalence.
"""
from __future__ import annotations

import json
from copy import deepcopy

from app.adapters.testing.fake_shadow_evidence_repository import (
    FakeShadowEvidenceRepository,
)
from app.adapters.postgres.context_repository import PostgresContextRepository
from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.context_validator import validate_context_snapshot
from app.test_runtime.composition import create_shadow_test_runtime
from app.test_runtime.offline_adapters import (
    ShadowTestContextRepository,
    ShadowTestSqlGenerator,
    ShadowTestSqlRepairer,
)
from testar_postgres_context_repository import FakeConnect
from testar_shadow_test_runtime import _env, _run_asgi


def _raw_base() -> dict:
    """Reuse already valid structural offline contract, not n8n answers."""
    canonical = ShadowTestContextRepository().load_active_context(
        user_profile="portability_test"
    )
    return {
        "semantic_agent_version": "portable-context-a-v1",
        "semantic_context_source": "synthetic_portability",
        "regras": deepcopy(canonical["rules"]),
        "entidades": deepcopy(canonical["entities"]),
        "dre": [],
        "padroes": deepcopy(canonical["query_patterns"]),
        "catalogo": deepcopy(canonical["table_catalog"]),
        "context_counts": {
            "regras": len(canonical["rules"]),
            "entidades": len(canonical["entities"]),
            "dre": 0,
            "padroes": len(canonical["query_patterns"]),
            "catalogo": len(canonical["table_catalog"]),
        },
    }


def _raw_alternative() -> dict:
    """Different schema, columns, metric vocabulary and intent, with no DRE."""
    source = _raw_base()
    source["semantic_agent_version"] = "portable-context-b-v1"
    source["entidades"][0]["user_term"] = "invoice ledger analysis"
    source["entidades"][0]["canonical_value"] = "ledger_reporting"
    source["regras"][1]["applies_to_intents"] = ["ledger_reporting"]
    source["padroes"][0]["intent_name"] = "ledger_reporting"
    source["padroes"][0]["pattern_name"] = "synthetic_ledger_pattern"
    source["padroes"][0]["required_tables"] = ["billing_archive.billing_entries"]
    table = source["catalogo"][0]
    table.update({
        "schema_name": "billing_archive",
        "table_name": "billing_entries",
        "primary_key": ["record_key"],
        "key_columns": ["record_key"],
        "metric_columns": ["net_amount"],
        "date_columns": ["invoice_date"],
    })
    return source


def _request(question: str, agent_run_id: str, organization_id: str) -> dict:
    return {
        "contract_version": "1",
        "agent_run_id": agent_run_id,
        "question": question,
        "principal": {
            "id": "synthetic-operator",
            "profile": "runtime_validation",
            "organization_id": organization_id,
        },
        "correlation_metadata": {
            "source": "independent-portability-fixture",
        },
    }


def _runtime(raw: dict, *, source_name: str, sql: str, pin: str | None = None):
    conn = FakeConnect(row=raw)
    fake_sql_generator = ShadowTestSqlGenerator(sql)
    fake_shadow = FakeShadowEvidenceRepository()
    version = raw["semantic_agent_version"]
    env = _env(
        SEMANTIC_AGENT_VERSION=version,
        CONTEXT_POSTGRES_DSN=f"postgresql://{source_name}.invalid/context",
        LANGGRAPH_EXPECTED_ORGANIZATION_ID=source_name,
        SEMANTIC_CONTEXT_EXPECTED_FINGERPRINT=pin or normalize_context_snapshot(raw)["fingerprint"],
        **({
            "POSTGRES_CONTEXT_SCHEMA": "alt_metadata",
            "CONTEXT_CATALOG_TABLES_JSON": json.dumps({
                "rules": "semantic_rules",
                "entities": "semantic_aliases",
                "dre": None,
                "patterns": "semantic_patterns",
                "catalog": "semantic_tables",
            }),
        } if source_name == "tenant-B" else {}),
    )
    runtime = create_shadow_test_runtime(
        env,
        shadow_repository_override=fake_shadow,
        context_connect_override=conn,
        sql_generator_override=fake_sql_generator,
        sql_repairer_override=ShadowTestSqlRepairer(sql),
    )
    assert isinstance(runtime.context_repository, PostgresContextRepository)
    assert runtime.config.allow_real_sql_execution is False
    return runtime, conn, fake_sql_generator, fake_shadow


def test_same_runtime_plans_and_gates_two_independent_catalogs() -> None:
    first, second = _raw_base(), _raw_alternative()
    first_snapshot = normalize_context_snapshot(first)
    second_snapshot = normalize_context_snapshot(second)
    assert first_snapshot["fingerprint"] != second_snapshot["fingerprint"]
    assert first_snapshot["allowed_schemas"] == ["schema_test"]
    assert second_snapshot["allowed_schemas"] == ["billing_archive"]
    assert first_snapshot["dre_mappings"] == second_snapshot["dre_mappings"] == []
    for snapshot in (first_snapshot, second_snapshot):
        checked = validate_context_snapshot(snapshot)
        assert checked["status"] == "valid", [
            e["code"] for e in checked["errors"]
        ]

    cases = (
        ("tenant-A", first, "Execute uma generic analysis de teste.",
         "SELECT id FROM schema_test.table_test", "schema_test.table_test"),
        ("tenant-B", second, "Execute uma invoice ledger analysis de teste.",
         "SELECT record_key FROM billing_archive.billing_entries",
         "billing_archive.billing_entries"),
    )
    for idx, (tenant, raw, question, sql, physical_table) in enumerate(cases):
        runtime, conn, fake_generator, evidence = _runtime(
            raw, source_name=tenant, sql=sql
        )
        http, response = _run_asgi(
            runtime.app,
            "POST",
            "/v1/internal/sql-agent/generate",
            _request(question, f"synthetic-j2-run-{idx}", tenant),
        )
        assert http == 200, (tenant, http, response.get("errors"))
        assert response["status"] == "success", (tenant, response.get("errors"))
        assert response["sql"] == sql
        assert fake_generator.calls == 1
        assert response.get("plan_status") == "planned"
        assert conn.cursor.executed_parameters == {
            "agent_version": raw["semantic_agent_version"],
        }
        assert "benchmark" not in conn.cursor.executed_query.lower()
        if tenant == "tenant-B":
            assert "alt_metadata.semantic_rules" in conn.cursor.executed_query
            assert "ai_ducklake_dre_mapping" not in conn.cursor.executed_query
        assert evidence.create_calls >= 1
        assert all(
            item.get("principal", {}).get("organization_id") == tenant
            for item in evidence.created_records
        )
        serialized = repr(response.get("metadata", {}))
        assert physical_table.split(".")[0] in (
            repr(response) + repr(evidence.created_records)
        )


def test_fingerprint_drift_blocks_generation_before_provider_even_same_version() -> None:
    original = _raw_base()
    frozen = normalize_context_snapshot(original)["fingerprint"]
    drift = deepcopy(original)
    drift["catalogo"][0]["metric_columns"] = ["unapproved_measure"]
    drift["semantic_agent_version"] = original["semantic_agent_version"]
    assert normalize_context_snapshot(drift)["fingerprint"] != frozen

    runtime, conn, generator, evidence = _runtime(
        drift,
        source_name="tenant-A",
        sql="SELECT id FROM schema_test.table_test",
        pin=frozen,
    )
    status, body = _run_asgi(
        runtime.app,
        "POST",
        "/v1/internal/sql-agent/generate",
        _request("Execute uma generic analysis de teste.", "j2-drift-run", "tenant-A"),
    )
    assert status != 200 or body["status"] != "success"
    assert generator.calls == 0
    assert not body.get("sql")
    assert conn.cursor.executed_parameters == {
        "agent_version": original["semantic_agent_version"],
    }
    serialized = json.dumps(body, ensure_ascii=False)
    for forbidden in (
        frozen, "unapproved_measure", "postgresql://", "SELECT id",
    ):
        assert forbidden not in serialized
    assert "CONTEXT_LOAD_FAILED" in serialized


def test_tenant_mismatch_rejected_before_even_loading_context() -> None:
    runtime, conn, generator, evidence = _runtime(
        _raw_base(),
        source_name="tenant-A",
        sql="SELECT id FROM schema_test.table_test",
    )
    status, body = _run_asgi(
        runtime.app, "POST", "/v1/internal/sql-agent/generate",
        _request("Execute uma generic analysis de teste.", "cross-tenant-run", "tenant-B"),
    )
    assert body["status"] != "success"
    assert generator.calls == 0
    assert conn.cursor.executed_query is None
    assert evidence.create_calls == 0
    assert "tenant-A" not in json.dumps(body)


def test_unknown_metric_in_other_context_does_not_fallback_to_first_client() -> None:
    runtime, conn, generator, _ = _runtime(
        _raw_alternative(),
        source_name="tenant-B",
        sql="SELECT record_key FROM billing_archive.billing_entries",
    )
    status, body = _run_asgi(
        runtime.app, "POST", "/v1/internal/sql-agent/generate",
        _request("Execute uma generic analysis de teste.", "j2-unmapped-run", "tenant-B"),
    )
    assert body["status"] != "success"
    assert generator.calls == 0
    assert "schema_test.table_test" not in json.dumps(body)


def main() -> None:
    tests = (
        test_same_runtime_plans_and_gates_two_independent_catalogs,
        test_fingerprint_drift_blocks_generation_before_provider_even_same_version,
        test_tenant_mismatch_rejected_before_even_loading_context,
        test_unknown_metric_in_other_context_does_not_fallback_to_first_client,
    )
    for test in tests:
        test()
        print(test.__name__ + ": PASS")
    print("J2_OFFLINE_CONTEXT_PORTABILITY=PASS")


if __name__ == "__main__":
    main()
