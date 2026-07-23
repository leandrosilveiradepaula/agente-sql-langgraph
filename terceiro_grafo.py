from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict, total=False):
    """
    Estado compartilhado pelo grafo.

    Neste exemplo, a SQL e as falhas são simuladas.
    Ainda não existe geração ou validação real.
    """

    question: str
    normalized_question: str

    current_sql: str

    validation_status: str
    validation_errors: list[str]

    repair_attempts: int
    max_repair_attempts: int
    repair_history: list[str]

    simulation_failures_before_success: int

    current_stage: str
    final_status: str


def receive_question(state: GraphState) -> GraphState:
    """
    Recebe e normaliza a pergunta.
    """

    print("1. Node receive_question executado")

    question = state.get("question", "").strip()
    normalized_question = " ".join(question.split())

    return {
        "question": question,
        "normalized_question": normalized_question,
        "repair_attempts": 0,
        "repair_history": [],
        "current_stage": "receive_question",
        "final_status": "processing",
    }


def generate_sql_mock(state: GraphState) -> GraphState:
    """
    Simula uma primeira geração de SQL.

    O texto não é uma SQL real.
    É apenas um identificador para acompanharmos as tentativas.
    """

    print("2. Node generate_sql_mock executado")

    return {
        "current_sql": "SQL_SIMULADA_INICIAL",
        "current_stage": "generate_sql_mock",
    }


def validate_sql_mock(state: GraphState) -> GraphState:
    """
    Simula a validação da SQL.

    simulation_failures_before_success controla quantos repairs
    devem acontecer antes da aprovação.

    Esse campo existe somente para o teste.
    """

    repair_attempts = state.get("repair_attempts", 0)

    failures_before_success = state.get(
        "simulation_failures_before_success",
        0,
    )

    print(
        "3. Node validate_sql_mock executado "
        f"(repairs realizados: {repair_attempts})"
    )

    if repair_attempts >= failures_before_success:
        return {
            "validation_status": "approved",
            "validation_errors": [],
            "current_stage": "validate_sql_mock",
        }

    return {
        "validation_status": "rejected",
        "validation_errors": [
            (
                "Falha simulada de validação. "
                f"Repairs realizados: {repair_attempts}."
            )
        ],
        "current_stage": "validate_sql_mock",
    }


def route_after_validation(
    state: GraphState,
) -> Literal["approved", "repair", "exhausted"]:
    """
    Decide se o grafo:

    - aprova;
    - tenta repair;
    - encerra porque atingiu o limite.
    """

    validation_status = state.get(
        "validation_status",
        "rejected",
    )

    if validation_status == "approved":
        print("4. Rota escolhida: approved")
        return "approved"

    repair_attempts = state.get("repair_attempts", 0)
    max_repair_attempts = state.get(
        "max_repair_attempts",
        2,
    )

    if repair_attempts < max_repair_attempts:
        print("4. Rota escolhida: repair")
        return "repair"

    print("4. Rota escolhida: exhausted")
    return "exhausted"


def repair_sql_mock(state: GraphState) -> GraphState:
    """
    Simula uma tentativa de repair.

    Não corrige SQL real.
    Apenas incrementa o contador e registra o histórico.
    """

    next_attempt = state.get("repair_attempts", 0) + 1

    repair_history = list(
        state.get("repair_history", [])
    )

    repair_history.append(
        f"Repair simulado {next_attempt} executado."
    )

    print(
        "5. Node repair_sql_mock executado "
        f"(repair {next_attempt})"
    )

    return {
        "current_sql": f"SQL_SIMULADA_REPAIR_{next_attempt}",
        "repair_attempts": next_attempt,
        "repair_history": repair_history,
        "current_stage": "repair_sql_mock",
    }


def finalize_success(state: GraphState) -> GraphState:
    """
    Finaliza a execução aprovada.
    """

    print("6. Node finalize_success executado")

    return {
        "current_stage": "finalize_success",
        "final_status": "approved",
    }


def finalize_error(state: GraphState) -> GraphState:
    """
    Finaliza após esgotar as tentativas.
    """

    print("6. Node finalize_error executado")

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
        "generate_sql_mock",
        generate_sql_mock,
    )

    builder.add_node(
        "validate_sql_mock",
        validate_sql_mock,
    )

    builder.add_node(
        "repair_sql_mock",
        repair_sql_mock,
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
        "generate_sql_mock",
    )

    builder.add_edge(
        "generate_sql_mock",
        "validate_sql_mock",
    )

    builder.add_conditional_edges(
        "validate_sql_mock",
        route_after_validation,
        {
            "approved": "finalize_success",
            "repair": "repair_sql_mock",
            "exhausted": "finalize_error",
        },
    )

    builder.add_edge(
        "repair_sql_mock",
        "validate_sql_mock",
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
    Exibe os campos mais importantes do estado final.
    """

    print("\nResultado final:")

    fields = [
        "question",
        "current_sql",
        "validation_status",
        "validation_errors",
        "repair_attempts",
        "max_repair_attempts",
        "repair_history",
        "current_stage",
        "final_status",
    ]

    for field in fields:
        print(f"{field}: {result.get(field)}")


if __name__ == "__main__":
    graph = create_graph()

    print("=" * 70)
    print("TESTE 1 — APROVA DEPOIS DE UM REPAIR")
    print("=" * 70)

    success_state: GraphState = {
        "question": (
            "Quais as contas que tiveram maiores "
            "estouros de orçamento no mês?"
        ),
        "max_repair_attempts": 2,
        "simulation_failures_before_success": 1,
    }

    success_result = graph.invoke(
        success_state,
        config={
            "recursion_limit": 20,
        },
    )

    print_result(success_result)

    print("\n")
    print("=" * 70)
    print("TESTE 2 — ESGOTA AS DUAS TENTATIVAS")
    print("=" * 70)

    failure_state: GraphState = {
        "question": (
            "Nos gastos com pessoal, "
            "traga as maiores e menores contas."
        ),
        "max_repair_attempts": 2,
        "simulation_failures_before_success": 3,
    }

    failure_result = graph.invoke(
        failure_state,
        config={
            "recursion_limit": 20,
        },
    )

    print_result(failure_result)