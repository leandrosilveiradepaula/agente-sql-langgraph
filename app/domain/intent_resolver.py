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


class SemanticDefaultRule(TypedDict):
    rule_name: str
    when_present: list[str]
    when_absent: list[str]
    produce: list[str]
    priority: int


class SemanticDefaultsConfig(TypedDict):
    component: str
    rules: list[SemanticDefaultRule]


class SemanticDefaultsDiagnostic(TypedDict):
    requested: bool
    applied: list[dict[str, Any]]
    suppressed: list[dict[str, Any]]


class IntentCatalogTermEvaluation(TypedDict):
    """
    Resultado da avaliação de um termo configurado do catálogo.
    """

    term: str
    normalized_term: str
    matched: bool
    match_details: dict[str, Any] | None


class SemanticSignal(TypedDict):
    """
    Evidência semântica extraída de termos já versionados no contexto.
    """

    concept_name: str
    term: str
    normalized_term: str
    source: str
    confidence: float
    matched_tokens: list[str]


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
    semantic_signals: list[SemanticSignal]


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
    semantic_defaults: SemanticDefaultsDiagnostic
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
    semantic_defaults_config = _validated_semantic_defaults_config(
        intent_resolution.get("semantic_defaults", {})
    )
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
    semantic_defaults = _apply_semantic_defaults(
        catalog_evaluations,
        semantic_defaults_config,
    )

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
        "semantic_defaults": semantic_defaults,
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


def _validated_semantic_defaults_config(
    value: Any,
) -> SemanticDefaultsConfig | None:
    if value in ({}, None):
        return None
    if not isinstance(value, Mapping):
        raise IntentResolverInputError(
            "intent_resolution.semantic_defaults deve ser um objeto."
        )
    if value.get("component") != "semantic_defaults":
        raise IntentResolverInputError(
            "semantic_defaults.component deve ser semantic_defaults."
        )
    rules = value.get("rules")
    if not isinstance(rules, list):
        raise IntentResolverInputError(
            "semantic_defaults.rules deve ser uma lista."
        )

    names: set[str] = set()
    edges: dict[str, set[str]] = {}
    validated_rules: list[SemanticDefaultRule] = []
    for index, raw_rule in enumerate(rules):
        if not isinstance(raw_rule, Mapping):
            raise IntentResolverInputError(
                f"semantic_defaults.rules[{index}] deve ser objeto."
            )
        rule_name = raw_rule.get("rule_name")
        if not _is_non_empty_text(rule_name):
            raise IntentResolverInputError(
                "semantic_defaults.rule_name deve ser texto não vazio."
            )
        rule_name_text = str(rule_name).strip()
        rule_key = rule_name_text.casefold()
        if rule_key in names:
            raise IntentResolverInputError(
                "semantic_defaults.rule_name deve ser único."
            )
        names.add(rule_key)

        when_present = _validated_semantic_default_concept_list(
            raw_rule.get("when_present"),
            field_name="when_present",
            allow_empty=False,
        )
        when_absent = _validated_semantic_default_concept_list(
            raw_rule.get("when_absent"),
            field_name="when_absent",
            allow_empty=True,
        )
        produce = _validated_semantic_default_concept_list(
            raw_rule.get("produce"),
            field_name="produce",
            allow_empty=False,
        )
        if set(item.casefold() for item in when_present) & set(
            item.casefold() for item in when_absent
        ):
            raise IntentResolverInputError(
                "semantic_defaults possui conflito present/absent."
            )

        priority = raw_rule.get("priority")
        if (
            not isinstance(priority, int)
            or isinstance(priority, bool)
            or priority < 0
        ):
            raise IntentResolverInputError(
                "semantic_defaults.priority deve ser inteiro não negativo."
            )

        for concept in produce:
            concept_key = concept.casefold()
            edges.setdefault(concept_key, set()).update(
                item.casefold() for item in when_present
            )

        validated_rules.append(
            {
                "rule_name": rule_name_text,
                "when_present": when_present,
                "when_absent": when_absent,
                "produce": produce,
                "priority": priority,
            }
        )

    if _has_semantic_default_cycle(edges):
        raise IntentResolverInputError(
            "semantic_defaults não pode conter ciclos."
        )
    validated_rules.sort(
        key=lambda rule: (rule["priority"], rule["rule_name"].casefold())
    )
    return {"component": "semantic_defaults", "rules": validated_rules}


