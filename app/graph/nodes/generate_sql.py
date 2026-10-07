from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Callable, cast

from app.domain.planning import QueryPlan
from app.domain.sql_generation import (
    SqlGenerationInputError,
    SqlGenerationProviderError,
    SqlGenerationProviderResult,
    SqlGenerationValidationError,
    build_sql_generation_request,
    create_error_result,
    create_success_result,
    validate_sql_generation_response,
)
from app.graph.state import AgentError, GraphState
from app.ports.sql_generator import SqlGenerator


def create_generate_sql_node(
    sql_generator: SqlGenerator,
) -> Callable[[GraphState], GraphState]:
    """
    Cria o node generate_sql com o gerador injetado.
    """

    def generate_sql(state: GraphState) -> GraphState:
        query_plan = state.get("query_plan")
        attempt = 1

        if not isinstance(query_plan, Mapping) or not query_plan:
            result = create_error_result(
                status="contract_error",
                code="SQL_GENERATION_PLAN_MISSING",
                message="query_plan esta ausente para geracao SQL.",
                request=None,
                provider_result=None,
                reason="query_plan_missing",
                attempt=attempt,
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
            )

        try:
            request = build_sql_generation_request(
                cast(QueryPlan, query_plan)
            )
        except SqlGenerationInputError as error:
            result = create_error_result(
                status="contract_error",
                code="SQL_GENERATION_PLAN_INVALID",
                message=str(error),
                request=None,
                provider_result=None,
                reason="query_plan_invalid",
                attempt=attempt,
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
            )
        except Exception as error:
            return _unexpected_error_state(state, error)

        try:
            provider_result = sql_generator.generate(
                deepcopy(request)
            )
        except SqlGenerationProviderError as error:
            result = create_error_result(
                status="provider_error",
                code="SQL_GENERATION_PROVIDER_FAILED",
                message="O provedor de geracao SQL falhou.",
                request=request,
                provider_result=None,
                reason="provider_failed",
                attempt=attempt,
                details={
                    "exception_type": type(error).__name__,
                    "provider_reason": error.reason,
                },
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
            )
        except Exception as error:
            result = create_error_result(
                status="provider_error",
                code="SQL_GENERATION_PROVIDER_FAILED",
                message="O provedor de geracao SQL falhou.",
                request=request,
                provider_result=None,
                reason="provider_exception",
                attempt=attempt,
                details={
                    "exception_type": type(error).__name__,
                },
            )
            return _error_state(
                state,
                result,
                final_status="infrastructure_error",
            )

        try:
            sql = validate_sql_generation_response(
                cast(
                    SqlGenerationProviderResult,
                    provider_result,
                )
            )
        except SqlGenerationValidationError as error:
            result = create_error_result(
                status="rejected",
                code=error.code,
                message=error.message,
                request=request,
                provider_result=cast(
                    SqlGenerationProviderResult,
                    provider_result
                    if isinstance(provider_result, Mapping)
                    else {},
                ),
                reason=error.reason,
                attempt=attempt,
            )
            return _error_state(
                state,
                result,
                final_status="rejected",
            )
        except Exception as error:
            return _unexpected_error_state(state, error)

        result = create_success_result(
            sql=sql,
            request=request,
            provider_result=cast(
                SqlGenerationProviderResult,
                provider_result,
            ),
            attempt=attempt,
        )

        return {
            "generated_sql": sql,
            "current_sql": sql,
            "sql_generation_result": result,
            "current_stage": "generate_sql",
            "final_status": "processing",
            "failure_stage": "",
        }

    return generate_sql


def _error_state(
    state: GraphState,
    result: dict,
    *,
    final_status: str,
) -> GraphState:
    error = result.get("error") or {}
    agent_error: AgentError = {
        "code": str(error.get("code", "")),
        "message": str(error.get("message", "")),
        "source": "sql_generator",
        "stage": "generate_sql",
        "repairable": False,
        "details": {
            "diagnostic": result.get("diagnostic", {}),
            **(
                error.get("details", {})
                if isinstance(error.get("details"), Mapping)
                else {}
            ),
        },
    }

    return {
        "sql_generation_result": result,
        "errors": [
            *state.get("errors", []),
            agent_error,
        ],
        "current_stage": "generate_sql",
        "final_status": final_status,
        "failure_stage": "generate_sql",
    }


def _unexpected_error_state(
    state: GraphState,
    error: Exception,
) -> GraphState:
    result = create_error_result(
        status="provider_error",
        code="SQL_GENERATION_UNEXPECTED_ERROR",
        message=(
            "Ocorreu um erro inesperado durante a geracao SQL."
        ),
        request=None,
        provider_result=None,
        reason="unexpected_error",
        attempt=1,
        details={
            "exception_type": type(error).__name__,
        },
    )
    return _error_state(
        state,
        result,
        final_status="infrastructure_error",
    )
