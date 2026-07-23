from app.graph.state import GraphState


def mark_ready_for_intent(
    state: GraphState,
) -> GraphState:
    """
    Marca o estado como pronto para classificação de intenção.

    Este node será substituído posteriormente pelo node
    real classify_intent.
    """

    return {
        "current_stage": "ready_for_classify_intent",
        "final_status": "processing",
    }