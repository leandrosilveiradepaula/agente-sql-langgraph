from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Literal, TypedDict

from app.domain.context import (
    IntentCatalogConcept,
    IntentCatalogEntry,
    IntentCatalogRule,
    IntentCatalogRuleEffect,
    IntentMatchMode,
    IntentResolutionContext,
    IntentResolutionSignal,
    IntentResolverConfig,
    IntentSignalPolarity,
    IntentTokenFallbackConfig,
)
from app.domain.search_text import (
    normalize_search_text,
    tokenize_search_text,
)


RESOLVER_VERSION = "v1.3.0-context-driven-intent-catalog"

IntentMatchStrategy = Literal[
    "configured_match",
    "token_coverage_fallback",
    "intent_catalog_rule",
]

IntentResolutionReason = Literal[
    "configured_intent_selected",
    "ambiguous_candidates",
    "minimum_score_not_reached",
]

_INTENT_MATCH_MODES = {
    "exact",
    "contains",
    "starts_with",
    "ends_with",
    "all_tokens",
    "any_token",
    "regex",
}

_INTENT_CATALOG_RULE_EFFECTS = {
    "positive_score",
    "negative_score",
    "require",
    "exclude",
}


class IntentTokenMatch(TypedDict):
    """
    Correspondência entre um token do padrão e um token da pergunta.
    """

    pattern_token: str
    question_token: str
    question_index: int
    method: Literal["exact_token", "prefix_equivalence"]
    prefix_ratio: float


class IntentSignalMatch(TypedDict, total=False):
    """
    Evidência que contribuiu para a pontuação de um candidato.

    Os campos de catálogo são opcionais para preservar o diagnóstico
    legado dos sinais simples.
    """

    pattern: str
    match_mode: IntentMatchMode
    match_strategy: IntentMatchStrategy
    match_details: dict[str, Any] | None
    polarity: IntentSignalPolarity
    score: float
    entity_type: str | None
    target_table: str | None
    target_column: str | None
    definition_name: str
    rule_name: str
    rule_effect: IntentCatalogRuleEffect


class IntentCandidate(TypedDict):
    """
    Pontuação agregada de uma intenção candidata elegível.
    """

    intent_name: str
    score: float
    positive_score: float
    negative_score: float
    best_priority: float | None
    matches: list[IntentSignalMatch]


class IntentTokenFallbackDiagnostic(TypedDict):
    """
    Diagnóstico do fallback configurável por cobertura de tokens.
    """

    requested: bool
    configuration_valid: bool
    enabled: bool
    configuration: IntentTokenFallbackConfig | None
    used_for_selected_intent: bool


class IntentCatalogTermEvaluation(TypedDict):
    """
    Resultado da avaliação de um termo configurado do catálogo.
    """

    term: str
    normalized_term: str
    matched: bool
    match_details: dict[str, Any] | None


class IntentCatalogConceptEvaluation(TypedDict):
    """
    Resultado determinístico de um conceito composto.
    """

    concept_name: str
    match_mode: IntentMatchMode
    minimum_term_matches: int
    matched_term_count: int
    satisfied: bool
    terms: list[IntentCatalogTermEvaluation]


class IntentCatalogRuleEvaluation(TypedDict):
    """
    Resultado determinístico de uma regra do catálogo.
    """

    rule_name: str
    effect: IntentCatalogRuleEffect
    score: float | None
    priority: float | None
    minimum_concept_matches: int
    matched_concept_count: int
    satisfied: bool
    concepts: list[IntentCatalogConceptEvaluation]


class IntentCatalogEntryEvaluation(TypedDict):
    """
    Diagnóstico completo de uma definição semântica de intenção.
    """

    intent_name: str
    definition_name: str
    semantic_description: str
    priority: float | None
    eligible: bool
    excluded: bool
    require_rule_count: int
    satisfied_require_rule_count: int
    positive_score: float
    negative_score: float
    score_delta: float
    rules: list[IntentCatalogRuleEvaluation]


class IntentCatalogDiagnostic(TypedDict):
    """
    Diagnóstico global da avaliação do catálogo semântico.
    """

    available: bool
    entries_evaluated: int
    used_for_selected_intent: bool
    contributed_score_to_selected_intent: bool
    evaluations: list[IntentCatalogEntryEvaluation]


