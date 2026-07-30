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
    ):
        return "complete"

    if final_status == "rejected":
        return "complete"

    return "infrastructure_error"
