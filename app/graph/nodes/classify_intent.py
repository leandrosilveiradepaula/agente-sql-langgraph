from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from app.domain.context import IntentResolutionContext
from app.domain.intent_resolver import (
    IntentCandidate,
    IntentResolutionResult,
    IntentResolverInputError,
    resolve_intent,
)
from app.graph.state import AgentError, GraphState


def classify_intent(
    state: GraphState,
) -> GraphState:
    """
    Classifica a intenção usando somente o contexto semântico versionado.

    O node não conhece intenções, aliases, scores ou termos de negócio.
    O motor determinístico recebe a pergunta normalizada e a projeção
    context.intent_resolution validada anteriormente por load_context.
    """

    question = (
        state.get("normalized_question")
        or state.get("question")
        or ""
    )
    context = state.get("context", {})
    intent_resolution = (
        context.get("intent_resolution")
        if isinstance(context, Mapping)
        else None
    )

    try:
        result = resolve_intent(
            question,
            cast(
                IntentResolutionContext,
                intent_resolution,
            ),
        )
    except IntentResolverInputError as error:
        return _contract_error_state(
            state,
            error,
        )
    except Exception as error:
        return _unexpected_error_state(
            state,
            error,
        )

    if result["applied"]:
        intent = result["intent"]
        confidence = result["intent_confidence"]

        if intent is None or confidence is None:
            return _invalid_result_state(
                state,
                result,
            )

        return {
            "intent": intent,
            "intent_confidence": confidence,
            "intent_resolution_result": result,
            "current_stage": "classify_intent",
            "final_status": "processing",
            "failure_stage": "",
        }

    rejection_error = _resolution_rejection_error(
        result,
    )

    return {
        "intent": None,
        "intent_confidence": None,
        "intent_resolution_result": result,
        "errors": [
            *state.get("errors", []),
            rejection_error,
        ],
        "current_stage": "classify_intent",
        "final_status": "rejected",
        "failure_stage": "classify_intent",
    }


def _resolution_rejection_error(
    result: IntentResolutionResult,
) -> AgentError:
    reason = result["reason"]

    if reason == "ambiguous_candidates":
        code = "INTENT_RESOLUTION_AMBIGUOUS"
        message = (
            "A pergunta correspondeu a mais de uma intenção "
            "sem margem suficiente para uma decisão segura."
        )
    else:
        code = (
            "INTENT_RESOLUTION_MINIMUM_SCORE_NOT_REACHED"
        )
        message = (
            "A pergunta não atingiu a pontuação mínima "
            "configurada para resolução de intenção."
        )

    configuration = result["resolver_configuration"]

    return {
        "code": code,
        "message": message,
        "source": "intent_resolver",
        "stage": "classify_intent",
        "repairable": False,
        "details": {
            "reason": reason,
            "minimum_score": configuration[
                "minimum_score"
            ],
            "ambiguity_margin": configuration[
                "ambiguity_margin"
            ],
            "best_candidate": _candidate_summary(
                result["best_candidate"]
            ),
            "second_candidate": _candidate_summary(
                result["second_candidate"]
            ),
            "resolver_version": result[
                "resolver_version"
            ],
        },
    }


def _candidate_summary(
    candidate: IntentCandidate | None,
) -> dict[str, Any] | None:
    if candidate is None:
        return None

    return {
        "intent_name": candidate["intent_name"],
        "score": candidate["score"],
        "positive_score": candidate[
            "positive_score"
        ],
        "negative_score": candidate[
            "negative_score"
        ],
        "best_priority": candidate[
            "best_priority"
        ],
    }


def _contract_error_state(
    state: GraphState,
    error: IntentResolverInputError,
) -> GraphState:
    agent_error: AgentError = {
        "code": "INTENT_RESOLUTION_CONTRACT_ERROR",
        "message": str(error),
        "source": "intent_resolver",
        "stage": "classify_intent",
        "repairable": False,
        "details": {},
    }

    return {
        "errors": [
            *state.get("errors", []),
            agent_error,
        ],
        "current_stage": "classify_intent",
        "final_status": "infrastructure_error",
        "failure_stage": "classify_intent",
    }


def _unexpected_error_state(
    state: GraphState,
    error: Exception,
) -> GraphState:
    agent_error: AgentError = {
        "code": "UNEXPECTED_INTENT_RESOLUTION_ERROR",
        "message": (
            "Ocorreu um erro inesperado durante "
            "a resolução de intenção."
        ),
        "source": "intent_resolver",
        "stage": "classify_intent",
        "repairable": False,
        "details": {
            "exception_type": type(error).__name__,
        },
    }

    return {
        "errors": [
            *state.get("errors", []),
            agent_error,
        ],
        "current_stage": "classify_intent",
        "final_status": "infrastructure_error",
        "failure_stage": "classify_intent",
    }


def _invalid_result_state(
    state: GraphState,
    result: IntentResolutionResult,
) -> GraphState:
    agent_error: AgentError = {
        "code": "INTENT_RESOLUTION_RESULT_INVALID",
        "message": (
            "O motor marcou a resolução como aplicada, "
            "mas não retornou intenção e confiança."
        ),
        "source": "intent_resolver",
        "stage": "classify_intent",
        "repairable": False,
        "details": {
            "resolver_version": result[
                "resolver_version"
            ],
        },
    }

    return {
        "intent": None,
        "intent_confidence": None,
        "intent_resolution_result": result,
        "errors": [
            *state.get("errors", []),
            agent_error,
        ],
        "current_stage": "classify_intent",
        "final_status": "infrastructure_error",
        "failure_stage": "classify_intent",
    }
