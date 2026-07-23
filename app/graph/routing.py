from typing import Literal

from app.graph.state import GraphState


def route_after_receive_question(
    state: GraphState,
) -> Literal["continue", "invalid_request"]:
    """
    Decide o caminho depois da validação inicial.
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

    if (
        final_status == "processing"
        and context_version
    ):
        return "continue"

    return "infrastructure_error"