class IntentResolutionResult(TypedDict):
    """
    Resultado puro da resolução determinística de intenção.
    """

    applied: bool
    reason: IntentResolutionReason
    intent: str | None
    intent_confidence: float | None
    normalized_question: str
    best_candidate: IntentCandidate | None
    second_candidate: IntentCandidate | None
    candidates: list[IntentCandidate]
    resolver_configuration: IntentResolverConfig
    token_fallback: IntentTokenFallbackDiagnostic
    intent_catalog: IntentCatalogDiagnostic
    resolver_version: str


class _MatchResult(TypedDict):
    matched: bool
    strategy: IntentMatchStrategy
    details: dict[str, Any] | None


class _TokenComparison(TypedDict):
    equivalent: bool
    method: Literal[
        "exact_token",
        "prefix_equivalence",
    ] | None
    prefix_ratio: float | None


class IntentResolverInputError(ValueError):
    """
    Indica uso incorreto do motor fora do contrato já validado.

    O carregamento do contexto deve executar context_validator antes de
    chamar este motor. Esta exceção protege usos diretos e testes isolados.
    """


def resolve_intent(
    question: str,
    intent_resolution: IntentResolutionContext,
) -> IntentResolutionResult:
    """
    Resolve uma intenção exclusivamente a partir do contexto versionado.

    O motor:
    - não conhece nomes de intenções;
    - não conhece termos de negócio;
    - não define scores, margens ou palavras ignoradas;
    - não chama IA, banco de dados ou serviços externos;
    - não utiliza classificador anterior como fallback;
    - agrega sinais simples e regras compostas configuradas no catálogo.

    O campo fallback_to_previous_intent permanece preservado na
    configuração por compatibilidade com a origem n8n, mas o LangGraph
    não possui classificador legado anterior nesta etapa. Quando a
    resolução não é aplicada, intent permanece nulo.
    """

    if not isinstance(question, str):
        raise IntentResolverInputError(
            "question deve ser um texto."
        )

    if not isinstance(intent_resolution, Mapping):
        raise IntentResolverInputError(
            "intent_resolution deve ser um objeto."
        )

    raw_config = intent_resolution.get("config")
    raw_signals = intent_resolution.get("signals")
    raw_catalog = intent_resolution.get("intent_catalog", [])

    if not isinstance(raw_config, Mapping):
        raise IntentResolverInputError(
            "intent_resolution.config deve ser um objeto validado."
        )

    if not isinstance(raw_signals, list):
        raise IntentResolverInputError(
            "intent_resolution.signals deve ser uma lista validada."
        )

    if not isinstance(raw_catalog, list):
        raise IntentResolverInputError(
            "intent_resolution.intent_catalog deve ser uma lista validada."
        )

    config = _validated_config(raw_config)
    signals = [
        _validated_signal(signal, index=index)
        for index, signal in enumerate(raw_signals)
    ]
    catalog = _validated_catalog(raw_catalog)

    normalized_question = normalize_search_text(question)
    token_fallback_config = _effective_token_fallback(config)
    candidate_map: dict[str, IntentCandidate] = {}

    for signal in signals:
        match_result = _match_configured_rule(
            normalized_question,
            signal["normalized_pattern"],
            signal["match_mode"],
        )

        if (
            not match_result["matched"]
            and _fallback_applies_to_signal(
                signal,
                token_fallback_config,
            )
        ):
            match_result = _match_by_token_coverage(
                normalized_question,
                signal["normalized_pattern"],
                token_fallback_config,
            )

        if not match_result["matched"]:
            continue

        candidate = _get_or_create_candidate(
            candidate_map,
            signal["intent_name"],
        )

        signal_score = float(signal["score"])
        _apply_score(
            candidate,
            polarity=signal["polarity"],
            score=signal_score,
        )
        _update_candidate_priority(
            candidate,
            signal.get("priority"),
        )

        candidate["matches"].append(
            {
                "pattern": signal["raw_pattern"],
                "match_mode": signal["match_mode"],
                "match_strategy": match_result["strategy"],
                "match_details": deepcopy(
                    match_result["details"]
                ),
                "polarity": signal["polarity"],
                "score": signal_score,
                "entity_type": signal.get("entity_type"),
                "target_table": signal.get("target_table"),
                "target_column": signal.get("target_column"),
            }
        )

    catalog_evaluations = [
        _evaluate_catalog_entry(
            normalized_question,
            entry,
        )
        for entry in catalog
    ]

    blocked_intents: set[str] = set()
    for evaluation in catalog_evaluations:
        _apply_catalog_evaluation(
            candidate_map,
            blocked_intents,
            evaluation,
        )

    eligible_candidate_map = {
        intent_name: candidate
        for intent_name, candidate in candidate_map.items()
        if intent_name.casefold() not in blocked_intents
    }

    candidates = _sorted_candidates(eligible_candidate_map)
    best_candidate = candidates[0] if candidates else None
    second_candidate = candidates[1] if len(candidates) > 1 else None

    minimum_score = float(config["minimum_score"])
    ambiguity_margin = float(config["ambiguity_margin"])

    reached_minimum_score = bool(
        best_candidate
        and best_candidate["score"] >= minimum_score
    )

    ambiguous = bool(
        best_candidate
        and second_candidate
        and best_candidate["intent_name"]
        != second_candidate["intent_name"]
        and (
            best_candidate["score"]
            - second_candidate["score"]
        )
        < ambiguity_margin
    )

    applied = reached_minimum_score and not ambiguous

    if applied:
        reason: IntentResolutionReason = (
            "configured_intent_selected"
        )
    elif ambiguous:
        reason = "ambiguous_candidates"
    else:
        reason = "minimum_score_not_reached"

    used_token_fallback = bool(
        applied
        and best_candidate
        and any(
            match["match_strategy"]
            == "token_coverage_fallback"
            for match in best_candidate["matches"]
        )
    )

    fallback_requested = bool(
        isinstance(config.get("token_fallback"), Mapping)
        and config["token_fallback"].get("enabled") is True
    )

    selected_catalog_evaluation = _find_catalog_evaluation(
        catalog_evaluations,
        best_candidate["intent_name"]
        if applied and best_candidate
        else None,
    )

    return {
        "applied": applied,
        "reason": reason,
        "intent": (
            best_candidate["intent_name"]
            if applied and best_candidate
            else None
        ),
        "intent_confidence": (
            float(config["applied_confidence"])
            if applied
            else None
        ),
        "normalized_question": normalized_question,
        "best_candidate": deepcopy(best_candidate),
        "second_candidate": deepcopy(second_candidate),
        "candidates": deepcopy(candidates),
        "resolver_configuration": deepcopy(config),
        "token_fallback": {
            "requested": fallback_requested,
            "configuration_valid": True,
            "enabled": token_fallback_config is not None,
            "configuration": deepcopy(token_fallback_config),
            "used_for_selected_intent": used_token_fallback,
        },
        "intent_catalog": {
            "available": bool(catalog),
            "entries_evaluated": len(catalog_evaluations),
            "used_for_selected_intent": (
                selected_catalog_evaluation is not None
            ),
            "contributed_score_to_selected_intent": bool(
                selected_catalog_evaluation
                and (
                    selected_catalog_evaluation["positive_score"] > 0
                    or selected_catalog_evaluation["negative_score"] > 0
                )
            ),
            "evaluations": deepcopy(catalog_evaluations),
        },
        "resolver_version": RESOLVER_VERSION,
    }


