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


def _concept(
    *,
    concept_name: str,
    terms: list[str],
    match_mode: str = "contains",
    minimum_term_matches: int = 1,
) -> dict:
    return {
        "concept_name": concept_name,
        "terms": terms,
        "normalized_terms": terms,
        "match_mode": match_mode,
        "minimum_term_matches": minimum_term_matches,
    }


def _rule(
    *,
    rule_name: str,
    effect: str,
    concepts: list[dict],
    minimum_concept_matches: int = 1,
    score: float | None = None,
    priority: float | None = 1,
) -> dict:
    return {
        "rule_name": rule_name,
        "effect": effect,
        "concepts": concepts,
        "minimum_concept_matches": minimum_concept_matches,
        "score": score,
        "priority": priority,
    }


def _catalog_entry(
    *,
    intent_name: str,
    rules: list[dict],
    definition_name: str | None = None,
    priority: float | None = 1,
) -> dict:
    return {
        "intent_name": intent_name,
        "definition_name": (
            definition_name or f"{intent_name}_definition"
        ),
        "semantic_description": "Generic semantic definition.",
        "rules": rules,
        "priority": priority,
    }


def _context(
    signals: list[dict],
    *,
    config: dict | None = None,
    intent_catalog: list[dict] | None = None,
    semantic_defaults: dict | None = None,
) -> dict:
    context = {
        "config": config or _config(),
        "signals": signals,
        "intent_catalog": intent_catalog or [],
    }
    if semantic_defaults is not None:
        context["semantic_defaults"] = semantic_defaults
    return context


def _semantic_defaults(*rules: list[dict]) -> dict:
    return {
        "component": "semantic_defaults",
        "rules": list(rules),
    }


def _default_rule(
    *,
    rule_name: str = "default_rule",
    when_present: list[str] | None = None,
    when_absent: list[str] | None = None,
    produce: list[str] | None = None,
    priority: int = 1,
) -> dict:
    return {
        "rule_name": rule_name,
        "when_present": when_present or ["first_concept"],
        "when_absent": when_absent or [],
        "produce": produce or ["default_concept"],
        "priority": priority,
    }


def _first_concept_requirement() -> dict:
    return _rule(
        rule_name="requires_first_concept",
        effect="require",
        concepts=[
            _concept(
                concept_name="first_concept",
                terms=["alpha"],
            )
        ],
    )


def _blocking_concept_requirement() -> dict:
    return _rule(
        rule_name="requires_blocking_concept",
        effect="require",
        concepts=[
            _concept(
                concept_name="blocking_concept",
                terms=["beta"],
            )
        ],
    )


def _find_evaluated_concept(result: dict, concept_name: str) -> dict:
    for entry in result["intent_catalog"]["evaluations"]:
        for rule in entry["rules"]:
            for concept in rule["concepts"]:
                if concept["concept_name"] == concept_name:
                    return concept
    raise AssertionError(f"Conceito não encontrado: {concept_name}")


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


def test_catalogo_ausente_preserva_comportamento() -> None:
    legacy_context = {
        "config": _config(),
        "signals": [
            _signal(
                intent_name="generic_intent",
                pattern="alpha",
            )
        ],
    }

    result = resolve_intent("alpha", legacy_context)

    assert result["applied"] is True
    assert result["intent"] == "generic_intent"
    assert result["intent_catalog"] == {
        "available": False,
        "entries_evaluated": 0,
        "used_for_selected_intent": False,
        "contributed_score_to_selected_intent": False,
        "evaluations": [],
    }
    assert result["semantic_defaults"] == {
        "requested": False,
        "applied": [],
        "suppressed": [],
    }


