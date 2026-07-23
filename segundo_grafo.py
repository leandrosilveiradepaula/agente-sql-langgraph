from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict, total=False):
    """
    Estado compartilhado entre todos os nodes.
    """

    question: str
    normalized_question: str

    validation_status: str
    errors: list[str]

    current_stage: str
    final_status: str


def receive_question(state: GraphState) -> GraphState:
    """
    Recebe e normaliza a pergunta.

    Não interpreta regras financeiras.
    Não chama IA.
    """

    print("1. Node receive_question executado")

    question = state.get("question", "")
    question = question.strip()

    normalized_question = " ".join(question.split())

    return {
        "question": question,
        "normalized_question": normalized_question,
        "current_stage": "receive_question",
        "final_status": "processing",
    }


def validate_question(state: GraphState) -> GraphState:
    """
    Valida somente se existe uma pergunta.

    Esta ainda não é uma validação de SQL.
    """

    print("2. Node validate_question executado")

    normalized_question = state.get("normalized_question", "")

    if not normalized_question:
        return {
            "validation_status": "rejected",
            "errors": ["A pergunta não pode estar vazia."],
            "current_stage": "validate_question",
        }

    return {
        "validation_status": "approved",
        "errors": [],
        "current_stage": "validate_question",
    }


def route_after_validation(
    state: GraphState,
) -> Literal["approved", "rejected"]:
    """
    Decide qual caminho será seguido.

    Esta função não altera o estado.
    Ela apenas retorna o nome lógico da rota.
    """

    validation_status = state.get(
        "validation_status",
        "rejected",
    )

    if validation_status == "approved":
        print("3. Rota escolhida: approved")
        return "approved"

    print("3. Rota escolhida: rejected")
    return "rejected"


def finalize_success(state: GraphState) -> GraphState:
    """
    Finaliza uma execução aprovada.
    """

    print("4. Node finalize_success executado")

    return {
        "current_stage": "finalize_success",
        "final_status": "approved",
    }


def finalize_error(state: GraphState) -> GraphState:
    """
    Finaliza uma execução rejeitada.
    """

    print("4. Node finalize_error executado")

    return {
        "current_stage": "finalize_error",
        "final_status": "rejected",
    }


def create_graph():
    """
    Monta e compila o grafo.
    """

    builder = StateGraph(GraphState)

    builder.add_node(
        "receive_question",
        receive_question,
    )

    builder.add_node(
        "validate_question",
        validate_question,
    )

    builder.add_node(
        "finalize_success",
        finalize_success,
    )

    builder.add_node(
        "finalize_error",
        finalize_error,
    )

    builder.add_edge(
        START,
        "receive_question",
    )

    builder.add_edge(
        "receive_question",
        "validate_question",
    )

    builder.add_conditional_edges(
        "validate_question",
        route_after_validation,
        {
            "approved": "finalize_success",
            "rejected": "finalize_error",
        },
    )

    builder.add_edge(
        "finalize_success",
        END,
    )

    builder.add_edge(
        "finalize_error",
        END,
    )

    return builder.compile()


def print_result(result: GraphState) -> None:
    """
    Exibe o estado final.
    """

    print("\nResultado final do grafo:")

    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    graph = create_graph()

    print("=" * 60)
    print("TESTE 1 — PERGUNTA VÁLIDA")
    print("=" * 60)

    valid_state: GraphState = {
        "question": (
            "Quais as contas que tiveram maiores "
            "estouros de orçamento no mês?"
        )
    }

    valid_result = graph.invoke(valid_state)
    print_result(valid_result)

    print("\n")
    print("=" * 60)
    print("TESTE 2 — PERGUNTA VAZIA")
    print("=" * 60)

    invalid_state: GraphState = {
        "question": "   "
    }

    invalid_result = graph.invoke(invalid_state)
    print_result(invalid_result)