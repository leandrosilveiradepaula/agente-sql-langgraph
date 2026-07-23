from app.graph.state import GraphState


def finalize_infrastructure_error(
    state: GraphState,
) -> GraphState:
    """
    Encerra uma execução por falha de infraestrutura.

    O erro original produzido pelo node anterior é preservado.
    """

    return {
        "current_stage": (
            "finalize_infrastructure_error"
        ),
        "final_status": "infrastructure_error",
        "failure_stage": (
            state.get("failure_stage")
            or "unknown"
        ),
    }