def test_semantic_default_aplica_com_presenca_e_ausencia() -> None:
    catalog = [
        _catalog_entry(
            intent_name="generic_intent",
            rules=[
                _first_concept_requirement(),
                _rule(
                    rule_name="requires_default",
                    effect="require",
                    concepts=[
                        _concept(
                            concept_name="default_concept",
                            terms=["delta"],
                        )
                    ],
                ),
                _rule(
                    rule_name="scores_default",
                    effect="positive_score",
                    concepts=[
                        _concept(
                            concept_name="default_concept",
                            terms=["delta"],
                        )
                    ],
                    score=120,
                ),
            ],
        )
    ]

    result = resolve_intent(
        "alpha",
        _context(
            [],
            intent_catalog=catalog,
            semantic_defaults=_semantic_defaults(
                _default_rule(
                    when_present=["first_concept"],
                    when_absent=["blocking_concept"],
                    produce=["default_concept"],
                )
            ),
        ),
    )

    assert result["applied"] is True
    assert result["intent"] == "generic_intent"
    assert result["best_candidate"]["score"] == 120
    defaults = result["semantic_defaults"]
    assert defaults["requested"] is True
    assert defaults["applied"][0]["concept_name"] == "default_concept"
    default_concept = _find_evaluated_concept(result, "default_concept")
    assert default_concept["satisfied"] is True
    assert default_concept["terms"][0]["matched"] is False
    assert default_concept["semantic_signals"][0]["source"] == (
        "semantic_default"
    )
    assert default_concept["semantic_signals"][0][
        "explicit_vs_default"
    ] == "default"


def test_semantic_default_nao_aplica_sem_presenca() -> None:
    catalog = [
        _catalog_entry(
            intent_name="generic_intent",
            rules=[
                _first_concept_requirement(),
                _rule(
                    rule_name="scores_default",
                    effect="positive_score",
                    concepts=[
                        _concept(
                            concept_name="default_concept",
                            terms=["delta"],
                        )
                    ],
                    score=120,
                )
            ],
        )
    ]

    result = resolve_intent(
        "omega",
        _context(
            [],
            intent_catalog=catalog,
            semantic_defaults=_semantic_defaults(_default_rule()),
        ),
    )

    assert result["applied"] is False
    assert result["semantic_defaults"]["applied"] == []
    assert result["semantic_defaults"]["suppressed"][0]["reason"] == (
        "when_present_missing"
    )


def test_semantic_default_nao_aplica_com_absencia_explicita() -> None:
    catalog = [
        _catalog_entry(
            intent_name="generic_intent",
            rules=[
                _first_concept_requirement(),
                _blocking_concept_requirement(),
                _rule(
                    rule_name="scores_default",
                    effect="positive_score",
                    concepts=[
                        _concept(
                            concept_name="default_concept",
                            terms=["delta"],
                        )
                    ],
                    score=120,
                )
            ],
        )
    ]

    result = resolve_intent(
        "alpha beta",
        _context(
            [],
            intent_catalog=catalog,
            semantic_defaults=_semantic_defaults(
                _default_rule(
                    when_present=["first_concept"],
                    when_absent=["blocking_concept"],
                )
            ),
        ),
    )

    assert result["applied"] is False
    assert result["semantic_defaults"]["applied"] == []
    assert result["semantic_defaults"]["suppressed"][0]["reason"] == (
        "when_absent_present"
    )


def test_semantic_default_nao_duplica_conceito_explicito() -> None:
    catalog = [
        _catalog_entry(
            intent_name="generic_intent",
            rules=[
                _first_concept_requirement(),
                _rule(
                    rule_name="scores_explicit",
                    effect="positive_score",
                    concepts=[
                        _concept(
                            concept_name="default_concept",
                            terms=["gamma"],
                        )
                    ],
                    score=120,
                )
            ],
        )
    ]

    result = resolve_intent(
        "alpha gamma",
        _context(
            [],
            intent_catalog=catalog,
            semantic_defaults=_semantic_defaults(_default_rule()),
        ),
    )

    assert result["applied"] is True
    assert result["semantic_defaults"]["applied"] == []
    assert result["semantic_defaults"]["suppressed"][0]["reason"] == (
        "concept_already_explicit"
    )


