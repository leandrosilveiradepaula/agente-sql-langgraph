"""Opt-in semantic interpretation after a deterministic low-score rejection.

This node never bypasses an ambiguous or excluded catalog intent. A provider
can propose a concept, but the catalog and physical planning gates remain the
only authority. No SQL generation takes place in this node.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Callable, cast

from app.domain.intent_resolver import IntentResolutionResult
from app.domain.search_text import normalize_search_text
from app.domain.semantic_intent_fallback import (
    SemanticIntentRejected,
    prepare_interpretation,
    validate_interpretation,
    versioned_policy,
)
from app.graph.nodes.classify_intent import classify_intent
from app.graph.state import GraphState
from app.ports.semantic_intent_interpreter import SemanticIntentInterpreter


def create_semantic_classification_node(
    interpreter: SemanticIntentInterpreter | None,
) -> Callable[[GraphState], GraphState]:
    def classify(state: GraphState) -> GraphState:
        original = classify_intent(state)
        if original.get("final_status") != "rejected":
            return original
        result = original.get("intent_resolution_result")
        if not isinstance(result, Mapping) or result.get("reason") != "minimum_score_not_reached":
            # Never let the model break the deterministic ambiguity guard.
            return original
        context = state.get("context")
        if not isinstance(context, Mapping):
            return original
        try:
            policy = versioned_policy(context)
            if policy is None:
                return original
            if interpreter is None:
                raise RuntimeError("semantic_interpreter_unavailable")
            request = prepare_interpretation(str(state.get("question") or ""), context)
            response = interpreter.interpret(request)
            if not isinstance(response, Mapping):
                raise RuntimeError("semantic_provider_result_invalid")
            raw_text = response.get("output_text")
            if not isinstance(raw_text, str):
                raise RuntimeError("semantic_provider_text_invalid")
            validated = validate_interpretation(raw_text, request, result)
        except (SemanticIntentRejected, RuntimeError, ValueError, TypeError) as exc:
            return _safe_rejection(original, type(exc).__name__)
        except Exception:
            return _safe_rejection(original, "unexpected_provider_error")

        chosen = validated["intent_name"]
        evidence = deepcopy(dict(result))
        concepts = []
        for binding in validated["bindings"]:
            span = binding["question_span"]
            concept = binding["concept_name"]
            concepts.append({
                "concept_name": concept,
                "satisfied": True,
                "semantic_signals": [{
                    "concept_name": concept,
                    "term": span,
                    "normalized_term": normalize_search_text(span),
                    "source": "grounded_semantic_interpretation",
                    "confidence": 1.0,
                    "matched_tokens": normalize_search_text(span).split(),
                }],
            })
        best_candidate = {
            "intent_name": chosen,
            "matches": [{"match_details": {"concepts": concepts}}],
        }
        evidence.update({
            "applied": True,
            "reason": "semantic_interpretation_selected",
            "intent": chosen,
            "intent_confidence": float(policy["applied_confidence"]),
            "best_candidate": best_candidate,
            "candidates": [best_candidate],
            "second_candidate": None,
        })
        return {
            "intent": chosen,
            "intent_confidence": float(policy["applied_confidence"]),
            "intent_resolution_result": cast(IntentResolutionResult, evidence),
            "semantic_interpretation_result": {
                "status": "selected",
                "source": "provider_interpretation",
                "context_fingerprint": validated["context_fingerprint"],
                "binding_count": len(validated["bindings"]),
                "provider_name": str(response.get("provider_name", ""))[:128],
                "provider_model": str(response.get("provider_model", ""))[:128],
                "token_usage": deepcopy(response.get("token_usage") or {}),
                "no_sql_executed": True,
            },
            "current_stage": "classify_intent",
            "final_status": "processing",
            "failure_stage": "",
        }

    return classify


def _safe_rejection(original: GraphState, reason: str) -> GraphState:
    return {
        **original,
        "semantic_interpretation_result": {
            "status": "not_applied",
            "reason": reason,
            "no_sql_executed": True,
        },
    }
