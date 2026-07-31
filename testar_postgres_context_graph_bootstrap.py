from __future__ import annotations

from typing import Any

from app.bootstrap import (
    create_http_entry_adapter,
    create_application_service,
    create_engine_preflight_from_runtime_config,
    create_postgres_context_application_service,
    create_postgres_context_graph,
)
from app.http.http_request import default_http_request_limits
from app.http.http_response import default_http_response_limits
from app.config.engine_preflight_runtime import (
    EnginePreflightRuntimeConfig,
)
from app.config.postgres_context import (
    PostgresContextRuntimeConfig,
    RuntimeConfigError,
)
from app.ports.context_repository import ContextRepository


FAKE_ENVIRONMENT = {
    "POSTGRES_DSN": (
        "postgresql://example.invalid/database"
    ),
    "SEMANTIC_AGENT_VERSION": "semantic-test-v1",
    "POSTGRES_CONNECT_TIMEOUT_SECONDS": "3",
}


class FakeSqlGenerator:
    def generate(self, request):
        del request
        return {
            "provider_name": "fake_sql_generator",
            "output_text": "SELECT 1",
        }


class FakeEnginePreflight:
    def preflight(self, request):
        del request
        return {
            "status": "approved",
            "provider_name": "fake_engine_preflight",
            "executed": False,
            "rows_returned": 0,
        }


class FakeSqlRepairer:
    def repair(self, request):
        del request
        return {
            "provider_name": "fake_sql_repairer",
            "output_text": "SELECT 1",
        }


class FakeSqlExecutor:
    def execute(self, request):
        del request
        return {
            "status": "success",
            "provider_name": "fake_sql_executor",
            "columns": [],
            "rows": [],
            "row_count": 0,
            "executed": True,
        }


class FakeRunRepository:
    def save(self, request):
        return {
            "status": "persisted",
            "record_id": "record-test",
            "persisted_fingerprint": request["run_record_fingerprint"],
            "idempotency_key": request["idempotency_key"],
            "failure_category": "none",
            "diagnostic": None,
            "duration_ms": 1,
        }


class FakeAuditSink:
    def write(self, event):
        return {
            "status": "written",
            "event_id": event["event_id"],
            "event_fingerprint": event["fingerprint"],
            "idempotency_key": event["idempotency_key"],
            "failure_category": "none",
            "diagnostic": None,
            "duration_ms": 1,
        }


class FakeObservabilitySink:
    def emit(self, event):
        return {
            "status": "emitted",
            "event_fingerprint": event["fingerprint"],
            "diagnostic": None,
            "duration_ms": 1,
        }


def test_bootstrap_padrao_compila_sem_abrir_conexao() -> None:
    graph = create_postgres_context_graph(
        FAKE_ENVIRONMENT,
        sql_generator=FakeSqlGenerator(),
        engine_preflight=FakeEnginePreflight(),
        sql_repairer=FakeSqlRepairer(),
        sql_executor=FakeSqlExecutor(),
        run_repository=FakeRunRepository(),
        audit_sink=FakeAuditSink(),
        observability_sink=FakeObservabilitySink(),
    )

    assert callable(getattr(graph, "invoke", None))


def test_entrada_invalida_nao_acessa_postgres() -> None:
    graph = create_postgres_context_graph(
        FAKE_ENVIRONMENT,
        sql_generator=FakeSqlGenerator(),
        engine_preflight=FakeEnginePreflight(),
        sql_repairer=FakeSqlRepairer(),
        sql_executor=FakeSqlExecutor(),
        run_repository=FakeRunRepository(),
        audit_sink=FakeAuditSink(),
        observability_sink=FakeObservabilitySink(),
    )

    result = graph.invoke(
        {
            "question": "",
            "user": {
                "id": "generic-user",
                "email": "generic@example.invalid",
                "profile": "generic-profile",
            },
            "options": {
                "use_cache": False,
                "max_repair_attempts": 2,
                "shadow_mode": False,
            },
        }
    )

    assert result["final_status"] == "invalid_request"
    assert result["failure_stage"] == "receive_question"
    assert result["current_stage"] == "build_application_response"
    assert result["run_record"]["previous_stage"] == (
        "finalize_invalid_request"
    )
    assert result["application_response"]["status"] == "rejected"
    assert result["application_response"]["data"] is None
    assert result["errors"][0]["code"] == "EMPTY_QUESTION"


