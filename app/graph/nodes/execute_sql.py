from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import cast

from app.domain.engine_preflight_types import EnginePreflightResult
from app.domain.planning import QueryPlan
from app.domain.sql_contract import SqlContractResult
from app.domain.sql_execution import (
    SqlExecutionInputError,
    SqlExecutionProviderError,
    SqlExecutionProviderResult,
    SqlExecutionResult,
    build_sql_execution_request,
    create_sql_execution_error_result,
    normalize_sql_execution_result,
)
from app.domain.sql_security import SqlSecurityResult
from app.graph.state import AgentError, GraphState
from app.ports.sql_executor import SqlExecutor


def create_execute_sql_node(
    sql_executor: SqlExecutor,
) -> Callable[[GraphState], GraphState]:
    """
    Cria o node execute_sql com executor explicitamente injetado.
    """

    def execute_sql(state: GraphState) -> GraphState:
        current_sql = state.get("current_sql")
        query_plan = state.get("query_plan")
        security_result = state.get("security_result")
        contract_result = state.get("contract_result")
        engine_preflight_result = state.get("engine_preflight_result")
        request = None

        try:
            request = build_sql_execution_request(
                current_sql=current_sql if isinstance(current_sql, str) else "",
                query_plan=cast(
                    QueryPlan,
                    query_plan if isinstance(query_plan, Mapping) else {},
                ),
                security_result=cast(
                    SqlSecurityResult,
                    (
                        security_result
                        if isinstance(security_result, Mapping)
                        else {}
                    ),
                ),
                contract_result=cast(
                    SqlContractResult,
                    (
                        contract_result
                        if isinstance(contract_result, Mapping)
                        else {}
                    ),
                ),
                engine_preflight_result=cast(
                    EnginePreflightResult,
                    (
                        engine_preflight_result
                        if isinstance(engine_preflight_result, Mapping)
                        else {}
                    ),
                ),
                request_id=str(state.get("request_id", "")),
                run_id=str(state.get("run_id", "")),
                options=(
                    state.get("options")
                    if isinstance(state.get("options"), Mapping)
                    else None
                ),
            )
        except SqlExecutionInputError as error:
            result = create_sql_execution_error_result(
                request=None,
                code=error.code,
                message=error.message,
                category=error.category,
                status="rejected",
            )
            return _error_state(
                state,
                result,
                final_status="rejected",
            )
        except Exception as error:
            result = create_sql_execution_error_result(
                request=None,
                code="SQL_EXECUTION_UNEXPECTED_ERROR",
                message="Erro inesperado ao construir execucao SQL.",
                category="unexpected_error",
                status="infrastructure_error",
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
                details={"exception_type": type(error).__name__},
            )

        try:
            provider_result = sql_executor.execute(deepcopy(request))
        except SqlExecutionProviderError as error:
            result = create_sql_execution_error_result(
                request=request,
                code="SQL_EXECUTION_PROVIDER_FAILED",
                message="Executor SQL falhou.",
                category="provider_failed",
                status="infrastructure_error",
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
                details={"exception_type": type(error).__name__},
            )
        except TimeoutError:
            result = create_sql_execution_error_result(
                request=request,
                code="SQL_EXECUTION_TIMEOUT",
                message="Executor SQL excedeu o timeout.",
                category="timeout",
                status="infrastructure_error",
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
            )
        except Exception as error:
            result = create_sql_execution_error_result(
                request=request,
                code="SQL_EXECUTION_UNEXPECTED_ERROR",
                message="Erro inesperado no executor SQL.",
                category="unexpected_error",
                status="infrastructure_error",
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
                details={"exception_type": type(error).__name__},
            )

        try:
            result = normalize_sql_execution_result(
                request=request,
                provider_result=cast(
                    SqlExecutionProviderResult,
                    provider_result,
                ),
            )
        except Exception as error:
            result = create_sql_execution_error_result(
                request=request,
                code="SQL_EXECUTION_RESPONSE_INVALID",
                message="Resposta do executor SQL e invalida.",
                category="response_invalid",
                status="rejected",
            )
            return _error_state(
                state,
                result,
                final_status="rejected",
                details={"exception_type": type(error).__name__},
            )

        if result["status"] == "success":
            return {
                "sql_execution_result": result,
                "current_stage": "execute_sql",
                "final_status": "approved",
                "failure_stage": "",
            }

        return _error_state(
            state,
            result,
            final_status=(
                "infrastructure_error"
                if result["status"] == "infrastructure_error"
                else "rejected"
            ),
        )

    return execute_sql


def _error_state(
    state: GraphState,
    result: SqlExecutionResult,
    *,
    final_status: str,
    details: dict | None = None,
) -> GraphState:
    error = _agent_error(
        code=result["error_code"] or "SQL_EXECUTION_RESPONSE_INVALID",
        message=_message(result),
        details={
            "failure_category": result["failure_category"],
            "diagnostic": result["diagnostics"][0],
            **(details or {}),
        },
    )
    return {
        "sql_execution_result": result,
        "errors": [
            *state.get("errors", []),
            error,
        ],
        "current_stage": "execute_sql",
        "final_status": final_status,
        "failure_stage": "execute_sql",
    }


def _message(result: SqlExecutionResult) -> str:
    code = result["error_code"] or "SQL_EXECUTION_RESPONSE_INVALID"
    messages = {
        "SQL_EXECUTION_ROW_LIMIT_EXCEEDED": (
            "Executor SQL excedeu o limite de linhas."
        ),
        "SQL_EXECUTION_BYTE_LIMIT_EXCEEDED": (
            "Executor SQL excedeu o limite de bytes."
        ),
        "SQL_EXECUTION_CELL_LIMIT_EXCEEDED": (
            "Executor SQL excedeu o limite de celula."
        ),
        "SQL_EXECUTION_TIMEOUT": "Executor SQL excedeu o timeout.",
        "SQL_EXECUTION_AUTHENTICATION_FAILED": (
            "Executor SQL falhou por autenticacao."
        ),
    }
    return messages.get(code, "Execucao SQL nao autorizada ou falhou.")


def _agent_error(
    *,
    code: str,
    message: str,
    details: dict,
) -> AgentError:
    return {
        "code": code,
        "message": message,
        "source": "sql_execution",
        "stage": "execute_sql",
        "repairable": False,
        "details": details,
    }
