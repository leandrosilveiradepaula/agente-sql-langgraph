from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import cast

from app.domain.engine_preflight import EnginePreflightResult
from app.domain.planning import QueryPlan
from app.domain.sql_repair import (
    SqlRepairInputError,
    SqlRepairProviderError,
    SqlRepairProviderResult,
    SqlRepairRequest,
    SqlRepairResult,
    build_sql_repair_request,
    create_sql_repair_error_result,
    create_sql_repair_success_result,
    validate_sql_repair_response,
)
from app.graph.state import AgentError, GraphState
from app.ports.sql_repairer import SqlRepairer


def create_repair_sql_node(
    sql_repairer: SqlRepairer,
) -> Callable[[GraphState], GraphState]:
    """
    Cria o node repair_sql com reparador injetado.
    """

    def repair_sql(state: GraphState) -> GraphState:
        current_sql = state.get("current_sql")
        query_plan = state.get("query_plan")
        engine_preflight_result = state.get("engine_preflight_result")
        repair_attempts = state.get("repair_attempts", 0)
        max_repair_attempts = state.get("max_repair_attempts", 0)
        repair_history = state.get("repair_history", [])

        request: SqlRepairRequest | None = None
        try:
            request = build_sql_repair_request(
                current_sql=(
                    current_sql if isinstance(current_sql, str) else ""
                ),
                query_plan=cast(
                    QueryPlan,
                    query_plan if isinstance(query_plan, Mapping) else {},
                ),
                engine_preflight_result=cast(
                    EnginePreflightResult,
                    (
                        engine_preflight_result
                        if isinstance(engine_preflight_result, Mapping)
                        else {}
                    ),
                ),
                repair_attempts=(
                    repair_attempts
                    if isinstance(repair_attempts, int)
                    else -1
                ),
                max_repair_attempts=(
                    max_repair_attempts
                    if isinstance(max_repair_attempts, int)
                    else -1
                ),
                repair_history=(
                    repair_history
                    if isinstance(repair_history, list)
                    else []
                ),
            )
        except SqlRepairInputError as error:
            result = create_sql_repair_error_result(
                request=None,
                code=error.code,
                message=error.message,
                reason=error.reason,
                status="rejected",
                current_sql=current_sql if isinstance(current_sql, str) else "",
                attempt=_next_attempt(repair_attempts),
                max_attempts=_safe_counter(max_repair_attempts),
            )
            return _error_state(
                state,
                result,
                final_status="rejected",
                append_history=False,
                increment_attempts=False,
            )
        except Exception as error:
            result = create_sql_repair_error_result(
                request=None,
                code="SQL_REPAIR_UNEXPECTED_ERROR",
                message="Erro inesperado ao construir reparo SQL.",
                reason="sql_repair_unexpected_error",
                status="infrastructure_error",
                current_sql=current_sql if isinstance(current_sql, str) else "",
                attempt=_next_attempt(repair_attempts),
                max_attempts=_safe_counter(max_repair_attempts),
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
                append_history=False,
                increment_attempts=False,
                details={"exception_type": type(error).__name__},
            )

        try:
            provider_result = sql_repairer.repair(deepcopy(request))
        except SqlRepairProviderError as error:
            result = create_sql_repair_error_result(
                request=request,
                code="SQL_REPAIR_PROVIDER_FAILED",
                message="Provider de reparo SQL falhou.",
                reason="sql_repair_provider_failed",
                status="infrastructure_error",
                current_sql=request["current_sql"],
                attempt=request["attempt"],
                max_attempts=request["max_attempts"],
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
                append_history=True,
                increment_attempts=True,
                details={"exception_type": type(error).__name__},
            )
        except TimeoutError:
            result = create_sql_repair_error_result(
                request=request,
                code="SQL_REPAIR_PROVIDER_FAILED",
                message="Provider de reparo SQL excedeu o timeout.",
                reason="sql_repair_provider_failed",
                status="infrastructure_error",
                current_sql=request["current_sql"],
                attempt=request["attempt"],
                max_attempts=request["max_attempts"],
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
                append_history=True,
                increment_attempts=True,
            )
        except Exception as error:
            result = create_sql_repair_error_result(
                request=request,
                code="SQL_REPAIR_UNEXPECTED_ERROR",
                message="Erro inesperado no provider de reparo SQL.",
                reason="sql_repair_unexpected_error",
                status="infrastructure_error",
                current_sql=request["current_sql"],
                attempt=request["attempt"],
                max_attempts=request["max_attempts"],
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
                append_history=True,
                increment_attempts=True,
                details={"exception_type": type(error).__name__},
            )

        try:
            repaired_sql = validate_sql_repair_response(
                provider_result=cast(
                    SqlRepairProviderResult,
                    provider_result,
                ),
                current_sql=request["current_sql"],
                repair_history=cast(list[Mapping], repair_history),
            )
        except SqlRepairInputError as error:
            result = create_sql_repair_error_result(
                request=request,
                code=error.code,
                message=error.message,
                reason=error.reason,
                status="rejected",
                current_sql=request["current_sql"],
                attempt=request["attempt"],
                max_attempts=request["max_attempts"],
                provider_result=cast(
                    SqlRepairProviderResult,
                    provider_result if isinstance(provider_result, Mapping) else {},
                ),
            )
            return _error_state(
                state,
                result,
                final_status="rejected",
                append_history=True,
                increment_attempts=True,
            )
        except Exception as error:
            result = create_sql_repair_error_result(
                request=request,
                code="SQL_REPAIR_UNEXPECTED_ERROR",
                message="Erro inesperado ao validar SQL reparada.",
                reason="sql_repair_unexpected_error",
                status="infrastructure_error",
                current_sql=request["current_sql"],
                attempt=request["attempt"],
                max_attempts=request["max_attempts"],
                provider_result=cast(
                    SqlRepairProviderResult,
                    provider_result if isinstance(provider_result, Mapping) else {},
                ),
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
                append_history=True,
                increment_attempts=True,
                details={"exception_type": type(error).__name__},
            )

        result = create_sql_repair_success_result(
            request=request,
            repaired_sql=repaired_sql,
            provider_result=cast(
                SqlRepairProviderResult,
                provider_result,
            ),
        )
        return {
            "current_sql": repaired_sql,
            "repair_attempts": request["attempt"],
            "repair_history": [
                *deepcopy(state.get("repair_history", [])),
                result["history_entry"],
            ],
            "sql_repair_result": result,
            "security_result": _not_run_result(),
            "contract_result": _not_run_result(),
            "engine_preflight_result": _not_run_result(),
            "current_stage": "repair_sql",
            "final_status": "processing",
            "failure_stage": "",
        }

    return repair_sql


def _error_state(
    state: GraphState,
    result: SqlRepairResult,
    *,
    final_status: str,
    append_history: bool,
    increment_attempts: bool,
    details: dict | None = None,
) -> GraphState:
    history = deepcopy(state.get("repair_history", []))
    if append_history and result["history_entry"] is not None:
        history.append(result["history_entry"])
    error: AgentError = {
        "code": result["error_code"] or "SQL_REPAIR_RESPONSE_INVALID",
        "message": result["message"],
        "source": "sql_repair",
        "stage": "repair_sql",
        "repairable": False,
        "details": {
            "diagnostic": result["diagnostic"],
            **(details or {}),
        },
    }
    output: GraphState = {
        "sql_repair_result": result,
        "errors": [
            *state.get("errors", []),
            error,
        ],
        "current_stage": "repair_sql",
        "final_status": final_status,
        "failure_stage": "repair_sql",
    }
    if append_history:
        output["repair_history"] = history
    if increment_attempts:
        output["repair_attempts"] = result["diagnostic"]["attempt"]
    return output


def _not_run_result() -> dict:
    return {
        "status": "not_run",
        "errors": [],
        "warnings": [],
    }


def _next_attempt(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value + 1
    return 1


def _safe_counter(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0