def test_factories_recebem_dependencias_corretas() -> None:
    captured: dict[str, Any] = {}
    expected_environment = {
        "POSTGRES_DSN": "ignored-by-fake-loader",
    }
    expected_config = PostgresContextRuntimeConfig(
        dsn="postgresql://example.invalid/database",
        semantic_agent_version="semantic-test-v2",
        connect_timeout_seconds=5,
    )
    expected_graph = object()
    expected_sql_generator = FakeSqlGenerator()
    expected_engine_preflight = FakeEnginePreflight()
    expected_sql_repairer = FakeSqlRepairer()
    expected_sql_executor = FakeSqlExecutor()
    expected_run_repository = FakeRunRepository()
    expected_audit_sink = FakeAuditSink()
    expected_observability_sink = FakeObservabilitySink()

    class FakeRepository:
        def load_active_context(
            self,
            *,
            user_profile: str,
        ) -> dict[str, Any]:
            del user_profile
            raise AssertionError(
                "O repositorio nao deve ser executado "
                "durante o bootstrap."
            )

    expected_repository: ContextRepository = (
        FakeRepository()
    )

    def fake_config_loader(
        environ: Any,
    ) -> PostgresContextRuntimeConfig:
        captured["environment"] = environ
        return expected_config

    def fake_repository_factory(
        config: PostgresContextRuntimeConfig,
    ) -> ContextRepository:
        captured["config"] = config
        return expected_repository

    def fake_graph_factory(
        repository: ContextRepository,
        sql_generator,
        engine_preflight,
        sql_repairer,
        sql_executor,
        run_repository,
        audit_sink,
        observability_sink,
    ) -> Any:
        captured["repository"] = repository
        captured["sql_generator"] = sql_generator
        captured["engine_preflight"] = engine_preflight
        captured["sql_repairer"] = sql_repairer
        captured["sql_executor"] = sql_executor
        captured["run_repository"] = run_repository
        captured["audit_sink"] = audit_sink
        captured["observability_sink"] = observability_sink
        return expected_graph

    graph = create_postgres_context_graph(
        expected_environment,
        sql_generator=expected_sql_generator,
        engine_preflight=expected_engine_preflight,
        sql_repairer=expected_sql_repairer,
        sql_executor=expected_sql_executor,
        run_repository=expected_run_repository,
        audit_sink=expected_audit_sink,
        observability_sink=expected_observability_sink,
        config_loader=fake_config_loader,
        repository_factory=fake_repository_factory,
        graph_factory=fake_graph_factory,
    )

    assert graph is expected_graph
    assert captured["environment"] is (
        expected_environment
    )
    assert captured["config"] is expected_config
    assert captured["repository"] is (
        expected_repository
    )
    assert captured["sql_generator"] is expected_sql_generator
    assert captured["engine_preflight"] is expected_engine_preflight
    assert captured["sql_repairer"] is expected_sql_repairer
    assert captured["sql_executor"] is expected_sql_executor
    assert captured["run_repository"] is expected_run_repository
    assert captured["audit_sink"] is expected_audit_sink
    assert captured["observability_sink"] is expected_observability_sink


def test_bootstrap_exige_preflight_explicito() -> None:
    try:
        create_postgres_context_graph(
            FAKE_ENVIRONMENT,
            sql_generator=FakeSqlGenerator(),
            sql_repairer=FakeSqlRepairer(),
            sql_executor=FakeSqlExecutor(),
            run_repository=FakeRunRepository(),
            audit_sink=FakeAuditSink(),
            observability_sink=FakeObservabilitySink(),
        )
    except RuntimeError as error:
        assert str(error) == (
            "engine_preflight deve ser injetado no composition root."
        )
    else:
        raise AssertionError("Era esperado RuntimeError.")


def test_bootstrap_exige_repairer_explicito() -> None:
    try:
        create_postgres_context_graph(
            FAKE_ENVIRONMENT,
            sql_generator=FakeSqlGenerator(),
            engine_preflight=FakeEnginePreflight(),
            sql_executor=FakeSqlExecutor(),
            run_repository=FakeRunRepository(),
            audit_sink=FakeAuditSink(),
            observability_sink=FakeObservabilitySink(),
        )
    except RuntimeError as error:
        assert str(error) == (
            "sql_repairer deve ser injetado no composition root."
        )
    else:
        raise AssertionError("Era esperado RuntimeError.")


def test_bootstrap_exige_executor_explicito() -> None:
    try:
        create_postgres_context_graph(
            FAKE_ENVIRONMENT,
            sql_generator=FakeSqlGenerator(),
            engine_preflight=FakeEnginePreflight(),
            sql_repairer=FakeSqlRepairer(),
            run_repository=FakeRunRepository(),
            audit_sink=FakeAuditSink(),
            observability_sink=FakeObservabilitySink(),
        )
    except RuntimeError as error:
        assert str(error) == (
            "sql_executor deve ser injetado no composition root."
        )
    else:
        raise AssertionError("Era esperado RuntimeError.")


