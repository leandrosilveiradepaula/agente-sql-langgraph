from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import cast

from app.domain.planning import QueryPlan
from app.domain.sql_analysis import safe_sql_analysis
from app.domain.sql_security import (
    SqlSecurityResult,
    run_sql_security_gate,
)
from app.graph.state import AgentError, GraphState


def security_gate(
    state: GraphState,
) -> GraphState:
    current_sql = state.get("current_sql")
    query_plan = state.get("query_plan")

    if not isinstance(current_sql, str) or not current_sql.strip():
        return _infrastructure_error(
            state,
            code="SQL_SECURITY_INPUT_INVALID",
            message="current_sql esta ausente para o Security Gate.",
            result=None,
        )
    if not isinstance(query_plan, Mapping) or not query_plan:
        return _infrastructure_error(
            state,
            code="SQL_SECURITY_INPUT_INVALID",
            message="query_plan esta ausente para o Security Gate.",
            result=None,
        )

    try:
        result, analysis = run_sql_security_gate(
            current_sql=current_sql,
            query_plan=cast(QueryPlan, query_plan),
        )
    except Exception as error:
        return _infrastructure_error(
            state,
            code="SQL_SECURITY_UNEXPECTED_ERROR",
            message=(
                "Ocorreu erro inesperado durante o Security Gate."
            ),
            result=None,
            details={
                "exception_type": type(error).__name__,
            },
        )

    if result["status"] == "approved":
        output: GraphState = {
            "security_result": result,
            "current_stage": "security_gate",
            "final_status": "processing",
            "failure_stage": "",
        }
        if analysis is not None:
            output["sql_analysis"] = safe_sql_analysis(analysis)
        return output

    final_status = (
        "infrastructure_error"
        if result["status"] == "error"
        else "rejected"
    )
    return _gate_error_state(
        state,
        result,
        final_status=final_status,
    )


def _gate_error_state(
    state: GraphState,
    result: SqlSecurityResult,
    *,
    final_status: str,
) -> GraphState:
    error = _primary_error(result)
    return {
        "security_result": result,
        "errors": [
            *state.get("errors", []),
            _agent_error(
                code=error["code"],
                message=error["message"],
                details={
                    "security_result": _safe_result(result),
                    **error.get("details", {}),
                },
            ),
        ],
        "current_stage": "security_gate",
        "final_status": final_status,
        "failure_stage": "security_gate",
    }


def _infrastructure_error(
    state: GraphState,
    *,
    code: str,
    message: str,
    result: SqlSecurityResult | None,
    details: dict | None = None,
) -> GraphState:
    return {
        **({"security_result": result} if result else {}),
        "errors": [
            *state.get("errors", []),
            _agent_error(
                code=code,
                message=message,
                details=details or {},
            ),
        ],
        "current_stage": "security_gate",
        "final_status": "infrastructure_error",
        "failure_stage": "security_gate",
    }


def _primary_error(result: SqlSecurityResult) -> dict:
    if result["errors"]:
        return result["errors"][0]
    if result["findings"]:
        return result["findings"][0]
    return {
        "code": "SQL_SECURITY_INPUT_INVALID",
        "message": "Security Gate falhou sem detalhe estruturado.",
        "details": {},
    }


def _agent_error(
    *,
    code: str,
    message: str,
    details: dict,
) -> AgentError:
    return {
        "code": code,
        "message": message,
        "source": "security_gate",
        "stage": "security_gate",
        "repairable": False,
        "details": details,
    }


def _safe_result(result: SqlSecurityResult) -> dict:
    safe = deepcopy(result)
    safe.pop("objects", None)
    return safe