def test_semantic_default_participa_de_negative_score_e_exclude() -> None:
    catalog = [
        _catalog_entry(
            intent_name="intent_a",
            rules=[
                _rule(
                    rule_name="base_score",
                    effect="positive_score",
                    concepts=[
                        _concept(
                            concept_name="first_concept",
                            terms=["alpha"],
                        )
                    ],
                    score=160,
                ),
                _rule(
                    rule_name="default_penalty",
                    effect="negative_score",
                    concepts=[
                        _concept(
                            concept_name="default_concept",
                            terms=["delta"],
                        )
                    ],
                    score=40,
                ),
            ],
        ),
        _catalog_entry(
            intent_name="intent_b",
            rules=[
                _rule(
                    rule_name="base_score",
                    effect="positive_score",
                    concepts=[
                        _concept(
                            concept_name="first_concept",
                            terms=["alpha"],
                        )
                    ],
                    score=160,
                ),
                _rule(
                    rule_name="default_exclude",
                    effect="exclude",
                    concepts=[
                        _concept(
                            concept_name="default_concept",
                            terms=["delta"],
                        )
                    ],
                ),
            ],
        ),
    ]

    result = resolve_intent(
        "alpha",
        _context(
            [],
            config=_config(ambiguity_margin=0),
            intent_catalog=catalog,
            semantic_defaults=_semantic_defaults(_default_rule()),
        ),
    )

    assert result["applied"] is True
    assert result["intent"] == "intent_a"
    assert result["best_candidate"]["score"] == 120
    intent_b = [
        item
        for item in result["intent_catalog"]["evaluations"]
        if item["intent_name"] == "intent_b"
    ][0]
    assert intent_b["excluded"] is True


def test_semantic_defaults_deterministicos_compativeis() -> None:
    catalog = [
        _catalog_entry(
            intent_name="generic_intent",
            rules=[
                _first_concept_requirement(),
                _rule(
                    rule_name="scores_defaults",
                    effect="positive_score",
                    concepts=[
                        _concept(
                            concept_name="default_a",
                            terms=["delta"],
                        ),
                        _concept(
                            concept_name="default_b",
                            terms=["epsilon"],
                        ),
                    ],
                    minimum_concept_matches=2,
                    score=120,
                )
            ],
        )
    ]

    result = resolve_intent(
        "alpha",
        _context(
            [],
            intent_catalog=catalog,
            semantic_defaults=_semantic_defaults(
                _default_rule(
                    rule_name="second_rule",
                    produce=["default_b"],
                    priority=2,
                ),
                _default_rule(
                    rule_name="first_rule",
                    produce=["default_a"],
                    priority=1,
                ),
            ),
        ),
    )

    assert result["applied"] is True
    assert [
        item["rule_name"] for item in result["semantic_defaults"]["applied"]
    ] == ["first_rule", "second_rule"]


def test_semantic_defaults_invalidos_falham_fechado() -> None:
    catalog = [
        _catalog_entry(
            intent_name="generic_intent",
            rules=[
                _rule(
                    rule_name="scores_default",
                    effect="positive_score",
                    concepts=[
                        _concept(
                            concept_name="default_concept",
                            terms=["delta"],
                        )
                    ],
                    score=120,
                )
            ],
        )
    ]

    try:
        resolve_intent(
            "alpha",
            _context(
                [],
                intent_catalog=catalog,
                semantic_defaults=_semantic_defaults(
                    _default_rule(priority=True),
                ),
            ),
        )
    except IntentResolverInputError as error:
        assert "priority" in str(error)
    else:
        raise AssertionError("Era esperado IntentResolverInputError.")


def test_semantic_defaults_equivalentes_produzem_uma_vez() -> None:
    catalog = [
        _catalog_entry(
            intent_name="generic_intent",
            rules=[
                _first_concept_requirement(),
                _rule(
                    rule_name="scores_default",
                    effect="positive_score",
                    concepts=[
                        _concept(
                            concept_name="default_concept",
                            terms=["delta"],
                        )
                    ],
                    score=120,
                ),
            ],
        )
    ]

    result = resolve_intent(
        "alpha",
        _context(
            [],
            intent_catalog=catalog,
            semantic_defaults=_semantic_defaults(
                _default_rule(rule_name="first_rule", priority=1),
                _default_rule(rule_name="second_rule", priority=2),
            ),
        ),
    )

    assert result["applied"] is True
    assert len(result["semantic_defaults"]["applied"]) == 1
    assert result["semantic_defaults"]["applied"][0]["rule_name"] == (
        "first_rule"
    )
    assert result["semantic_defaults"]["suppressed"][0]["reason"] == (
        "equivalent_default_already_produced"
    )


