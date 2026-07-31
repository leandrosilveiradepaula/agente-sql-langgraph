from pprint import pprint

from app.graph.nodes.receive_question import receive_question
from app.graph.state import GraphState


def run_test(
    title: str,
    initial_state: GraphState,
    assertion=None,
) -> None:
    print("=" * 70)
    print(title)
    print("=" * 70)

    result = receive_question(initial_state)

    pprint(
        result,
        sort_dicts=False,
    )

    if assertion is not None:
        assertion(result)
        print("ASSERTIONS: OK")

    print()


def _assert_resultados_anteriores_limpos(result: GraphState) -> None:
    assert result["sql_execution_result"] is None
    assert result["normalized_result"] is None
    assert result["serialized_result"] is None


def main() -> None:
    run_test(
        "TESTE 1 — PERGUNTA VÁLIDA",
        {
            "question": (
                "  Quais   as contas que tiveram maiores "
                "estouros de orçamento no mês?  "
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
        "TESTE 2 — PERGUNTA VAZIA",
        {
            "question": "   ",
            "options": {
                "max_repair_attempts": 2,
            },
        },
    )

    run_test(
        "TESTE 3 — LIMITE INVÁLIDO",
        {
            "question": "Teste de pergunta válida",
            "options": {
                "max_repair_attempts": 5,
            },
        },
    )


if __name__ == "__main__":
    run_test(
        "TESTE 0 - RESULTADOS ANTERIORES LIMPOS",
        {
            "question": "Teste de pergunta valida.",
            "sql_execution_result": {"status": "success"},
            "normalized_result": {"status": "success"},
            "serialized_result": {"status": "success"},
            "options": {
                "max_repair_attempts": 2,
            },
        },
        _assert_resultados_anteriores_limpos,
    )
    main()
