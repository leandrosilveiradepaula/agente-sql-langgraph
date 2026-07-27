from __future__ import annotations

from copy import deepcopy

from app.domain.intent_resolver import (
    RESOLVER_VERSION,
    IntentResolverInputError,
    resolve_intent,
)


def _config(
    *,
    minimum_score: float = 100,
    ambiguity_margin: float = 20,
    applied_confidence: float = 0.98,
    token_fallback: dict | None = None,
) -> dict:
    return {
        "component": "intent_resolver",
        "minimum_score": minimum_score,
        "ambiguity_margin": ambiguity_margin,
        "applied_confidence": applied_confidence,
        "fallback_to_previous_intent": True,
        "token_fallback": (
            {"enabled": False}
            if token_fallback is None
            else token_fallback
        ),
    }


def _signal(
    *,
    intent_name: str,
    pattern: str,
    match_mode: str = "contains",
    polarity: str = "positive",
    score: float = 120,
    priority: float | None = 1,
) -> dict:
    return {
        "intent_name": intent_name,
        "raw_pattern": pattern,
        "normalized_pattern": pattern,
        "match_mode": match_mode,
        "polarity": polarity,
        "score": score,
        "priority": priority,
        "entity_type": "intent_signal",
        "target_table": None,
        "target_column": None,
    }


def _context(
    signals: list[dict],
    *,
    config: dict | None = None,
) -> dict:
    return {
        "config": config or _config(),
        "signals": signals,
    }


def test_aplica_todos_os_modos_diretos() -> None:
    cases = [
        ("exact", "alpha beta", "alpha beta"),
        ("contains", "prefix alpha beta suffix", "alpha beta"),
        ("starts_with", "alpha beta suffix", "alpha beta"),
        ("ends_with", "prefix alpha beta", "alpha beta"),
        ("all_tokens", "beta gamma alpha", "alpha beta"),
        ("any_token", "gamma alpha", "alpha beta"),
        ("regex", "alpha beta", r"^alpha\s+beta$"),
    ]

    for match_mode, question, pattern in cases:
        result = resolve_intent(
            question,
            _context(
                [
                    _signal(
                        intent_name="generic_intent",
                        pattern=pattern,
                        match_mode=match_mode,
                    )
                ]
            ),
        )

        assert result["applied"] is True
        assert result["intent"] == "generic_intent"
        assert result["reason"] == "configured_intent_selected"
        assert result["resolver_version"] == RESOLVER_VERSION


def test_normaliza_pergunta_sem_termos_de_negocio() -> None:
    result = resolve_intent(
        "  ÁLPHA,   Bêta!  ",
        _context(
            [
                _signal(
                    intent_name="generic_intent",
                    pattern="alpha beta",
                )
            ]
        ),
    )

    assert result["applied"] is True
    assert result["normalized_question"] == "alpha beta"


def test_regex_invalida_nao_interrompe_motor() -> None:
    result = resolve_intent(
        "alpha beta",
        _context(
            [
                _signal(
                    intent_name="generic_intent",
                    pattern="(",
                    match_mode="regex",
                )
            ]
        ),
    )

    assert result["applied"] is False
    assert result["reason"] == "minimum_score_not_reached"
    assert result["candidates"] == []


def test_agrega_sinais_positivos_e_negativos() -> None:
    result = resolve_intent(
        "alpha beta blocked",
        _context(
            [
                _signal(
                    intent_name="intent_a",
                    pattern="alpha",
                    score=140,
                ),
                _signal(
                    intent_name="intent_a",
                    pattern="blocked",
                    polarity="negative",
                    score=30,
                    priority=2,
                ),
                _signal(
                    intent_name="intent_b",
                    pattern="beta",
                    score=80,
                ),
            ],
            config=_config(
                minimum_score=100,
                ambiguity_margin=20,
            ),
        ),
    )

    assert result["applied"] is True
    assert result["intent"] == "intent_a"
    assert result["best_candidate"] == result["candidates"][0]
    assert result["best_candidate"]["score"] == 110
    assert result["best_candidate"]["positive_score"] == 140
    assert result["best_candidate"]["negative_score"] == 30


