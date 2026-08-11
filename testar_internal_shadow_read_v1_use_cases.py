from __future__ import annotations

from copy import deepcopy

from app.adapters.testing.fake_shadow_evidence_repository import (
    FakeShadowEvidenceRepository,
)
from app.adapters.testing.shadow_run_visualization_fixtures import (
    SYNTHETIC_QUESTION,
    SYNTHETIC_REPAIR_SQL,
    SYNTHETIC_SQL,
    all_records,
    generate_for_agent,
)
from app.application.internal_shadow_read_v1 import (
    DEFAULT_SHADOW_RUN_LIST_LIMIT,
    MAX_SHADOW_RUN_LIST_LIMIT,
    GetShadowRunSafeViewUseCase,
    GetShadowRunVisualizationUseCase,
    ListAgentShadowRunsUseCase,
    ShadowReadError,
    validate_shadow_read_id,
)


class FailingRepository:
    def fetch_by_shadow_record_id(self, shadow_record_id: str):
        del shadow_record_id
        raise RuntimeError("postgresql://hidden secret stack trace")

    def list_by_agent_run_id(self, agent_run_id: str):
        del agent_run_id
        raise RuntimeError("postgresql://hidden secret stack trace")


class UnavailableResultRepository:
    def fetch_by_shadow_record_id(self, shadow_record_id: str):
        del shadow_record_id
        return {
            "status": "unavailable",
            "record": None,
            "diagnostic": {
                "code": "SHADOW_REPOSITORY_UNAVAILABLE",
                "message": "raw psycopg postgresql://hidden traceback",
                "failure_category": "unavailable",
                "safe_details": {},
            },
        }

    def list_by_agent_run_id(self, agent_run_id: str):
        del agent_run_id
        return {
            "status": "unavailable",
            "records": [],
            "diagnostic": {
                "code": "SHADOW_REPOSITORY_UNAVAILABLE",
                "message": "raw psycopg SELECT traceback",
                "failure_category": "unavailable",
                "safe_details": {},
            },
        }


def main() -> None:
    records = all_records()
    tests = [
        lambda: _test_shadow_run_found(records),
        lambda: _test_not_found(records),
        lambda: _test_safe_projection_redacts_raw_fields(records),
        lambda: _test_fingerprints_and_ids(records),
        lambda: _test_warnings_errors_requires_reapproval(records),
        _test_repository_unavailable_is_safe,
        lambda: _test_list_by_agent_run_id(records),
        lambda: _test_list_limits(records),
        _test_shadow_read_id_validation,
        lambda: _test_visualization_endpoint_model(records),
        lambda: _test_read_only_guarantee(records),
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__ if hasattr(test, '__name__') else 'scenario'}: OK")
    print("testar_internal_shadow_read_v1_use_cases.py: 44/44 OK")


def _repo_with_records(*records):
    repo = FakeShadowEvidenceRepository()
    for record in records:
        repo.create(record)
    return repo


def _get_view(repo, shadow_record_id):
    return GetShadowRunSafeViewUseCase(repository=repo).execute(shadow_record_id)


def _test_shadow_run_found(records) -> None:
    record = records["generate_without_repair"]
    view = _get_view(_repo_with_records(record), record["shadow_record_id"])
    assert view["shadow_record_id"] == record["shadow_record_id"]
    assert view["contract_version"] == "1"
    assert view["status"] == "success"


def _test_not_found(records) -> None:
    repo = _repo_with_records(records["generate_without_repair"])
    try:
        _get_view(repo, "shadow-missing")
    except ShadowReadError as error:
        assert error.code == "SHADOW_RECORD_NOT_FOUND"
        assert error.status_code == 404
    else:
        raise AssertionError("missing shadow record should return 404")


