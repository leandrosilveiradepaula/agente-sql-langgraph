from app.graph.state import GraphState


def finalize_invalid_request(
    state: GraphState,
) -> GraphState:
    """
    Encerra uma execução cuja entrada foi considerada inválida.

    Os erros produzidos por receive_question são preservados.
    """

    return {
        "current_stage": "finalize_invalid_request",
        "final_status": "invalid_request",
        "failure_stage": (
            state.get("failure_stage")
            or "receive_question"
        ),
    }