def test_semantic_defaults_rejeitam_ciclo() -> None:
    catalog = [
        _catalog_entry(
            intent_name="generic_intent",
            rules=[
                _rule(
                    rule_name="score",
                    effect="positive_score",
                    concepts=[
                        _concept(
                            concept_name="concept_a",
                            terms=["alpha"],
                        )
                    ],
                    score=120,
                )
            ],
        )
    ]

    try:
        resolve_intent(
            "alpha",
            _context(
                [],
                intent_catalog=catalog,
                semantic_defaults=_semantic_defaults(
                    _default_rule(
                        rule_name="a_to_b",
                        when_present=["concept_a"],
                        produce=["concept_b"],
                    ),
                    _default_rule(
                        rule_name="b_to_a",
                        when_present=["concept_b"],
                        produce=["concept_a"],
                    ),
                ),
            ),
        )
    except IntentResolverInputError as error:
        assert "ciclos" in str(error)
    else:
        raise AssertionError("Era esperado IntentResolverInputError.")


def test_aplica_positive_score_sem_sinal_simples() -> None:
    catalog = [
        _catalog_entry(
            intent_name="generic_intent",
            rules=[
                _rule(
                    rule_name="composite_positive",
                    effect="positive_score",
                    concepts=[
                        _concept(
                            concept_name="first_concept",
                            terms=["alpha"],
                        ),
                        _concept(
                            concept_name="second_concept",
                            terms=["beta"],
                        ),
                    ],
                    minimum_concept_matches=2,
                    score=120,
                )
            ],
        )
    ]

    result = resolve_intent(
        "alpha beta",
        _context([], intent_catalog=catalog),
    )

    assert result["applied"] is True
    assert result["intent"] == "generic_intent"
    assert result["best_candidate"]["score"] == 120
    assert result["best_candidate"]["positive_score"] == 120
    assert (
        result["best_candidate"]["matches"][0]
        ["match_strategy"]
        == "intent_catalog_rule"
    )


def test_agrega_negative_score_do_catalogo_com_sinal() -> None:
    catalog = [
        _catalog_entry(
            intent_name="generic_intent",
            rules=[
                _rule(
                    rule_name="configured_penalty",
                    effect="negative_score",
                    concepts=[
                        _concept(
                            concept_name="blocking_concept",
                            terms=["blocked"],
                        )
                    ],
                    score=30,
                )
            ],
        )
    ]

    result = resolve_intent(
        "alpha blocked",
        _context(
            [
                _signal(
                    intent_name="generic_intent",
                    pattern="alpha",
                    score=140,
                )
            ],
            intent_catalog=catalog,
        ),
    )

    assert result["applied"] is True
    assert result["best_candidate"]["score"] == 110
    assert result["best_candidate"]["positive_score"] == 140
    assert result["best_candidate"]["negative_score"] == 30


def test_require_satisfeita_mantem_candidato() -> None:
    catalog = [
        _catalog_entry(
            intent_name="generic_intent",
            rules=[
                _rule(
                    rule_name="required_context",
                    effect="require",
                    concepts=[
                        _concept(
                            concept_name="required_concept",
                            terms=["beta"],
                        )
                    ],
                )
            ],
        )
    ]

    result = resolve_intent(
        "alpha beta",
        _context(
            [
                _signal(
                    intent_name="generic_intent",
                    pattern="alpha",
                )
            ],
            intent_catalog=catalog,
        ),
    )

    assert result["applied"] is True
    evaluation = result["intent_catalog"]["evaluations"][0]
    assert evaluation["eligible"] is True
    assert evaluation["satisfied_require_rule_count"] == 1


def test_require_nao_satisfeita_bloqueia_candidato() -> None:
    catalog = [
        _catalog_entry(
            intent_name="generic_intent",
            rules=[
                _rule(
                    rule_name="required_context",
                    effect="require",
                    concepts=[
                        _concept(
                            concept_name="required_concept",
                            terms=["beta"],
                        )
                    ],
                )
            ],
        )
    ]

    result = resolve_intent(
        "alpha",
        _context(
            [
                _signal(
                    intent_name="generic_intent",
                    pattern="alpha",
                )
            ],
            intent_catalog=catalog,
        ),
    )

    assert result["applied"] is False
    assert result["candidates"] == []
    evaluation = result["intent_catalog"]["evaluations"][0]
    assert evaluation["eligible"] is False
    assert evaluation["excluded"] is False