def _validated_config(
    value: Mapping[str, Any],
) -> IntentResolverConfig:
    required_fields = (
        "component",
        "minimum_score",
        "ambiguity_margin",
        "applied_confidence",
        "fallback_to_previous_intent",
    )
    missing = [
        field_name
        for field_name in required_fields
        if field_name not in value
    ]
    if missing:
        raise IntentResolverInputError(
            "configuração do resolvedor incompleta: "
            + ", ".join(missing)
            + "."
        )

    if value.get("component") != "intent_resolver":
        raise IntentResolverInputError(
            "configuração não pertence ao componente intent_resolver."
        )

    for field_name in (
        "minimum_score",
        "ambiguity_margin",
        "applied_confidence",
    ):
        field_value = value.get(field_name)
        if (
            isinstance(field_value, bool)
            or not isinstance(field_value, (int, float))
            or not math.isfinite(float(field_value))
        ):
            raise IntentResolverInputError(
                f"{field_name} deve ser numérico e finito."
            )

    if not isinstance(
        value.get("fallback_to_previous_intent"),
        bool,
    ):
        raise IntentResolverInputError(
            "fallback_to_previous_intent deve ser booleano."
        )

    return deepcopy(dict(value))


def _validated_signal(
    value: Any,
    *,
    index: int,
) -> IntentResolutionSignal:
    if not isinstance(value, Mapping):
        raise IntentResolverInputError(
            f"signals[{index}] deve ser um objeto validado."
        )

    required_fields = (
        "intent_name",
        "raw_pattern",
        "normalized_pattern",
        "match_mode",
        "polarity",
        "score",
    )
    missing = [
        field_name
        for field_name in required_fields
        if field_name not in value
    ]
    if missing:
        raise IntentResolverInputError(
            f"signals[{index}] está incompleto: "
            + ", ".join(missing)
            + "."
        )

    return deepcopy(dict(value))


