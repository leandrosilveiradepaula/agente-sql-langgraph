from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any
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
            intent_resolution_result=_planner_intent_evidence(
                state.get("intent_resolution_result")
            ),
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


def _planner_intent_evidence(
    intent_resolution_result: Any,
) -> dict[str, Any] | None:
    if not isinstance(intent_resolution_result, Mapping):
        return None

    projected: dict[str, Any] = {
        "intent": intent_resolution_result.get("intent"),
    }
    best_candidate = _project_dimension_grouping_candidate(
        intent_resolution_result.get("best_candidate")
    )
    if best_candidate is not None:
        projected["best_candidate"] = best_candidate

    candidates = intent_resolution_result.get("candidates")
    if isinstance(candidates, list):
        projected_candidates = [
            candidate
            for candidate in (
                _project_dimension_grouping_candidate(candidate)
                for candidate in candidates
            )
            if candidate is not None
        ]
        if projected_candidates:
            projected["candidates"] = projected_candidates

    if "best_candidate" not in projected and "candidates" not in projected:
        return None
    return projected


def _project_dimension_grouping_candidate(
    candidate: Any,
) -> dict[str, Any] | None:
    if not isinstance(candidate, Mapping):
        return None

    matches = candidate.get("matches")
    if not isinstance(matches, list):
        return None

    projected_matches: list[dict[str, Any]] = []
    for match in matches:
        if not isinstance(match, Mapping):
            continue
        details = match.get("match_details")
        if not isinstance(details, Mapping):
            continue
        concepts = details.get("concepts")
        if not isinstance(concepts, list):
            continue
        planner_concepts = [
            projected
            for projected in (
                _project_planner_concept(concept)
                for concept in concepts
            )
            if projected is not None
        ]
        if planner_concepts:
            projected_matches.append(
                {"match_details": {"concepts": planner_concepts}}
            )

    if not projected_matches:
        return None
    return {
        "intent_name": candidate.get("intent_name"),
        "matches": projected_matches,
    }


def _project_planner_concept(concept: Any) -> dict[str, Any] | None:
    if not isinstance(concept, Mapping):
        return None
    concept_name = str(concept.get("concept_name", "")).strip()
    if not concept_name:
        return None
    projected: dict[str, Any] = {
        "concept_name": concept_name,
        "satisfied": concept.get("satisfied") is True,
    }
    semantic_signals = _project_semantic_signals(concept)
    if semantic_signals:
        projected["semantic_signals"] = semantic_signals
        projected["terms"] = [
            {
                "matched": True,
                "normalized_term": str(
                    signal.get("normalized_term")
                    or signal.get("term")
                    or ""
                ),
                "match_details": {
                    "semantic_signal": deepcopy(signal),
                },
            }
            for signal in semantic_signals
            if (
                isinstance(
                    signal.get("normalized_term")
                    or signal.get("term"),
                    str,
                )
                and str(
                    signal.get("normalized_term")
                    or signal.get("term")
                ).strip()
            )
        ]
    return projected


def _project_semantic_signals(
    concept: Mapping[str, Any],
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for signal in concept.get("semantic_signals", []):
        projected = _project_semantic_signal(signal)
        if projected is not None:
            signals.append(projected)
    for term in concept.get("terms", []):
        if not isinstance(term, Mapping):
            continue
        details = term.get("match_details")
        if not isinstance(details, Mapping):
            continue
        for signal in details.get("semantic_signals", []):
            projected = _project_semantic_signal(signal)
            if projected is not None:
                signals.append(projected)
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, tuple[str, ...]]] = set()
    for signal in signals:
        key = (
            str(signal.get("concept_name", "")).casefold(),
            str(signal.get("source", "")).casefold(),
            str(
                signal.get("normalized_term")
                or signal.get("term")
                or ""
            ).casefold(),
            tuple(
                str(token).casefold()
                for token in signal.get("matched_tokens", [])
                if isinstance(token, str)
            ),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(signal)
    return output


def _project_semantic_signal(signal: Any) -> dict[str, Any] | None:
    if not isinstance(signal, Mapping):
        return None
    concept_name = str(signal.get("concept_name", "")).strip()
    source = str(signal.get("source", "")).strip()
    if not concept_name or not source:
        return None

    projected: dict[str, Any] = {
        "concept_name": concept_name,
        "source": source,
    }
    term = signal.get("term")
    normalized_term = signal.get("normalized_term")
    matched_tokens = signal.get("matched_tokens")

    if isinstance(term, str) and term.strip():
        projected["term"] = term.strip()
    if isinstance(normalized_term, str) and normalized_term.strip():
        projected["normalized_term"] = normalized_term.strip()
    if isinstance(matched_tokens, list):
        projected["matched_tokens"] = [
            str(token).strip()
            for token in matched_tokens
            if isinstance(token, str) and token.strip()
        ]

    return projected
