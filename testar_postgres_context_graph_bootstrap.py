from __future__ import annotations

from typing import Any

from app.bootstrap import (
    create_postgres_context_graph,
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


def test_bootstrap_padrao_compila_sem_abrir_conexao() -> None:
    graph = create_postgres_context_graph(
        FAKE_ENVIRONMENT
    )

    assert callable(getattr(graph, "invoke", None))


def test_entrada_invalida_nao_acessa_postgres() -> None:
    graph = create_postgres_context_graph(
        FAKE_ENVIRONMENT
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

    class FakeRepository:
        def load_active_context(
            self,
            *,
            user_profile: str,
        ) -> dict[str, Any]:
            del user_profile
            raise AssertionError(
                "O repositório não deve ser executado "
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
    ) -> Any:
        captured["repository"] = repository
        return expected_graph

    graph = create_postgres_context_graph(
        expected_environment,
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


def test_configuracao_invalida_interrompe_bootstrap() -> None:
    try:
        create_postgres_context_graph({})
    except RuntimeConfigError as error:
        assert str(error) == (
            "A variável POSTGRES_DSN não está definida."
        )
    else:
        raise AssertionError(
            "Era esperado RuntimeConfigError."
        )


def main() -> None:
    tests = [
        (
            "bootstrap padrão compila sem abrir conexão",
            test_bootstrap_padrao_compila_sem_abrir_conexao,
        ),
        (
            "entrada inválida não acessa PostgreSQL",
            test_entrada_invalida_nao_acessa_postgres,
        ),
        (
            "factories recebem dependências corretas",
            test_factories_recebem_dependencias_corretas,
        ),
        (
            "configuração inválida interrompe bootstrap",
            test_configuracao_invalida_interrompe_bootstrap,
        ),
    ]

    for index, (name, test_function) in enumerate(
        tests,
        start=1,
    ):
        test_function()
        print(f"TESTE {index} — {name}: OK")


if __name__ == "__main__":
    main()
