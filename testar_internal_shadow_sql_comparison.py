"""Correlated post-generation SQL comparison. No LLM, SQL engine or network."""
from __future__ import annotations

import json
from copy import deepcopy

from app.application.internal_shadow_sql_comparison import CompareShadowSqlUseCase
from app.domain.result_normalization import stable_fingerprint
from app.domain.shadow_evidence_types import build_generate_shadow_record
from app.http.internal_sql_agent_v1_handler import InternalSqlAgentV1HttpHandler
from app.http.internal_service_auth_handler import protect_internal_service_http_handler
from app.security.internal_service_auth import InternalServiceAuthConfig


class FakeRepository:
    def __init__(self, record=None):
        self.record = record
        self.reads = 0
        self.writes = 0

    def fetch_by_shadow_record_id(self, key):
        self.reads += 1
        if self.record is None or self.record.get("shadow_record_id") != key:
            return {"status": "not_found", "record": None, "diagnostic": None}
        return {"status": "ok", "record": deepcopy(self.record), "diagnostic": None}

    def create(self, *args, **kwargs):
        self.writes += 1
        raise AssertionError("Comparison must not write")

    update_evidence = create
    finalize = create


def record(sql, *, tenant=None, status="success"):
    principal = {"id": "operator-one", "profile": "admin"}
    if tenant:
        principal["organization_id"] = tenant
    return build_generate_shadow_record(
        shadow_record_id="shadow-1", agent_run_id="product-run-1", run_id="lg-run-1",
        created_at="2026-01-01T00:00:00Z", completed_at="2026-01-01T00:00:01Z",
        status=status,
        request={"question": "Show total orders for last month", "principal": principal},
        state={"generated_sql": sql, "current_sql": sql,
               "context_fingerprint": "context-one", "context_version": "tenant-config-v1"},
        response={"status": status, "gates": {}},
    )


def request(sql, *, tenant=None):
    principal = {"id": "operator-one"}
    if tenant:
        principal["organization_id"] = tenant
    return {
        "contract_version": "1", "agent_run_id": "product-run-1",
        "shadow_record_id": "shadow-1",
        "question": "Show total orders for last month",
        "official_sql": sql, "principal": principal,
    }


def test_structures_and_no_raw_data():
    expected = "SELECT SUM(amount) AS total FROM orders WHERE period_id = 202610"
    repo = FakeRepository(record("select SUM(amount) as total from orders where period_id=202610;", tenant="company-A"))
    service = CompareShadowSqlUseCase(repository=repo)
    matched = service.execute(request(expected, tenant="company-A"))
    assert matched["status"] == "success", matched
    parity = matched["metadata"]["comparison"]
    assert parity["verdict"] == "normalized_sql_match", parity
    assert parity["tenant_identity_attested"] is True
    assert parity["financial_parity_proven"] is False
    assert parity["real_sql_executed"] is False
    assert "202610" not in json.dumps(matched)
    assert "orders" not in json.dumps(matched)
    modified = service.execute(request("SELECT SUM(amount) AS total FROM orders WHERE period_id = 202611", tenant="company-A"))
    assert modified["status"] == "success", modified
    assert modified["metadata"]["comparison"]["verdict"] == "structural_differences"
    assert "predicates" in modified["metadata"]["comparison"]["different_facets"]
    tables = service.execute(request("SELECT SUM(amount) FROM subscriptions", tenant="company-A"))
    assert "physical_tables" in tables["metadata"]["comparison"]["different_facets"]
    assert repo.writes == 0 and repo.reads == 3


