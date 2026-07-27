from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Literal, TypedDict

from app.domain.context import (
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


RESOLVER_VERSION = "v1.2.0-config-driven-token-fallback"

IntentMatchStrategy = Literal[
    "configured_match",
    "token_coverage_fallback",
]

IntentResolutionReason = Literal[
    "configured_intent_selected",
    "ambiguous_candidates",
    "minimum_score_not_reached",
]


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
    Sinal que contribuiu para a pontuação de um candidato.
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


class IntentCandidate(TypedDict):
    """
    Pontuação agregada de uma intenção candidata.
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
    - não utiliza classificador anterior como fallback.

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

    if not isinstance(raw_config, Mapping):
        raise IntentResolverInputError(
            "intent_resolution.config deve ser um objeto validado."
        )

    if not isinstance(raw_signals, list):
        raise IntentResolverInputError(
            "intent_resolution.signals deve ser uma lista validada."
        )

    config = _validated_config(raw_config)
    signals = [
        _validated_signal(signal, index=index)
        for index, signal in enumerate(raw_signals)
    ]

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

        candidate = candidate_map.setdefault(
            signal["intent_name"],
            {
                "intent_name": signal["intent_name"],
                "score": 0.0,
                "positive_score": 0.0,
                "negative_score": 0.0,
                "best_priority": None,
                "matches": [],
            },
        )

        signal_score = float(signal["score"])
        if signal["polarity"] == "positive":
            candidate["score"] += signal_score
            candidate["positive_score"] += signal_score
        else:
            candidate["score"] -= signal_score
            candidate["negative_score"] += signal_score

        priority = signal.get("priority")
        if priority is not None:
            numeric_priority = float(priority)
            current_priority = candidate["best_priority"]
            if (
                current_priority is None
                or numeric_priority < current_priority
            ):
                candidate["best_priority"] = numeric_priority

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

    candidates = _sorted_candidates(candidate_map)
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
