from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import cast

from app.domain.engine_preflight import (
    EnginePreflightInputError,
    EnginePreflightProviderError,
    EnginePreflightProviderResult,
    EnginePreflightResult,
    build_engine_preflight_request,
    create_engine_preflight_provider_error_result,
    normalize_engine_preflight_result,
)
from app.domain.planning import QueryPlan
from app.domain.sql_contract import SqlContractResult
from app.domain.sql_security import SqlSecurityResult
from app.graph.state import AgentError, GraphState
from app.ports.engine_preflight import EnginePreflight


def create_engine_preflight_node(
    engine_preflight: EnginePreflight,
) -> Callable[[GraphState], GraphState]:
    """
    Cria o node engine_preflight com porta injetada.
    """

    def engine_preflight_node(state: GraphState) -> GraphState:
        current_sql = state.get("current_sql")
        query_plan = state.get("query_plan")
        security_result = state.get("security_result")
        contract_result = state.get("contract_result")
        attempt = 1

        try:
            request = build_engine_preflight_request(
                current_sql=(
                    current_sql if isinstance(current_sql, str) else ""
                ),
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
                options={
                    "attempt": attempt,
                    "engine_preflight_timeout_ms": (
                        state.get("options", {}).get(
                            "engine_preflight_timeout_ms"
                        )
                        if isinstance(state.get("options"), Mapping)
                        else None
                    ),
                },
            )
        except EnginePreflightInputError as error:
            result = create_engine_preflight_provider_error_result(
                request=None,
                code=error.code,
                category="adapter_error",
                message=error.message,
                attempt=attempt,
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
            )
        except Exception as error:
            result = create_engine_preflight_provider_error_result(
                request=None,
                code="ENGINE_PREFLIGHT_UNEXPECTED_ERROR",
                category="adapter_error",
                message="Erro inesperado ao construir preflight.",
                attempt=attempt,
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
                details={
                    "exception_type": type(error).__name__,
                },
            )

        try:
            provider_result = engine_preflight.preflight(
                deepcopy(request)
            )
        except EnginePreflightProviderError as error:
            result = create_engine_preflight_provider_error_result(
                request=request,
                code="ENGINE_PREFLIGHT_PROVIDER_FAILED",
                category="adapter_error",
                message="Provider de preflight falhou.",
                attempt=attempt,
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
                details={
                    "exception_type": type(error).__name__,
                },
            )
        except TimeoutError:
            result = create_engine_preflight_provider_error_result(
                request=request,
                code="ENGINE_PREFLIGHT_TIMEOUT",
                category="timeout",
                message="Provider de preflight excedeu o timeout.",
                attempt=attempt,
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
            )
        except Exception as error:
            result = create_engine_preflight_provider_error_result(
                request=request,
                code="ENGINE_PREFLIGHT_UNEXPECTED_ERROR",
                category="adapter_error",
                message="Erro inesperado no provider de preflight.",
                attempt=attempt,
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
                details={
                    "exception_type": type(error).__name__,
                },
            )

        result = normalize_engine_preflight_result(
            request=request,
            provider_result=cast(
                EnginePreflightProviderResult,
                provider_result,
            ),
        )

        if result["status"] == "approved":
            return {
                "engine_preflight_result": result,
                "current_stage": "engine_preflight",
                "final_status": "processing",
                "failure_stage": "",
            }

        return _error_state(
            state,
            result,
            final_status=(
                "infrastructure_error"
                if result["status"] == "error"
                else "rejected"
            ),
        )

    return engine_preflight_node


def _error_state(
    state: GraphState,
    result: EnginePreflightResult,
    *,
    final_status: str,
    details: dict | None = None,
) -> GraphState:
    error = _primary_error(result)
    return {
        "engine_preflight_result": result,
        "errors": [
            *state.get("errors", []),
            _agent_error(
                code=error["code"],
                message=error["message"],
                repairable=bool(error.get("repairable", False)),
                details={
                    "category": error.get("category"),
                    "provider_code": error.get("provider_code"),
                    "sqlstate": error.get("sqlstate"),
                    "line": error.get("line"),
                    "column": error.get("column"),
                    "position": error.get("position"),
                    "related_object": error.get("related_object"),
                    "sanitized_hint": error.get("sanitized_hint"),
                    "repairable": error.get("repairable", False),
                    "attempt": result["attempt"],
                    "diagnostic": result["diagnostic"],
                    **(details or {}),
                },
            ),
        ],
        "current_stage": "engine_preflight",
        "final_status": final_status,
        "failure_stage": "engine_preflight",
    }


def _primary_error(result: EnginePreflightResult) -> dict:
    if result["errors"]:
        return result["errors"][0]
    if result["findings"]:
        return result["findings"][0]
    return {
        "code": "ENGINE_PREFLIGHT_RESPONSE_INVALID",
        "message": "Engine Preflight falhou sem detalhe estruturado.",
        "category": "adapter_error",
        "repairable": False,
    }


def _agent_error(
    *,
    code: str,
    message: str,
    repairable: bool,
    details: dict,
) -> AgentError:
    return {
        "code": code,
        "message": message,
        "source": "engine_preflight",
        "stage": "engine_preflight",
        "repairable": repairable,
        "details": details,
    }