def _validated_catalog(
    value: list[Any],
) -> list[IntentCatalogEntry]:
    entries: list[IntentCatalogEntry] = []
    intent_names: set[str] = set()

    for index, raw_entry in enumerate(value):
        entry = _validated_catalog_entry(
            raw_entry,
            index=index,
        )
        intent_key = entry["intent_name"].casefold()
        if intent_key in intent_names:
            raise IntentResolverInputError(
                "intent_resolution.intent_catalog contém "
                "intenções duplicadas."
            )
        intent_names.add(intent_key)
        entries.append(entry)

    entries.sort(
        key=lambda entry: (
            _optional_priority_sort_value(entry.get("priority")),
            entry["intent_name"].casefold(),
            entry["definition_name"].casefold(),
        )
    )
    return entries


def _validated_catalog_entry(
    value: Any,
    *,
    index: int,
) -> IntentCatalogEntry:
    path = f"intent_catalog[{index}]"
    if not isinstance(value, Mapping):
        raise IntentResolverInputError(
            f"{path} deve ser um objeto validado."
        )

    required_fields = (
        "intent_name",
        "definition_name",
        "semantic_description",
        "rules",
    )
    missing = [
        field_name
        for field_name in required_fields
        if field_name not in value
    ]
    if missing:
        raise IntentResolverInputError(
            f"{path} está incompleto: "
            + ", ".join(missing)
            + "."
        )

    for field_name in (
        "intent_name",
        "definition_name",
        "semantic_description",
    ):
        if not _is_non_empty_text(value.get(field_name)):
            raise IntentResolverInputError(
                f"{path}.{field_name} deve ser texto não vazio."
            )

    rules = value.get("rules")
    if not isinstance(rules, list) or not rules:
        raise IntentResolverInputError(
            f"{path}.rules deve ser uma lista não vazia."
        )

    validated_rules = [
        _validated_catalog_rule(
            rule,
            path=f"{path}.rules[{rule_index}]",
        )
        for rule_index, rule in enumerate(rules)
    ]
    validated_rules.sort(
        key=lambda rule: (
            _optional_priority_sort_value(rule.get("priority")),
            rule["rule_name"].casefold(),
        )
    )

    priority = value.get("priority")
    _validate_optional_number(
        priority,
        path=f"{path}.priority",
    )

    return {
        "intent_name": str(value["intent_name"]),
        "definition_name": str(value["definition_name"]),
        "semantic_description": str(value["semantic_description"]),
        "rules": validated_rules,
        "priority": (
            float(priority) if priority is not None else None
        ),
    }


def _validated_catalog_rule(
    value: Any,
    *,
    path: str,
) -> IntentCatalogRule:
    if not isinstance(value, Mapping):
        raise IntentResolverInputError(
            f"{path} deve ser um objeto validado."
        )

    required_fields = (
        "rule_name",
        "effect",
        "concepts",
        "minimum_concept_matches",
    )
    missing = [
        field_name
        for field_name in required_fields
        if field_name not in value
    ]
    if missing:
        raise IntentResolverInputError(
            f"{path} está incompleto: "
            + ", ".join(missing)
            + "."
        )

    rule_name = value.get("rule_name")
    if not _is_non_empty_text(rule_name):
        raise IntentResolverInputError(
            f"{path}.rule_name deve ser texto não vazio."
        )

    effect = value.get("effect")
    if effect not in _INTENT_CATALOG_RULE_EFFECTS:
        raise IntentResolverInputError(
            f"{path}.effect não pertence ao contrato suportado."
        )

    concepts = value.get("concepts")
    if not isinstance(concepts, list) or not concepts:
        raise IntentResolverInputError(
            f"{path}.concepts deve ser uma lista não vazia."
        )

    minimum_concept_matches = value.get(
        "minimum_concept_matches"
    )
    if (
        not isinstance(minimum_concept_matches, int)
        or isinstance(minimum_concept_matches, bool)
        or minimum_concept_matches <= 0
        or minimum_concept_matches > len(concepts)
    ):
        raise IntentResolverInputError(
            f"{path}.minimum_concept_matches é inválido."
        )

    score = value.get("score")
    if effect in {"positive_score", "negative_score"}:
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
            or float(score) < 0
        ):
            raise IntentResolverInputError(
                f"{path}.score é inválido para regra de pontuação."
            )
    elif score is not None:
        raise IntentResolverInputError(
            f"{path}.score deve ser nulo em regras {effect}."
        )

    priority = value.get("priority")
    _validate_optional_number(
        priority,
        path=f"{path}.priority",
    )

    validated_concepts = [
        _validated_catalog_concept(
            concept,
            path=f"{path}.concepts[{concept_index}]",
        )
        for concept_index, concept in enumerate(concepts)
    ]
    validated_concepts.sort(
        key=lambda concept: concept["concept_name"].casefold()
    )

    return {
        "rule_name": str(rule_name),
        "effect": effect,
        "concepts": validated_concepts,
        "minimum_concept_matches": minimum_concept_matches,
        "score": (
            float(score) if score is not None else None
        ),
        "priority": (
            float(priority) if priority is not None else None
        ),
    }