def test_rejeita_pontuacao_abaixo_do_minimo_sem_fallback_legado() -> None:
    result = resolve_intent(
        "alpha",
        _context(
            [
                _signal(
                    intent_name="generic_intent",
                    pattern="alpha",
                    score=99,
                )
            ],
            config=_config(minimum_score=100),
        ),
    )

    assert result["applied"] is False
    assert result["intent"] is None
    assert result["intent_confidence"] is None
    assert result["reason"] == "minimum_score_not_reached"
    assert (
        result["resolver_configuration"]
        ["fallback_to_previous_intent"]
        is True
    )


def test_rejeita_candidatos_ambiguos() -> None:
    result = resolve_intent(
        "alpha beta",
        _context(
            [
                _signal(
                    intent_name="intent_a",
                    pattern="alpha",
                    score=120,
                ),
                _signal(
                    intent_name="intent_b",
                    pattern="beta",
                    score=110,
                ),
            ],
            config=_config(
                minimum_score=100,
                ambiguity_margin=20,
            ),
        ),
    )

    assert result["applied"] is False
    assert result["intent"] is None
    assert result["reason"] == "ambiguous_candidates"
    assert result["best_candidate"]["intent_name"] == "intent_a"
    assert result["second_candidate"]["intent_name"] == "intent_b"


def test_usa_prioridade_para_desempatar_pontuacao() -> None:
    result = resolve_intent(
        "alpha beta",
        _context(
            [
                _signal(
                    intent_name="intent_a",
                    pattern="alpha",
                    score=120,
                    priority=2,
                ),
                _signal(
                    intent_name="intent_b",
                    pattern="beta",
                    score=120,
                    priority=1,
                ),
            ],
            config=_config(
                minimum_score=100,
                ambiguity_margin=0,
            ),
        ),
    )

    assert result["applied"] is True
    assert result["intent"] == "intent_b"
    assert result["best_candidate"]["best_priority"] == 1


def test_aplica_fallback_por_cobertura_de_tokens() -> None:
    token_fallback = {
        "enabled": True,
        "apply_to_polarities": ["positive"],
        "apply_to_match_modes": ["contains"],
        "ignored_tokens": ["middle"],
        "minimum_pattern_tokens": 2,
        "minimum_matched_tokens": 2,
        "minimum_pattern_coverage": 1.0,
        "maximum_unmatched_pattern_tokens": 0,
        "allow_prefix_equivalence": False,
        "minimum_prefix_length": 6,
        "minimum_prefix_ratio": 0.85,
    }

    result = resolve_intent(
        "alpha middle beta",
        _context(
            [
                _signal(
                    intent_name="generic_intent",
                    pattern="alpha beta",
                    match_mode="contains",
                )
            ],
            config=_config(token_fallback=token_fallback),
        ),
    )

    assert result["applied"] is True
    assert result["intent"] == "generic_intent"
    assert result["token_fallback"]["requested"] is True
    assert result["token_fallback"]["enabled"] is True
    assert (
        result["token_fallback"]["used_for_selected_intent"]
        is True
    )
    assert (
        result["best_candidate"]["matches"][0]
        ["match_strategy"]
        == "token_coverage_fallback"
    )


def test_aplica_equivalencia_configurada_por_prefixo() -> None:
    token_fallback = {
        "enabled": True,
        "apply_to_polarities": ["positive"],
        "apply_to_match_modes": ["contains"],
        "ignored_tokens": [],
        "minimum_pattern_tokens": 2,
        "minimum_matched_tokens": 2,
        "minimum_pattern_coverage": 1.0,
        "maximum_unmatched_pattern_tokens": 0,
        "allow_prefix_equivalence": True,
        "minimum_prefix_length": 6,
        "minimum_prefix_ratio": 0.70,
    }

    result = resolve_intent(
        "analyses generic",
        _context(
            [
                _signal(
                    intent_name="generic_intent",
                    pattern="analysis generic",
                    match_mode="contains",
                )
            ],
            config=_config(token_fallback=token_fallback),
        ),
    )

    assert result["applied"] is True
    token_matches = (
        result["best_candidate"]["matches"][0]
        ["match_details"]["token_matches"]
    )
    assert token_matches[0]["method"] == "prefix_equivalence"


