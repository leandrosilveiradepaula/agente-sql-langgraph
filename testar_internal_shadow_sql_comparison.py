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


def record(sql, *, tenant=None, status="success", generation_provider=None,
           generation_model=None, repair_provider=None, repair_model=None,
           repaired_sql=None, shadow_intent=None):
    principal = {"id": "operator-one", "profile": "admin"}
    if tenant:
        principal["organization_id"] = tenant
    provider_result = {}
    if generation_provider is not None:
        provider_result["sql_generation_result"] = {
            "provider_name": generation_provider,
            "provider_model": generation_model,
        }
    if repair_provider is not None:
        provider_result["sql_repair_result"] = {
            "provider_name": repair_provider,
            "provider_model": repair_model,
        }
    return build_generate_shadow_record(
        shadow_record_id="shadow-1", agent_run_id="product-run-1", run_id="lg-run-1",
        created_at="2026-01-01T00:00:00Z", completed_at="2026-01-01T00:00:01Z",
        status=status,
        request={"question": "Show total orders for last month", "principal": principal},
        state={"generated_sql": sql, "current_sql": repaired_sql or sql,
               "context_fingerprint": "context-one", "context_version": "tenant-config-v1",
               **({"intent": shadow_intent} if shadow_intent is not None else {}),
               **provider_result},
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
    assert modified["response_id"] != matched["response_id"]
    assert modified["response_fingerprint"] != matched["response_fingerprint"]
    assert "predicates" in modified["metadata"]["comparison"]["different_facets"]
    tables = service.execute(request("SELECT SUM(amount) FROM subscriptions", tenant="company-A"))
    assert "physical_tables" in tables["metadata"]["comparison"]["different_facets"]
    assert repo.writes == 0 and repo.reads == 3



def test_signed_provider_model_attestation():
    sql = "SELECT COUNT(*) FROM records"
    repo = FakeRepository(record(
        sql, tenant="tenant-X",
        generation_provider="provider-neutral", generation_model="model-v3"
    ))
    output = CompareShadowSqlUseCase(repository=repo).execute(
        request(sql, tenant="tenant-X")
    )
    assert output["status"] == "success", output
    details = output["metadata"]["comparison"]
    assert details["shadow_generator_provider"] == "provider-neutral"
    assert details["shadow_generator_model"] == "model-v3"
    assert details["shadow_repair_provider"] is None
    assert details["shadow_repair_model"] is None
    assert details["generator_identity_attested"] is True
    assert details["repair_identity_attested"] is True
    assert "token_usage" not in json.dumps(output)
    assert "api_key" not in json.dumps(output)

    # An unrecorded model must remain unattested, never filled from defaults.
    no_model = CompareShadowSqlUseCase(repository=FakeRepository(
        record(sql, generation_provider="provider-neutral")
    )).execute(request(sql))
    partial = no_model["metadata"]["comparison"]
    assert partial["shadow_generator_model"] is None
    assert partial["generator_identity_attested"] is False

    # Tampering with signed provider/model evidence must invalidate the record.
    repo.record["langgraph_evidence"]["provider_metadata"][
        "sql_generation_result_provider_model"
    ] = "model-tampered"
    tampered = CompareShadowSqlUseCase(repository=repo).execute(
        request(sql, tenant="tenant-X")
    )
    assert tampered["status"] == "rejected"
    assert tampered["errors"][0]["code"] == "SHADOW_COMPARE_EVIDENCE_INVALID"

    # A malicious free-form model value is neither reflected nor considered proof.
    unsafe = CompareShadowSqlUseCase(repository=FakeRepository(
        record(sql, generation_provider="provider-neutral", generation_model="Bearer secret")
    )).execute(request(sql))
    assert unsafe["status"] == "success"
    unsafe_info = unsafe["metadata"]["comparison"]
    assert unsafe_info["shadow_generator_model"] is None
    assert unsafe_info["generator_identity_attested"] is False
    assert "Bearer secret" not in json.dumps(unsafe)

def test_repair_provider_identity_for_changed_sql():
    sql = "SELECT item_id FROM entries WHERE category = 'Original'"
    repaired = "SELECT item_id FROM entries WHERE category = 'Corrected'"
    kwargs = {
        "generation_provider": "provider-neutral",
        "generation_model": "model-v3",
        "repaired_sql": repaired,
    }

    incomplete = CompareShadowSqlUseCase(
        repository=FakeRepository(record(sql, **kwargs))
    ).execute(request(sql))
    assert incomplete["status"] == "success", incomplete
    details = incomplete["metadata"]["comparison"]
    assert details["generator_identity_attested"] is True
    assert details["repair_identity_attested"] is False
    assert details["requires_reapproval"] is True
    assert details["financial_parity_proven"] is False

    complete = CompareShadowSqlUseCase(
        repository=FakeRepository(
            record(sql, repair_provider="provider-neutral",
                   repair_model="model-v3", **kwargs)
        )
    ).execute(request(sql))
    assert complete["status"] == "success", complete
    details = complete["metadata"]["comparison"]
    assert details["repair_identity_attested"] is True
    assert details["shadow_repair_model"] == "model-v3"
    assert details["requires_reapproval"] is True

    # Model alone (without a provider) is not evidence of a repair model.
    only_model = CompareShadowSqlUseCase(
        repository=FakeRepository(
            record(sql, repair_provider=None, repair_model="model-v3", **kwargs)
        )
    ).execute(request(sql))
    assert only_model["metadata"]["comparison"]["repair_identity_attested"] is False

def test_case_sensitive_sql_values_and_quoted_identifiers():
    # PostgreSQL text literals and quoted identifier names can be case-sensitive.
    # A casefolded normalized token stream must not be called equivalent.
    lower = "SELECT amount FROM financial_records WHERE entity_code = 'regionA'"
    upper = "SELECT amount FROM financial_records WHERE entity_code = 'RegionA'"
    service = CompareShadowSqlUseCase(repository=FakeRepository(record(upper, tenant="tenant-one")))
    result = service.execute(request(lower, tenant="tenant-one"))
    assert result["status"] == "success", result
    diff = result["metadata"]["comparison"]
    assert diff["normalized_sql_match"] is False, diff
    assert diff["verdict"] != "normalized_sql_match", diff
    assert "predicates" in diff["different_facets"], diff

    quoted_lower = 'SELECT "Amount" FROM financial_records'
    quoted_upper = 'SELECT "amount" FROM financial_records'
    service = CompareShadowSqlUseCase(
        repository=FakeRepository(record(quoted_upper, tenant="tenant-one"))
    )
    result = service.execute(request(quoted_lower, tenant="tenant-one"))
    assert result["status"] == "success", result
    diff = result["metadata"]["comparison"]
    assert diff["normalized_sql_match"] is False
    assert diff["verdict"] != "normalized_sql_match"

    # Unquoted SQL keywords remain case-insensitive and cosmetic whitespace
    # is intentionally ignored (but no literals are case-folded).
    same = "SELECT id FROM financial_records WHERE entity_code = 'RegionA'"
    service = CompareShadowSqlUseCase(
        repository=FakeRepository(record(same.lower().replace("'regiona'", "'RegionA'"), tenant="tenant-one"))
    )
    result = service.execute(request(same, tenant="tenant-one"))
    assert result["status"] == "success", result
    assert result["metadata"]["comparison"]["verdict"] == "normalized_sql_match"


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


def test_recorded_intent_label_pair_is_post_generation_only():
    sql = "SELECT COUNT(*) FROM events"
    service = CompareShadowSqlUseCase(
        repository=FakeRepository(record(sql, shadow_intent="intent-example"))
    )
    exact = service.execute({
        **request(sql), "official_detected_intent": "intent-example"
    })
    assert exact["status"] == "success", exact
    assert exact["metadata"]["comparison"]["intent_label_status"] == "identifiers_matched"

    different = service.execute({
        **request(sql), "official_detected_intent": "different-intent"
    })
    assert different["status"] == "success", different
    assert different["metadata"]["comparison"]["intent_label_status"] == "identifier_mismatch"
    assert "intent-example" not in json.dumps(different)
    assert "different-intent" not in json.dumps(different)
    assert different["metadata"]["comparison"]["financial_parity_proven"] is False

    missing_official = service.execute(request(sql))
    assert missing_official["metadata"]["comparison"]["intent_label_status"] == "unattested"
    missing_shadow = CompareShadowSqlUseCase(
        repository=FakeRepository(record(sql))
    ).execute({**request(sql), "official_detected_intent": "intent-example"})
    assert missing_shadow["metadata"]["comparison"]["intent_label_status"] == "unattested"

    # Extra benchmark/expected labels still cannot reach the generator.
    for wrong in ("", "  ", "x" * 129):
        rejected = service.execute({
            **request(sql), "official_detected_intent": wrong
        })
        assert rejected["status"] == "rejected", rejected
        assert rejected["errors"][0]["code"] == "SHADOW_COMPARE_REQUEST_INVALID"


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
        inner=handler, auth_config=InternalServiceAuthConfig(expected_token="test-s2s-token")
    )
    request_body = json.dumps(request(sql)).encode("utf-8")
    message = {
        "method": "POST", "path": "/v1/internal/sql-agent/compare-shadow-sql",
        "headers": {"Content-Type": "application/json"},
        "body": request_body,
    }
    assert protected.handle(message)["status_code"] == 401
    message["headers"]["Authorization"] = "Bearer test-s2s-token"
    result = protected.handle(message)
    assert result["status_code"] == 200, result
    parsed = json.loads(result["body"])
    assert parsed["status"] == "success"
    fp = parsed.pop("response_fingerprint")
    assert stable_fingerprint(parsed) == fp
    assert sql not in json.dumps(parsed)


if __name__ == "__main__":
    test_structures_and_no_raw_data()
    test_signed_provider_model_attestation()
    test_repair_provider_identity_for_changed_sql()
    test_recorded_intent_label_pair_is_post_generation_only()
    test_case_sensitive_sql_values_and_quoted_identifiers()
    test_isolation_rejection()
    test_missing_corrupted_or_goldens()
    test_distinct_contexts()
    test_authenticated_http_and_response_fingerprint()
    print("POST_GENERATION_SQL_COMPARISON=PASS")
