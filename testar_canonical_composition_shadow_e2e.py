"""Full isolated Shadow HTTP path for dynamic, two-source metric SQL.

Exercise application → auth/scope → approved canonical context → real
LangGraph classification/planner → generator port → SQL Security/Contract
gates → sanitized evidence. The generator adapter is local and structural;
no LLM, n8n, customer DB, benchmark, approval of G5 accounting, or SQL execute.
"""
from __future__ import annotations

from copy import deepcopy

from app.adapters.postgres.canonical_context_repository import (
    CanonicalContextRepository,
)
from app.adapters.postgres.metric_source_composition_sql import (
    build_postgres_metric_source_sql,
)
from app.adapters.testing.fake_shadow_evidence_repository import (
    FakeShadowEvidenceRepository,
)
from app.domain.context_normalizer import normalize_context_snapshot
from app.test_runtime.composition import create_shadow_test_runtime
from app.test_runtime.offline_adapters import ShadowTestSqlRepairer
from testar_metric_source_composition_e2e import (
    fixture_a, fixture_b, fixture_temporal,
)
from testar_postgres_context_repository import FakeConnect
from testar_shadow_test_runtime import _env, _run_asgi


class OfflineDynamicSqlGenerator:
    def __init__(self) -> None:
        self.calls = 0
        self.request_fingerprints = []

    def generate(self, request):
        from app.domain.sql_generation import request_fingerprint
        self.calls += 1
        self.request_fingerprints.append(request_fingerprint(request))
        return {
            "provider_name": "offline_contract_renderer",
            "provider_model": "non_llm_test_adapter",
            "output_text": build_postgres_metric_source_sql(request),
        }


def _canonical_payload(raw: dict, tenant: str) -> dict:
    payload = deepcopy(raw)
    for original, mapped in (
        ("rules", "regras"),
        ("entities", "entidades"),
        ("dre_mappings", "dre"),
        ("query_patterns", "padroes"),
        ("table_catalog", "catalogo"),
    ):
        payload[mapped] = payload.pop(original)
    for pattern in payload["padroes"]:
        pattern.update({
            "source_use": "APPROVED_SEMANTIC_STRUCTURAL",
            "business_question_examples": [],
            "sql_pattern": "",
            "notes": None,
        })
    payload.update({
        "tenant_id": tenant,
        "source_approval_status": "APPROVED",
        "historical_evaluation_sql_excluded": True,
    })
    return payload


def _instance(raw: dict, tenant: str, *, pin: str | None = None):
    payload = _canonical_payload(raw, tenant)
    expected = pin or normalize_context_snapshot(payload)["fingerprint"]
    fake_db = FakeConnect(
        row={"snapshot_payload": payload, "matching_rows": 1}
    )
    repo = CanonicalContextRepository(
        dsn="postgresql://fake.invalid/catalog",
        tenant_id=tenant,
        semantic_agent_version=payload["semantic_agent_version"],
        expected_context_fingerprint=expected,
        context_schema="approved_metadata",
        context_table="versioned_snapshots",
        connect=fake_db,
    )
    generator = OfflineDynamicSqlGenerator()
    evidence = FakeShadowEvidenceRepository()
    env = _env(
        SEMANTIC_AGENT_VERSION=payload["semantic_agent_version"],
        LANGGRAPH_EXPECTED_ORGANIZATION_ID=tenant,
        SEMANTIC_CONTEXT_EXPECTED_FINGERPRINT=expected,
    )
    runtime = create_shadow_test_runtime(
        env,
        shadow_repository_override=evidence,
        context_repository_override=repo,
        sql_generator_override=generator,
        sql_repairer_override=ShadowTestSqlRepairer("SELECT 1"),
    )
    assert runtime.config.allow_real_sql_execution is False
    return runtime, fake_db, generator, evidence


def _request(
    tenant: str, run_id: str,
    question: str = "synthetic report about two combined streams",
) -> dict:
    return {
        "contract_version": "1",
        "agent_run_id": run_id,
        "question": question,
        "principal": {
            "id": "operator-fixture",
            "profile": "sql_generation",
            "organization_id": tenant,
        },
        "correlation_metadata": {
            "source": "offline-dynamic-composition-witness",
        },
    }


def test_end_to_end_two_canonical_tenants_generate_real_dynamic_sql_offline():
    first, second = fixture_a(), fixture_b()
    observed = []
    for tenant, fixture in (("tenant-C1", first), ("tenant-C2", second)):
        runtime, db, generator, evidence = _instance(fixture, tenant)
        http, result = _run_asgi(
            runtime.app, "POST", "/v1/internal/sql-agent/generate",
            _request(tenant, "synthetic-composition-" + tenant),
        )
        assert http == 200, (tenant, http, result)
        assert result["status"] == "success", (tenant, result)
        sql = result.get("sql", "")
        assert "UNION ALL" in sql
        assert "JOIN" not in sql
        assert "SUM" in sql
        for source in fixture["metric_source_compositions"][0]["sources"]:
            assert source["target_table"].split(".")[0] in sql
            assert source["value_column"] in sql
        assert generator.calls == 1
        assert len(generator.request_fingerprints) == 1
        assert db.cursor.executed_parameters == {
            "tenant_id": tenant,
            "agent_version": fixture["semantic_agent_version"],
        }
        assert "WHERE tenant_id =" in db.cursor.executed_query
        assert evidence.create_calls >= 1
        assert all(
            record.get("principal", {}).get("organization_id") == tenant
            for record in evidence.created_records
        )
        observed.append(sql)
    assert observed[0] != observed[1]


def test_mismatched_principal_cannot_reuse_another_tenants_catalog():
    runtime, _, generator, _ = _instance(fixture_a(), "tenant-C1")
    http, response = _run_asgi(
        runtime.app, "POST", "/v1/internal/sql-agent/generate",
        _request("tenant-C2", "synthetic-cross-tenant"),
    )
    assert not (http == 200 and response.get("status") == "success")
    assert generator.calls == 0


def test_changed_sign_requires_new_fingerprint_before_generator():
    raw = fixture_a()
    current = normalize_context_snapshot(
        _canonical_payload(raw, "tenant-C1")
    )["fingerprint"]
    raw["metric_source_compositions"][0]["sources"][1][
        "sign_multiplier"
    ] = 1
    runtime, _, generator, _ = _instance(
        raw, "tenant-C1", pin=current,
    )
    http, response = _run_asgi(
        runtime.app, "POST", "/v1/internal/sql-agent/generate",
        _request("tenant-C1", "synthetic-drift"),
    )
    assert not (http == 200 and response.get("status") == "success")
    assert generator.calls == 0



def test_http_shadow_monthly_composition_for_two_unrelated_tenants():
    for name, data in (
        ("temporal-tenant-a", fixture_a()),
        ("temporal-tenant-b", fixture_b()),
    ):
        runtime, _, generator, evidence = _instance(
            fixture_temporal(data), name,
        )
        http, result = _run_asgi(
            runtime.app, "POST", "/v1/internal/sql-agent/generate",
            _request(
                name, f"temporal-composition-{name}",
                question="synthetic report monthly",
            ),
        )
        assert http == 200 and result["status"] == "success", (http, result)
        assert result["sql"].count("date_trunc('month',") == 2
        assert generator.calls == 1
        assert evidence.create_calls >= 1


def main():
    tests = sorted(
        (name, test) for name, test in globals().items()
        if name.startswith("test_") and callable(test)
    )
    for name, test in tests:
        test()
        print("PASS", name)
    print("TOTAL_TESTS", len(tests))


if __name__ == "__main__":
    main()
