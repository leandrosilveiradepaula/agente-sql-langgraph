from langgraph.graph import END, START, StateGraph

from app.graph.nodes.build_plan import build_plan
from app.graph.nodes.build_run_record import build_run_record_node
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
from app.graph.nodes.emit_observability import (
    create_emit_observability_node,
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
from app.graph.nodes.normalize_result import (
    normalize_result,
)
from app.graph.nodes.persist_run import create_persist_run_node
from app.graph.nodes.load_context import (
    create_load_context_node,
)
from app.graph.nodes.receive_question import (
    receive_question,
)
from app.graph.nodes.repair_sql import (
    create_repair_sql_node,
)
from app.graph.nodes.record_audit import create_record_audit_node
from app.graph.nodes.security_gate import (
    security_gate,
)
from app.graph.nodes.serialize_result import (
    serialize_result,
)
from app.graph.routing import (
    route_after_build_plan,
    route_after_build_run_record,
    route_after_classify_intent,
    route_after_contract_gate,
    route_after_engine_preflight,
    route_after_execute_sql,
    route_after_generate_sql,
    route_after_load_context,
    route_after_normalize_result,
    route_after_persist_run,
    route_after_receive_question,
    route_after_record_audit,
    route_after_repair_sql,
    route_after_security_gate,
    route_after_serialize_result,
)
from app.graph.state import GraphState
from app.ports.context_repository import (
    ContextRepository,
)
from app.ports.engine_preflight import EnginePreflight
from app.ports.sql_generator import SqlGenerator
from app.ports.sql_executor import SqlExecutor
from app.ports.sql_repairer import SqlRepairer
from app.ports.run_repository import RunRepository
from app.ports.audit_sink import AuditSink
from app.ports.observability_sink import ObservabilitySink


def create_graph(
    context_repository: ContextRepository,
    sql_generator: SqlGenerator,
    engine_preflight: EnginePreflight,
    sql_repairer: SqlRepairer,
    sql_executor: SqlExecutor,
    run_repository: RunRepository,
    audit_sink: AuditSink,
    observability_sink: ObservabilitySink,
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
    persist_run_node = create_persist_run_node(run_repository)
    record_audit_node = create_record_audit_node(audit_sink)
    emit_observability_node = create_emit_observability_node(
        observability_sink
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
        "normalize_result",
        normalize_result,
    )

    builder.add_node(
        "serialize_result",
        serialize_result,
    )

    builder.add_node(
        "build_run_record",
        build_run_record_node,
    )

    builder.add_node(
        "persist_run",
        persist_run_node,
    )

    builder.add_node(
        "record_audit",
        record_audit_node,
    )

    builder.add_node(
        "emit_observability",
        emit_observability_node,
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
            "complete": "build_run_record",
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
            "complete": "build_run_record",
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
            "complete": "build_run_record",
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
            "complete": "build_run_record",
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
            "complete": "build_run_record",
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
            "complete": "build_run_record",
            "infrastructure_error": (
                "finalize_infrastructure_error"
            ),
        },
    )

    builder.add_conditional_edges(
        "execute_sql",
        route_after_execute_sql,
        {
            "normalize_result": "normalize_result",
            "complete": "build_run_record",
            "infrastructure_error": (
                "finalize_infrastructure_error"
            ),
        },
    )

    builder.add_conditional_edges(
        "normalize_result",
        route_after_normalize_result,
        {
            "serialize_result": "serialize_result",
            "complete": "build_run_record",
            "infrastructure_error": (
                "finalize_infrastructure_error"
            ),
        },
    )

    builder.add_conditional_edges(
        "serialize_result",
        route_after_serialize_result,
        {
            "complete": "build_run_record",
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
            "complete": "build_run_record",
            "infrastructure_error": (
                "finalize_infrastructure_error"
            ),
        },
    )

    builder.add_edge(
        "finalize_invalid_request",
        "build_run_record",
    )

    builder.add_edge(
        "finalize_infrastructure_error",
        "build_run_record",
    )

    builder.add_conditional_edges(
        "build_run_record",
        route_after_build_run_record,
        {
            "persist_run": "persist_run",
            "complete": END,
        },
    )

    builder.add_conditional_edges(
        "persist_run",
        route_after_persist_run,
        {
            "record_audit": "record_audit",
            "emit_observability": "emit_observability",
        },
    )

    builder.add_conditional_edges(
        "record_audit",
        route_after_record_audit,
        {
            "emit_observability": "emit_observability",
        },
    )

    builder.add_edge(
        "emit_observability",
        END,
    )

    return builder.compile()
