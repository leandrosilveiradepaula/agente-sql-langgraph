from langgraph.graph import END, START, StateGraph

from app.graph.nodes.classify_intent import (
    classify_intent,
)
from app.graph.nodes.finalize_infrastructure_error import (
    finalize_infrastructure_error,
)
from app.graph.nodes.finalize_invalid_request import (
    finalize_invalid_request,
)
from app.graph.nodes.load_context import (
    create_load_context_node,
)
from app.graph.nodes.receive_question import (
    receive_question,
)
from app.graph.routing import (
    route_after_classify_intent,
    route_after_load_context,
    route_after_receive_question,
)
from app.graph.state import GraphState
from app.ports.context_repository import (
    ContextRepository,
)


def create_graph(
    context_repository: ContextRepository,
):
    """
    Monta e compila o grafo-base do Agente SQL Financeiro.

    O repositório de contexto é recebido externamente.
    """

    load_context = create_load_context_node(
        context_repository,
    )

    builder = StateGraph(GraphState)

    builder.add_node(
        "receive_question",
        receive_question,
    )

    builder.add_node(
        "load_context",
        load_context,
    )

    builder.add_node(
        "classify_intent",
        classify_intent,
    )

    builder.add_node(
        "finalize_invalid_request",
        finalize_invalid_request,
    )

    builder.add_node(
        "finalize_infrastructure_error",
        finalize_infrastructure_error,
    )

    builder.add_edge(
        START,
        "receive_question",
    )

    builder.add_conditional_edges(
        "receive_question",
        route_after_receive_question,
        {
            "continue": "load_context",
            "invalid_request": (
                "finalize_invalid_request"
            ),
        },
    )

    builder.add_conditional_edges(
        "load_context",
        route_after_load_context,
        {
            "continue": "classify_intent",
            "infrastructure_error": (
                "finalize_infrastructure_error"
            ),
        },
    )

    builder.add_conditional_edges(
        "classify_intent",
        route_after_classify_intent,
        {
            "complete": END,
            "infrastructure_error": (
                "finalize_infrastructure_error"
            ),
        },
    )

    builder.add_edge(
        "finalize_invalid_request",
        END,
    )

    builder.add_edge(
        "finalize_infrastructure_error",
        END,
    )

    return builder.compile()
