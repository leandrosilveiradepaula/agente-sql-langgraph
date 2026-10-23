from __future__ import annotations

"""Offline two-tenant Shadow evidence READ/COMPARE regression.

No network, deployed runtime, external SQL execution, LLM, database write or
business schema. Exact tenant equality comes from deployment configuration.
"""

from copy import deepcopy
from typing import Any

from app.adapters.testing.fake_shadow_evidence_repository import (
    FakeShadowEvidenceRepository,
)
from app.adapters.testing.shadow_run_visualization_fixtures import (
    SYNTHETIC_QUESTION,
    SYNTHETIC_SQL,
    generate_for_agent,
)
from app.application.internal_shadow_read_v1 import (
    GetShadowRunSafeViewUseCase,
    GetShadowRunVisualizationUseCase,
    ListAgentShadowRunsUseCase,
    ShadowReadError,
)
from app.application.internal_shadow_sql_comparison import CompareShadowSqlUseCase
from app.domain.result_normalization import stable_fingerprint
from app.domain.shadow_evidence_types import (
    _fingerprint_payload,
    validate_shadow_run_record,
)
from app.infrastructure.persistence.postgres_shadow_evidence_repository import (
    PostgresShadowEvidenceRepository,
)
from app.test_runtime.composition import create_shadow_test_runtime
from app.test_runtime.offline_adapters import (
    ShadowTestContextRepository,
    ShadowTestSqlGenerator,
    ShadowTestSqlRepairer,
)
from testar_internal_shadow_read_v1_http_handler import (
    _env as _offline_env,
    _run_asgi as _asgi_request,
)


def _record(organization_id: str, run_id: str) -> dict[str, Any]:
    # Rewrite only a synthetic principal; reattest the entire fixture using
    # the real evidence fingerprint contract rather than bypass validation.
    source = generate_for_agent("agent-shared", run_id)
    source["principal"]["organization_id"] = organization_id
    evidence_digest = stable_fingerprint(_fingerprint_payload(source))
    source["fingerprints"]["evidence_payload"] = evidence_digest
    source["evidence_fingerprint"] = evidence_digest
    return validate_shadow_run_record(source)


def _expect_not_found(callback) -> None:
    try:
        callback()
    except ShadowReadError as error:
        assert error.status_code == 404
        assert error.code == "SHADOW_RECORD_NOT_FOUND"
        assert "organization" not in str(error).casefold()
    else:
        raise AssertionError("foreign/missing tenant must be non-enumerable")


def test_read_and_visualization_never_return_foreign_tenant() -> None:
    repo = FakeShadowEvidenceRepository()
    own = _record("tenant-one", "run-one")
    foreign = _record("tenant-two", "run-two")
    missing = generate_for_agent("agent-shared", "run-legacy")
    for record in (own, foreign, missing):
        assert repo.create(record)["status"] == "created"

    own_view = GetShadowRunSafeViewUseCase(
        repository=repo, expected_organization_id="tenant-one"
    )
    visualization = GetShadowRunVisualizationUseCase(
        repository=repo, expected_organization_id="tenant-one"
    )
    listing = ListAgentShadowRunsUseCase(
        repository=repo, expected_organization_id="tenant-one"
    )
    assert own_view.execute(own["shadow_record_id"])["run_id"] == "run-one"
    assert visualization.execute(own["shadow_record_id"])["run"]["run_id"] == "run-one"
    for record in (foreign, missing):
        _expect_not_found(lambda: own_view.execute(record["shadow_record_id"]))
        _expect_not_found(lambda: visualization.execute(record["shadow_record_id"]))

    result = listing.execute("agent-shared", limit=50)
    assert [item["run_id"] for item in result["items"]] == ["run-one"]
    assert "tenant-two" not in repr(result)
    assert "tenant-one" not in repr(result)

    other_list = ListAgentShadowRunsUseCase(
        repository=repo, expected_organization_id="tenant-two"
    ).execute("agent-shared")
    assert [item["run_id"] for item in other_list["items"]] == ["run-two"]

    # Unbound legacy mode remains available, explicitly NOT tenant isolation.
    legacy = ListAgentShadowRunsUseCase(repository=repo).execute("agent-shared")
    assert {item["run_id"] for item in legacy["items"]} == {
        "run-one", "run-two", "run-legacy",
    }


def test_actual_s2s_asgi_routes_enforce_configured_organization() -> None:
    """Exercise production composition/HTTP handler with in-memory sources."""
    repo = FakeShadowEvidenceRepository()
    own = _record("tenant-one", "asgi-one")
    foreign = _record("tenant-two", "asgi-two")
    repo.create(own)
    repo.create(foreign)
    env = _offline_env()
    env["LANGGRAPH_EXPECTED_ORGANIZATION_ID"] = "tenant-one"
    runtime = create_shadow_test_runtime(
        env,
        shadow_repository_override=repo,
        context_repository_override=ShadowTestContextRepository(),
        sql_generator_override=ShadowTestSqlGenerator(),
        sql_repairer_override=ShadowTestSqlRepairer(),
    )
    base = "/v1/internal/shadow-runs/"
    own_status, own_body = _asgi_request(
        runtime.app, "GET", base + own["shadow_record_id"]
    )
    assert own_status == 200
    assert own_body["run_id"] == "asgi-one"

    for path in (
        base + foreign["shadow_record_id"],
        base + foreign["shadow_record_id"] + "/visualization",
    ):
        code, body = _asgi_request(runtime.app, "GET", path)
        assert code == 404
        assert body["error"]["code"] == "SHADOW_RECORD_NOT_FOUND"
        assert "tenant-two" not in repr(body)

    status, result = _asgi_request(
        runtime.app,
        "GET",
        "/v1/internal/agent-runs/agent-shared/shadow-runs",
    )
    assert status == 200
    assert [item["run_id"] for item in result["items"]] == ["asgi-one"]