def test_isolation_rejection():
    sql = "SELECT id FROM entries"
    repo = FakeRepository(record(sql, tenant="tenant-one"))
    service = CompareShadowSqlUseCase(repository=repo)
    base = request(sql, tenant="tenant-one")
    for key, value, expected_error in (
        ("question", "Different question", "SHADOW_COMPARE_QUESTION_MISMATCH"),
        ("agent_run_id", "run-other", "SHADOW_COMPARE_IDENTITY_MISMATCH"),
        ("principal", {"id": "intruder", "organization_id": "tenant-one"}, "SHADOW_COMPARE_IDENTITY_MISMATCH"),
        ("principal", {"id": "operator-one", "organization_id": "tenant-two"}, "SHADOW_COMPARE_TENANT_MISMATCH"),
        ("principal", {"id": "operator-one"}, "SHADOW_COMPARE_TENANT_MISMATCH"),
    ):
        arg = deepcopy(base)
        arg[key] = value
        result = service.execute(arg)
        assert result["status"] == "rejected" and result["errors"][0]["code"] == expected_error, result
    for bad_sql in ("DELETE FROM entries", "SELECT * INTO temporary FROM entries", "SELECT 1; DROP TABLE entries;"):
        result = service.execute({**base, "official_sql": bad_sql})
        assert result["status"] == "rejected", result
    assert repo.writes == 0


def test_missing_corrupted_or_goldens():
    sql = "SELECT id FROM records"
    repo = FakeRepository()
    service = CompareShadowSqlUseCase(repository=repo)
    assert service.execute(request(sql))["errors"][0]["code"] == "SHADOW_COMPARE_EVIDENCE_MISSING"
    repo.record = record(sql)
    repo.record["generated_sql"] = "SELECT changed FROM records"
    bad = service.execute(request(sql))
    assert bad["status"] == "rejected"
    assert bad["errors"][0]["code"] in ("SHADOW_COMPARE_EVIDENCE_INVALID", "SHADOW_COMPARE_SQL_FINGERPRINT_MISMATCH")
    repo.record = record(sql, status="rejected")
    assert service.execute(request(sql))["errors"][0]["code"] == "SHADOW_COMPARE_GENERATION_NOT_SUCCESSFUL"
    repo.record = record(sql)
    assert service.execute({**request(sql), "golden_answer": "no"})["errors"][0]["code"] == "SHADOW_COMPARE_REQUEST_INVALID"


def test_distinct_contexts():
    for tenant, sql in (
        ("tenant-alpha", "SELECT AVG(score) FROM quality_events WHERE segment = 'regional'"),
        ("tenant-beta", "SELECT COUNT(*) FROM registration_log WHERE created_day >= '2026-01-01'"),
    ):
        service = CompareShadowSqlUseCase(repository=FakeRepository(record(sql, tenant=tenant)))
        result = service.execute(request(sql, tenant=tenant))
        assert result["status"] == "success", result
        assert result["metadata"]["comparison"]["verdict"] == "normalized_sql_match"
        assert result["metadata"]["comparison"]["financial_parity_proven"] is False


class NeverCalled:
    def execute(self, arg):
        raise AssertionError("Generation and approved execution must remain unused")


def test_authenticated_http_and_response_fingerprint():
    sql = "SELECT id FROM records"
    use_case = CompareShadowSqlUseCase(repository=FakeRepository(record(sql)))
    handler = InternalSqlAgentV1HttpHandler(
        generate_use_case=NeverCalled(),
        execute_approved_shadow_use_case=NeverCalled(),
        compare_shadow_sql_use_case=use_case,
    )
    protected = protect_internal_service_http_handler(
        inner=handler, auth_config=InternalServiceAuthConfig(expected_token="offline-s2s-token")
    )
    request_body = json.dumps(request(sql)).encode("utf-8")
    message = {
        "method": "POST", "path": "/v1/internal/sql-agent/compare-shadow-sql",
        "headers": {"Content-Type": "application/json"},
        "body": request_body,
    }
    assert protected.handle(message)["status_code"] == 401
    message["headers"]["Authorization"] = "Bearer offline-s2s-token"
    result = protected.handle(message)
    assert result["status_code"] == 200, result
    parsed = json.loads(result["body"])
    assert parsed["status"] == "success"
    fp = parsed.pop("response_fingerprint")
    assert stable_fingerprint(parsed) == fp
    assert sql not in json.dumps(parsed)


if __name__ == "__main__":
    test_structures_and_no_raw_data()
    test_isolation_rejection()
    test_missing_corrupted_or_goldens()
    test_distinct_contexts()
    test_authenticated_http_and_response_fingerprint()
    print("POST_GENERATION_SQL_COMPARISON=PASS")