def test_bootstrap_exige_run_repository_explicito() -> None:
    try:
        create_postgres_context_graph(
            FAKE_ENVIRONMENT,
            sql_generator=FakeSqlGenerator(),
            engine_preflight=FakeEnginePreflight(),
            sql_repairer=FakeSqlRepairer(),
            sql_executor=FakeSqlExecutor(),
            audit_sink=FakeAuditSink(),
            observability_sink=FakeObservabilitySink(),
        )
    except RuntimeError as error:
        assert str(error) == (
            "run_repository deve ser injetado no composition root."
        )
    else:
        raise AssertionError("Era esperado RuntimeError.")


def test_bootstrap_exige_audit_sink_explicito() -> None:
    try:
        create_postgres_context_graph(
            FAKE_ENVIRONMENT,
            sql_generator=FakeSqlGenerator(),
            engine_preflight=FakeEnginePreflight(),
            sql_repairer=FakeSqlRepairer(),
            sql_executor=FakeSqlExecutor(),
            run_repository=FakeRunRepository(),
            observability_sink=FakeObservabilitySink(),
        )
    except RuntimeError as error:
        assert str(error) == (
            "audit_sink deve ser injetado no composition root."
        )
    else:
        raise AssertionError("Era esperado RuntimeError.")


def test_bootstrap_exige_observability_sink_explicito() -> None:
    try:
        create_postgres_context_graph(
            FAKE_ENVIRONMENT,
            sql_generator=FakeSqlGenerator(),
            engine_preflight=FakeEnginePreflight(),
            sql_repairer=FakeSqlRepairer(),
            sql_executor=FakeSqlExecutor(),
            run_repository=FakeRunRepository(),
            audit_sink=FakeAuditSink(),
        )
    except RuntimeError as error:
        assert str(error) == (
            "observability_sink deve ser injetado no composition root."
        )
    else:
        raise AssertionError("Era esperado RuntimeError.")


def test_configuracao_invalida_interrompe_bootstrap() -> None:
    try:
        create_postgres_context_graph({})
    except RuntimeConfigError as error:
        assert "POSTGRES_DSN" in str(error)
        assert "definida" in str(error)
    else:
        raise AssertionError(
            "Era esperado RuntimeConfigError."
        )


def test_factory_preflight_live_falha_fechada_sem_rede() -> None:
    provider = create_engine_preflight_from_runtime_config(
        EnginePreflightRuntimeConfig(
            provider_type="capability_diagnostic",
            capability_mode="unavailable",
            dialect="generic_sql",
            timeout_seconds=5,
        )
    )

    assert provider.__class__.__name__ == (
        "CapabilityUnavailableEnginePreflight"
    )


def test_application_service_exige_runtime_ou_graph() -> None:
    try:
        create_application_service(id_generator=lambda: "id-1")
    except RuntimeError as error:
        assert str(error) == (
            "runtime ou graph deve ser injetado explicitamente."
        )
    else:
        raise AssertionError("Era esperado RuntimeError.")


def test_application_service_exige_id_generator() -> None:
    class FakeRuntime:
        def invoke(self, initial_state):
            return initial_state

    try:
        create_application_service(runtime=FakeRuntime())
    except RuntimeError as error:
        assert str(error) == (
            "id_generator deve ser injetado explicitamente."
        )
    else:
        raise AssertionError("Era esperado RuntimeError.")


def test_application_service_criado_sem_singleton_ou_rede() -> None:
    class FakeRuntime:
        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, initial_state):
            self.calls += 1
            return {
                "application_response": {
                    "contract_version": "v1.0.0-application-response",
                    "response_id": "invalid-for-this-test",
                    "request_id": initial_state["request_id"],
                    "run_id": initial_state["run_id"],
                    "status": "success",
                    "response_fingerprint": "invalid-for-this-test",
                    "finalization": {},
                }
            }

    runtime = FakeRuntime()
    first = create_application_service(
        runtime=runtime,
        id_generator=lambda: "id-1",
    )
    second = create_application_service(
        runtime=runtime,
        id_generator=lambda: "id-2",
    )
    assert first is not second
    assert runtime.calls == 0


