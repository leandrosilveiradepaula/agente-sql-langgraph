from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.domain.search_text import normalize_search_text
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
        "normalized_pattern": normalize_search_text(pattern),
        "match_mode": "contains",
        "polarity": "positive",
        "score": score,
        "priority": priority,
        "entity_type": "intent_signal",
        "target_table": None,
        "target_column": None,
    }


def _catalog_entry(
    *,
    intent_name: str,
    effect: str,
    term: str,
    score: float | None,
    priority: float = 1,
) -> dict[str, Any]:
    return {
        "intent_name": intent_name,
        "definition_name": (
            f"{intent_name}_definition"
        ),
        "semantic_description": (
            "Definição semântica genérica usada somente no teste."
        ),
        "rules": [
            {
                "rule_name": (
                    f"{effect}_generic_rule"
                ),
                "effect": effect,
                "concepts": [
                    {
                        "concept_name": "generic_concept",
                        "terms": [term],
                        "normalized_terms": [
                            normalize_search_text(term),
                        ],
                        "match_mode": "contains",
                        "minimum_term_matches": 1,
                    }
                ],
                "minimum_concept_matches": 1,
                "score": score,
                "priority": priority,
            }
        ],
        "priority": priority,
    }


def _state(
    *,
    question: str,
    config: dict[str, Any],
    signals: list[dict[str, Any]],
    intent_catalog: list[dict[str, Any]] | None = None,
) -> GraphState:
    intent_resolution: dict[str, Any] = {
        "config": config,
        "signals": signals,
    }
    if intent_catalog is not None:
        intent_resolution["intent_catalog"] = (
            intent_catalog
        )

    return {
        "question": question,
        "normalized_question": question,
        "context": {
            "intent_resolution": intent_resolution,
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
    resolution = result["intent_resolution_result"]
    assert resolution["applied"] is True
    assert resolution["reason"] == (
        "configured_intent_selected"
    )
    assert resolution["intent_catalog"]["available"] is False
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


def test_aplica_intencao_somente_pelo_catalogo() -> None:
    state = _state(
        question="Prepare alpha report",
        config=_config(
            applied_confidence=0.95,
        ),
        signals=[],
        intent_catalog=[
            _catalog_entry(
                intent_name="intent_alpha",
                effect="positive_score",
                term="alpha report",
                score=120,
            )
        ],
    )
    original = deepcopy(state)

    result = classify_intent(state)

    assert result["intent"] == "intent_alpha"
    assert result["intent_confidence"] == 0.95
    assert result["final_status"] == "processing"
    resolution = result["intent_resolution_result"]
    assert resolution["applied"] is True
    assert resolution["best_candidate"] is not None
    assert resolution["best_candidate"]["matches"][0][
        "match_strategy"
    ] == "intent_catalog_rule"

    diagnostic = resolution["intent_catalog"]
    assert diagnostic["available"] is True
    assert diagnostic["entries_evaluated"] == 1
    assert diagnostic["used_for_selected_intent"] is True
    assert diagnostic[
        "contributed_score_to_selected_intent"
    ] is True
    assert diagnostic["evaluations"][0]["eligible"] is True
    assert diagnostic["evaluations"][0]["score_delta"] == 120
    assert state == original


def test_require_nao_satisfeita_bloqueia_candidato() -> None:
    state = _state(
        question="Prepare alpha report",
        config=_config(),
        signals=[
            _signal(
                intent_name="intent_alpha",
                pattern="alpha report",
                score=120,
            )
        ],
        intent_catalog=[
            _catalog_entry(
                intent_name="intent_alpha",
                effect="require",
                term="beta condition",
                score=None,
            )
        ],
    )

    result = classify_intent(state)

    assert result["intent"] is None
    assert result["final_status"] == "rejected"
    resolution = result["intent_resolution_result"]
    assert resolution["best_candidate"] is None
    assert resolution["candidates"] == []
    evaluation = resolution["intent_catalog"][
        "evaluations"
    ][0]
    assert evaluation["eligible"] is False
    assert evaluation["excluded"] is False
    assert evaluation["require_rule_count"] == 1
    assert evaluation["satisfied_require_rule_count"] == 0


def test_exclude_satisfeita_bloqueia_candidato() -> None:
    state = _state(
        question="Prepare alpha report",
        config=_config(),
        signals=[
            _signal(
                intent_name="intent_alpha",
                pattern="alpha report",
                score=120,
            )
        ],
        intent_catalog=[
            _catalog_entry(
                intent_name="intent_alpha",
                effect="exclude",
                term="alpha report",
                score=None,
            )
        ],
    )

    result = classify_intent(state)

    assert result["intent"] is None
    assert result["final_status"] == "rejected"
    resolution = result["intent_resolution_result"]
    assert resolution["best_candidate"] is None
    evaluation = resolution["intent_catalog"][
        "evaluations"
    ][0]
    assert evaluation["eligible"] is False
    assert evaluation["excluded"] is True


def test_converte_catalogo_invalido_em_erro_de_contrato() -> None:
    state = _state(
        question="Prepare alpha report",
        config=_config(),
        signals=[],
    )
    state["context"]["intent_resolution"][
        "intent_catalog"
    ] = {}

    result = classify_intent(state)

    assert result["final_status"] == (
        "infrastructure_error"
    )
    assert result["failure_stage"] == "classify_intent"
    assert (
        "INTENT_RESOLUTION_CONTRACT_ERROR"
        in _error_codes(result)
    )


def test_converte_contexto_ausente_em_erro_de_contrato() -> None:
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
            "aplica intenção somente pelo catálogo",
            test_aplica_intencao_somente_pelo_catalogo,
        ),
        (
            "require não satisfeita bloqueia candidato",
            test_require_nao_satisfeita_bloqueia_candidato,
        ),
        (
            "exclude satisfeita bloqueia candidato",
            test_exclude_satisfeita_bloqueia_candidato,
        ),
        (
            "converte catálogo inválido em erro de contrato",
            test_converte_catalogo_invalido_em_erro_de_contrato,
        ),
        (
            "converte contexto ausente em erro de contrato",
            test_converte_contexto_ausente_em_erro_de_contrato,
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