def _validated_catalog_concept(
    value: Any,
    *,
    path: str,
) -> IntentCatalogConcept:
    if not isinstance(value, Mapping):
        raise IntentResolverInputError(
            f"{path} deve ser um objeto validado."
        )

    required_fields = (
        "concept_name",
        "terms",
        "normalized_terms",
        "match_mode",
        "minimum_term_matches",
    )
    missing = [
        field_name
        for field_name in required_fields
        if field_name not in value
    ]
    if missing:
        raise IntentResolverInputError(
            f"{path} está incompleto: "
            + ", ".join(missing)
            + "."
        )

    concept_name = value.get("concept_name")
    if not _is_non_empty_text(concept_name):
        raise IntentResolverInputError(
            f"{path}.concept_name deve ser texto não vazio."
        )

    match_mode = value.get("match_mode")
    if match_mode not in _INTENT_MATCH_MODES:
        raise IntentResolverInputError(
            f"{path}.match_mode não pertence ao contrato suportado."
        )

    terms = value.get("terms")
    normalized_terms = value.get("normalized_terms")
    if (
        not isinstance(terms, list)
        or not terms
        or not isinstance(normalized_terms, list)
        or len(terms) != len(normalized_terms)
        or any(not _is_non_empty_text(term) for term in terms)
        or any(
            not _is_non_empty_text(term)
            for term in normalized_terms
        )
    ):
        raise IntentResolverInputError(
            f"{path}.terms e normalized_terms são inválidos."
        )

    minimum_term_matches = value.get("minimum_term_matches")
    if (
        not isinstance(minimum_term_matches, int)
        or isinstance(minimum_term_matches, bool)
        or minimum_term_matches <= 0
        or minimum_term_matches > len(terms)
    ):
        raise IntentResolverInputError(
            f"{path}.minimum_term_matches é inválido."
        )

    return {
        "concept_name": str(concept_name),
        "terms": [str(term) for term in terms],
        "normalized_terms": [
            str(term) for term in normalized_terms
        ],
        "match_mode": match_mode,
        "minimum_term_matches": minimum_term_matches,
    }


def _validate_optional_number(
    value: Any,
    *,
    path: str,
) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise IntentResolverInputError(
            f"{path} deve ser numérico, finito e não negativo."
        )


def _is_non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _effective_token_fallback(
    config: IntentResolverConfig,
) -> IntentTokenFallbackConfig | None:
    token_fallback = config.get("token_fallback")
    if not isinstance(token_fallback, Mapping):
        return None
    if token_fallback.get("enabled") is not True:
        return None
    return deepcopy(dict(token_fallback))


def _fallback_applies_to_signal(
    signal: IntentResolutionSignal,
    config: IntentTokenFallbackConfig | None,
) -> bool:
    if config is None:
        return False

    return (
        signal["polarity"]
        in config["apply_to_polarities"]
        and signal["match_mode"]
        in config["apply_to_match_modes"]
    )


def _get_or_create_candidate(
    candidate_map: dict[str, IntentCandidate],
    intent_name: str,
) -> IntentCandidate:
    return candidate_map.setdefault(
        intent_name,
        {
            "intent_name": intent_name,
            "score": 0.0,
            "positive_score": 0.0,
            "negative_score": 0.0,
            "best_priority": None,
            "matches": [],
        },
    )


