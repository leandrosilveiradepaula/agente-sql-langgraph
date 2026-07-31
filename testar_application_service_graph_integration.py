from __future__ import annotations

from app.adapters.testing.fake_audit_sink import FakeAuditSink
from app.adapters.testing.fake_engine_preflight import FakeEnginePreflight
from app.adapters.testing.fake_observability_sink import FakeObservabilitySink
from app.adapters.testing.fake_run_repository import FakeRunRepository
from app.adapters.testing.fake_sql_executor import FakeSqlExecutor
from app.adapters.testing.fake_sql_repairer import FakeSqlRepairer
from app.application.sql_agent_service import SqlAgentApplicationService
from app.bootstrap import CompiledGraphRuntime
from app.graph.builder import create_graph
from testar_grafo_base import SuccessContextRepository


class FakeSqlGenerator:
    def __init__(self, sql: str = "SELECT id FROM schema_test.table_test") -> None:
        self.sql = sql
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        assert "context" not in request
        return {
            "provider_name": "fake_sql_generator",
            "provider_version": "test-v1",
            "output_text": self.sql,
        }


class Ids:
    def __init__(self) -> None:
        self.values = ["request-generated", "run-generated"]
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return self.values.pop(0)


def _service(
    *,
    sql_generator=None,
    preflight=None,
    repairer=None,
    executor=None,
):
    sql_generator = sql_generator or FakeSqlGenerator()
    preflight = preflight or FakeEnginePreflight()
    repairer = repairer or FakeSqlRepairer()
    executor = executor or FakeSqlExecutor()
    run_repository = FakeRunRepository()
    audit_sink = FakeAuditSink()
    observability_sink = FakeObservabilitySink()
    graph = create_graph(
        SuccessContextRepository(),
        sql_generator,
        preflight,
        repairer,
        executor,
        run_repository,
        audit_sink,
        observability_sink,
    )
    runtime = CompiledGraphRuntime(graph)
    service = SqlAgentApplicationService(
        runtime=runtime,
        id_generator=Ids(),
    )
    return (
        service,
        sql_generator,
        preflight,
        repairer,
        executor,
        run_repository,
        audit_sink,
        observability_sink,
    )


def test_request_valida_percorre_grafo_e_retorna_response() -> None:
    service, generator, preflight, repairer, executor, repo, audit, obs = (
        _service()
    )
    response = service.execute(
        {
            "question": "Execute uma generic analysis de teste.",
            "request_id": "request-1",
            "run_id": "run-1",
            "user": {"profile": "admin"},
        }
    )
    assert response["status"] == "success"
    assert response["request_id"] == "request-1"
    assert response["run_id"] == "run-1"
    assert "final_status" not in response
    assert generator.calls == 1
    assert preflight.calls == 1
    assert repairer.calls == 0
    assert executor.calls == 1
    assert repo.calls == 1
    assert audit.calls == 1
    assert obs.calls == 1


def test_request_rejeitada_nao_expoe_graphstate() -> None:
    service, *_ = _service()
    response = service.execute(
        {
            "question": "Pergunta sem sinal catalogado.",
            "request_id": "request-2",
            "run_id": "run-2",
            "user": {"profile": "admin"},
        }
    )
    assert response["status"] == "rejected"
    assert response["data"] is None
    assert "query_plan" not in repr(response)
    assert "GraphState" not in repr(response)


def test_capability_unavailable_retorna_infrastructure_error() -> None:
    service, _, preflight, _, executor, *_ = _service(
        preflight=FakeEnginePreflight(
            status="rejected",
            failure_category="capability_unavailable",
            message="capability unavailable",
            repairable=False,
        )
    )
    response = service.execute(
        {
            "question": "Execute uma generic analysis de teste.",
            "request_id": "request-3",
            "run_id": "run-3",
            "user": {"profile": "admin"},
        }
    )
    assert response["status"] == "infrastructure_error"
    assert response["data"] is None
    assert preflight.calls == 1
    assert executor.calls == 0


def test_repair_path_continua_funcional() -> None:
    preflight = FakeEnginePreflight(
        responses=[
            {
                "status": "rejected",
                "provider_name": "fake_engine_preflight",
                "provider_version": "test-v1",
                "duration_ms": 3,
                "statement_planned": False,
                "executed": False,
                "rows_returned": 0,
                "failure_category": "syntax_error",
                "message": "syntax issue",
                "repairable": True,
            },
            {
                "status": "approved",
                "provider_name": "fake_engine_preflight",
                "provider_version": "test-v1",
                "duration_ms": 3,
                "statement_planned": True,
                "executed": False,
                "rows_returned": 0,
            },
        ]
    )
    repairer = FakeSqlRepairer(
        responses=["SELECT id FROM schema_test.table_test"]
    )
    service, generator, preflight, repairer, executor, *_ = _service(
        sql_generator=FakeSqlGenerator(
            "SELECT value FROM schema_test.table_test"
        ),
        preflight=preflight,
        repairer=repairer,
    )
    response = service.execute(
        {
            "question": "Execute uma generic analysis de teste.",
            "request_id": "request-4",
            "run_id": "run-4",
            "user": {"profile": "admin"},
            "options": {"max_repair_attempts": 1},
        }
    )
    assert response["status"] == "success"
    assert generator.calls == 1
    assert preflight.calls == 2
    assert repairer.calls == 1
    assert executor.calls == 1


def test_ids_gerados_e_sem_dependencia_live() -> None:
    service, _, preflight, _, executor, repo, audit, obs = _service()
    response = service.execute(
        {
            "question": "Execute uma generic analysis de teste.",
            "user": {"profile": "admin"},
        }
    )
    assert response["request_id"] == "request-generated"
    assert response["run_id"] == "run-generated"
    assert preflight.calls == 1
    assert "current_sql" not in preflight.last_request
    assert executor.calls == 1
    assert repo.calls == 1
    assert audit.calls == 1
    assert obs.calls == 1


def main() -> None:
    tests = [
        test_request_valida_percorre_grafo_e_retorna_response,
        test_request_rejeitada_nao_expoe_graphstate,
        test_capability_unavailable_retorna_infrastructure_error,
        test_repair_path_continua_funcional,
        test_ids_gerados_e_sem_dependencia_live,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()
