from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from app.adapters.testing.fake_engine_preflight import FakeEnginePreflight
from app.adapters.testing.fake_shadow_evidence_repository import (
    FakeShadowEvidenceRepository,
)
from app.adapters.testing.fake_sql_repairer import FakeSqlRepairer
from app.application.internal_sql_agent_v1 import (
    ExecuteApprovedSqlShadowUseCase,
    GenerateSqlUseCase,
)
from app.domain.shadow_evidence_types import (
    ShadowEvidenceValidationError,
    build_execute_shadow_record,
    build_generate_shadow_record,
    sanitize_shadow_evidence,
    strict_json_dumps,
)
from app.domain.sql_generation import SqlGenerationProviderError
from app.infrastructure.persistence.postgres_shadow_evidence_repository import (
    PostgresShadowEvidenceRepository,
    FETCH_SHADOW_RUN_SQL,
    FINALIZE_SHADOW_RUN_SQL,
    INSERT_SHADOW_RUN_SQL,
    LIST_SHADOW_RUNS_BY_AGENT_SQL,
    UPDATE_SHADOW_EVIDENCE_SQL,
)
from testar_grafo_base import SuccessContextRepository


ROOT = Path(__file__).resolve().parent

class RaisingShadowEvidenceRepository:
    def create(self, record: dict[str, Any]) -> dict[str, Any]:
        del record
        raise RuntimeError("shadow repository unavailable")

    def update_evidence(self, record: dict[str, Any]) -> dict[str, Any]:
        del record
        raise RuntimeError("shadow repository unavailable")

    def finalize(self, request: dict[str, Any]) -> dict[str, Any]:
        del request
        raise RuntimeError("shadow repository unavailable")

    def fetch_by_shadow_record_id(self, shadow_record_id: str) -> None:
        del shadow_record_id
        return None

    def list_by_agent_run_id(self, agent_run_id: str) -> list[dict[str, Any]]:
        del agent_run_id
        return []