def test_exclude_satisfeita_bloqueia_candidato() -> None:
    catalog = [
        _catalog_entry(
            intent_name="generic_intent",
            rules=[
                _rule(
                    rule_name="excluded_context",
                    effect="exclude",
                    concepts=[
                        _concept(
                            concept_name="excluded_concept",
                            terms=["blocked"],
                        )
                    ],
                )
            ],
        )
    ]

    result = resolve_intent(
        "alpha blocked",
        _context(
            [
                _signal(
                    intent_name="generic_intent",
                    pattern="alpha",
                )
            ],
            intent_catalog=catalog,
        ),
    )

    assert result["applied"] is False
    assert result["candidates"] == []
    evaluation = result["intent_catalog"]["evaluations"][0]
    assert evaluation["excluded"] is True
    assert evaluation["eligible"] is False


def test_avalia_limites_compostos_de_termos_e_conceitos() -> None:
    catalog = [
        _catalog_entry(
            intent_name="generic_intent",
            rules=[
                _rule(
                    rule_name="composite_threshold",
                    effect="positive_score",
                    concepts=[
                        _concept(
                            concept_name="multi_term_concept",
                            terms=["alpha", "gamma"],
                            minimum_term_matches=2,
                        ),
                        _concept(
                            concept_name="single_term_concept",
                            terms=["beta"],
                        ),
                    ],
                    minimum_concept_matches=2,
                    score=120,
                )
            ],
        )
    ]

    result = resolve_intent(
        "alpha beta gamma",
        _context([], intent_catalog=catalog),
    )

    assert result["applied"] is True
    rule = result["intent_catalog"]["evaluations"][0]["rules"][0]
    assert rule["matched_concept_count"] == 2
    assert rule["satisfied"] is True
    assert rule["concepts"][0]["matched_term_count"] == 2


def test_agrega_sinais_catalogo_e_prioridade_deterministica() -> None:
    catalog = [
        _catalog_entry(
            intent_name="intent_a",
            priority=2,
            rules=[
                _rule(
                    rule_name="catalog_a",
                    effect="positive_score",
                    concepts=[
                        _concept(
                            concept_name="concept_a",
                            terms=["gamma"],
                        )
                    ],
                    score=20,
                    priority=2,
                )
            ],
        ),
        _catalog_entry(
            intent_name="intent_b",
            priority=1,
            rules=[
                _rule(
                    rule_name="catalog_b",
                    effect="positive_score",
                    concepts=[
                        _concept(
                            concept_name="concept_b",
                            terms=["beta"],
                        )
                    ],
                    score=120,
                    priority=1,
                )
            ],
        ),
    ]

    result = resolve_intent(
        "alpha beta gamma",
        _context(
            [
                _signal(
                    intent_name="intent_a",
                    pattern="alpha",
                    score=100,
                    priority=3,
                )
            ],
            config=_config(ambiguity_margin=0),
            intent_catalog=catalog,
        ),
    )

    assert result["applied"] is True
    assert result["intent"] == "intent_b"
    assert result["best_candidate"]["score"] == 120
    assert result["second_candidate"]["score"] == 120
    assert result["best_candidate"]["best_priority"] == 1



def test_regra_nao_satisfeita_nao_altera_prioridade() -> None:
    catalog = [
        _catalog_entry(
            intent_name="intent_a",
            priority=1,
            rules=[
                _rule(
                    rule_name="unmatched_score",
                    effect="positive_score",
                    concepts=[
                        _concept(
                            concept_name="unmatched_concept",
                            terms=["gamma"],
                        )
                    ],
                    score=50,
                    priority=1,
                )
            ],
        )
    ]

    result = resolve_intent(
        "alpha beta",
        _context(
            [
                _signal(
                    intent_name="intent_a",
                    pattern="alpha",
                    score=120,
                    priority=3,
                ),
                _signal(
                    intent_name="intent_b",
                    pattern="beta",
                    score=120,
                    priority=2,
                ),
            ],
            config=_config(ambiguity_margin=0),
            intent_catalog=catalog,
        ),
    )

    assert result["applied"] is True
    assert result["intent"] == "intent_b"
    assert result["second_candidate"]["intent_name"] == "intent_a"
    assert result["second_candidate"]["best_priority"] == 3