def _apply_score(
    candidate: IntentCandidate,
    *,
    polarity: IntentSignalPolarity,
    score: float,
) -> None:
    if polarity == "positive":
        candidate["score"] += score
        candidate["positive_score"] += score
    else:
        candidate["score"] -= score
        candidate["negative_score"] += score


def _update_candidate_priority(
    candidate: IntentCandidate,
    priority: Any,
) -> None:
    if priority is None:
        return

    numeric_priority = float(priority)
    current_priority = candidate["best_priority"]
    if (
        current_priority is None
        or numeric_priority < current_priority
    ):
        candidate["best_priority"] = numeric_priority


def _evaluate_catalog_entry(
    normalized_question: str,
    entry: IntentCatalogEntry,
) -> IntentCatalogEntryEvaluation:
    rule_evaluations = [
        _evaluate_catalog_rule(
            normalized_question,
            rule,
        )
        for rule in entry["rules"]
    ]

    require_rules = [
        rule
        for rule in rule_evaluations
        if rule["effect"] == "require"
    ]
    satisfied_require_rules = [
        rule for rule in require_rules if rule["satisfied"]
    ]
    excluded = any(
        rule["effect"] == "exclude" and rule["satisfied"]
        for rule in rule_evaluations
    )
    positive_score = sum(
        float(rule["score"] or 0.0)
        for rule in rule_evaluations
        if rule["effect"] == "positive_score"
        and rule["satisfied"]
    )
    negative_score = sum(
        float(rule["score"] or 0.0)
        for rule in rule_evaluations
        if rule["effect"] == "negative_score"
        and rule["satisfied"]
    )

    return {
        "intent_name": entry["intent_name"],
        "definition_name": entry["definition_name"],
        "semantic_description": entry["semantic_description"],
        "priority": entry.get("priority"),
        "eligible": (
            len(satisfied_require_rules) == len(require_rules)
            and not excluded
        ),
        "excluded": excluded,
        "require_rule_count": len(require_rules),
        "satisfied_require_rule_count": len(
            satisfied_require_rules
        ),
        "positive_score": positive_score,
        "negative_score": negative_score,
        "score_delta": positive_score - negative_score,
        "rules": rule_evaluations,
    }


def _evaluate_catalog_rule(
    normalized_question: str,
    rule: IntentCatalogRule,
) -> IntentCatalogRuleEvaluation:
    concept_evaluations = [
        _evaluate_catalog_concept(
            normalized_question,
            concept,
        )
        for concept in rule["concepts"]
    ]
    matched_concept_count = sum(
        1
        for concept in concept_evaluations
        if concept["satisfied"]
    )

    return {
        "rule_name": rule["rule_name"],
        "effect": rule["effect"],
        "score": rule.get("score"),
        "priority": rule.get("priority"),
        "minimum_concept_matches": rule[
            "minimum_concept_matches"
        ],
        "matched_concept_count": matched_concept_count,
        "satisfied": (
            matched_concept_count
            >= rule["minimum_concept_matches"]
        ),
        "concepts": concept_evaluations,
    }


def _evaluate_catalog_concept(
    normalized_question: str,
    concept: IntentCatalogConcept,
) -> IntentCatalogConceptEvaluation:
    term_evaluations: list[IntentCatalogTermEvaluation] = []

    for raw_term, normalized_term in zip(
        concept["terms"],
        concept["normalized_terms"],
        strict=True,
    ):
        match_result = _match_configured_rule(
            normalized_question,
            normalized_term,
            concept["match_mode"],
        )
        term_evaluations.append(
            {
                "term": raw_term,
                "normalized_term": normalized_term,
                "matched": match_result["matched"],
                "match_details": deepcopy(
                    match_result["details"]
                ),
            }
        )

    matched_term_count = sum(
        1
        for term in term_evaluations
        if term["matched"]
    )

    return {
        "concept_name": concept["concept_name"],
        "match_mode": concept["match_mode"],
        "minimum_term_matches": concept[
            "minimum_term_matches"
        ],
        "matched_term_count": matched_term_count,
        "satisfied": (
            matched_term_count
            >= concept["minimum_term_matches"]
        ),
        "terms": term_evaluations,
    }


