from typing import Literal

from app.graph.state import GraphState


def route_after_receive_question(
    state: GraphState,
) -> Literal["continue", "invalid_request"]:
    """
    Decide o caminho depois da validacao inicial.
    """

    if state.get("final_status") == "processing":
        return "continue"

    return "invalid_request"


def route_after_load_context(
    state: GraphState,
) -> Literal[
    "continue",
    "infrastructure_error",
]:
    """
    Decide o caminho depois do carregamento do contexto.
    """

    final_status = state.get(
        "final_status",
        "infrastructure_error",
    )

    context_version = state.get(
        "context_version",
        "",
    )

    if final_status == "processing" and context_version:
        return "continue"

    return "infrastructure_error"


def route_after_classify_intent(
    state: GraphState,
) -> Literal[
    "build_plan",
    "complete",
    "infrastructure_error",
]:
    """
    Decide o caminho depois da classificacao de intencao.
    """

    final_status = state.get(
        "final_status",
        "infrastructure_error",
    )

    if final_status == "processing" and state.get("intent"):
        return "build_plan"

    if final_status == "rejected":
        return "complete"

    return "infrastructure_error"


def route_after_build_plan(
    state: GraphState,
) -> Literal[
    "complete",
    "infrastructure_error",
]:
    """
    Decide o encerramento depois da construcao do plano.
    """

    final_status = state.get(
        "final_status",
        "infrastructure_error",
    )

    if final_status == "processing" and state.get("query_plan"):
        return "complete"

    if final_status == "rejected":
        return "complete"

    return "infrastructure_error"