def test_diagnostico_completo_do_catalogo_sem_mutacao() -> None:
    resolution_context = _context(
        [],
        intent_catalog=[
            _catalog_entry(
                intent_name="generic_intent",
                rules=[
                    _rule(
                        rule_name="required_context",
                        effect="require",
                        concepts=[
                            _concept(
                                concept_name="required_concept",
                                terms=["alpha"],
                            )
                        ],
                    ),
                    _rule(
                        rule_name="positive_context",
                        effect="positive_score",
                        concepts=[
                            _concept(
                                concept_name="scored_concept",
                                terms=["beta"],
                            )
                        ],
                        score=120,
                        priority=2,
                    ),
                ],
            )
        ],
    )
    original = deepcopy(resolution_context)

    first = resolve_intent("alpha beta", resolution_context)
    second = resolve_intent("alpha beta", resolution_context)

    assert first == second
    assert resolution_context == original
    diagnostic = first["intent_catalog"]
    assert diagnostic["available"] is True
    assert diagnostic["entries_evaluated"] == 1
    assert diagnostic["used_for_selected_intent"] is True
    assert diagnostic["contributed_score_to_selected_intent"] is True
    evaluation = diagnostic["evaluations"][0]
    assert evaluation["eligible"] is True
    assert evaluation["score_delta"] == 120
    assert len(evaluation["rules"]) == 2
    assert all(rule["satisfied"] for rule in evaluation["rules"])


def test_rejeita_catalogo_fora_do_contrato_validado() -> None:
    invalid_context = _context(
        [],
        intent_catalog=[
            {
                "intent_name": "generic_intent",
                "definition_name": "generic_definition",
                "semantic_description": "Generic definition.",
                "rules": [],
                "priority": 1,
            }
        ],
    )

    try:
        resolve_intent("alpha", invalid_context)
    except IntentResolverInputError as error:
        assert "rules deve ser uma lista não vazia" in str(error)
    else:
        raise AssertionError(
            "Era esperado IntentResolverInputError."
        )


def _semantic_metric_context() -> dict:
    concepts = {
        "metric": _concept(
            concept_name="metric",
            terms=["amount", "revenue"],
        ),
        "dimension": _concept(
            concept_name="dimension_grouping",
            terms=["by region", "by channel", "by cost center"],
        ),
        "period": _concept(
            concept_name="period",
            terms=["last period"],
        ),
        "operation": _concept(
            concept_name="operation",
            terms=["total", "distributed", "highest", "compare"],
        ),
    }

    return _context(
        [],
        intent_catalog=[
            _catalog_entry(
                intent_name="synthetic_metric",
                rules=[
                    _rule(
                        rule_name="semantic_require",
                        effect="require",
                        concepts=list(concepts.values()),
                        minimum_concept_matches=2,
                    ),
                    _rule(
                        rule_name="metric_dimension_period",
                        effect="positive_score",
                        concepts=[
                            concepts["metric"],
                            concepts["dimension"],
                            concepts["period"],
                        ],
                        minimum_concept_matches=3,
                        score=130,
                    ),
                    _rule(
                        rule_name="metric_operation_period",
                        effect="positive_score",
                        concepts=[
                            concepts["metric"],
                            concepts["operation"],
                            concepts["period"],
                        ],
                        minimum_concept_matches=3,
                        score=125,
                    ),
                    _rule(
                        rule_name="metric_operation_dimension",
                        effect="positive_score",
                        concepts=[
                            concepts["metric"],
                            concepts["operation"],
                            concepts["dimension"],
                        ],
                        minimum_concept_matches=3,
                        score=120,
                    ),
                ],
            )
        ],
    )