def _test_safe_projection_redacts_raw_fields(records) -> None:
    record = records["generate_with_secret_metadata"]
    view = _get_view(_repo_with_records(record), record["shadow_record_id"])
    serialized = repr(view)
    blocked_values = [
        SYNTHETIC_QUESTION,
        SYNTHETIC_SQL,
        SYNTHETIC_REPAIR_SQL,
        "sensitive-password-value",
        "sensitive-token-value",
        "sensitive-authorization-value",
        "sensitive-cookie-value",
        "sensitive-dsn-value",
        "sensitive-approved-sql-value",
        "sensitive-repaired-sql-value",
        "sensitive-question-value",
        "sensitive-raw-response-value",
        "raw_response",
        "semantic_context",
    ]
    for value in blocked_values:
        assert value not in serialized
    assert "fingerprints" in serialized
    assert "question" in view["fingerprints"]
    assert "generated_sql" not in view
    assert "approved_sql_original" not in view
    assert "repaired_sql_proposal" not in view


def _test_fingerprints_and_ids(records) -> None:
    record = records["generate_without_repair"]
    view = _get_view(_repo_with_records(record), record["shadow_record_id"])
    assert view["agent_run_id"] == record["agent_run_id"]
    assert view["run_id"] == record["run_id"]
    assert view["event_type"] == "generate"
    assert "question" in view["fingerprints"]
    assert "langgraph_sql" in view["fingerprints"]
    assert "sql_fingerprint" in view["lineage"]


def _test_warnings_errors_requires_reapproval(records) -> None:
    record = records["execute_approved_repair_reapproval"]
    view = _get_view(_repo_with_records(record), record["shadow_record_id"])
    serialized = repr(view)
    assert view["requires_reapproval"] is True
    assert view["gates"]["preflight"]["repairable"] is True
    assert "message" not in serialized
    assert SYNTHETIC_REPAIR_SQL not in serialized


def _test_repository_unavailable_is_safe() -> None:
    try:
        _get_view(FailingRepository(), "shadow-any")
    except ShadowReadError as error:
        serialized = repr(error)
        assert error.code == "SHADOW_REPOSITORY_UNAVAILABLE"
        assert error.status_code == 503
        assert "postgresql://" not in serialized
        assert "secret" not in serialized
    else:
        raise AssertionError("failing repository should become safe 503")
    try:
        _get_view(UnavailableResultRepository(), "shadow-any")
    except ShadowReadError as error:
        serialized = repr(error)
        assert error.code == "SHADOW_REPOSITORY_UNAVAILABLE"
        assert error.status_code == 503
        assert "postgresql://" not in serialized
        assert "psycopg" not in serialized.casefold()
        assert "traceback" not in serialized.casefold()
    else:
        raise AssertionError("unavailable fetch result should become safe 503")
    try:
        ListAgentShadowRunsUseCase(repository=UnavailableResultRepository()).execute(
            "agent-run-any",
            limit=10,
        )
    except ShadowReadError as error:
        serialized = repr(error)
        assert error.code == "SHADOW_REPOSITORY_UNAVAILABLE"
        assert error.status_code == 503
        assert "select" not in serialized.casefold()
        assert "traceback" not in serialized.casefold()
    else:
        raise AssertionError("unavailable list result should become safe 503")


def _test_list_by_agent_run_id(records) -> None:
    first = records["generate_without_repair"]
    second = records["execute_approved_valid"]
    other = generate_for_agent("agent-run-other", "lg-run-other")
    repo = _repo_with_records(second, other, first)
    result = ListAgentShadowRunsUseCase(repository=repo).execute(
        first["agent_run_id"],
        limit=10,
    )
    items = result["items"]
    assert result["agent_run_id"] == first["agent_run_id"]
    assert [item["event_type"] for item in items] == [
        "generate",
        "execute_approved_shadow",
    ]
    assert all(item["agent_run_id"] == first["agent_run_id"] for item in items)
    assert "lg-run-other" not in repr(result)
    assert items[0]["created_at"] <= items[1]["created_at"]
    assert isinstance(items[0]["has_repair"], bool)
    assert isinstance(items[0]["has_error"], bool)