class FakePostgresCursor:
    def __init__(
        self,
        *,
        rowcount: int = 1,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.rowcount = rowcount
        self.rows = list(rows or [])
        self.query: str | None = None
        self.parameters: dict[str, Any] | None = None

    def __enter__(self) -> "FakePostgresCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback

    def execute(self, query: str, parameters: dict[str, Any]) -> None:
        self.query = query
        self.parameters = deepcopy(parameters)

    def fetchone(self) -> dict[str, Any] | None:
        return deepcopy(self.rows[0]) if self.rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return deepcopy(self.rows)


class FakePostgresConnection:
    def __init__(self, cursor: FakePostgresCursor) -> None:
        self._cursor = cursor
        self.committed = False

    def __enter__(self) -> "FakePostgresConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback

    def cursor(self) -> FakePostgresCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True


class FakePostgresConnect:
    def __init__(self, cursor: FakePostgresCursor) -> None:
        self.cursor = cursor
        self.calls = 0
        self.last_kwargs: dict[str, Any] | None = None

    def __call__(self, *_args: Any, **kwargs: Any) -> FakePostgresConnection:
        self.calls += 1
        self.last_kwargs = deepcopy(kwargs)
        return FakePostgresConnection(self.cursor)

class FakeSqlGenerator:
    def __init__(
        self,
        sql: str = "SELECT id FROM schema_test.table_test",
        *,
        exception: Exception | None = None,
    ) -> None:
        self.sql = sql
        self.exception = exception
        self.calls = 0
        self.requests: list[dict[str, Any]] = []

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        self.requests.append(deepcopy(request))
        if self.exception is not None:
            raise self.exception
        return {
            "provider_name": "fake_sql_generator",
            "provider_version": "test-v1",
            "output_text": self.sql,
        }


class Ids:
    def __init__(self) -> None:
        self.index = 0

    def __call__(self) -> str:
        self.index += 1
        return f"lg-run-{self.index}"


def _principal() -> dict[str, str]:
    return {
        "id": "user-1",
        "email": "user@example.invalid",
        "profile": "admin",
        "organization_id": "org-1",
    }


def _request() -> dict[str, Any]:
    return {
        "contract_version": "1",
        "agent_run_id": "agent-run-1",
        "question": "Execute uma generic analysis de teste.",
        "principal": _principal(),
        "correlation_metadata": {"source": "unit-test"},
    }


def _execute_request(sql: str = "SELECT id FROM schema_test.table_test") -> dict[str, Any]:
    return {
        "contract_version": "1",
        "agent_run_id": "agent-run-1",
        "approved_sql": sql,
        "principal": _principal(),
        "correlation_metadata": {"source": "unit-test"},
    }


def _generate_record(
    *,
    agent_run_id: str = "agent-run-1",
    run_id: str = "lg-run-1",
    sql: str = "SELECT id FROM schema_test.table_test",
    question: str = "Execute uma generic analysis de teste.",
    status: str = "success",
) -> dict[str, Any]:
    request = _request()
    request["agent_run_id"] = agent_run_id
    request["question"] = question
    state = {
        "question": question,
        "request_id": agent_run_id,
        "run_id": run_id,
        "current_sql": sql,
        "generated_sql": sql,
        "query_plan": {"intent_name": "generic_test_intent"},
        "security_result": {"status": "approved", "executed": False},
        "contract_result": {"status": "approved", "executed": False},
        "engine_preflight_result": {"status": "approved", "executed": False},
        "repair_history": [],
        "repair_attempts": 0,
        "options": {"shadow_mode": True},
        "final_status": "approved",
    }
    response = {
        "agent_run_id": agent_run_id,
        "run_id": run_id,
        "status": status,
        "sql": sql,
        "gates": {},
        "preflight": {},
        "errors": [],
    }
    return build_generate_shadow_record(
        shadow_record_id=f"shadow-{run_id}",
        agent_run_id=agent_run_id,
        run_id=run_id,
        created_at="2026-08-08T00:00:00+00:00",
        completed_at="2026-08-08T00:00:01+00:00",
        status=status,
        request=request,
        state=state,
        response=response,
        langgraph_version="test-version",
        langgraph_commit="test-commit",
    )


def _generate_use_case(
    *,
    repository: FakeShadowEvidenceRepository | None = None,
    generator: FakeSqlGenerator | None = None,
    preflight: FakeEnginePreflight | None = None,
    repairer: FakeSqlRepairer | None = None,
) -> tuple[
    GenerateSqlUseCase,
    FakeShadowEvidenceRepository,
    FakeSqlGenerator,
    FakeEnginePreflight,
    FakeSqlRepairer,
]:
    repository = repository or FakeShadowEvidenceRepository()
    generator = generator or FakeSqlGenerator()
    preflight = preflight or FakeEnginePreflight()
    repairer = repairer or FakeSqlRepairer()
    return (
        GenerateSqlUseCase(
            context_repository=SuccessContextRepository(),
            sql_generator=generator,
            engine_preflight=preflight,
            sql_repairer=repairer,
            id_generator=Ids(),
            shadow_repository=repository,
            langgraph_version="test-version",
            langgraph_commit="test-commit",
        ),
        repository,
        generator,
        preflight,
        repairer,
    )


def _execute_use_case(
    *,
    repository: FakeShadowEvidenceRepository | None = None,
    preflight: FakeEnginePreflight | None = None,
    repairer: FakeSqlRepairer | None = None,
) -> tuple[
    ExecuteApprovedSqlShadowUseCase,
    FakeShadowEvidenceRepository,
    FakeEnginePreflight,
    FakeSqlRepairer,
]:
    repository = repository or FakeShadowEvidenceRepository()
    preflight = preflight or FakeEnginePreflight()
    repairer = repairer or FakeSqlRepairer()
    return (
        ExecuteApprovedSqlShadowUseCase(
            engine_preflight=preflight,
            sql_repairer=repairer,
            id_generator=Ids(),
            shadow_repository=repository,
            langgraph_version="test-version",
            langgraph_commit="test-commit",
        ),
        repository,
        preflight,
        repairer,
    )


def test_repository_create_shadow_record() -> None:
    repository = FakeShadowEvidenceRepository()
    result = repository.create(_generate_record())

    assert result["status"] == "created"
    assert repository.create_calls == 1
    assert len(repository.records) == 1


def test_repository_preserves_agent_run_id() -> None:
    repository = FakeShadowEvidenceRepository()
    repository.create(_generate_record(agent_run_id="agent-run-preserved"))
    record = next(iter(repository.records.values()))

    assert record["agent_run_id"] == "agent-run-preserved"


def test_repository_preserves_run_id() -> None:
    repository = FakeShadowEvidenceRepository()
    repository.create(_generate_record(run_id="lg-run-preserved"))
    record = next(iter(repository.records.values()))

    assert record["run_id"] == "lg-run-preserved"


def test_repository_allows_many_shadow_records_per_agent_run() -> None:
    repository = FakeShadowEvidenceRepository()
    repository.create(_generate_record(agent_run_id="agent-run-1", run_id="lg-run-1"))
    repository.create(_generate_record(agent_run_id="agent-run-1", run_id="lg-run-2"))

    records = repository.list_by_agent_run_id("agent-run-1")
    assert len(records) == 2
    assert {record["run_id"] for record in records} == {"lg-run-1", "lg-run-2"}


def test_strict_json_is_canonical_and_deterministic() -> None:
    left = strict_json_dumps({"b": 2, "a": [3, 1]})
    right = strict_json_dumps({"a": [3, 1], "b": 2})

    assert left == right
    assert left.startswith('{"a"')


def test_strict_json_rejects_non_finite_numbers() -> None:
    try:
        sanitize_shadow_evidence({"value": float("nan")})
    except ShadowEvidenceValidationError as error:
        assert error.code == "SHADOW_EVIDENCE_NON_FINITE_NUMBER"
    else:
        raise AssertionError("NaN should be rejected")


def test_shadow_evidence_blocks_secret_keys() -> None:
    sanitized = sanitize_shadow_evidence({"safe": "ok", "secret": "hidden"})

    assert sanitized == {"safe": "ok"}


def test_shadow_evidence_fingerprints_are_stable() -> None:
    first = _generate_record()
    second = _generate_record()

    assert first["evidence_fingerprint"] == second["evidence_fingerprint"]
    assert first["fingerprints"] == second["fingerprints"]


def test_repository_fetch_by_shadow_record_id() -> None:
    repository = FakeShadowEvidenceRepository()
    record = _generate_record(run_id="lg-run-fetch")
    repository.create(record)

    fetched = repository.fetch_by_shadow_record_id(record["shadow_record_id"])
    assert fetched is not None
    assert fetched["shadow_record_id"] == record["shadow_record_id"]


def test_repository_list_by_agent_run_id() -> None:
    repository = FakeShadowEvidenceRepository()
    repository.create(_generate_record(agent_run_id="agent-a", run_id="lg-run-1"))
    repository.create(_generate_record(agent_run_id="agent-b", run_id="lg-run-2"))
    repository.create(_generate_record(agent_run_id="agent-a", run_id="lg-run-3"))

    assert [record["agent_run_id"] for record in repository.list_by_agent_run_id("agent-a")] == [
        "agent-a",
        "agent-a",
    ]


def test_repository_finalize_updates_status() -> None:
    repository = FakeShadowEvidenceRepository()
    record = _generate_record(status="success")
    repository.create(record)
    result = repository.finalize(
        {
            "shadow_record_id": record["shadow_record_id"],
            "status": "success",
            "completed_at": record["completed_at"] or "2026-08-08T00:00:01+00:00",
            "evidence_fingerprint": record["evidence_fingerprint"],
        }
    )

    assert result["status"] == "finalized"
    assert repository.records[record["shadow_record_id"]]["status"] == "success"


def test_shadow_record_keeps_rich_payload_without_truncation() -> None:
    large_sql = "SELECT '" + ("x" * 10000) + "' AS payload FROM schema_test.table_test"
    record = _generate_record(sql=large_sql)

    assert record["generated_sql"] == large_sql
    assert record["langgraph_evidence"]["current_sql"] == large_sql


def test_generate_persistence_called_on_generate() -> None:
    use_case, repository, generator, preflight, repairer = _generate_use_case()
    response = use_case.execute(_request())

    assert response["status"] == "success"
    assert repository.create_calls == 1
    assert repository.update_calls == 1
    assert repository.finalize_calls == 1
    assert generator.calls == 1
    assert preflight.calls == 1
    assert repairer.calls == 0


def test_generate_persists_full_sql() -> None:
    sql = "SELECT id, value FROM schema_test.table_test"
    use_case, repository, _generator, _preflight, _repairer = _generate_use_case(
        generator=FakeSqlGenerator(sql)
    )
    response = use_case.execute(_request())
    record = repository.updated_records[-1]

    assert response["sql"] == sql
    assert record["generated_sql"] == sql
    assert record["langgraph_evidence"]["current_sql"] == sql


def test_generate_persists_intent_plan_and_gates() -> None:
    use_case, repository, _generator, _preflight, _repairer = _generate_use_case()
    use_case.execute(_request())
    evidence = repository.updated_records[-1]["langgraph_evidence"]

    assert evidence["intent"] == "generic_test_intent"
    assert evidence["plan"]["intent_name"] == "generic_test_intent"
    assert evidence["gates"]["security"]["status"] == "approved"
    assert evidence["gates"]["contract"]["status"] == "approved"
    assert evidence["preflight_result"]["executed"] is False


def test_generate_persists_repair_history() -> None:
    preflight = FakeEnginePreflight(
        responses=[
            {
                "status": "rejected",
                "provider_name": "fake_engine_preflight",
                "failure_category": "column_not_found",
                "message": "column not found",
                "repairable": True,
                "executed": False,
                "rows_returned": 0,
            },
            {
                "status": "approved",
                "provider_name": "fake_engine_preflight",
                "duration_ms": 1,
                "statement_planned": True,
                "executed": False,
                "rows_returned": 0,
            },
        ]
    )
    repairer = FakeSqlRepairer(responses=["SELECT id FROM schema_test.table_test"])
    use_case, repository, _generator, _preflight, _repairer = _generate_use_case(
        generator=FakeSqlGenerator("SELECT value FROM schema_test.table_test"),
        preflight=preflight,
        repairer=repairer,
    )
    use_case.execute(_request())
    record = repository.updated_records[-1]

    assert record["repaired_sql_proposal"] == "SELECT id FROM schema_test.table_test"
    assert record["langgraph_evidence"]["repair_attempts"] == 1
    assert record["langgraph_evidence"]["repair_history"]


def test_generate_failure_is_persisted() -> None:
    use_case, repository, generator, preflight, repairer = _generate_use_case(
        generator=FakeSqlGenerator(
            exception=SqlGenerationProviderError("provider unavailable")
        )
    )
    response = use_case.execute(_request())
    record = repository.updated_records[-1]

    assert response["status"] == "infrastructure_error"
    assert record["status"] == "infrastructure_error"
    assert record["langgraph_evidence"]["errors"][0]["code"] == "SQL_GENERATION_PROVIDER_FAILED"
    assert generator.calls == 1
    assert preflight.calls == 0
    assert repairer.calls == 0


def test_generate_does_not_execute_real_sql() -> None:
    use_case, repository, _generator, preflight, _repairer = _generate_use_case()
    use_case.execute(_request())
    record = repository.updated_records[-1]

    assert preflight.calls == 1
    assert record["langgraph_evidence"]["preflight_result"]["executed"] is False


def test_execute_persists_approved_sql_original() -> None:
    use_case, repository, preflight, repairer = _execute_use_case()
    response = use_case.execute(_execute_request())
    record = repository.updated_records[-1]

    assert response["status"] == "success"
    assert record["approved_sql_original"] == "SELECT id FROM schema_test.table_test"
    assert record["event_type"] == "execute_approved_shadow"
    assert preflight.calls == 1
    assert repairer.calls == 0


def test_execute_persists_repaired_sql_proposal_separately() -> None:
    use_case, repository, _preflight, _repairer = _execute_repair_case()
    use_case.execute(_execute_request("SELECT value FROM schema_test.table_test"))
    record = repository.updated_records[-1]

    assert record["approved_sql_original"] == "SELECT value FROM schema_test.table_test"
    assert record["repaired_sql_proposal"] == "SELECT id FROM schema_test.table_test"


def test_execute_repaired_sql_requires_reapproval() -> None:
    use_case, repository, _preflight, _repairer = _execute_repair_case()
    response = use_case.execute(_execute_request("SELECT value FROM schema_test.table_test"))
    record = repository.updated_records[-1]

    assert response["requires_reapproval"] is True
    assert record["requires_reapproval"] is True


def test_execute_repaired_sql_is_never_marked_approved() -> None:
    use_case, repository, _preflight, _repairer = _execute_repair_case()
    response = use_case.execute(_execute_request("SELECT value FROM schema_test.table_test"))
    record = repository.updated_records[-1]

    assert response["status"] == "rejected"
    assert record["status"] == "rejected"
    assert record["approved_sql_original"] != record["repaired_sql_proposal"]
    assert record["langgraph_evidence"]["requires_reapproval"] is True


def test_execute_shadow_does_not_execute_real_sql() -> None:
    use_case, repository, preflight, repairer = _execute_use_case()
    use_case.execute(_execute_request())
    record = repository.updated_records[-1]

    assert preflight.calls == 1
    assert repairer.calls == 0
    assert record["langgraph_evidence"]["preflight_result"]["executed"] is False


def test_sanitization_removes_token_key() -> None:
    sanitized = sanitize_shadow_evidence({"token": "hidden", "amount": 10})

    assert sanitized == {"amount": 10}


def test_sanitization_removes_cookie_key() -> None:
    sanitized = sanitize_shadow_evidence({"cookie": "hidden", "month": "2026-08"})

    assert sanitized == {"month": "2026-08"}


def test_sanitization_removes_password_key() -> None:
    sanitized = sanitize_shadow_evidence({"password": "hidden", "region": "BR"})

    assert sanitized == {"region": "BR"}


def test_sanitization_removes_authorization_key() -> None:
    sanitized = sanitize_shadow_evidence({"authorization": "hidden", "cost": 42})

    assert sanitized == {"cost": 42}


def test_sanitization_preserves_legitimate_financial_fields() -> None:
    payload = {
        "gross_revenue": 1000.50,
        "net_margin_pct": 12.5,
        "cost_center": "sales",
        "currency": "BRL",
    }

    assert sanitize_shadow_evidence(payload) == payload


def test_migration_sql_defines_separated_shadow_table() -> None:
    migration = (
        ROOT
        / "scripts"
        / "migrations"
        / "001_create_langgraph_shadow_runs.sql"
    ).read_text(encoding="utf-8")
    lowered = migration.casefold()

    assert "create table if not exists public.langgraph_shadow_runs" in lowered
    assert "agent_run_id" in lowered
    assert "run_id" in lowered
    assert "jsonb" in lowered
    assert "create index if not exists" in lowered
    assert "ai_agent_runs" not in lowered
    assert "ai_agent_metadata" not in lowered


def test_postgres_adapter_uses_bind_parameters_only() -> None:
    queries = [
        INSERT_SHADOW_RUN_SQL,
        UPDATE_SHADOW_EVIDENCE_SQL,
        FINALIZE_SHADOW_RUN_SQL,
        FETCH_SHADOW_RUN_SQL,
        LIST_SHADOW_RUNS_BY_AGENT_SQL,
    ]
    source = (
        ROOT
        / "app"
        / "infrastructure"
        / "persistence"
        / "postgres_shadow_evidence_repository.py"
    ).read_text(encoding="utf-8")

    assert all("%(" in query for query in queries)
    assert ".format(" not in source
    assert " + " not in "\n".join(queries)
    assert "execute(" in source



def test_postgres_create_returns_already_exists_when_rowcount_zero() -> None:
    record = _generate_record()
    cursor = FakePostgresCursor(rowcount=0)
    connect = FakePostgresConnect(cursor)
    repository = PostgresShadowEvidenceRepository(
        dsn="postgresql://shadow-test",
        connect=connect,
    )

    result = repository.create(record)

    assert result["status"] == "already_exists"
    assert result["shadow_record_id"] == record["shadow_record_id"]
    assert cursor.query == INSERT_SHADOW_RUN_SQL
    assert cursor.parameters is not None
    assert cursor.parameters["shadow_record_id"] == record["shadow_record_id"]


def test_postgres_finalize_returns_not_found_when_rowcount_zero() -> None:
    record = _generate_record()
    cursor = FakePostgresCursor(rowcount=0)
    repository = PostgresShadowEvidenceRepository(
        dsn="postgresql://shadow-test",
        connect=FakePostgresConnect(cursor),
    )

    result = repository.finalize(
        {
            "shadow_record_id": record["shadow_record_id"],
            "status": record["status"],
            "completed_at": record["completed_at"] or "2026-08-08T00:00:01+00:00",
            "evidence_fingerprint": record["evidence_fingerprint"],
        }
    )

    assert result["status"] == "not_found"
    assert result["diagnostic"] is not None
    assert result["diagnostic"]["code"] == "SHADOW_RECORD_NOT_FOUND"


def test_postgres_fetch_and_list_normalize_timestamps_for_fingerprint() -> None:
    record = _generate_record()
    row = deepcopy(record)
    row["created_at"] = "2026-08-08 00:00:00+00"
    row["completed_at"] = "2026-08-08 00:00:01+00"
    cursor = FakePostgresCursor(rows=[row])
    repository = PostgresShadowEvidenceRepository(
        dsn="postgresql://shadow-test",
        connect=FakePostgresConnect(cursor),
    )

    fetched = repository.fetch_by_shadow_record_id(record["shadow_record_id"])
    listed = repository.list_by_agent_run_id(record["agent_run_id"])

    assert fetched is not None
    assert fetched["evidence_fingerprint"] == record["evidence_fingerprint"]
    assert fetched["created_at"] == record["created_at"]
    assert fetched["completed_at"] == record["completed_at"]
    assert listed[0]["evidence_fingerprint"] == record["evidence_fingerprint"]


def test_generate_shadow_repository_failure_does_not_change_response() -> None:
    baseline_use_case, _repository, _generator, _preflight, _repairer = _generate_use_case()
    failing_use_case, _failing_repository, _generator2, _preflight2, _repairer2 = _generate_use_case(
        repository=RaisingShadowEvidenceRepository()  # type: ignore[arg-type]
    )

    baseline = baseline_use_case.execute(_request())
    observed = failing_use_case.execute(_request())

    assert observed["status"] == "success"
    assert observed["sql"] == baseline["sql"]
    assert observed["message"] == baseline["message"]
    assert observed["status"] != "infrastructure_error"


def test_execute_shadow_repository_failure_does_not_change_response() -> None:
    baseline_use_case, _repository, _preflight, _repairer = _execute_use_case()
    failing_use_case, _failing_repository, _preflight2, _repairer2 = _execute_use_case(
        repository=RaisingShadowEvidenceRepository()  # type: ignore[arg-type]
    )

    baseline = baseline_use_case.execute(_execute_request())
    observed = failing_use_case.execute(_execute_request())

    assert observed["status"] == "success"
    assert observed["approved_sql_original"] == baseline["approved_sql_original"]
    assert observed["requires_reapproval"] == baseline["requires_reapproval"]
    assert observed["status"] != "infrastructure_error"

def _execute_repair_case() -> tuple[
    ExecuteApprovedSqlShadowUseCase,
    FakeShadowEvidenceRepository,
    FakeEnginePreflight,
    FakeSqlRepairer,
]:
    preflight = FakeEnginePreflight(
        responses=[
            {
                "status": "rejected",
                "provider_name": "fake_engine_preflight",
                "failure_category": "column_not_found",
                "message": "column not found",
                "repairable": True,
                "executed": False,
                "rows_returned": 0,
            },
        ]
    )
    repairer = FakeSqlRepairer(responses=["SELECT id FROM schema_test.table_test"])
    return _execute_use_case(preflight=preflight, repairer=repairer)


def main() -> None:
    tests = [
        test_repository_create_shadow_record,
        test_repository_preserves_agent_run_id,
        test_repository_preserves_run_id,
        test_repository_allows_many_shadow_records_per_agent_run,
        test_strict_json_is_canonical_and_deterministic,
        test_strict_json_rejects_non_finite_numbers,
        test_shadow_evidence_blocks_secret_keys,
        test_shadow_evidence_fingerprints_are_stable,
        test_repository_fetch_by_shadow_record_id,
        test_repository_list_by_agent_run_id,
        test_repository_finalize_updates_status,
        test_shadow_record_keeps_rich_payload_without_truncation,
        test_generate_persistence_called_on_generate,
        test_generate_persists_full_sql,
        test_generate_persists_intent_plan_and_gates,
        test_generate_persists_repair_history,
        test_generate_failure_is_persisted,
        test_generate_does_not_execute_real_sql,
        test_execute_persists_approved_sql_original,
        test_execute_persists_repaired_sql_proposal_separately,
        test_execute_repaired_sql_requires_reapproval,
        test_execute_repaired_sql_is_never_marked_approved,
        test_execute_shadow_does_not_execute_real_sql,
        test_sanitization_removes_token_key,
        test_sanitization_removes_cookie_key,
        test_sanitization_removes_password_key,
        test_sanitization_removes_authorization_key,
        test_sanitization_preserves_legitimate_financial_fields,
        test_migration_sql_defines_separated_shadow_table,
        test_postgres_adapter_uses_bind_parameters_only,
        test_postgres_create_returns_already_exists_when_rowcount_zero,
        test_postgres_finalize_returns_not_found_when_rowcount_zero,
        test_postgres_fetch_and_list_normalize_timestamps_for_fingerprint,
        test_generate_shadow_repository_failure_does_not_change_response,
        test_execute_shadow_repository_failure_does_not_change_response,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()
