from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import cast

from app.domain.planning import QueryPlan
from app.domain.sql_analysis import SqlStatementAnalysis, safe_sql_analysis
from app.domain.sql_contract import (
    SqlContractResult,
    run_sql_contract_gate,
)
from app.graph.state import AgentError, GraphState


def contract_gate(
    state: GraphState,
) -> GraphState:
    current_sql = state.get("current_sql")
    query_plan = state.get("query_plan")
    security_result = state.get("security_result")

    if not isinstance(security_result, Mapping) or (
        security_result.get("status") != "approved"
    ):
        return _infrastructure_error(
            state,
            code="SQL_CONTRACT_SECURITY_NOT_APPROVED",
            message=(
                "Contract Gate exige Security Gate aprovado."
            ),
            result=None,
        )
    if not isinstance(current_sql, str) or not current_sql.strip():
        return _infrastructure_error(
            state,
            code="SQL_CONTRACT_INPUT_INVALID",
            message="current_sql esta ausente para o Contract Gate.",
            result=None,
        )
    if not isinstance(query_plan, Mapping) or not query_plan:
        return _infrastructure_error(
            state,
            code="SQL_CONTRACT_INPUT_INVALID",
            message="query_plan esta ausente para o Contract Gate.",
            result=None,
        )

    analysis = state.get("sql_analysis")
    safe_analysis = (
        cast(SqlStatementAnalysis, analysis)
        if isinstance(analysis, Mapping)
        else None
    )
    try:
        result, reused_analysis = run_sql_contract_gate(
            current_sql=current_sql,
            query_plan=cast(QueryPlan, query_plan),
            analysis=safe_analysis,
        )
    except Exception as error:
        return _infrastructure_error(
            state,
            code="SQL_CONTRACT_UNEXPECTED_ERROR",
            message=(
                "Ocorreu erro inesperado durante o Contract Gate."
            ),
            result=None,
            details={
                "exception_type": type(error).__name__,
            },
        )

    if result["status"] == "approved":
        output: GraphState = {
            "contract_result": result,
            "current_stage": "contract_gate",
            "final_status": "processing",
            "failure_stage": "",
        }
        if reused_analysis is not None:
            output["sql_analysis"] = safe_sql_analysis(reused_analysis)
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
    result: SqlContractResult,
    *,
    final_status: str,
) -> GraphState:
    error = _primary_error(result)
    return {
        "contract_result": result,
        "errors": [
            *state.get("errors", []),
            _agent_error(
                code=error["code"],
                message=error["message"],
                details={
                    "contract_result": _safe_result(result),
                    **error.get("details", {}),
                },
            ),
        ],
        "current_stage": "contract_gate",
        "final_status": final_status,
        "failure_stage": "contract_gate",
    }


def _infrastructure_error(
    state: GraphState,
    *,
    code: str,
    message: str,
    result: SqlContractResult | None,
    details: dict | None = None,
) -> GraphState:
    return {
        **({"contract_result": result} if result else {}),
        "errors": [
            *state.get("errors", []),
            _agent_error(
                code=code,
                message=message,
                details=details or {},
            ),
        ],
        "current_stage": "contract_gate",
        "final_status": "infrastructure_error",
        "failure_stage": "contract_gate",
    }


def _primary_error(result: SqlContractResult) -> dict:
    if result["errors"]:
        return result["errors"][0]
    if result["findings"]:
        return result["findings"][0]
    return {
        "code": "SQL_CONTRACT_INPUT_INVALID",
        "message": "Contract Gate falhou sem detalhe estruturado.",
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
        "source": "contract_gate",
        "stage": "contract_gate",
        "repairable": False,
        "details": details,
    }


def _safe_result(result: SqlContractResult) -> dict:
    safe = deepcopy(result)
    return safe
