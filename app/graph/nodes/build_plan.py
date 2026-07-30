from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from app.domain.context import ContextSnapshot
from app.domain.planner import (
    PlanningInputError,
    build_query_plan,
)
from app.graph.state import AgentError, GraphState


def build_plan(
    state: GraphState,
) -> GraphState:
    """
    Constroi o plano deterministico a partir do contexto versionado.
    """

    intent_name = state.get("intent")
    context = state.get("context")
    normalized_question = (
        state.get("normalized_question")
        or state.get("question")
        or ""
    )

    if not isinstance(context, Mapping):
        return _contract_error_state(
            state,
            "Contexto canonico ausente para planejamento.",
            code="PLANNING_CONTEXT_INVALID",
        )

    try:
        result = build_query_plan(
            context=cast(ContextSnapshot, context),
            intent_name=intent_name,
            intent_confidence=state.get("intent_confidence"),
            normalized_question=normalized_question,
        )
    except PlanningInputError as error:
        return _contract_error_state(
            state,
            str(error),
            code="PLANNING_CONTEXT_INVALID",
        )
    except Exception as error:
        return _unexpected_error_state(state, error)

    if result["status"] == "planned":
        query_plan = result["query_plan"]
        if query_plan is None:
            return _contract_error_state(
                state,
                "Planner retornou status planned sem query_plan.",
                code="PLANNING_CONTEXT_INVALID",
            )

        return {
            "query_plan": query_plan,
            "current_stage": "build_plan",
            "final_status": "processing",
            "failure_stage": "",
        }

    error_code = result["error_code"] or "PLANNING_CONTEXT_INVALID"
    error_message = (
        result["error_message"]
        or "Nao foi possivel construir o plano de consulta."
    )

    return {
        "query_plan": {},
        "errors": [
            *state.get("errors", []),
            _planning_error(
                code=error_code,
                message=error_message,
                details={
                    "selection_result": result["selection_result"],
                    "planner_status": result["status"],
                },
            ),
        ],
        "current_stage": "build_plan",
        "final_status": (
            "infrastructure_error"
            if result["status"] == "contract_error"
            else "rejected"
        ),
        "failure_stage": "build_plan",
    }


def _planning_error(
    *,
    code: str,
    message: str,
    details: dict,
) -> AgentError:
    return {
        "code": code,
        "message": message,
        "source": "planner",
        "stage": "build_plan",
        "repairable": False,
        "details": details,
    }


def _contract_error_state(
    state: GraphState,
    message: str,
    *,
    code: str,
) -> GraphState:
    return {
        "errors": [
            *state.get("errors", []),
            _planning_error(
                code=code,
                message=message,
                details={},
            ),
        ],
        "current_stage": "build_plan",
        "final_status": "infrastructure_error",
        "failure_stage": "build_plan",
    }


def _unexpected_error_state(
    state: GraphState,
    error: Exception,
) -> GraphState:
    return {
        "errors": [
            *state.get("errors", []),
            _planning_error(
                code="PLANNING_UNEXPECTED_ERROR",
                message=(
                    "Ocorreu um erro inesperado durante o planejamento."
                ),
                details={
                    "exception_type": type(error).__name__,
                },
            ),
        ],
        "current_stage": "build_plan",
        "final_status": "infrastructure_error",
        "failure_stage": "build_plan",
    }
