from langgraph.graph import END, START, StateGraph

from app.graph.nodes.build_plan import build_plan
from app.graph.nodes.classify_intent import (
    classify_intent,
)
from app.graph.nodes.contract_gate import (
    contract_gate,
)
from app.graph.nodes.engine_preflight import (
    create_engine_preflight_node,
)
from app.graph.nodes.execute_sql import (
    create_execute_sql_node,
)
from app.graph.nodes.finalize_infrastructure_error import (
    finalize_infrastructure_error,
)
from app.graph.nodes.finalize_invalid_request import (
    finalize_invalid_request,
)
from app.graph.nodes.generate_sql import (
    create_generate_sql_node,
)
from app.graph.nodes.load_context import (
    create_load_context_node,
)
from app.graph.nodes.receive_question import (
    receive_question,
)
from app.graph.nodes.repair_sql import (
    create_repair_sql_node,
)
from app.graph.nodes.security_gate import (
    security_gate,
)
from app.graph.routing import (
    route_after_build_plan,
    route_after_classify_intent,
    route_after_contract_gate,
    route_after_engine_preflight,
    route_after_execute_sql,
    route_after_generate_sql,
    route_after_load_context,
    route_after_receive_question,
    route_after_repair_sql,
    route_after_security_gate,
)
from app.graph.state import GraphState
from app.ports.context_repository import (
    ContextRepository,
)
from app.ports.engine_preflight import EnginePreflight
from app.ports.sql_generator import SqlGenerator
from app.ports.sql_executor import SqlExecutor
from app.ports.sql_repairer import SqlRepairer


def create_graph(
    context_repository: ContextRepository,
    sql_generator: SqlGenerator,
    engine_preflight: EnginePreflight,
    sql_repairer: SqlRepairer,
    sql_executor: SqlExecutor,
):
    """
    Monta e compila o grafo-base do agente.

    Repositorio de contexto e gerador SQL sao recebidos externamente.
    """

    load_context = create_load_context_node(
        context_repository,
    )
    generate_sql = create_generate_sql_node(
        sql_generator,
    )
    engine_preflight_node = create_engine_preflight_node(
        engine_preflight,
    )
    repair_sql_node = create_repair_sql_node(
        sql_repairer,
    )
    execute_sql_node = create_execute_sql_node(
        sql_executor,
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
        "build_plan",
        build_plan,
    )

    builder.add_node(
        "generate_sql",
        generate_sql,
    )

    builder.add_node(
        "security_gate",
        security_gate,
    )

    builder.add_node(
        "contract_gate",
        contract_gate,
    )

    builder.add_node(
        "engine_preflight",
        engine_preflight_node,
    )

    builder.add_node(
        "repair_sql",
        repair_sql_node,
    )

    builder.add_node(
        "execute_sql",
        execute_sql_node,
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
            "build_plan": "build_plan",
            "complete": END,
            "infrastructure_error": (
                "finalize_infrastructure_error"
            ),
        },
    )

    builder.add_conditional_edges(
        "build_plan",
        route_after_build_plan,
        {
            "generate_sql": "generate_sql",
            "complete": END,
            "infrastructure_error": (
                "finalize_infrastructure_error"
            ),
        },
    )

    builder.add_conditional_edges(
        "generate_sql",
        route_after_generate_sql,
        {
            "security_gate": "security_gate",
            "complete": END,
            "infrastructure_error": (
                "finalize_infrastructure_error"
            ),
        },
    )

    builder.add_conditional_edges(
        "security_gate",
        route_after_security_gate,
        {
            "contract_gate": "contract_gate",
            "complete": END,
            "infrastructure_error": (
                "finalize_infrastructure_error"
            ),
        },
    )

    builder.add_conditional_edges(
        "contract_gate",
        route_after_contract_gate,
        {
            "engine_preflight": "engine_preflight",
            "complete": END,
            "infrastructure_error": (
                "finalize_infrastructure_error"
            ),
        },
    )

    builder.add_conditional_edges(
        "engine_preflight",
        route_after_engine_preflight,
        {
            "execute_sql": "execute_sql",
            "repair_sql": "repair_sql",
            "complete": END,
            "infrastructure_error": (
                "finalize_infrastructure_error"
            ),
        },
    )

    builder.add_conditional_edges(
        "execute_sql",
        route_after_execute_sql,
        {
            "complete": END,
            "infrastructure_error": (
                "finalize_infrastructure_error"
            ),
        },
    )

    builder.add_conditional_edges(
        "repair_sql",
        route_after_repair_sql,
        {
            "security_gate": "security_gate",
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