def test_reconhece_dimensao_sem_frase_literal_by() -> None:
    result = resolve_intent(
        "amount distributed across regions last period",
        _semantic_metric_context(),
    )

    assert result["applied"] is True
    assert result["intent"] == "synthetic_metric"
    best = result["best_candidate"]
    assert best is not None
    matched = _matched_catalog_concepts(best)
    assert "by region" in matched["dimension_grouping"]
    assert "distributed" in matched["operation"]


def test_reconhece_ranking_com_dimensao_sem_lookup_literal() -> None:
    result = resolve_intent(
        "highest amounts among regions last period",
        _semantic_metric_context(),
    )

    assert result["applied"] is True
    best = result["best_candidate"]
    assert best is not None
    matched = _matched_catalog_concepts(best)
    assert "by region" in matched["dimension_grouping"]
    assert "highest" in matched["operation"]


def test_reconhece_comparacao_com_dimensao_sem_lookup_literal() -> None:
    result = resolve_intent(
        "compare amount across channels last period",
        _semantic_metric_context(),
    )

    assert result["applied"] is True
    best = result["best_candidate"]
    assert best is not None
    matched = _matched_catalog_concepts(best)
    assert "by channel" in matched["dimension_grouping"]
    assert "compare" in matched["operation"]


def test_nao_extrai_metrica_de_termo_composto_de_dimensao() -> None:
    result = resolve_intent(
        "last period by cost center",
        _semantic_metric_context(),
    )

    assert result["applied"] is False
    metric_entry = result["intent_catalog"]["evaluations"][0]
    metric_terms = [
        term
        for rule in metric_entry["rules"]
        for concept in rule["concepts"]
        if concept["concept_name"] == "metric"
        for term in concept["terms"]
        if term["matched"]
    ]
    assert metric_terms == []


def test_metrica_periodo_sem_dimensao_continua_valida() -> None:
    result = resolve_intent(
        "total revenue last period",
        _semantic_metric_context(),
    )

    assert result["applied"] is True
    assert result["intent"] == "synthetic_metric"
    best = result["best_candidate"]
    assert best is not None
    matched = _matched_catalog_concepts(best)
    assert "revenue" in matched["metric"]
    assert "dimension_grouping" not in matched


def test_pergunta_desconhecida_nao_ganha_sinais_artificiais() -> None:
    result = resolve_intent(
        "explain the deployment status",
        _semantic_metric_context(),
    )

    assert result["applied"] is False
    assert result["candidates"] == []


def _semantic_alpha_beta_context() -> dict:
    concept = _concept(
        concept_name="synthetic_concept",
        terms=["alpha beta"],
    )
    return _context(
        [],
        intent_catalog=[
            _catalog_entry(
                intent_name="synthetic_intent",
                rules=[
                    _rule(
                        rule_name="alpha_beta_score",
                        effect="positive_score",
                        concepts=[concept],
                        score=120,
                    )
                ],
            )
        ],
    )


def test_termo_composto_nao_casa_tokens_invertidos() -> None:
    result = resolve_intent(
        "beta unrelated words alpha",
        _semantic_alpha_beta_context(),
    )

    assert result["applied"] is False
    assert result["candidates"] == []


def test_termo_composto_casa_tokens_em_ordem_adjacente() -> None:
    result = resolve_intent(
        "alpha beta",
        _semantic_alpha_beta_context(),
    )

    assert result["applied"] is True
    assert result["intent"] == "synthetic_intent"


def test_termo_composto_casa_tokens_em_janela_curta() -> None:
    result = resolve_intent(
        "alpha nearby beta",
        _semantic_alpha_beta_context(),
    )

    assert result["applied"] is True
    assert result["intent"] == "synthetic_intent"


def test_pluralizacao_nao_cria_equivalencia_artificial() -> None:
    context = _context(
        [],
        intent_catalog=[
            _catalog_entry(
                intent_name="synthetic_intent",
                rules=[
                    _rule(
                        rule_name="status_score",
                        effect="positive_score",
                        concepts=[
                            _concept(
                                concept_name="synthetic_concept",
                                terms=["status"],
                            )
                        ],
                        score=120,
                    )
                ],
            )
        ],
    )

    result = resolve_intent(
        "statu",
        context,
    )

    assert result["applied"] is False
    assert result["candidates"] == []