def _apply_catalog_evaluation(
    candidate_map: dict[str, IntentCandidate],
    blocked_intents: set[str],
    evaluation: IntentCatalogEntryEvaluation,
) -> None:
    scoring_rules = [
        rule
        for rule in evaluation["rules"]
        if rule["satisfied"]
        and rule["effect"]
        in {"positive_score", "negative_score"}
    ]

    existing_candidate = candidate_map.get(
        evaluation["intent_name"]
    )
    if existing_candidate is None and not scoring_rules:
        if not evaluation["eligible"]:
            blocked_intents.add(
                evaluation["intent_name"].casefold()
            )
        return

    candidate = _get_or_create_candidate(
        candidate_map,
        evaluation["intent_name"],
    )
    constraint_rules = [
        rule
        for rule in evaluation["rules"]
        if rule["effect"] in {"require", "exclude"}
    ]
    if scoring_rules or constraint_rules:
        _update_candidate_priority(
            candidate,
            evaluation.get("priority"),
        )

    for rule in scoring_rules:
        rule_score = float(rule["score"] or 0.0)
        polarity: IntentSignalPolarity = (
            "positive"
            if rule["effect"] == "positive_score"
            else "negative"
        )
        _apply_score(
            candidate,
            polarity=polarity,
            score=rule_score,
        )
        _update_candidate_priority(
            candidate,
            rule.get("priority"),
        )
        candidate["matches"].append(
            {
                "pattern": rule["rule_name"],
                "match_strategy": "intent_catalog_rule",
                "match_details": {
                    "definition_name": evaluation[
                        "definition_name"
                    ],
                    "rule_name": rule["rule_name"],
                    "effect": rule["effect"],
                    "minimum_concept_matches": rule[
                        "minimum_concept_matches"
                    ],
                    "matched_concept_count": rule[
                        "matched_concept_count"
                    ],
                    "concepts": deepcopy(rule["concepts"]),
                },
                "polarity": polarity,
                "score": rule_score,
                "entity_type": "intent_definition",
                "target_table": None,
                "target_column": None,
                "definition_name": evaluation[
                    "definition_name"
                ],
                "rule_name": rule["rule_name"],
                "rule_effect": rule["effect"],
            }
        )

    if not evaluation["eligible"]:
        blocked_intents.add(
            evaluation["intent_name"].casefold()
        )


def _find_catalog_evaluation(
    evaluations: list[IntentCatalogEntryEvaluation],
    intent_name: str | None,
) -> IntentCatalogEntryEvaluation | None:
    if intent_name is None:
        return None

    intent_key = intent_name.casefold()
    for evaluation in evaluations:
        if evaluation["intent_name"].casefold() == intent_key:
            return evaluation
    return None


def _match_configured_rule(
    normalized_question: str,
    normalized_pattern: str,
    match_mode: IntentMatchMode,
) -> _MatchResult:
    if not normalized_question or not normalized_pattern:
        return {
            "matched": False,
            "strategy": "configured_match",
            "details": None,
        }

    question_tokens = normalized_question.split()
    pattern_tokens = normalized_pattern.split()
    matched = False

    if match_mode == "exact":
        matched = normalized_question == normalized_pattern
    elif match_mode == "contains":
        matched = normalized_pattern in normalized_question
    elif match_mode == "starts_with":
        matched = normalized_question.startswith(normalized_pattern)
    elif match_mode == "ends_with":
        matched = normalized_question.endswith(normalized_pattern)
    elif match_mode == "all_tokens":
        matched = bool(pattern_tokens) and all(
            token in question_tokens
            for token in pattern_tokens
        )
    elif match_mode == "any_token":
        matched = bool(pattern_tokens) and any(
            token in question_tokens
            for token in pattern_tokens
        )
    elif match_mode == "regex":
        try:
            matched = bool(
                re.search(
                    normalized_pattern,
                    normalized_question,
                    flags=re.IGNORECASE,
                )
            )
        except re.error:
            matched = False

    return {
        "matched": matched,
        "strategy": "configured_match",
        "details": (
            {"match_mode": match_mode}
            if matched
            else None
        ),
    }


def _tokens_equivalent(
    question_token: str,
    pattern_token: str,
    config: IntentTokenFallbackConfig,
) -> _TokenComparison:
    if question_token == pattern_token:
        return {
            "equivalent": True,
            "method": "exact_token",
            "prefix_ratio": 1.0,
        }

    if not config["allow_prefix_equivalence"]:
        return {
            "equivalent": False,
            "method": None,
            "prefix_ratio": None,
        }

    minimum_prefix_length = config["minimum_prefix_length"]
    minimum_prefix_ratio = float(config["minimum_prefix_ratio"])

    if (
        len(question_token) < minimum_prefix_length
        or len(pattern_token) < minimum_prefix_length
    ):
        return {
            "equivalent": False,
            "method": None,
            "prefix_ratio": None,
        }

    prefix_length = _common_prefix_length(
        question_token,
        pattern_token,
    )
    denominator = min(
        len(question_token),
        len(pattern_token),
    )
    prefix_ratio = (
        prefix_length / denominator
        if denominator > 0
        else 0.0
    )

    return {
        "equivalent": (
            prefix_length >= minimum_prefix_length
            and prefix_ratio >= minimum_prefix_ratio
        ),
        "method": "prefix_equivalence",
        "prefix_ratio": prefix_ratio,
    }


