from __future__ import annotations

from typing import Any

from app.bootstrap import (
    create_engine_preflight_from_runtime_config,
    create_postgres_context_graph,
)
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


def test_bootstrap_padrao_compila_sem_abrir_conexao() -> None:
    graph = create_postgres_context_graph(
        FAKE_ENVIRONMENT,
        sql_generator=FakeSqlGenerator(),
        engine_preflight=FakeEnginePreflight(),
        sql_repairer=FakeSqlRepairer(),
    )

    assert callable(getattr(graph, "invoke", None))


def test_entrada_invalida_nao_acessa_postgres() -> None:
    graph = create_postgres_context_graph(
        FAKE_ENVIRONMENT,
        sql_generator=FakeSqlGenerator(),
        engine_preflight=FakeEnginePreflight(),
        sql_repairer=FakeSqlRepairer(),
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
    assert result["current_stage"] == (
        "finalize_invalid_request"
    )
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
    ) -> Any:
        captured["repository"] = repository
        captured["sql_generator"] = sql_generator
        captured["engine_preflight"] = engine_preflight
        captured["sql_repairer"] = sql_repairer
        return expected_graph

    graph = create_postgres_context_graph(
        expected_environment,
        sql_generator=expected_sql_generator,
        engine_preflight=expected_engine_preflight,
        sql_repairer=expected_sql_repairer,
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


def test_bootstrap_exige_preflight_explicito() -> None:
    try:
        create_postgres_context_graph(
            FAKE_ENVIRONMENT,
            sql_generator=FakeSqlGenerator(),
            sql_repairer=FakeSqlRepairer(),
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
        )
    except RuntimeError as error:
        assert str(error) == (
            "sql_repairer deve ser injetado no composition root."
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
            provider_type="generic_engine",
            capability_mode="unavailable",
            dialect="generic_sql",
            timeout_seconds=5,
        )
    )

    assert provider.__class__.__name__ == (
        "CapabilityUnavailableEnginePreflight"
    )


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
            "configuracao invalida interrompe bootstrap",
            test_configuracao_invalida_interrompe_bootstrap,
        ),
        (
            "factory preflight live falha fechada",
            test_factory_preflight_live_falha_fechada_sem_rede,
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
