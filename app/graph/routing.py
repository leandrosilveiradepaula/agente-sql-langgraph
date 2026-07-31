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
    "generate_sql",
    "complete",
    "infrastructure_error",
]:
    """
    Decide o caminho depois da construcao do plano.
    """

    final_status = state.get(
        "final_status",
        "infrastructure_error",
    )

    if final_status == "processing" and state.get("query_plan"):
        return "generate_sql"

    if final_status == "rejected":
        return "complete"

    return "infrastructure_error"


def route_after_generate_sql(
    state: GraphState,
) -> Literal[
    "security_gate",
    "complete",
    "infrastructure_error",
]:
    """
    Decide o encerramento depois da geracao SQL.
    """

    final_status = state.get(
        "final_status",
        "infrastructure_error",
    )

    if (
        final_status == "processing"
        and state.get("current_sql")
        and state.get("query_plan")
    ):
        return "security_gate"

    if final_status == "rejected":
        return "complete"

    return "infrastructure_error"


def route_after_security_gate(
    state: GraphState,
) -> Literal[
    "contract_gate",
    "complete",
    "infrastructure_error",
]:
    """
    Decide o caminho depois do Security Gate.
    """

    final_status = state.get(
        "final_status",
        "infrastructure_error",
    )
    security_result = state.get("security_result", {})

    if (
        final_status == "processing"
        and isinstance(security_result, dict)
        and security_result.get("status") == "approved"
    ):
        return "contract_gate"

    if final_status == "rejected":
        return "complete"

    return "infrastructure_error"


def route_after_contract_gate(
    state: GraphState,
) -> Literal[
    "engine_preflight",
    "complete",
    "infrastructure_error",
]:
    """
    Decide o encerramento depois do Contract Gate.
    """

    final_status = state.get(
        "final_status",
        "infrastructure_error",
    )
    contract_result = state.get("contract_result", {})

    if (
        final_status == "processing"
        and isinstance(contract_result, dict)
        and contract_result.get("status") == "approved"
    ):
        return "engine_preflight"

    if final_status == "rejected":
        return "complete"

    return "infrastructure_error"


def route_after_engine_preflight(
    state: GraphState,
) -> Literal[
    "execute_sql",
    "repair_sql",
    "complete",
    "infrastructure_error",
]:
    """
    Decide o encerramento depois do Engine Preflight.
    """

    final_status = state.get(
        "final_status",
        "infrastructure_error",
    )
    engine_preflight_result = state.get(
        "engine_preflight_result",
        {},
    )

    if (
        final_status == "processing"
        and isinstance(engine_preflight_result, dict)
        and engine_preflight_result.get("status") == "approved"
        and engine_preflight_result.get("approved") is True
        and engine_preflight_result.get("failure_category") in {None, "none"}
        and not engine_preflight_result.get("errors")
        and not engine_preflight_result.get("findings")
        and engine_preflight_result.get("executed") is False
        and engine_preflight_result.get("rows_returned") == 0
        and engine_preflight_result.get("statement_planned") is True
    ):
        return "execute_sql"

    if (
        final_status == "rejected"
        and isinstance(engine_preflight_result, dict)
        and engine_preflight_result.get("status") == "rejected"
        and engine_preflight_result.get("repairable") is True
    ):
        return "repair_sql"

    if final_status == "rejected":
        return "complete"

    return "infrastructure_error"


def route_after_execute_sql(
    state: GraphState,
) -> Literal[
    "normalize_result",
    "complete",
    "infrastructure_error",
]:
    """
    Decide o encerramento depois da execucao SQL controlada.
    """

    final_status = state.get(
        "final_status",
        "infrastructure_error",
    )

    execution_result = state.get("sql_execution_result", {})
    if (
        final_status == "processing"
        and isinstance(execution_result, dict)
        and execution_result.get("status") == "success"
        and execution_result.get("executed") is True
    ):
        return "normalize_result"

    if final_status == "rejected":
        return "complete"

    return "infrastructure_error"


def route_after_normalize_result(
    state: GraphState,
) -> Literal[
    "serialize_result",
    "complete",
    "infrastructure_error",
]:
    """
    Decide o caminho depois da normalizacao do resultado.
    """

    final_status = state.get(
        "final_status",
        "infrastructure_error",
    )
    normalized_result = state.get("normalized_result", {})

    if (
        final_status == "processing"
        and isinstance(normalized_result, dict)
        and normalized_result.get("status") == "success"
    ):
        return "serialize_result"

    if final_status == "rejected":
        return "complete"

    return "infrastructure_error"


def route_after_serialize_result(
    state: GraphState,
) -> Literal[
    "complete",
    "infrastructure_error",
]:
    """
    Decide o encerramento depois da serializacao do resultado.
    """

    final_status = state.get(
        "final_status",
        "infrastructure_error",
    )

    if final_status in {"approved", "rejected"}:
        return "complete"

    return "infrastructure_error"


def route_after_repair_sql(
    state: GraphState,
) -> Literal[
    "security_gate",
    "complete",
    "infrastructure_error",
]:
    """
    Decide o caminho depois do reparo SQL.
    """

    final_status = state.get(
        "final_status",
        "infrastructure_error",
    )

    if (
        final_status == "processing"
        and state.get("current_sql")
        and state.get("query_plan")
    ):
        return "security_gate"

    if final_status == "rejected":
        return "complete"

    return "infrastructure_error"