def test_respeita_escopo_configurado_do_token_fallback() -> None:
    token_fallback = {
        "enabled": True,
        "apply_to_polarities": ["positive"],
        "apply_to_match_modes": ["contains"],
        "ignored_tokens": ["middle"],
        "minimum_pattern_tokens": 2,
        "minimum_matched_tokens": 2,
        "minimum_pattern_coverage": 1.0,
        "maximum_unmatched_pattern_tokens": 0,
        "allow_prefix_equivalence": False,
        "minimum_prefix_length": 6,
        "minimum_prefix_ratio": 0.85,
    }

    result = resolve_intent(
        "alpha middle beta",
        _context(
            [
                _signal(
                    intent_name="generic_intent",
                    pattern="alpha beta",
                    match_mode="exact",
                )
            ],
            config=_config(token_fallback=token_fallback),
        ),
    )

    assert result["applied"] is False
    assert result["candidates"] == []
    assert (
        result["token_fallback"]["used_for_selected_intent"]
        is False
    )


def test_resultado_deterministico_sem_mutar_entrada() -> None:
    resolution_context = _context(
        [
            _signal(
                intent_name="generic_intent",
                pattern="alpha",
            ),
            _signal(
                intent_name="generic_intent",
                pattern="alpha",
            ),
        ]
    )
    original = deepcopy(resolution_context)

    first = resolve_intent("alpha", resolution_context)
    second = resolve_intent("alpha", resolution_context)

    assert first == second
    assert resolution_context == original
    assert len(first["best_candidate"]["matches"]) == 1


def test_rejeita_uso_fora_do_contrato_validado() -> None:
    try:
        resolve_intent(
            "alpha",
            {
                "config": {"component": "intent_resolver"},
                "signals": [],
            },
        )
    except IntentResolverInputError as error:
        assert "configuração do resolvedor incompleta" in str(error)
    else:
        raise AssertionError(
            "Era esperado IntentResolverInputError."
        )


def main() -> None:
    tests = [
        (
            "aplica todos os modos diretos",
            test_aplica_todos_os_modos_diretos,
        ),
        (
            "normaliza pergunta sem termos de negócio",
            test_normaliza_pergunta_sem_termos_de_negocio,
        ),
        (
            "regex inválida não interrompe motor",
            test_regex_invalida_nao_interrompe_motor,
        ),
        (
            "agrega sinais positivos e negativos",
            test_agrega_sinais_positivos_e_negativos,
        ),
        (
            "rejeita pontuação abaixo do mínimo",
            test_rejeita_pontuacao_abaixo_do_minimo_sem_fallback_legado,
        ),
        (
            "rejeita candidatos ambíguos",
            test_rejeita_candidatos_ambiguos,
        ),
        (
            "usa prioridade para desempatar",
            test_usa_prioridade_para_desempatar_pontuacao,
        ),
        (
            "aplica fallback por cobertura de tokens",
            test_aplica_fallback_por_cobertura_de_tokens,
        ),
        (
            "aplica equivalência por prefixo",
            test_aplica_equivalencia_configurada_por_prefixo,
        ),
        (
            "respeita escopo do token fallback",
            test_respeita_escopo_configurado_do_token_fallback,
        ),
        (
            "resultado determinístico sem mutação",
            test_resultado_deterministico_sem_mutar_entrada,
        ),
        (
            "rejeita uso fora do contrato validado",
            test_rejeita_uso_fora_do_contrato_validado,
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