def _validated_semantic_default_concept_list(
    value: Any,
    *,
    field_name: str,
    allow_empty: bool,
) -> list[str]:
    if not isinstance(value, list):
        raise IntentResolverInputError(
            f"semantic_defaults.{field_name} deve ser lista."
        )
    if not allow_empty and not value:
        raise IntentResolverInputError(
            f"semantic_defaults.{field_name} deve ser não vazio."
        )
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not _is_non_empty_text(item):
            raise IntentResolverInputError(
                f"semantic_defaults.{field_name} deve conter textos."
            )
        text = str(item).strip()
        key = text.casefold()
        if key in seen:
            raise IntentResolverInputError(
                f"semantic_defaults.{field_name} contém duplicatas."
            )
        seen.add(key)
        result.append(text)
    return result


def _has_semantic_default_cycle(
    edges: Mapping[str, set[str]],
) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for dependency in sorted(edges.get(node, set())):
            if visit(dependency):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in sorted(edges))


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
    protected_token_indexes = _protected_dimension_token_indexes(
        normalized_question,
        rule["concepts"],
    )
    concept_evaluations = [
        _evaluate_catalog_concept(
            normalized_question,
            concept,
            protected_token_indexes=protected_token_indexes,
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


def _apply_semantic_defaults(
    catalog_evaluations: list[IntentCatalogEntryEvaluation],
    config: SemanticDefaultsConfig | None,
) -> SemanticDefaultsDiagnostic:
    if config is None:
        return {"requested": False, "applied": [], "suppressed": []}

    explicit_concepts = _explicitly_satisfied_concept_names(
        catalog_evaluations
    )
    applied: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    produced_concepts: dict[str, dict[str, Any]] = {}

    for rule in config["rules"]:
        present = {item.casefold() for item in rule["when_present"]}
        absent = {item.casefold() for item in rule["when_absent"]}
        missing_present = sorted(present - explicit_concepts)
        present_absent = sorted(absent & explicit_concepts)
        if missing_present or present_absent:
            suppressed.append(
                {
                    "rule_name": rule["rule_name"],
                    "reason": (
                        "when_present_missing"
                        if missing_present
                        else "when_absent_present"
                    ),
                    "missing_present": missing_present,
                    "present_absent": present_absent,
                    "priority": rule["priority"],
                }
            )
            continue

        for concept in rule["produce"]:
            concept_key = concept.casefold()
            if concept_key in explicit_concepts:
                suppressed.append(
                    {
                        "rule_name": rule["rule_name"],
                        "reason": "concept_already_explicit",
                        "concept_name": concept,
                        "priority": rule["priority"],
                    }
                )
                continue
            if concept_key in produced_concepts:
                suppressed.append(
                    {
                        "rule_name": rule["rule_name"],
                        "reason": "equivalent_default_already_produced",
                        "concept_name": concept,
                        "priority": rule["priority"],
                    }
                )
                continue
            produced_concepts[concept_key] = {
                "concept_name": concept,
                "source": "semantic_default",
                "rule_name": rule["rule_name"],
                "priority": rule["priority"],
                "explicit_vs_default": "default",
                "produced_because": {
                    "present": list(rule["when_present"]),
                    "absent": list(rule["when_absent"]),
                },
            }
            applied.append(
                {
                    "rule_name": rule["rule_name"],
                    "concept_name": concept,
                    "priority": rule["priority"],
                    "explicit_vs_default": "default",
                }
            )

    if produced_concepts:
        _apply_default_concepts_to_catalog_evaluations(
            catalog_evaluations,
            produced_concepts,
        )

    return {"requested": True, "applied": applied, "suppressed": suppressed}


def _explicitly_satisfied_concept_names(
    catalog_evaluations: list[IntentCatalogEntryEvaluation],
) -> set[str]:
    concepts: set[str] = set()
    for entry in catalog_evaluations:
        for rule in entry["rules"]:
            for concept in rule["concepts"]:
                if concept["satisfied"]:
                    concepts.add(concept["concept_name"].casefold())
    return concepts


def _apply_default_concepts_to_catalog_evaluations(
    catalog_evaluations: list[IntentCatalogEntryEvaluation],
    produced_concepts: Mapping[str, dict[str, Any]],
) -> None:
    for entry in catalog_evaluations:
        for rule in entry["rules"]:
            changed = False
            for concept in rule["concepts"]:
                concept_key = concept["concept_name"].casefold()
                evidence = produced_concepts.get(concept_key)
                if evidence is None or concept["satisfied"]:
                    continue
                concept["satisfied"] = True
                concept["semantic_signals"].append(deepcopy(evidence))
                changed = True
            if changed:
                rule["matched_concept_count"] = sum(
                    1
                    for concept in rule["concepts"]
                    if concept["satisfied"]
                )
                rule["satisfied"] = (
                    rule["matched_concept_count"]
                    >= rule["minimum_concept_matches"]
                )
        _refresh_catalog_entry_scores(entry)


def _refresh_catalog_entry_scores(
    entry: IntentCatalogEntryEvaluation,
) -> None:
    require_rules = [
        rule for rule in entry["rules"] if rule["effect"] == "require"
    ]
    satisfied_require_rules = [
        rule for rule in require_rules if rule["satisfied"]
    ]
    excluded = any(
        rule["effect"] == "exclude" and rule["satisfied"]
        for rule in entry["rules"]
    )
    positive_score = sum(
        float(rule["score"] or 0.0)
        for rule in entry["rules"]
        if rule["effect"] == "positive_score" and rule["satisfied"]
    )
    negative_score = sum(
        float(rule["score"] or 0.0)
        for rule in entry["rules"]
        if rule["effect"] == "negative_score" and rule["satisfied"]
    )
    entry["eligible"] = (
        len(satisfied_require_rules) == len(require_rules)
        and not excluded
    )
    entry["excluded"] = excluded
    entry["satisfied_require_rule_count"] = len(satisfied_require_rules)
    entry["positive_score"] = positive_score
    entry["negative_score"] = negative_score
    entry["score_delta"] = positive_score - negative_score


def _evaluate_catalog_concept(
    normalized_question: str,
    concept: IntentCatalogConcept,
    *,
    protected_token_indexes: set[int] | None = None,
) -> IntentCatalogConceptEvaluation:
    term_evaluations: list[IntentCatalogTermEvaluation] = []
    semantic_signals: list[SemanticSignal] = []
    protected = protected_token_indexes or set()

    for raw_term, normalized_term in zip(
        concept["terms"],
        concept["normalized_terms"],
        strict=True,
    ):
        if _requires_semantic_token_match(concept):
            match_result = _match_catalog_term_semantically(
                normalized_question,
                normalized_term,
                protected_token_indexes=(
                    protected
                    if concept["concept_name"]
                    != "dimension_grouping"
                    else set()
                ),
            )
        else:
            match_result = _match_configured_rule(
                normalized_question,
                normalized_term,
                concept["match_mode"],
            )
            if not match_result["matched"]:
                match_result = _match_catalog_term_semantically(
                    normalized_question,
                    normalized_term,
                    protected_token_indexes=(
                        protected
                        if concept["concept_name"]
                        != "dimension_grouping"
                        else set()
                    ),
                )
        if match_result["matched"]:
            details = match_result["details"] or {}
            semantic_signal = details.get("semantic_signal")
            if isinstance(semantic_signal, Mapping):
                semantic_signals.append(
                    {
                        "concept_name": concept["concept_name"],
                        "term": raw_term,
                        "normalized_term": normalized_term,
                        "source": str(
                            semantic_signal.get(
                                "source",
                                match_result["strategy"],
                            )
                        ),
                        "confidence": float(
                            semantic_signal.get("confidence", 1.0)
                        ),
                        "matched_tokens": [
                            str(token)
                            for token in semantic_signal.get(
                                "matched_tokens",
                                [],
                            )
                        ],
                    }
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
        "semantic_signals": semantic_signals,
    }


_SEMANTIC_RELATION_TOKENS = {
    "a",
    "as",
    "by",
    "de",
    "do",
    "dos",
    "das",
    "e",
    "em",
    "entre",
    "of",
    "os",
    "per",
    "por",
}
_SEMANTIC_MAX_TOKEN_WINDOW = 3


def _requires_semantic_token_match(
    concept: IntentCatalogConcept,
) -> bool:
    return (
        concept["match_mode"] == "contains"
        and any(
            len(_semantic_tokens(normalized_term)) == 1
            for normalized_term in concept["normalized_terms"]
        )
    )


def _protected_dimension_token_indexes(
    normalized_question: str,
    concepts: list[IntentCatalogConcept],
) -> set[int]:
    protected: set[int] = set()
    for concept in concepts:
        if concept["concept_name"] != "dimension_grouping":
            continue
        for normalized_term in concept["normalized_terms"]:
            match_result = _match_catalog_term_semantically(
                normalized_question,
                normalized_term,
                protected_token_indexes=set(),
            )
            if not match_result["matched"]:
                continue
            details = match_result["details"] or {}
            indexes = details.get("matched_token_indexes", [])
            if isinstance(indexes, list):
                protected.update(
                    int(index)
                    for index in indexes
                    if isinstance(index, int)
                )
    return protected


def _match_catalog_term_semantically(
    normalized_question: str,
    normalized_term: str,
    *,
    protected_token_indexes: set[int],
) -> _MatchResult:
    question_tokens = _semantic_tokens(normalized_question)
    term_tokens = _semantic_tokens(normalized_term)

    if not question_tokens or not term_tokens:
        return {
            "matched": False,
            "strategy": "configured_match",
            "details": None,
        }

    selected_indexes: list[int] = []
    selected_tokens: list[str] = []
    consumed_indexes: set[int] = set()
    next_start_index = 0

    for term_token in term_tokens:
        selected_index: int | None = None
        selected_question_token: str | None = None
        for index, question_token in enumerate(
            question_tokens[next_start_index:],
            start=next_start_index,
        ):
            if (
                index in consumed_indexes
                or index in protected_token_indexes
            ):
                continue
            if _semantic_tokens_equivalent(
                question_token,
                term_token,
            ):
                selected_index = index
                selected_question_token = question_token
                break

        if selected_index is None or selected_question_token is None:
            return {
                "matched": False,
                "strategy": "configured_match",
                "details": None,
            }
        consumed_indexes.add(selected_index)
        selected_indexes.append(selected_index)
        selected_tokens.append(selected_question_token)
        next_start_index = selected_index + 1

    if (
        len(selected_indexes) > 1
        and selected_indexes[-1] - selected_indexes[0] + 1
        > _SEMANTIC_MAX_TOKEN_WINDOW
    ):
        return {
            "matched": False,
            "strategy": "configured_match",
            "details": None,
        }

    return {
        "matched": True,
        "strategy": "configured_match",
        "details": {
            "match_mode": "semantic_token_concept",
            "matched_token_indexes": selected_indexes,
            "semantic_signal": {
                "source": "intent_catalog_concept",
                "confidence": 1.0,
                "matched_tokens": selected_tokens,
            },
        },
    }


def _semantic_tokens(value: str) -> list[str]:
    return [
        _semantic_token_root(token)
        for token in tokenize_search_text(value)
        if token not in _SEMANTIC_RELATION_TOKENS
    ]


def _semantic_tokens_equivalent(
    question_token: str,
    term_token: str,
) -> bool:
    return _semantic_token_root(question_token) == _semantic_token_root(
        term_token
    )


def _semantic_token_root(token: str) -> str:
    if len(token) <= 3:
        return token
    if token.endswith("oes") and len(token) > 5:
        return token[:-3] + "ao"
    if (
        token.endswith("s")
        and len(token) > 4
        and not token.endswith(("ss", "us", "is"))
    ):
        return token[:-1]
    return token


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
