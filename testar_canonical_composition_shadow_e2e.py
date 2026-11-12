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
from app.adapters.postgres.catalog_composition_sql_generator import (
    CatalogCompositionSqlGenerator,
)
from app.domain.sql_generation import SqlGenerationProviderError
from app.adapters.testing.fake_shadow_evidence_repository import (
    FakeShadowEvidenceRepository,
)
from app.domain.context_normalizer import normalize_context_snapshot
from app.test_runtime.composition import create_shadow_test_runtime
from app.test_runtime.offline_adapters import ShadowTestSqlRepairer
from testar_metric_source_composition_e2e import (
    fixture_a, fixture_b, fixture_temporal, fixture_calendar_year,
    fixture_attested_ratio, fixture_versioned_ranking, fixture_calendar_range,
)
from testar_postgres_context_repository import FakeConnect
from testar_shadow_test_runtime import _env, _run_asgi


class OfflineDynamicSqlGenerator:
    """Spy around the production opt-in provider, not a mock SQL answer."""

    def __init__(self, *, version: str, fingerprint: str) -> None:
        self._adapter = CatalogCompositionSqlGenerator(
            source_mode="canonical_snapshot",
            expected_context_version=version,
            expected_context_fingerprint=fingerprint,
        )
        self.calls = 0
        self.request_fingerprints = []

    def generate(self, request):
        from app.domain.sql_generation import request_fingerprint
        self.calls += 1
        self.request_fingerprints.append(request_fingerprint(request))
        return self._adapter.generate(request)


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
    generator = OfflineDynamicSqlGenerator(
        version=payload["semantic_agent_version"], fingerprint=expected,
    )
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



def test_canonical_shadow_ratio_rule_is_external_and_context_fingerprinted():
    for tenant, raw in (
        ("ratio-fixture-a", fixture_a()),
        ("ratio-fixture-b", fixture_b()),
    ):
        fixture = fixture_attested_ratio(raw)
        runtime, db, generator, evidence = _instance(fixture, tenant)
        http, result = _run_asgi(
            runtime.app, "POST", "/v1/internal/sql-agent/generate",
            _request(tenant, "ratio-source-test-" + tenant),
        )
        assert http == 200, (http, result)
        assert result["status"] == "success", result
        generated = result["sql"]
        assert "NULLIF" in generated
        assert "CASE WHEN" in generated
        assert "UNION ALL" in generated
        assert generator.calls == 1
        assert db.cursor.executed_parameters["tenant_id"] == tenant
        assert evidence.create_calls >= 1
    raw = fixture_attested_ratio(fixture_a())
    pinned = normalize_context_snapshot(
        _canonical_payload(raw, "ratio-fixture-a")
    )["fingerprint"]
    raw["metric_source_compositions"][0]["calculation"]["scale"] = 1
    runtime, _, generator, _ = _instance(
        raw, "ratio-fixture-a", pin=pinned
    )
    http, result = _run_asgi(
        runtime.app, "POST", "/v1/internal/sql-agent/generate",
        _request("ratio-fixture-a", "ratio-fingerprint-changed"),
    )
    assert not (http == 200 and result.get("status") == "success")
    assert generator.calls == 0


def test_canonical_shadow_configured_ranking_two_tenants_and_drift():
    for tenant, base in (("ranking-tenant-one",fixture_a()),("ranking-tenant-two",fixture_b())):
        raw=fixture_versioned_ranking(fixture_calendar_range(base))
        runtime, db, generator, evidence=_instance(raw,tenant)
        http,result=_run_asgi(
            runtime.app, "POST", "/v1/internal/sql-agent/generate",
            _request(
                tenant, "ranking-" + tenant,
                question="synthetic report monthly highest 2 between 2025 and 2026",
            ),
        )
        assert http==200,(http,result)
        assert result["status"]=="success",result
        assert 'ORDER BY "metric_value" DESC NULLS LAST' in result["sql"]
        assert 'LIMIT 2' in result["sql"]
        assert generator.calls==1
        assert db.cursor.executed_parameters["tenant_id"]==tenant
        assert evidence.create_calls>=1
    raw=fixture_versioned_ranking(fixture_calendar_range(fixture_a()))
    pinned=normalize_context_snapshot(_canonical_payload(raw,"ranking-tenant-one"))["fingerprint"]
    raw["metric_source_compositions"][0]["ranking"]["maximum_limit"]=6
    runtime,_,generator,_=_instance(raw,"ranking-tenant-one",pin=pinned)
    status,response=_run_asgi(
        runtime.app,"POST","/v1/internal/sql-agent/generate",
        _request("ranking-tenant-one","ranking-version-drift",
                 question="synthetic report monthly highest 2 between 2025 and 2026"),
    )
    assert not (status==200 and response.get("status")=="success")
    assert generator.calls==0

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



def test_opt_in_compiler_rejects_legacy_mode_or_wrong_version_and_request():
    raw = fixture_temporal(fixture_a())
    payload = _canonical_payload(raw, "tenant-C1")
    fp = normalize_context_snapshot(payload)["fingerprint"]
    for mode, version, fingerprint in (
        ("legacy_tables", payload["semantic_agent_version"], fp),
        ("canonical_snapshot", payload["semantic_agent_version"], ""),
    ):
        try:
            CatalogCompositionSqlGenerator(
                source_mode=mode,
                expected_context_version=version,
                expected_context_fingerprint=fingerprint,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Compiler started without a secure pin")
    from app.domain.sql_generation import build_sql_generation_request
    from testar_metric_source_composition_e2e import _plan
    _, planned = _plan(payload, "synthetic report monthly")
    assert planned["status"] == "planned"
    request = build_sql_generation_request(planned["query_plan"])
    compiler = CatalogCompositionSqlGenerator(
        source_mode="canonical_snapshot",
        expected_context_version=payload["semantic_agent_version"],
        expected_context_fingerprint=fp,
    )
    generated = compiler.generate(request)
    assert generated["output_text"].count("date_trunc('month',") == 2
    assert generated["token_usage"]["total_tokens"] == 0
    wrong = deepcopy(request)
    wrong["generation_context"]["context_fingerprint"] = "a" * 64
    try:
        compiler.generate(wrong)
    except SqlGenerationProviderError as err:
        assert err.reason == "compiler_context_pin_mismatch"
    else:
        raise AssertionError("Wrong tenant context pin was accepted")
    no_composition = deepcopy(request)
    no_composition["generation_context"].pop("metric_source_composition")
    try:
        compiler.generate(no_composition)
    except SqlGenerationProviderError as err:
        assert err.reason == "compiler_composition_not_selected"
    else:
        raise AssertionError("SQL compiler guessed missing composition")



def test_http_canonical_year_filtered_metric_composition():
    for tenant, source in (
        ("period-tenant-1", fixture_a()),
        ("period-tenant-2", fixture_b()),
    ):
        runtime, _, generator, evidence = _instance(
            fixture_calendar_year(source), tenant,
        )
        http, response = _run_asgi(
            runtime.app, "POST", "/v1/internal/sql-agent/generate",
            _request(
                tenant, f"period-scoped-{tenant}",
                question="synthetic report monthly in 2026",
            ),
        )
        assert http == 200 and response["status"] == "success", (http, response)
        sql = response["sql"]
        assert sql.count("'2026-01-01'") == 2
        assert sql.count("'2027-01-01'") == 2
        assert generator.calls == 1 and evidence.create_calls >= 1


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
