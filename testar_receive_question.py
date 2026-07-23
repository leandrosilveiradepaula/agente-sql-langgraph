from pprint import pprint

from app.graph.nodes.receive_question import receive_question
from app.graph.state import GraphState


def run_test(
    title: str,
    initial_state: GraphState,
) -> None:
    print("=" * 70)
    print(title)
    print("=" * 70)

    result = receive_question(initial_state)

    pprint(
        result,
        sort_dicts=False,
    )

    print()


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
    main()