class ReadCountingRepository(FakeShadowEvidenceRepository):
    def __init__(self) -> None:
        super().__init__()
        self.read_count = 0

    def fetch_by_shadow_record_id(self, shadow_record_id: str):
        self.read_count += 1
        return super().fetch_by_shadow_record_id(shadow_record_id)


def _compare_request(record: dict[str, Any], tenant: str) -> dict[str, Any]:
    return {
        "contract_version": "1",
        "agent_run_id": record["agent_run_id"],
        "shadow_record_id": record["shadow_record_id"],
        "question": SYNTHETIC_QUESTION,
        "official_sql": SYNTHETIC_SQL,
        "principal": {"id": "synthetic-user", "organization_id": tenant},
    }


def test_comparison_rejects_foreign_tenant_before_repository_access() -> None:
    repo = ReadCountingRepository()
    one = _record("tenant-one", "run-compare-a")
    two = _record("tenant-two", "run-compare-b")
    repo.create(one)
    repo.create(two)
    compare = CompareShadowSqlUseCase(
        repository=repo, expected_organization_id="tenant-one"
    )
    denied = compare.execute(_compare_request(two, "tenant-two"))
    assert denied["status"] == "rejected"
    assert denied["errors"][0]["code"] == "SHADOW_COMPARE_TENANT_MISMATCH"
    assert repo.read_count == 0

    # An attacker claiming the bound tenant cannot match a record actually
    # persisted for another tenant. No official SQL/raw evidence is returned.
    mismatch = compare.execute(_compare_request(two, "tenant-one"))
    assert mismatch["status"] == "rejected"
    assert mismatch["errors"][0]["code"] == "SHADOW_COMPARE_TENANT_MISMATCH"
    assert repo.read_count == 1
    assert SYNTHETIC_SQL not in repr(mismatch)

    permitted = compare.execute(_compare_request(one, "tenant-one"))
    assert permitted["status"] == "success"
    assert permitted["metadata"]["comparison"]["tenant_identity_attested"] is True
    assert permitted["metadata"]["comparison"]["financial_parity_proven"] is False
    assert permitted["metadata"]["comparison"]["real_sql_executed"] is False


class ReadCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params):
        self.calls.append((query, deepcopy(params)))

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class ReadConnection:
    def __init__(self, cursor: ReadCursor) -> None:
        self.read_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.read_cursor


class ReadConnect:
    def __init__(self) -> None:
        self.cursor = ReadCursor()

    def __call__(self, *args, **kwargs):
        return ReadConnection(self.cursor)


def test_postgres_limits_rows_before_application_deserialization() -> None:
    connector = ReadConnect()
    repo = PostgresShadowEvidenceRepository(
        dsn="postgresql://fake.invalid/db",
        connect=connector,
        expected_organization_id="tenant-one",
    )
    assert repo.fetch_by_shadow_record_id("shadow-id")["status"] == "not_found"
    assert repo.list_by_agent_run_id("agent-shared")["status"] == "ok"
    assert len(connector.cursor.calls) == 2
    for query, params in connector.cursor.calls:
        assert "principal ->> 'organization_id' = %(organization_id)s" in query
        assert params["organization_id"] == "tenant-one"
        assert "tenant-one" not in query
        assert query.lstrip().startswith("SELECT")
        assert "benchmark" not in query.casefold()
    assert connector.cursor.calls[0][1]["shadow_record_id"] == "shadow-id"
    assert connector.cursor.calls[1][1]["agent_run_id"] == "agent-shared"

    unbound = ReadConnect()
    legacy = PostgresShadowEvidenceRepository(
        dsn="postgresql://fake.invalid/db", connect=unbound
    )
    legacy.fetch_by_shadow_record_id("shadow-id")
    legacy.list_by_agent_run_id("agent-shared")
    assert all("organization_id" not in params for _, params in unbound.cursor.calls)
    assert all(
        "principal ->> 'organization_id'" not in sql
        for sql, _ in unbound.cursor.calls
    )


def test_invalid_scope_refused_before_any_database_connection() -> None:
    for wrong in ("", "tenant two", "tenant-one';drop", "x" * 129):
        try:
            PostgresShadowEvidenceRepository(
                dsn="postgresql://fake.invalid/db",
                connect=ReadConnect(),
                expected_organization_id=wrong,
            )
        except ValueError as error:
            assert str(error) == "Expected organization scope is invalid."
        else:
            raise AssertionError("unsafe tenant scope accepted")
    for use_case in (
        GetShadowRunSafeViewUseCase,
        GetShadowRunVisualizationUseCase,
        ListAgentShadowRunsUseCase,
        CompareShadowSqlUseCase,
    ):
        try:
            use_case(repository=ReadCountingRepository(), expected_organization_id="tenant one")
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe tenant binding accepted")


def main() -> None:
    tests = (
        test_read_and_visualization_never_return_foreign_tenant,
        test_actual_s2s_asgi_routes_enforce_configured_organization,
        test_comparison_rejects_foreign_tenant_before_repository_access,
        test_postgres_limits_rows_before_application_deserialization,
        test_invalid_scope_refused_before_any_database_connection,
    )
    for test in tests:
        test()
        print(f"{test.__name__}: PASS")
    print("Shadow tenant-bound read isolation: PASS")


if __name__ == "__main__":
    main()