def _matched_catalog_concepts(
    candidate: dict,
) -> dict[str, list[str]]:
    matched: dict[str, list[str]] = {}
    for item in candidate["matches"]:
        details = item.get("match_details") or {}
        for concept in details.get("concepts", []):
            terms = [
                term["term"]
                for term in concept["terms"]
                if term["matched"]
            ]
            if terms:
                matched.setdefault(
                    concept["concept_name"],
                    [],
                ).extend(terms)
    return matched


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
        (
            "catálogo ausente preserva comportamento",
            test_catalogo_ausente_preserva_comportamento,
        ),
        (
            "semantic default aplica com presença e ausência",
            test_semantic_default_aplica_com_presenca_e_ausencia,
        ),
        (
            "semantic default não aplica sem presença",
            test_semantic_default_nao_aplica_sem_presenca,
        ),
        (
            "semantic default não aplica com ausência explícita",
            test_semantic_default_nao_aplica_com_absencia_explicita,
        ),
        (
            "semantic default não duplica conceito explícito",
            test_semantic_default_nao_duplica_conceito_explicito,
        ),
        (
            "semantic default participa de negative e exclude",
            test_semantic_default_participa_de_negative_score_e_exclude,
        ),
        (
            "semantic defaults compatíveis são determinísticos",
            test_semantic_defaults_deterministicos_compativeis,
        ),
        (
            "semantic defaults inválidos falham fechado",
            test_semantic_defaults_invalidos_falham_fechado,
        ),
        (
            "semantic defaults equivalentes produzem uma vez",
            test_semantic_defaults_equivalentes_produzem_uma_vez,
        ),
        (
            "semantic defaults rejeitam ciclo",
            test_semantic_defaults_rejeitam_ciclo,
        ),
        (
            "aplica positive_score sem sinal simples",
            test_aplica_positive_score_sem_sinal_simples,
        ),
        (
            "agrega negative_score com sinal simples",
            test_agrega_negative_score_do_catalogo_com_sinal,
        ),
        (
            "require satisfeita mantém candidato",
            test_require_satisfeita_mantem_candidato,
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
            "avalia limites compostos",
            test_avalia_limites_compostos_de_termos_e_conceitos,
        ),
        (
            "agrega sinais, catálogo e prioridade",
            test_agrega_sinais_catalogo_e_prioridade_deterministica,
        ),
        (
            "regra não satisfeita não altera prioridade",
            test_regra_nao_satisfeita_nao_altera_prioridade,
        ),
        (
            "diagnóstico completo sem mutação",
            test_diagnostico_completo_do_catalogo_sem_mutacao,
        ),
        (
            "rejeita catálogo fora do contrato",
            test_rejeita_catalogo_fora_do_contrato_validado,
        ),
        (
            "reconhece dimensão sem frase literal by",
            test_reconhece_dimensao_sem_frase_literal_by,
        ),
        (
            "reconhece ranking com dimensão",
            test_reconhece_ranking_com_dimensao_sem_lookup_literal,
        ),
        (
            "reconhece comparação com dimensão",
            test_reconhece_comparacao_com_dimensao_sem_lookup_literal,
        ),
        (
            "não extrai métrica de dimensão composta",
            test_nao_extrai_metrica_de_termo_composto_de_dimensao,
        ),
        (
            "métrica período sem dimensão continua válida",
            test_metrica_periodo_sem_dimensao_continua_valida,
        ),
        (
            "pergunta desconhecida não ganha sinais artificiais",
            test_pergunta_desconhecida_nao_ganha_sinais_artificiais,
        ),
        (
            "termo composto não casa tokens invertidos",
            test_termo_composto_nao_casa_tokens_invertidos,
        ),
        (
            "termo composto casa tokens adjacentes",
            test_termo_composto_casa_tokens_em_ordem_adjacente,
        ),
        (
            "termo composto casa janela curta",
            test_termo_composto_casa_tokens_em_janela_curta,
        ),
        (
            "pluralização não cria equivalência artificial",
            test_pluralizacao_nao_cria_equivalencia_artificial,
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