def _test_list_limits(records) -> None:
    repo = _repo_with_records(
        records["generate_without_repair"],
        records["generate_with_repair"],
        records["execute_approved_valid"],
    )
    use_case = ListAgentShadowRunsUseCase(repository=repo)
    default_result = use_case.execute(records["generate_without_repair"]["agent_run_id"])
    assert default_result["limit"] == DEFAULT_SHADOW_RUN_LIST_LIMIT
    assert len(default_result["items"]) == 3
    limited = use_case.execute(
        records["generate_without_repair"]["agent_run_id"],
        limit=2,
    )
    assert limited["limit"] == 2
    assert len(limited["items"]) == 2
    empty = use_case.execute("agent-run-empty", limit=10)
    assert empty["items"] == []
    for invalid in (0, -1, MAX_SHADOW_RUN_LIST_LIMIT + 1):
        try:
            use_case.execute(records["generate_without_repair"]["agent_run_id"], limit=invalid)
        except ShadowReadError as error:
            assert error.code == "SHADOW_RUN_LIMIT_INVALID"
            assert error.status_code == 400
        else:
            raise AssertionError("invalid limit should fail")


def _test_shadow_read_id_validation() -> None:
    valid_ids = [
        "shadow-0123456789abcdef0123456789abcdef",
        "agent-run-1",
        "ABC",
        "abc",
        "123",
        "a-b_c",
    ]
    for value in valid_ids:
        assert validate_shadow_read_id(value, field="agent_run_id") == value
    invalid_ids = [
        "agent-run-á",
        "agent-run-\u0430",
        "agent-run-\U0001f600",
        "agent run",
        "agent/run",
        "agent\\run",
        "..",
        "agent%run",
        "agent?run",
        "agent#run",
        "a" * 161,
    ]
    for value in invalid_ids:
        try:
            validate_shadow_read_id(value, field="agent_run_id")
        except ShadowReadError as error:
            assert error.status_code == 400
        else:
            raise AssertionError(f"invalid id accepted: {value!r}")


def _test_visualization_endpoint_model(records) -> None:
    repo = _repo_with_records(
        records["generate_with_two_repairs"],
        records["execute_approved_repair_reapproval"],
        records["internal_error_sanitized"],
    )
    use_case = GetShadowRunVisualizationUseCase(repository=repo)
    generate = use_case.execute(records["generate_with_two_repairs"]["shadow_record_id"])
    execute = use_case.execute(
        records["execute_approved_repair_reapproval"]["shadow_record_id"]
    )
    unknown = use_case.execute(records["internal_error_sanitized"]["shadow_record_id"])
    serialized = repr(generate) + repr(execute) + repr(unknown)
    assert generate["contract_version"] == "1"
    assert generate["run"]["event_type"] == "generate"
    assert [step["label"] for step in generate["steps"]].count("repair_sql") == 2
    assert generate["steps"][-1]["label"] == "final"
    assert execute["flags"]["requires_reapproval"] is True
    assert "evidence_not_recorded" in [step["label"] for step in unknown["steps"]]
    assert SYNTHETIC_SQL not in serialized
    assert SYNTHETIC_QUESTION not in serialized
    assert "metadata" in generate["steps"][0]
    try:
        use_case.execute("shadow-missing")
    except ShadowReadError as error:
        assert error.status_code == 404
    else:
        raise AssertionError("missing visualization should return 404")


def _test_read_only_guarantee(records) -> None:
    repo = _repo_with_records(records["generate_without_repair"])
    before = deepcopy((repo.create_calls, repo.update_calls, repo.finalize_calls))
    shadow_record_id = records["generate_without_repair"]["shadow_record_id"]
    _get_view(repo, shadow_record_id)
    GetShadowRunVisualizationUseCase(repository=repo).execute(shadow_record_id)
    ListAgentShadowRunsUseCase(repository=repo).execute(
        records["generate_without_repair"]["agent_run_id"],
        limit=10,
    )
    after = (repo.create_calls, repo.update_calls, repo.finalize_calls)
    assert after == before


if __name__ == "__main__":
    main()
