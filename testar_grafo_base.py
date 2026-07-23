from pprint import pprint

from app.domain.context import ContextSnapshot
from app.graph.builder import create_graph
from app.graph.state import GraphState
from app.ports.context_repository import (
    ContextRepositoryError,
)


class SuccessContextRepository:
    """
    Repositório falso usado somente no teste.

    Os dados abaixo não são contexto de produção.
    """

    def load_active_context(
        self,
        *,
        user_profile: str,
    ) -> ContextSnapshot:
        return {
            "version": "context-test-v1",
            "versions": {
                "catalog": "catalog-test-v1",
                "rules": "rules-test-v1",
                "aliases": "aliases-test-v1",
                "dre_mapping": "dre-test-v1",
                "sql_patterns": "patterns-test-v1",
            },
            "allowed_schemas": [
                "schema_autorizado_teste",
            ],
            "tables": [
                {
                    "schema": (
                        "schema_autorizado_teste"
                    ),
                    "name": "tabela_financeira_teste",
                    "description": (
                        "Tabela usada somente no teste."
                    ),
                    "columns": [
                        {
                            "name": "valor_teste",
                            "data_type": "DECIMAL",
                            "nullable": True,
                        }
                    ],
                }
            ],
            "rules": [],
            "aliases": {},
            "dre_mappings": [],
            "sql_patterns": [],
        }


class FailureContextRepository:
    """
    Simula falha ao acessar a fonte de contexto.
    """

    def load_active_context(
        self,
        *,
        user_profile: str,
    ) -> ContextSnapshot:
        raise ContextRepositoryError(
            "Falha simulada ao carregar o contexto."
        )


class ShouldNotBeCalledRepository:
    """
    Confirma que entrada inválida não carrega contexto.
    """

    def load_active_context(
        self,
        *,
        user_profile: str,
    ) -> ContextSnapshot:
        raise AssertionError(
            "O repositório não deveria ser chamado."
        )


def run_test(
    title: str,
    repository,
    initial_state: GraphState,
) -> None:
    print("=" * 70)
    print(title)
    print("=" * 70)

    graph = create_graph(repository)

    result = graph.invoke(
        initial_state,
        config={
            "recursion_limit": 10,
        },
    )

    pprint(
        result,
        sort_dicts=False,
    )

    print()


def main() -> None:
    run_test(
        "TESTE 1 — CONTEXTO CARREGADO",
        SuccessContextRepository(),
        {
            "question": (
                "Quais as contas que tiveram maiores "
                "estouros de orçamento no mês?"
            ),
            "user": {
                "id": "usuario-1",
                "email": "admin@local.com",
                "profile": "admin",
            },
            "options": {
                "use_cache": False,
                "max_repair_attempts": 2,
                "shadow_mode": False,
            },
        },
    )

    run_test(
        "TESTE 2 — FALHA AO CARREGAR CONTEXTO",
        FailureContextRepository(),
        {
            "question": (
                "Quais as contas que tiveram maiores "
                "estouros de orçamento no mês?"
            ),
            "user": {
                "id": "usuario-1",
                "email": "admin@local.com",
                "profile": "admin",
            },
            "options": {
                "max_repair_attempts": 2,
            },
        },
    )

    run_test(
        "TESTE 3 — ENTRADA INVÁLIDA NÃO ACESSA CONTEXTO",
        ShouldNotBeCalledRepository(),
        {
            "question": "   ",
            "options": {
                "max_repair_attempts": 2,
            },
        },
    )


if __name__ == "__main__":
    main()