def _match_by_token_coverage(
    normalized_question: str,
    normalized_pattern: str,
    config: IntentTokenFallbackConfig,
) -> _MatchResult:
    ignored_tokens = set(config["ignored_tokens"])
    question_tokens = [
        token
        for token in tokenize_search_text(normalized_question)
        if token not in ignored_tokens
    ]
    pattern_tokens = [
        token
        for token in tokenize_search_text(normalized_pattern)
        if token not in ignored_tokens
    ]

    if len(pattern_tokens) < config["minimum_pattern_tokens"]:
        return {
            "matched": False,
            "strategy": "token_coverage_fallback",
            "details": {
                "reason": (
                    "pattern_has_fewer_tokens_than_configured_minimum"
                ),
                "pattern_token_count": len(pattern_tokens),
            },
        }

    consumed_question_indexes: set[int] = set()
    token_matches: list[IntentTokenMatch] = []
    unmatched_pattern_tokens: list[str] = []

    for pattern_token in pattern_tokens:
        selected: IntentTokenMatch | None = None

        for index, question_token in enumerate(question_tokens):
            if index in consumed_question_indexes:
                continue

            comparison = _tokens_equivalent(
                question_token,
                pattern_token,
                config,
            )
            if not comparison["equivalent"]:
                continue

            method = comparison["method"]
            prefix_ratio = comparison["prefix_ratio"]
            if method is None or prefix_ratio is None:
                continue

            selected = {
                "pattern_token": pattern_token,
                "question_token": question_token,
                "question_index": index,
                "method": method,
                "prefix_ratio": prefix_ratio,
            }
            consumed_question_indexes.add(index)
            break

        if selected is not None:
            token_matches.append(selected)
        else:
            unmatched_pattern_tokens.append(pattern_token)

    matched_token_count = len(token_matches)
    pattern_token_count = len(pattern_tokens)
    coverage = (
        matched_token_count / pattern_token_count
        if pattern_token_count > 0
        else 0.0
    )
    unmatched_count = len(unmatched_pattern_tokens)

    matched = (
        matched_token_count >= config["minimum_matched_tokens"]
        and coverage >= float(config["minimum_pattern_coverage"])
        and unmatched_count
        <= config["maximum_unmatched_pattern_tokens"]
    )

    return {
        "matched": matched,
        "strategy": "token_coverage_fallback",
        "details": {
            "pattern_tokens": pattern_tokens,
            "question_tokens": question_tokens,
            "matched_token_count": matched_token_count,
            "pattern_token_count": pattern_token_count,
            "pattern_coverage": coverage,
            "unmatched_pattern_tokens": unmatched_pattern_tokens,
            "token_matches": token_matches,
        },
    }


def _common_prefix_length(left: str, right: str) -> int:
    max_length = min(len(left), len(right))
    length = 0

    while length < max_length and left[length] == right[length]:
        length += 1

    return length


def _optional_priority_sort_value(value: Any) -> float:
    return float(value) if value is not None else math.inf


def _sorted_candidates(
    candidate_map: Mapping[str, IntentCandidate],
) -> list[IntentCandidate]:
    candidates: list[IntentCandidate] = []

    for candidate in candidate_map.values():
        copied = deepcopy(candidate)
        copied["matches"] = _unique_matches(copied["matches"])
        candidates.append(copied)

    candidates.sort(
        key=lambda candidate: (
            -candidate["score"],
            (
                candidate["best_priority"]
                if candidate["best_priority"] is not None
                else math.inf
            ),
            candidate["intent_name"].casefold(),
        )
    )
    return candidates


def _unique_matches(
    matches: list[IntentSignalMatch],
) -> list[IntentSignalMatch]:
    seen: set[str] = set()
    output: list[IntentSignalMatch] = []

    for match in matches:
        serialized = json.dumps(
            match,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        if serialized in seen:
            continue
        seen.add(serialized)
        output.append(match)

    return output
