from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.graph.nodes.classify_intent import (
    classify_intent,
)
from app.graph.state import GraphState


def _config(
    *,
    minimum_score: float = 100,
    ambiguity_margin: float = 20,
    applied_confidence: float = 0.97,
) -> dict[str, Any]:
    return {
        "component": "intent_resolver",
        "minimum_score": minimum_score,
        "ambiguity_margin": ambiguity_margin,
        "applied_confidence": applied_confidence,
        "fallback_to_previous_intent": True,
        "token_fallback": {
            "enabled": False,
        },
    }


def _signal(
    *,
    intent_name: str,
    pattern: str,
    score: float,
    priority: float = 1,
) -> dict[str, Any]:
    return {
        "intent_name": intent_name,
        "raw_pattern": pattern,
        "normalized_pattern": pattern,
        "match_mode": "contains",
        "polarity": "positive",
        "score": score,
        "priority": priority,
        "entity_type": "intent_signal",
        "target_table": None,
        "target_column": None,
    }


def _state(
    *,
    question: str,
    config: dict[str, Any],
    signals: list[dict[str, Any]],
) -> GraphState:
    return {
        "question": question,
        "normalized_question": question,
        "context": {
            "intent_resolution": {
                "config": config,
                "signals": signals,
            }
        },
        "errors": [],
        "warnings": [],
        "final_status": "processing",
        "failure_stage": "",
    }


def _error_codes(result: GraphState) -> set[str]:
    return {
        error["code"]
        for error in result.get("errors", [])
    }


def test_aplica_intencao_e_diagnostico() -> None:
    state = _state(
        question="Prepare alpha report",
        config=_config(
            applied_confidence=0.96,
        ),
        signals=[
            _signal(
                intent_name="intent_alpha",
                pattern="alpha report",
                score=120,
            )
        ],
    )
    original = deepcopy(state)

    result = classify_intent(state)

    assert result["intent"] == "intent_alpha"
    assert result["intent_confidence"] == 0.96
    assert result["current_stage"] == "classify_intent"
    assert result["final_status"] == "processing"
    assert result["failure_stage"] == ""
    assert result["intent_resolution_result"][
        "applied"
    ] is True
    assert result["intent_resolution_result"][
        "reason"
    ] == "configured_intent_selected"
    assert state == original


def test_rejeita_pontuacao_insuficiente() -> None:
    state = _state(
        question="Prepare alpha report",
        config=_config(),
        signals=[
            _signal(
                intent_name="intent_alpha",
                pattern="alpha report",
                score=80,
            )
        ],
    )

    result = classify_intent(state)

    assert result["intent"] is None
    assert result["intent_confidence"] is None
    assert result["final_status"] == "rejected"
    assert result["failure_stage"] == "classify_intent"
    assert (
        "INTENT_RESOLUTION_MINIMUM_SCORE_NOT_REACHED"
        in _error_codes(result)
    )
    assert result["intent_resolution_result"][
        "reason"
    ] == "minimum_score_not_reached"


def test_rejeita_ambiguidade() -> None:
    state = _state(
        question="Prepare alpha report",
        config=_config(
            ambiguity_margin=20,
        ),
        signals=[
            _signal(
                intent_name="intent_alpha",
                pattern="alpha",
                score=120,
                priority=1,
            ),
            _signal(
                intent_name="intent_beta",
                pattern="report",
                score=120,
                priority=2,
            ),
        ],
    )

    result = classify_intent(state)

    assert result["intent"] is None
    assert result["intent_confidence"] is None
    assert result["final_status"] == "rejected"
    assert (
        "INTENT_RESOLUTION_AMBIGUOUS"
        in _error_codes(result)
    )
    assert result["intent_resolution_result"][
        "reason"
    ] == "ambiguous_candidates"


def test_converte_violacao_de_contrato() -> None:
    state: GraphState = {
        "question": "Prepare alpha report",
        "normalized_question": "Prepare alpha report",
        "context": {},
        "errors": [],
        "warnings": [],
        "final_status": "processing",
        "failure_stage": "",
    }

    result = classify_intent(state)

    assert result["final_status"] == (
        "infrastructure_error"
    )
    assert result["failure_stage"] == "classify_intent"
    assert (
        "INTENT_RESOLUTION_CONTRACT_ERROR"
        in _error_codes(result)
    )


def main() -> None:
    tests = [
        (
            "aplica intenção e diagnóstico",
            test_aplica_intencao_e_diagnostico,
        ),
        (
            "rejeita pontuação insuficiente",
            test_rejeita_pontuacao_insuficiente,
        ),
        (
            "rejeita ambiguidade",
            test_rejeita_ambiguidade,
        ),
        (
            "converte violação de contrato",
            test_converte_violacao_de_contrato,
        ),
    ]

    for index, (name, test_function) in enumerate(
        tests,
        start=1,
    ):
        test_function()
        print(f"TESTE {index} — {name}: OK")


if __name__ == "__main__":
    main()