def test_postgres_context_application_service_factory() -> None:
    captured: dict[str, Any] = {}

    class FakeGraph:
        def invoke(self, initial_state):
            return initial_state

    def fake_graph_factory(
        repository,
        sql_generator,
        engine_preflight,
        sql_repairer,
        sql_executor,
        run_repository,
        audit_sink,
        observability_sink,
    ):
        captured["repository"] = repository
        captured["sql_generator"] = sql_generator
        captured["engine_preflight"] = engine_preflight
        captured["sql_repairer"] = sql_repairer
        captured["sql_executor"] = sql_executor
        captured["run_repository"] = run_repository
        captured["audit_sink"] = audit_sink
        captured["observability_sink"] = observability_sink
        return FakeGraph()

    service = create_postgres_context_application_service(
        FAKE_ENVIRONMENT,
        id_generator=lambda: "id-1",
        sql_generator=FakeSqlGenerator(),
        engine_preflight=FakeEnginePreflight(),
        sql_repairer=FakeSqlRepairer(),
        sql_executor=FakeSqlExecutor(),
        run_repository=FakeRunRepository(),
        audit_sink=FakeAuditSink(),
        observability_sink=FakeObservabilitySink(),
        graph_factory=fake_graph_factory,
    )

    assert service.__class__.__name__ == "SqlAgentApplicationService"
    assert captured["sql_generator"].__class__.__name__ == "FakeSqlGenerator"


def test_http_entry_adapter_exige_application_service() -> None:
    try:
        create_http_entry_adapter(
            request_limits=default_http_request_limits(),
            response_limits=default_http_response_limits(),
        )
    except RuntimeError as error:
        assert str(error) == (
            "application_service deve ser injetado explicitamente."
        )
    else:
        raise AssertionError("Era esperado RuntimeError.")


def test_http_entry_adapter_exige_limits() -> None:
    class FakeService:
        def execute(self, request):
            return request

    try:
        create_http_entry_adapter(application_service=FakeService())
    except RuntimeError as error:
        assert str(error) == "request_limits deve ser injetado."
    else:
        raise AssertionError("Era esperado RuntimeError.")

    try:
        create_http_entry_adapter(
            application_service=FakeService(),
            request_limits=default_http_request_limits(),
        )
    except RuntimeError as error:
        assert str(error) == "response_limits deve ser injetado."
    else:
        raise AssertionError("Era esperado RuntimeError.")


def test_http_entry_adapter_criado_sem_servidor_ou_rede() -> None:
    class FakeService:
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, request):
            self.calls += 1
            return request

    service = FakeService()
    handler = create_http_entry_adapter(
        application_service=service,
        request_limits=default_http_request_limits(),
        response_limits=default_http_response_limits(),
    )
    assert handler.__class__.__name__ == "SqlAgentHttpHandler"
    assert service.calls == 0


def main() -> None:
    tests = [
        (
            "bootstrap padrao compila sem abrir conexao",
            test_bootstrap_padrao_compila_sem_abrir_conexao,
        ),
        (
            "entrada invalida nao acessa PostgreSQL",
            test_entrada_invalida_nao_acessa_postgres,
        ),
        (
            "factories recebem dependencias corretas",
            test_factories_recebem_dependencias_corretas,
        ),
        (
            "bootstrap exige preflight explicito",
            test_bootstrap_exige_preflight_explicito,
        ),
        (
            "bootstrap exige repairer explicito",
            test_bootstrap_exige_repairer_explicito,
        ),
        (
            "bootstrap exige executor explicito",
            test_bootstrap_exige_executor_explicito,
        ),
        (
            "bootstrap exige run repository explicito",
            test_bootstrap_exige_run_repository_explicito,
        ),
        (
            "bootstrap exige audit sink explicito",
            test_bootstrap_exige_audit_sink_explicito,
        ),
        (
            "bootstrap exige observability sink explicito",
            test_bootstrap_exige_observability_sink_explicito,
        ),
        (
            "configuracao invalida interrompe bootstrap",
            test_configuracao_invalida_interrompe_bootstrap,
        ),
        (
            "factory preflight live falha fechada",
            test_factory_preflight_live_falha_fechada_sem_rede,
        ),
        (
            "application service exige runtime ou graph",
            test_application_service_exige_runtime_ou_graph,
        ),
        (
            "application service exige id generator",
            test_application_service_exige_id_generator,
        ),
        (
            "application service criado sem singleton ou rede",
            test_application_service_criado_sem_singleton_ou_rede,
        ),
        (
            "postgres context application service factory",
            test_postgres_context_application_service_factory,
        ),
        (
            "http entry adapter exige application service",
            test_http_entry_adapter_exige_application_service,
        ),
        (
            "http entry adapter exige limits",
            test_http_entry_adapter_exige_limits,
        ),
        (
            "http entry adapter criado sem servidor ou rede",
            test_http_entry_adapter_criado_sem_servidor_ou_rede,
        ),
    ]

    for index, (name, test_function) in enumerate(
        tests,
        start=1,
    ):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()
