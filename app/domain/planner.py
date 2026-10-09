from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from app.domain.context import (
    AgentRule,
    ContextSnapshot,
    DreMapping,
    EntityAlias,
    QueryPattern,
    TableCatalogEntry,
)
from app.domain.planning import (
    PLANNER_VERSION,
    PatternCandidateDiagnostic,
    PatternSelectionDiagnostic,
    PatternSelectionResult,
    PlanningBuildResult,
    PlanningContextProjection,
    PlanningDecisionReason,
    PlanningErrorCode,
    ProjectedDreMapping,
    ProjectedDimension,
    ProjectedAnalyticalOperation,
    ProjectedEntity,
    ProjectedJoin,
    ProjectedPlannedFilter,
    ProjectedFilterBinding,
    ProjectedPlannedMetric,
    ProjectedRule,
    ProjectedTable,
    QueryPlan,
    SelectedPattern,
    selected_pattern_from_query_pattern,
)
from app.domain.search_text import (
    normalize_search_text,
    tokenize_search_text,
)


class PlanningInputError(ValueError):
    """
    Indica uso do planner fora do contrato canonico ja validado.
    """


class PlanningRejection(ValueError):
    """
    Rejeicao esperada quando o contexto nao sustenta um plano seguro.
    """

    def __init__(
        self,
        code: PlanningErrorCode,
        message: str,
    ) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def build_query_plan(
    *,
    context: ContextSnapshot,
    intent_name: str | None,
    intent_confidence: float | None,
    normalized_question: str,
    intent_resolution_result: Mapping[str, Any] | None = None,
) -> PlanningBuildResult:
    """
    Constroi um QueryPlan autocontido a partir do ContextSnapshot ja carregado.
    """

    selection = select_query_pattern(
        intent_name=intent_name,
        normalized_question=normalized_question,
        query_patterns=context.get("query_patterns", []),
    )

    if selection["status"] != "planned":
        return {
            "status": selection["status"],
            "query_plan": None,
            "selection_result": selection,
            "projection": None,
            "error_code": selection["error_code"],
            "error_message": selection["error_message"],
        }

    selected_pattern = selection["selected_pattern"]
    if selected_pattern is None:
        raise PlanningInputError(
            "selection planned sem selected_pattern."
        )

    try:
        projection = project_planning_context(
            context=context,
            intent_name=intent_name or "",
            normalized_question=normalized_question,
            selected_pattern=selected_pattern,
            intent_resolution_result=intent_resolution_result,
        )
    except PlanningRejection as rejection:
        failed_selection = deepcopy(selection)
        failed_selection["status"] = "rejected"
        failed_selection["error_code"] = rejection.code
        failed_selection["error_message"] = rejection.message
        return {
            "status": "rejected",
            "query_plan": None,
            "selection_result": failed_selection,
            "projection": None,
            "error_code": rejection.code,
            "error_message": rejection.message,
        }

    query_plan: QueryPlan = {
        "planner_version": PLANNER_VERSION,
        "context_version": context.get("version", ""),
        "context_fingerprint": context.get("fingerprint", ""),
        "intent_name": intent_name or "",
        "intent_confidence": intent_confidence,
        "normalized_question": normalized_question,
        "selected_pattern": deepcopy(selected_pattern),
        "planning_context": projection,
        "selection_diagnostic": selection["diagnostic"],
        "sql_pattern_metadata": selected_pattern.get(
            "sql_pattern",
            "",
        ),
    }

    return {
        "status": "planned",
        "query_plan": query_plan,
        "selection_result": selection,
        "projection": projection,
        "error_code": None,
        "error_message": None,
    }


def select_query_pattern(
    *,
    intent_name: str | None,
    normalized_question: str,
    query_patterns: list[QueryPattern],
) -> PatternSelectionResult:
    """
    Seleciona um query_pattern sem LLM, embeddings ou acesso externo.

    Ordem dos criterios:
    1. exemplo exatamente igual apos normalizacao;
    2. maior similaridade lexical deterministica;
    3. maior cobertura de tokens do exemplo;
    4. menor prioridade numerica configurada;
    5. pattern_name como desempate estavel somente quando ha evidencia.
    """

    if not _is_non_empty_text(intent_name):
        return _selection_rejection(
            code="PLANNING_INTENT_MISSING",
            message="Nenhuma intencao aplicada foi recebida pelo planner.",
            reason="intent_missing",
            candidates=[],
        )

    if not isinstance(query_patterns, list):
        raise PlanningInputError(
            "query_patterns deve ser uma lista."
        )

    matching_patterns = [
        _validated_pattern(pattern, index=index)
        for index, pattern in enumerate(query_patterns)
        if (
            isinstance(pattern, Mapping)
            and _same_text(pattern.get("intent_name"), intent_name)
        )
    ]

    if not matching_patterns:
        return _selection_rejection(
            code="PLANNING_PATTERN_NOT_FOUND",
            message=(
                "Nao existe query_pattern para a intencao selecionada."
            ),
            reason="pattern_not_found",
            candidates=[],
        )

    diagnostics = [
        _evaluate_pattern(pattern, normalized_question)
        for pattern in matching_patterns
    ]

    if len(matching_patterns) == 1:
        selected = selected_pattern_from_query_pattern(
            matching_patterns[0]
        )
        return _selection_success(
            selected=selected,
            candidates=diagnostics,
            reason="single_pattern_selected",
            fallback_used=None,
            tie_detected=False,
        )

    ranked = sorted(
        diagnostics,
        key=_candidate_sort_key,
    )
    best = ranked[0]
    second = ranked[1]

    best_key = _semantic_priority_key(best)
    second_key = _semantic_priority_key(second)
    tie_detected = best_key == second_key

    best_has_evidence = _has_semantic_evidence(best)
    priority_used = (
        best["criteria"]["priority"]
        != second["criteria"]["priority"]
    )

    if tie_detected and not best_has_evidence:
        return _selection_rejection(
            code="PLANNING_PATTERN_AMBIGUOUS",
            message=(
                "Padroes da mesma intencao ficaram indistinguiveis "
                "sem evidencia semantica suficiente."
            ),
            reason="pattern_ambiguous",
            candidates=ranked,
            tie_detected=True,
        )

    selected_pattern_name = best["pattern_name"]
    selected = selected_pattern_from_query_pattern(
        next(
            pattern
            for pattern in matching_patterns
            if pattern["pattern_name"] == selected_pattern_name
        )
    )

    reason = _decision_reason(
        best,
        second,
        priority_used=priority_used,
        tie_detected=tie_detected,
    )

    return _selection_success(
        selected=selected,
        candidates=ranked,
        reason=reason,
        fallback_used=(
            "priority"
            if reason == "priority_selected"
            else (
                "pattern_name"
                if reason == "stable_name_tiebreak_selected"
                else None
            )
        ),
        tie_detected=tie_detected,
    )


def project_planning_context(
    *,
    context: ContextSnapshot,
    intent_name: str,
    normalized_question: str,
    selected_pattern: SelectedPattern,
    intent_resolution_result: Mapping[str, Any] | None = None,
) -> PlanningContextProjection:
    """
    Projeta somente o necessario para planejamento e proximas fases.
    """

    if not isinstance(context, Mapping):
        raise PlanningInputError(
            "context deve ser um objeto canonico."
        )

    required_rules, missing_rules = _project_rules(
        context.get("rules", []),
        intent_name=intent_name,
        required_rule_names=selected_pattern.get(
            "required_rules",
            [],
        ),
    )
    if missing_rules:
        raise PlanningRejection(
            "PLANNING_REQUIRED_RULE_NOT_FOUND",
            "Uma ou mais regras requeridas pelo padrao nao existem.",
        )

    dimension_projection, dimension_diagnostic = _detect_grouping_dimensions(
        context=context,
        normalized_question=normalized_question,
        intent_resolution_result=intent_resolution_result,
    )
    operation_projection, operation_diagnostic = (
        _detect_analytical_operations(
            context=context,
            intent_resolution_result=intent_resolution_result,
        )
    )
    planned_metrics, planned_metric_diagnostic = _detect_planned_metrics(
        context=context,
        intent_resolution_result=intent_resolution_result,
        selected_pattern=selected_pattern,
    )
    planned_filters, planned_filter_diagnostic = _detect_planned_filters(
        context=context,
        intent_resolution_result=intent_resolution_result,
    )
    resolved_filter_bindings = _project_resolved_filter_bindings(
        entities=context.get("entities", []),
        planned_filters=planned_filters,
    )
    operation_projection, metric_binding_diagnostic = (
        _bind_metrics_to_analytical_operations(
            operations=operation_projection,
            planned_metrics=planned_metrics,
        )
    )
    operation_diagnostic["metric_binding"] = metric_binding_diagnostic
    required_table_names = _expand_required_tables_with_dimensions(
        selected_pattern.get("required_tables", []),
        dimension_projection,
        planned_metrics,
    )

    required_tables, missing_tables, ambiguous_tables = (
        _project_tables(
            context.get("table_catalog", []),
            required_table_names,
        )
    )
    if missing_tables or ambiguous_tables:
        raise PlanningRejection(
            "PLANNING_REQUIRED_TABLE_NOT_FOUND",
            "Uma ou mais tabelas requeridas pelo padrao nao existem.",
        )

    table_names = {
        table["qualified_name"].casefold()
        for table in required_tables
    }
    bare_table_names = {
        table["table_name"].casefold()
        for table in required_tables
    }
    selected_columns = _selected_column_names(required_tables)

    join_projection = _project_joins(required_tables, table_names)
    operation_projection, comparison_dimension_diagnostic = (
        _validate_comparison_dimension_compatibility(
            operations=operation_projection,
            planned_metrics=planned_metrics,
            dimensions=dimension_projection,
            required_tables=required_tables,
            authorized_joins=join_projection["joins"],
        )
    )
    if comparison_dimension_diagnostic["status"] != "not_applicable":
        operation_diagnostic["dimension_compatibility"] = (
            comparison_dimension_diagnostic
        )
        if comparison_dimension_diagnostic["status"] != "passed":
            planned_metrics = []
            operation_projection = _drop_comparison_operand_refs(
                operation_projection
            )
    entity_projection = _project_entities(
        context.get("entities", []),
        intent_name=intent_name,
        table_names=table_names,
        bare_table_names=bare_table_names,
        selected_columns=selected_columns,
    )
    dre_projection, dre_diagnostic = _project_dre_mappings(
        context.get("dre_mappings", []),
        intent_name=intent_name,
        table_names=table_names,
        bare_table_names=bare_table_names,
        selected_columns=selected_columns,
    )

    relevant_columns = {
        table["qualified_name"]: deepcopy(
            table.get("columns", [])
        )
        for table in required_tables
    }
    _include_dimension_columns(relevant_columns, dimension_projection)
    _include_metric_columns(relevant_columns, planned_metrics)

    return {
        "context_version": context.get("version", ""),
        "context_fingerprint": context.get("fingerprint", ""),
        "intent_name": intent_name,
        "normalized_question": normalized_question,
        "selected_pattern": deepcopy(selected_pattern),
        "rules": required_rules,
        "required_tables": required_tables,
        "relevant_columns": relevant_columns,
        "authorized_joins": join_projection["joins"],
        "relevant_entities": entity_projection,
        "relevant_dre_mappings": dre_projection,
        "detected_dimensions": dimension_projection,
        "analytical_operations": operation_projection,
        "planned_metrics": planned_metrics,
        "planned_filters": planned_filters,
        "resolved_filter_bindings": resolved_filter_bindings,
        "allowed_schemas": list(context.get("allowed_schemas", [])),
        "component_configs": deepcopy(
            context.get("component_configs", {})
        ),
        "diagnostics": {
            "missing_required_rules": missing_rules,
            "missing_required_tables": missing_tables,
            "ambiguous_required_tables": ambiguous_tables,
            "join_diagnostics": join_projection["diagnostics"],
            "dre_diagnostic": dre_diagnostic,
            "dimension_diagnostic": dimension_diagnostic,
            "analytical_operation_diagnostic": operation_diagnostic,
            "planned_metric_diagnostic": planned_metric_diagnostic,
            "planned_filter_diagnostic": planned_filter_diagnostic,
        },
    }


def _validated_pattern(
    value: Any,
    *,
    index: int,
) -> QueryPattern:
    if not isinstance(value, Mapping):
        raise PlanningInputError(
            f"query_patterns[{index}] deve ser um objeto."
        )

    required_fields = (
        "intent_name",
        "pattern_name",
        "business_question_examples",
        "required_tables",
        "required_rules",
    )
    missing = [
        field_name
        for field_name in required_fields
        if field_name not in value
    ]
    if missing:
        raise PlanningInputError(
            f"query_patterns[{index}] esta incompleto: "
            + ", ".join(missing)
            + "."
        )

    if not _is_non_empty_text(value.get("intent_name")):
        raise PlanningInputError(
            f"query_patterns[{index}].intent_name invalido."
        )
    if not _is_non_empty_text(value.get("pattern_name")):
        raise PlanningInputError(
            f"query_patterns[{index}].pattern_name invalido."
        )

    for field_name in (
        "business_question_examples",
        "required_tables",
        "required_rules",
    ):
        if not isinstance(value.get(field_name), list):
            raise PlanningInputError(
                f"query_patterns[{index}].{field_name} deve ser lista."
            )

    priority = value.get("priority")
    if priority is not None and _priority_sort_value(priority) == math.inf:
        raise PlanningInputError(
            f"query_patterns[{index}].priority invalida."
        )

    return deepcopy(dict(value))


def _evaluate_pattern(
    pattern: QueryPattern,
    normalized_question: str,
) -> PatternCandidateDiagnostic:
    examples = [
        example
        for example in pattern.get("business_question_examples", [])
        if isinstance(example, str) and example.strip()
    ]
    question_tokens = set(tokenize_search_text(normalized_question))

    best_similarity = 0.0
    best_coverage = 0.0
    matched_example: str | None = None
    exact_match = False

    for example in examples:
        normalized_example = normalize_search_text(example)
        example_tokens = set(tokenize_search_text(normalized_example))
        intersection_size = len(question_tokens & example_tokens)
        union_size = len(question_tokens | example_tokens)
        similarity = (
            intersection_size / union_size
            if union_size
            else 0.0
        )
        coverage = (
            intersection_size / len(example_tokens)
            if example_tokens
            else 0.0
        )

        is_exact = normalized_question == normalized_example
        current_key = (
            is_exact,
            similarity,
            coverage,
            normalized_example,
        )
        best_key = (
            exact_match,
            best_similarity,
            best_coverage,
            normalize_search_text(matched_example or ""),
        )
        if current_key > best_key:
            exact_match = is_exact
            best_similarity = similarity
            best_coverage = coverage
            matched_example = example

    return {
        "intent_name": pattern["intent_name"],
        "pattern_name": pattern["pattern_name"],
        "examples_count": len(examples),
        "criteria": {
            "exact_example_match": exact_match,
            "best_similarity": best_similarity,
            "best_coverage": best_coverage,
            "matched_example": matched_example,
            "priority": (
                float(pattern["priority"])
                if pattern.get("priority") is not None
                else None
            ),
            "pattern_name": pattern["pattern_name"],
        },
    }


def _candidate_sort_key(
    candidate: PatternCandidateDiagnostic,
) -> tuple[float, float, float, float, str]:
    criteria = candidate["criteria"]
    return (
        -float(criteria["exact_example_match"]),
        -criteria["best_similarity"],
        -criteria["best_coverage"],
        _priority_sort_value(criteria["priority"]),
        criteria["pattern_name"].casefold(),
    )


def _semantic_priority_key(
    candidate: PatternCandidateDiagnostic,
) -> tuple[bool, float, float, float]:
    criteria = candidate["criteria"]
    return (
        criteria["exact_example_match"],
        criteria["best_similarity"],
        criteria["best_coverage"],
        _priority_sort_value(criteria["priority"]),
    )


def _has_semantic_evidence(
    candidate: PatternCandidateDiagnostic,
) -> bool:
    criteria = candidate["criteria"]
    return (
        criteria["exact_example_match"]
        or criteria["best_similarity"] > 0
        or criteria["best_coverage"] > 0
    )


def _decision_reason(
    best: PatternCandidateDiagnostic,
    second: PatternCandidateDiagnostic,
    *,
    priority_used: bool,
    tie_detected: bool,
) -> PlanningDecisionReason:
    best_criteria = best["criteria"]
    second_criteria = second["criteria"]

    if (
        best_criteria["exact_example_match"]
        and not second_criteria["exact_example_match"]
    ):
        return "exact_example_match"
    if (
        best_criteria["best_similarity"]
        > second_criteria["best_similarity"]
    ):
        return "lexical_similarity_selected"
    if (
        best_criteria["best_coverage"]
        > second_criteria["best_coverage"]
    ):
        return "token_coverage_selected"
    if priority_used:
        return "priority_selected"
    if tie_detected:
        return "stable_name_tiebreak_selected"
    return "stable_name_tiebreak_selected"


def _selection_success(
    *,
    selected: SelectedPattern,
    candidates: list[PatternCandidateDiagnostic],
    reason: PlanningDecisionReason,
    fallback_used: str | None,
    tie_detected: bool,
) -> PatternSelectionResult:
    diagnostic: PatternSelectionDiagnostic = {
        "selected_pattern": deepcopy(selected),
        "candidates": deepcopy(candidates),
        "decision_reason": reason,
        "tie_detected": tie_detected,
        "fallback_used": fallback_used,
        "planner_version": PLANNER_VERSION,
    }
    return {
        "status": "planned",
        "selected_pattern": selected,
        "diagnostic": diagnostic,
        "error_code": None,
        "error_message": None,
    }


def _selection_rejection(
    *,
    code: PlanningErrorCode,
    message: str,
    reason: PlanningDecisionReason,
    candidates: list[PatternCandidateDiagnostic],
    tie_detected: bool = False,
) -> PatternSelectionResult:
    diagnostic: PatternSelectionDiagnostic = {
        "selected_pattern": None,
        "candidates": deepcopy(candidates),
        "decision_reason": reason,
        "tie_detected": tie_detected,
        "fallback_used": None,
        "planner_version": PLANNER_VERSION,
    }
    return {
        "status": "rejected",
        "selected_pattern": None,
        "diagnostic": diagnostic,
        "error_code": code,
        "error_message": message,
    }


def _project_rules(
    rules: list[AgentRule],
    *,
    intent_name: str,
    required_rule_names: list[str],
) -> tuple[list[ProjectedRule], list[str]]:
    if not isinstance(rules, list):
        raise PlanningInputError("context.rules deve ser uma lista.")

    required_keys = {
        name.strip().casefold()
        for name in required_rule_names
        if isinstance(name, str) and name.strip()
    }
    seen_required: set[str] = set()
    projected_by_key: dict[str, ProjectedRule] = {}

    for rule in rules:
        if not isinstance(rule, Mapping):
            raise PlanningInputError(
                "context.rules contem item invalido."
            )

        rule_name = str(rule.get("rule_name", "")).strip()
        rule_key = rule_name.casefold()
        applies = [
            item
            for item in rule.get("applies_to_intents", [])
            if isinstance(item, str)
        ]
        selection_reasons: list[str] = []
        if rule_key in required_keys:
            selection_reasons.append("required_by_pattern")
            seen_required.add(rule_key)
        if any(_same_text(item, intent_name) for item in applies):
            selection_reasons.append("applies_to_intent")

        if not selection_reasons:
            continue

        projected_by_key[rule_key] = {
            "rule_group": str(rule.get("rule_group", "")),
            "rule_name": rule_name,
            "rule_content": deepcopy(rule.get("rule_content")),
            "applies_to_intents": list(applies),
            "validation_hint": deepcopy(rule.get("validation_hint")),
            "severity": str(rule.get("severity", "")),
            "priority": _optional_int(rule.get("priority")),
            "selection_reasons": sorted(set(selection_reasons)),
        }

    missing_rules = sorted(required_keys - seen_required)
    projected = sorted(
        projected_by_key.values(),
        key=lambda rule: (
            _priority_sort_value(rule.get("priority")),
            rule["rule_name"].casefold(),
        ),
    )
    return projected, missing_rules


def _detect_grouping_dimensions(
    *,
    context: ContextSnapshot,
    normalized_question: str,
    intent_resolution_result: Mapping[str, Any] | None = None,
) -> tuple[list[ProjectedDimension], dict[str, Any]]:
    evidence_terms = _grouping_terms_from_intent_evidence(
        intent_resolution_result,
    )
    evidence_dimensions: list[ProjectedDimension] = []
    evidence_unresolved: list[str] = []
    for matched_user_term, dimension_term in evidence_terms:
        dimension = _resolve_grouping_dimension(
            context=context,
            matched_user_term=matched_user_term,
            dimension_term=dimension_term,
            detection_source="intent_semantic_evidence",
        )
        if dimension is None:
            evidence_unresolved.append(dimension_term)
            continue
        evidence_dimensions.append(dimension)

    if evidence_dimensions:
        return _dedupe_dimensions(evidence_dimensions), {
            "grouping_requested": True,
            "matched_terms": [term for term, _ in evidence_terms],
            "unresolved_terms": sorted(
                set(evidence_unresolved),
                key=str.casefold,
            ),
            "source": "intent_semantic_evidence",
            "detection_source": "intent_semantic_evidence",
            "fallback_used": False,
        }

    requested_terms = _grouping_terms_from_context(
        context.get("intent_resolution", {}),
        normalized_question,
    )
    if not requested_terms:
        return [], {
            "grouping_requested": False,
            "matched_terms": [],
            "unresolved_terms": [],
            "source": "none",
            "fallback_used": False,
        }

    dimensions: list[ProjectedDimension] = []
    unresolved: list[str] = []
    for matched_user_term, dimension_term in requested_terms:
        dimension = _resolve_grouping_dimension(
            context=context,
            matched_user_term=matched_user_term,
            dimension_term=dimension_term,
            detection_source="planner_lexical_fallback",
        )
        if dimension is None:
            unresolved.append(dimension_term)
            continue
        dimensions.append(dimension)

    return _dedupe_dimensions(dimensions), {
        "grouping_requested": True,
        "matched_terms": [term for term, _ in requested_terms],
        "unresolved_terms": sorted(set(unresolved), key=str.casefold),
        "source": "planner_lexical_fallback",
        "detection_source": "planner_lexical_fallback",
        "fallback_used": True,
    }


def _grouping_terms_from_intent_evidence(
    intent_resolution_result: Mapping[str, Any] | None,
) -> list[tuple[str, str]]:
    if not isinstance(intent_resolution_result, Mapping):
        return []

    selected_intent = intent_resolution_result.get("intent")
    best_candidate = intent_resolution_result.get("best_candidate")
    candidates: list[Any] = []
    if isinstance(best_candidate, Mapping):
        candidates.append(best_candidate)
    candidates.extend(
        candidate
        for candidate in intent_resolution_result.get("candidates", [])
        if isinstance(candidate, Mapping)
        and (
            selected_intent is None
            or _same_text(candidate.get("intent_name"), selected_intent)
        )
    )

    matches: list[tuple[str, str]] = []
    for candidate in candidates:
        for match in candidate.get("matches", []):
            if not isinstance(match, Mapping):
                continue
            details = match.get("match_details")
            if not isinstance(details, Mapping):
                continue
            for concept in details.get("concepts", []):
                if not isinstance(concept, Mapping):
                    continue
                if str(concept.get("concept_name", "")).casefold() != (
                    "dimension_grouping"
                ):
                    continue
                if not concept.get("satisfied"):
                    continue
                matches.extend(
                    _grouping_terms_from_concept_evidence(concept)
                )
    return sorted(set(matches), key=lambda item: (item[1], item[0]))


def _grouping_terms_from_concept_evidence(
    concept: Mapping[str, Any],
) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for term in concept.get("terms", []):
        if not isinstance(term, Mapping) or not term.get("matched"):
            continue
        signal = _semantic_signal_from_term(term)
        if signal is None:
            continue
        matched_user_term = str(signal.get("normalized_term") or "").strip()
        dimension = _dimension_name_from_semantic_signal(signal)
        if matched_user_term and dimension:
            matches.append((matched_user_term, dimension))
    return matches


def _detect_analytical_operations(
    *,
    context: ContextSnapshot,
    intent_resolution_result: Mapping[str, Any] | None = None,
) -> tuple[list[ProjectedAnalyticalOperation], dict[str, Any]]:
    evidence_terms = _operation_terms_from_intent_evidence(
        intent_resolution_result,
    )
    operations: list[ProjectedAnalyticalOperation] = []
    unresolved: list[str] = []
    invalid_metadata: list[str] = []
    for matched_user_term in evidence_terms:
        operation = _resolve_analytical_operation(
            context.get("entities", []),
            matched_user_term=matched_user_term,
        )
        if operation is None:
            unresolved.append(matched_user_term)
            continue
        operations.append(operation)

    if not operations:
        return [], {
            "operation_requested": bool(evidence_terms),
            "matched_terms": sorted(set(evidence_terms), key=str.casefold),
            "unresolved_terms": sorted(set(unresolved), key=str.casefold),
            "invalid_metadata_terms": sorted(
                set(invalid_metadata),
                key=str.casefold,
            ),
            "source": "none" if not evidence_terms else "intent_semantic_evidence",
        }

    return _dedupe_analytical_operations(operations), {
        "operation_requested": True,
        "matched_terms": sorted(set(evidence_terms), key=str.casefold),
        "unresolved_terms": sorted(set(unresolved), key=str.casefold),
        "invalid_metadata_terms": sorted(
            set(invalid_metadata),
            key=str.casefold,
        ),
        "source": "intent_semantic_evidence",
        "detection_source": "intent_semantic_evidence",
    }


def _operation_terms_from_intent_evidence(
    intent_resolution_result: Mapping[str, Any] | None,
) -> list[str]:
    if not isinstance(intent_resolution_result, Mapping):
        return []

    selected_intent = intent_resolution_result.get("intent")
    candidates = _selected_intent_candidates(
        intent_resolution_result,
        selected_intent=selected_intent,
    )
    matches: list[str] = []
    for candidate in candidates:
        for concept in _concepts_from_candidate(candidate):
            if str(concept.get("concept_name", "")).casefold() != (
                "analytical_operation"
            ):
                continue
            if not concept.get("satisfied"):
                continue
            for term in concept.get("terms", []):
                if not isinstance(term, Mapping) or not term.get("matched"):
                    continue
                signal = _semantic_signal_from_term(term)
                matched = (
                    signal.get("normalized_term")
                    if isinstance(signal, Mapping)
                    else term.get("normalized_term")
                )
                if isinstance(matched, str) and matched.strip():
                    matches.append(matched.strip())
    return sorted(set(matches), key=str.casefold)


def _detect_planned_metrics(
    *,
    context: ContextSnapshot,
    intent_resolution_result: Mapping[str, Any] | None = None,
    selected_pattern: Mapping[str, Any] | None = None,
) -> tuple[list[ProjectedPlannedMetric], dict[str, Any]]:
    evidence_terms = _metric_terms_from_intent_evidence(
        intent_resolution_result,
    )
    binding_context_concepts = _binding_context_concepts_from_intent_evidence(
        intent_resolution_result,
        selected_pattern=selected_pattern,
    )
    operation_cardinality = _metric_binding_cardinality_from_operations(
        context=context,
        intent_resolution_result=intent_resolution_result,
    )
    metrics: list[ProjectedPlannedMetric] = []
    unresolved: list[str] = []
    invalid_metadata: list[str] = []
    failed_bindings: list[dict[str, Any]] = []
    inference_diagnostic: dict[str, Any] = {"status": "not_applicable"}
    for matched_user_term in evidence_terms:
        resolved_metrics, reason, diagnostic = _resolve_planned_metrics(
            context=context,
            matched_user_term=matched_user_term,
            binding_context_concepts=binding_context_concepts,
            cardinality=operation_cardinality,
        )
        if not resolved_metrics:
            if reason == "invalid_metadata":
                invalid_metadata.append(matched_user_term)
            else:
                unresolved.append(matched_user_term)
            if diagnostic:
                failed_bindings.append(diagnostic)
            continue
        metrics.extend(resolved_metrics)

    if (
        not evidence_terms
        and operation_cardinality.get("mode") == "multiple"
    ):
        inferred_metrics, inference_diagnostic = (
            _infer_planned_metrics_from_binding_context(
                context=context,
                binding_context_concepts=binding_context_concepts,
                cardinality=operation_cardinality,
            )
        )
        metrics.extend(inferred_metrics)
        if (
            inference_diagnostic.get("status")
            not in {"resolved", "not_applicable"}
        ):
            failed_bindings.append(inference_diagnostic)

    planned_metrics = _dedupe_planned_metrics(metrics)
    global_binding_status = "not_applicable"
    if any(
        metric.get("mapping_source") == "metric_binding"
        for metric in planned_metrics
    ):
        global_binding_status = _metric_binding_cardinality_status(
            planned_metrics,
            cardinality=operation_cardinality,
        )
        if global_binding_status != "resolved":
            failed_bindings.append(
                {
                    "status": global_binding_status,
                    "scope": "global",
                    "planned_metric_count": len(planned_metrics),
                    "cardinality": operation_cardinality,
                }
            )
            planned_metrics = []
    return planned_metrics, {
        "metric_requested": bool(evidence_terms),
        "matched_terms": sorted(set(evidence_terms), key=str.casefold),
        "unresolved_terms": sorted(set(unresolved), key=str.casefold),
        "invalid_metadata_terms": sorted(
            set(invalid_metadata),
            key=str.casefold,
        ),
        "source": (
            "intent_semantic_evidence"
            if evidence_terms
            else (
                "selected_pattern_context"
                if inference_diagnostic.get("status") == "resolved"
                else "none"
            )
        ),
        "detection_source": (
            "intent_semantic_evidence"
            if evidence_terms
            else (
                "selected_pattern_context"
                if inference_diagnostic.get("status") == "resolved"
                else "none"
            )
        ),
        "projected_count": len(planned_metrics),
        "binding_inference": inference_diagnostic,
        "binding_context_concepts": binding_context_concepts,
        "binding_cardinality": operation_cardinality,
        "global_binding_status": global_binding_status,
        "binding_failures": failed_bindings,
    }


def _metric_terms_from_intent_evidence(
    intent_resolution_result: Mapping[str, Any] | None,
) -> list[str]:
    if not isinstance(intent_resolution_result, Mapping):
        return []

    selected_intent = intent_resolution_result.get("intent")
    candidates = _selected_intent_candidates(
        intent_resolution_result,
        selected_intent=selected_intent,
    )
    matches: list[str] = []
    for candidate in candidates:
        for concept in _concepts_from_candidate(candidate):
            if str(concept.get("concept_name", "")).casefold() != (
                "financial_metric"
            ):
                continue
            if not concept.get("satisfied"):
                continue
            for term in concept.get("terms", []):
                if not isinstance(term, Mapping) or not term.get("matched"):
                    continue
                signal = _semantic_signal_from_term(term)
                matched = (
                    signal.get("normalized_term")
                    if isinstance(signal, Mapping)
                    else term.get("normalized_term")
                )
                if isinstance(matched, str) and matched.strip():
                    matches.append(matched.strip())
    return sorted(set(matches), key=str.casefold)


def _binding_context_concepts_from_intent_evidence(
    intent_resolution_result: Mapping[str, Any] | None,
    *,
    selected_pattern: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(intent_resolution_result, Mapping):
        return []

    selected_intent = intent_resolution_result.get("intent")
    candidates = _selected_intent_candidates(
        intent_resolution_result,
        selected_intent=selected_intent,
    )
    concepts: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        for concept in _concepts_from_candidate(candidate):
            if not concept.get("satisfied"):
                continue
            concept_name = str(concept.get("concept_name", "")).strip()
            if not concept_name:
                continue
            key = concept_name.casefold()
            if key in concepts:
                continue
            sources = _semantic_sources_from_concept(concept)
            concepts[key] = {
                "concept_name": concept_name,
                "sources": sources,
            }

    if isinstance(selected_pattern, Mapping):
        required_rules = selected_pattern.get("required_rules")
        if isinstance(required_rules, list):
            for rule_name in required_rules:
                if not isinstance(rule_name, str) or not rule_name.strip():
                    continue
                name = rule_name.strip()
                concepts.setdefault(
                    name.casefold(),
                    {
                        "concept_name": name,
                        "sources": ["selected_pattern_required_rule"],
                    },
                )

    semantic_defaults = intent_resolution_result.get(
        "semantic_default_concepts",
        [],
    )
    if isinstance(semantic_defaults, list):
        for item in semantic_defaults:
            if not isinstance(item, Mapping):
                continue
            concept_name = str(item.get("concept_name", "")).strip()
            if not concept_name:
                continue
            key = concept_name.casefold()
            concepts.setdefault(
                key,
                {
                    "concept_name": concept_name,
                    "sources": ["semantic_default"],
                },
            )

    return [
        concepts[key]
        for key in sorted(concepts, key=str.casefold)
    ]


def _detect_planned_filters(
    *,
    context: ContextSnapshot,
    intent_resolution_result: Mapping[str, Any] | None,
) -> tuple[list[ProjectedPlannedFilter], dict[str, Any]]:
    """Resolve obrigacoes de filtro sem copiar detalhes fisicos ao plano."""

    evidence_terms = _matched_semantic_terms(intent_resolution_result)
    aliases = _filter_concept_aliases(context.get("entities", []))
    detected: dict[str, tuple[str, str]] = {}
    for term in evidence_terms:
        concept = aliases.get(normalize_search_text(term))
        if concept is not None:
            detected.setdefault(concept.casefold(), (concept, term))

    planned: list[ProjectedPlannedFilter] = []
    unresolved: list[dict[str, str]] = []
    for concept, matched_term in sorted(
        detected.values(),
        key=lambda item: (item[0].casefold(), item[1].casefold()),
    ):
        bindings = _filter_bindings_for_concept(
            context.get("entities", []),
            filter_concept=concept,
        )
        if len(bindings) != 1:
            unresolved.append(
                {
                    "filter_concept": concept,
                    "matched_user_term": matched_term,
                    "reason": (
                        "binding_not_found"
                        if not bindings
                        else "binding_ambiguous"
                    ),
                }
            )
            continue
        binding = bindings[0]
        binding_ref = binding["binding_ref"]
        planned.append(
            {
                "filter_ref": f"filter-{binding_ref}",
                "filter_concept": concept,
                "binding_ref": binding_ref,
                "required": binding["required"],
                "scope": binding["scope"],
                "detection_source": "intent_semantic_evidence",
                "mapping_source": "filter_binding",
                "matched_user_term": matched_term,
                "provenance": {
                    "context_version": str(context.get("version", "")),
                    "binding_source": "entity_alias",
                },
            }
        )

    return planned, {
        "status": "resolved" if planned and not unresolved else (
            "unresolved" if unresolved else "not_applicable"
        ),
        "detected_concepts": sorted(
            (item[0] for item in detected.values()),
            key=str.casefold,
        ),
        "unresolved": unresolved,
    }


def _matched_semantic_terms(
    intent_resolution_result: Mapping[str, Any] | None,
) -> list[str]:
    if not isinstance(intent_resolution_result, Mapping):
        return []
    candidates = _selected_intent_candidates(
        intent_resolution_result,
        selected_intent=intent_resolution_result.get("intent"),
    )
    terms: set[str] = set()
    for candidate in candidates:
        for concept in _concepts_from_candidate(candidate):
            if not concept.get("satisfied"):
                continue
            for term in concept.get("terms", []):
                if not isinstance(term, Mapping) or not term.get("matched"):
                    continue
                signal = _semantic_signal_from_term(term)
                value = (
                    signal.get("normalized_term")
                    if isinstance(signal, Mapping)
                    else term.get("normalized_term")
                )
                if isinstance(value, str) and value.strip():
                    terms.add(value.strip())
    return sorted(terms, key=lambda item: normalize_search_text(item))


def _filter_concept_aliases(entities: Any) -> dict[str, str]:
    if not isinstance(entities, list):
        return {}
    aliases: dict[str, str] = {}
    ambiguous: set[str] = set()
    for entity in entities:
        if not isinstance(entity, Mapping) or str(
            entity.get("entity_type", "")
        ).casefold() != "filter_concept":
            continue
        term = str(entity.get("user_term", "")).strip()
        concept = str(entity.get("canonical_value", "")).strip()
        key = normalize_search_text(term)
        if not key or not concept:
            continue
        previous = aliases.get(key)
        if previous is not None and not _same_text(previous, concept):
            ambiguous.add(key)
        else:
            aliases[key] = concept
    for key in ambiguous:
        aliases.pop(key, None)
    return aliases


def _filter_bindings_for_concept(
    entities: Any,
    *,
    filter_concept: str,
) -> list[dict[str, Any]]:
    if not isinstance(entities, list):
        return []
    bindings: list[dict[str, Any]] = []
    for entity in entities:
        if not isinstance(entity, Mapping) or str(
            entity.get("entity_type", "")
        ).casefold() != "filter_binding":
            continue
        rule = entity.get("business_rule")
        raw = rule.get("filter_binding") if isinstance(rule, Mapping) else None
        if not isinstance(raw, Mapping):
            continue
        concept = _non_empty_text(raw.get("filter_concept"))
        canonical_value = _non_empty_text(entity.get("canonical_value"))
        binding_ref = _non_empty_text(raw.get("binding_ref"))
        scope = _non_empty_text(raw.get("scope"))
        if not (
            concept is not None
            and canonical_value is not None
            and binding_ref is not None
            and scope is not None
            and _same_text(concept, filter_concept)
            and _same_text(canonical_value, concept)
        ):
            continue
        # A obrigacao so referencia bindings fisicos completos e versionados.
        if not (
            _non_empty_text(raw.get("target_table")) is not None
            and _non_empty_text(raw.get("target_column")) is not None
            and _non_empty_text(raw.get("operator")) is not None
            and isinstance(raw.get("required"), bool)
            and _valid_filter_binding_value(
                _non_empty_text(raw.get("operator")),
                raw.get("value"),
            )
            and _is_valid_join_path(raw.get("join_path"))
        ):
            continue
        bindings.append(
            {
                "binding_ref": binding_ref,
                "required": raw["required"],
                "scope": scope,
            }
        )
    return sorted(
        bindings,
        key=lambda binding: (
            binding["binding_ref"].casefold(),
            binding["binding_ref"],
        ),
    )


def _project_resolved_filter_bindings(
    *,
    entities: Any,
    planned_filters: list[ProjectedPlannedFilter],
) -> list[ProjectedFilterBinding]:
    if not isinstance(entities, list):
        return []
    referenced = {
        str(item.get("binding_ref", "")).strip().casefold(): item
        for item in planned_filters
        if isinstance(item, Mapping)
        and isinstance(item.get("binding_ref"), str)
        and item["binding_ref"].strip()
    }
    candidates: dict[str, list[ProjectedFilterBinding]] = {
        key: [] for key in referenced
    }
    for entity in entities:
        if not isinstance(entity, Mapping) or str(
            entity.get("entity_type", "")
        ).casefold() != "filter_binding":
            continue
        rule = entity.get("business_rule")
        raw = rule.get("filter_binding") if isinstance(rule, Mapping) else None
        if not isinstance(raw, Mapping):
            continue
        binding_ref = _non_empty_text(raw.get("binding_ref"))
        if binding_ref is None or binding_ref.casefold() not in referenced:
            continue
        filter_concept = _non_empty_text(raw.get("filter_concept"))
        target_table = _non_empty_text(raw.get("target_table"))
        target_column = _non_empty_text(raw.get("target_column"))
        operator = _non_empty_text(raw.get("operator"))
        scope = _non_empty_text(raw.get("scope"))
        required = raw.get("required")
        value = raw.get("value")
        join_path = raw.get("join_path")
        if not (
            filter_concept
            and target_table
            and target_column
            and operator
            and scope
            and isinstance(required, bool)
            and _valid_filter_binding_value(operator, value)
            and _is_valid_join_path(join_path)
        ):
            continue
        planned = referenced[binding_ref.casefold()]
        if not (
            _same_text(planned.get("filter_concept"), filter_concept)
            and _same_text(planned.get("scope"), scope)
            and planned.get("required") is required
        ):
            continue
        candidates[binding_ref.casefold()].append(
            {
                "binding_ref": binding_ref,
                "filter_concept": filter_concept,
                "target_table": target_table,
                "target_column": target_column,
                "operator": operator,
                "value": deepcopy(value),
                "join_path": deepcopy(join_path),
                "required": required,
                "scope": scope,
            }
        )
    output: list[ProjectedFilterBinding] = []
    for key in sorted(candidates):
        if len(candidates[key]) == 1:
            output.append(candidates[key][0])
    return output


def _non_empty_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _is_filled_json_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, bool) or isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return bool(value) and all(_is_filled_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return bool(value) and all(
            _non_empty_text(key) is not None and _is_filled_json_value(item)
            for key, item in value.items()
        )
    return False


def _valid_filter_binding_value(
    operator: str | None,
    value: Any,
) -> bool:
    if operator is None:
        return False
    normalized = operator.casefold()
    if normalized == "in":
        if not isinstance(value, list) or not value:
            return False
        literal_types = [_filter_literal_type(item) for item in value]
        if any(item is None for item in literal_types):
            return False
        if len(set(literal_types)) != 1:
            return False
        identities = [(_filter_literal_type(item), item) for item in value]
        return len(identities) == len(set(identities))
    if isinstance(value, list):
        return False
    return _is_filled_json_value(value)


def _filter_literal_type(value: Any) -> str | None:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string" if value.strip() else None
    if isinstance(value, int):
        return "number"
    if isinstance(value, float):
        return "number" if math.isfinite(value) else None
    return None


def _is_valid_join_path(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return all(
        isinstance(step, Mapping)
        and bool(step)
        and all(
            _non_empty_text(key) is not None and _is_filled_json_value(item)
            for key, item in step.items()
        )
        for step in value
    )


def _semantic_sources_from_concept(
    concept: Mapping[str, Any],
) -> list[str]:
    sources: set[str] = set()
    for signal in concept.get("semantic_signals", []):
        if not isinstance(signal, Mapping):
            continue
        source = signal.get("source")
        if isinstance(source, str) and source.strip():
            sources.add(source.strip())
    return sorted(sources, key=str.casefold)


def _metric_binding_cardinality_from_operations(
    *,
    context: ContextSnapshot,
    intent_resolution_result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    evidence_terms = _operation_terms_from_intent_evidence(
        intent_resolution_result,
    )
    cardinalities: list[dict[str, Any]] = []
    for matched_user_term in evidence_terms:
        operation = _resolve_analytical_operation(
            context.get("entities", []),
            matched_user_term=matched_user_term,
        )
        if operation is None:
            continue
        cardinality = operation.get("binding_cardinality")
        if isinstance(cardinality, Mapping):
            cardinalities.append(dict(cardinality))
    if not cardinalities:
        return _default_binding_cardinality()
    deduped = _dedupe_cardinalities(cardinalities)
    if len(deduped) == 1:
        return deduped[0]
    return {
        "mode": "single",
        "minimum": 1,
        "maximum": 1,
        "same_metric_concept": True,
        "distinct_bindings": True,
        "status": "conflicting_operation_cardinality",
    }


def _dedupe_cardinalities(
    cardinalities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in cardinalities:
        key = (
            item.get("mode"),
            item.get("minimum"),
            item.get("maximum"),
            item.get("same_metric_concept"),
            item.get("distinct_bindings"),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _resolve_planned_metrics(
    *,
    context: ContextSnapshot,
    matched_user_term: str,
    binding_context_concepts: list[dict[str, Any]],
    cardinality: dict[str, Any],
) -> tuple[list[ProjectedPlannedMetric], str, dict[str, Any]]:
    entities = context.get("entities", [])
    if not isinstance(entities, list):
        return [], "unresolved", {}
    normalized_term = normalize_search_text(matched_user_term)
    table_catalog = context.get("table_catalog", [])
    legacy_candidates: list[tuple[float, ProjectedPlannedMetric]] = []
    invalid_seen = False
    metric_concepts: set[str] = set()
    for entity in entities:
        if not isinstance(entity, Mapping):
            continue
        if str(entity.get("entity_type", "")).casefold() != (
            "financial_metric"
        ):
            continue
        user_term = str(entity.get("user_term", "")).strip()
        if normalize_search_text(user_term) != normalized_term:
            continue
        metric = _metric_metadata(entity.get("business_rule"))
        if metric is None:
            invalid_seen = True
            continue
        canonical_value = str(entity.get("canonical_value", "")).strip()
        if canonical_value:
            metric_concepts.add(canonical_value)
        target_table = str(entity.get("target_table", "")).strip()
        target_column = str(entity.get("target_column", "")).strip()
        if not (
            canonical_value
            and metric["metric_concept"] == canonical_value
            and target_table
            and target_column
            and metric["target_table"] == target_table
            and metric["target_column"] == target_column
            and _metric_column_allowed(
                table_catalog,
                target_table=target_table,
                target_column=target_column,
            )
        ):
            invalid_seen = True
            continue
        priority = _optional_int(entity.get("priority"))
        legacy_candidates.append(
            (
                _priority_sort_value(priority),
                {
                    "metric_ref": _metric_ref(
                        metric_concept=canonical_value,
                        target_table=target_table,
                        target_column=target_column,
                    ),
                    "metric_concept": canonical_value,
                    "target_table": target_table,
                    "target_column": target_column,
                    "aggregate": None,
                    "detection_source": "intent_semantic_evidence",
                    "mapping_source": "entity_alias",
                    "matched_user_term": matched_user_term,
                    "priority": priority,
                },
            )
        )
    if not metric_concepts:
        return [], "invalid_metadata" if invalid_seen else "unresolved", {}

    binding_metrics: list[ProjectedPlannedMetric] = []
    binding_diagnostics: list[dict[str, Any]] = []
    for metric_concept in sorted(metric_concepts, key=str.casefold):
        resolved, diagnostic = _resolve_metric_bindings(
            context=context,
            metric_concept=metric_concept,
            matched_user_term=matched_user_term,
            binding_context_concepts=binding_context_concepts,
            cardinality=cardinality,
        )
        binding_diagnostics.append(diagnostic)
        binding_metrics.extend(resolved)

    if any(
        diagnostic.get("configured_count", 0) > 0
        for diagnostic in binding_diagnostics
    ):
        if binding_metrics:
            return binding_metrics, "resolved", {
                "matched_user_term": matched_user_term,
                "binding_diagnostics": binding_diagnostics,
            }
        return [], "invalid_metadata", {
            "matched_user_term": matched_user_term,
            "binding_diagnostics": binding_diagnostics,
        }

    if not legacy_candidates:
        return [], "invalid_metadata" if invalid_seen else "unresolved", {}
    return [
        sorted(
            legacy_candidates,
            key=lambda item: (
                item[0],
                item[1]["metric_concept"].casefold(),
                item[1]["target_table"].casefold(),
                item[1]["target_column"].casefold(),
            ),
        )[0][1]
    ], "resolved", {}


def _infer_planned_metrics_from_binding_context(
    *,
    context: ContextSnapshot,
    binding_context_concepts: list[dict[str, Any]],
    cardinality: dict[str, Any],
) -> tuple[list[ProjectedPlannedMetric], dict[str, Any]]:
    metric_concepts: set[str] = set()
    for entity in context.get("entities", []):
        if not isinstance(entity, Mapping):
            continue
        if str(entity.get("entity_type", "")).casefold() != "metric_binding":
            continue
        binding, _reason = _metric_binding_metadata(
            entity,
            table_catalog=context.get("table_catalog", []),
        )
        if binding is not None:
            metric_concepts.add(binding["metric_concept"])

    resolved_by_concept: list[
        tuple[str, list[ProjectedPlannedMetric], dict[str, Any]]
    ] = []
    diagnostics: list[dict[str, Any]] = []
    for metric_concept in sorted(metric_concepts, key=str.casefold):
        resolved, diagnostic = _resolve_metric_bindings(
            context=context,
            metric_concept=metric_concept,
            matched_user_term=metric_concept,
            binding_context_concepts=binding_context_concepts,
            cardinality=cardinality,
        )
        diagnostics.append(diagnostic)
        if resolved:
            inferred = deepcopy(resolved)
            for metric in inferred:
                metric["detection_source"] = "selected_pattern_context"
            resolved_by_concept.append(
                (metric_concept, inferred, diagnostic)
            )

    if not resolved_by_concept:
        return [], {
            "status": "not_applicable",
            "candidate_metric_concepts": sorted(
                metric_concepts,
                key=str.casefold,
            ),
            "binding_diagnostics": diagnostics,
        }
    if len(resolved_by_concept) != 1:
        return [], {
            "status": "ambiguous_metric_concept",
            "candidate_metric_concepts": [
                item[0] for item in resolved_by_concept
            ],
            "binding_diagnostics": diagnostics,
        }

    metric_concept, metrics, _diagnostic = resolved_by_concept[0]
    return metrics, {
        "status": "resolved",
        "metric_concept": metric_concept,
        "projected_count": len(metrics),
        "binding_diagnostics": diagnostics,
    }


def _resolve_metric_bindings(
    *,
    context: ContextSnapshot,
    metric_concept: str,
    matched_user_term: str,
    binding_context_concepts: list[dict[str, Any]],
    cardinality: dict[str, Any],
) -> tuple[list[ProjectedPlannedMetric], dict[str, Any]]:
    concepts_present = {
        item["concept_name"].casefold()
        for item in binding_context_concepts
        if isinstance(item.get("concept_name"), str)
    }
    configured: list[dict[str, Any]] = []
    configured_count = 0
    applicable: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for entity in context.get("entities", []):
        if not isinstance(entity, Mapping):
            continue
        if str(entity.get("entity_type", "")).casefold() == "metric_binding":
            canonical_value = str(entity.get("canonical_value", "")).strip()
            if _same_text(canonical_value, metric_concept):
                configured_count += 1
        binding, reason = _metric_binding_metadata(
            entity,
            table_catalog=context.get("table_catalog", []),
        )
        if binding is None:
            if (
                str(entity.get("entity_type", "")).casefold()
                == "metric_binding"
            ):
                rejected.append(
                    {
                        "binding_ref": None,
                        "reason": reason,
                        "user_term": entity.get("user_term"),
                    }
                )
            continue
        if not _same_text(binding["metric_concept"], metric_concept):
            continue
        configured.append(binding)
        missing_present = sorted(
            set(binding["when_present"]) - concepts_present,
            key=str.casefold,
        )
        blocked_absent = sorted(
            set(binding["when_absent"]) & concepts_present,
            key=str.casefold,
        )
        if missing_present or blocked_absent:
            rejected.append(
                {
                    "binding_ref": binding["binding_ref"],
                    "reason": (
                        "when_present_missing"
                        if missing_present
                        else "when_absent_present"
                    ),
                    "missing_present": missing_present,
                    "blocked_absent": blocked_absent,
                }
            )
            continue
        applicable.append(binding)

    deduped_applicable = _dedupe_metric_bindings(applicable)
    metrics: list[ProjectedPlannedMetric] = []
    status = _metric_binding_cardinality_status(
        deduped_applicable,
        cardinality=cardinality,
    )
    if status == "resolved":
        metrics = [
            _planned_metric_from_binding(
                binding,
                matched_user_term=matched_user_term,
            )
            for binding in _sort_metric_bindings(deduped_applicable)
        ]
    return metrics, {
        "metric_concept": metric_concept,
        "configured_count": configured_count,
        "applicable_count": len(deduped_applicable),
        "status": status,
        "cardinality": deepcopy(cardinality),
        "applicable": [
            _metric_binding_diagnostic(binding)
            for binding in _sort_metric_bindings(deduped_applicable)
        ],
        "rejected": rejected,
    }


def _metric_binding_metadata(
    entity: Mapping[str, Any],
    *,
    table_catalog: Any,
) -> tuple[dict[str, Any] | None, str]:
    if str(entity.get("entity_type", "")).casefold() != "metric_binding":
        return None, "not_metric_binding"
    canonical_value = str(entity.get("canonical_value", "")).strip()
    target_table = str(entity.get("target_table", "")).strip()
    target_column = str(entity.get("target_column", "")).strip()
    metric_binding = _metric_binding_rule(entity.get("business_rule"))
    if metric_binding is None:
        return None, "invalid_metadata"
    if not (
        canonical_value
        and metric_binding["metric_concept"] == canonical_value
        and target_table
        and target_column
        and metric_binding["target_table"] == target_table
        and metric_binding["target_column"] == target_column
        and _metric_column_allowed(
            table_catalog,
            target_table=target_table,
            target_column=target_column,
        )
    ):
        return None, "invalid_physical_target"
    priority = _optional_int(entity.get("priority"))
    binding_ref = _binding_ref(
        metric_concept=canonical_value,
        target_table=target_table,
        target_column=target_column,
        when_present=metric_binding["when_present"],
        when_absent=metric_binding["when_absent"],
    )
    return {
        "binding_ref": binding_ref,
        "metric_concept": canonical_value,
        "target_table": target_table,
        "target_column": target_column,
        "aggregate": None,
        "when_present": metric_binding["when_present"],
        "when_absent": metric_binding["when_absent"],
        "priority": priority,
        "user_term": entity.get("user_term"),
    }, "resolved"


def _metric_binding_rule(
    business_rule: Any,
) -> dict[str, Any] | None:
    if not isinstance(business_rule, Mapping):
        return None
    binding = business_rule.get("metric_binding")
    if not isinstance(binding, Mapping):
        return None
    if binding.get("aggregate") is not None:
        return None
    metric_concept = str(binding.get("metric_concept", "")).strip()
    target_table = str(binding.get("target_table", "")).strip()
    target_column = str(binding.get("target_column", "")).strip()
    when_present = _concept_condition_list(binding.get("when_present"))
    when_absent = _concept_condition_list(
        binding.get("when_absent"),
        allow_empty=True,
    )
    if not (
        metric_concept
        and target_table
        and target_column
        and when_present
        and when_absent is not None
    ):
        return None
    if set(when_present) & set(when_absent):
        return None
    return {
        "metric_concept": metric_concept,
        "target_table": target_table,
        "target_column": target_column,
        "when_present": when_present,
        "when_absent": when_absent,
    }


def _concept_condition_list(
    value: Any,
    *,
    allow_empty: bool = False,
) -> list[str] | None:
    if not isinstance(value, list):
        return None
    output: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return None
        concept = item.strip()
        key = concept.casefold()
        if key in seen:
            return None
        seen.add(key)
        output.append(concept)
    if not output and not allow_empty:
        return None
    return output


def _metric_binding_cardinality_status(
    bindings: list[dict[str, Any]],
    *,
    cardinality: Mapping[str, Any],
) -> str:
    mode = cardinality.get("mode", "single")
    minimum = cardinality.get("minimum", 1)
    maximum = cardinality.get("maximum", 1)
    if cardinality.get("status") == "conflicting_operation_cardinality":
        return "metric_binding_cardinality_conflict"
    if mode == "single":
        if not bindings:
            return "metric_binding_not_applicable"
        if len(bindings) == 1:
            return "resolved"
        return "metric_binding_ambiguous"
    if len(bindings) < minimum:
        return "metric_binding_below_minimum"
    if len(bindings) > maximum:
        return "metric_binding_above_maximum"
    if cardinality.get("distinct_bindings") is True:
        refs = [
            str(binding.get("binding_ref", "")).strip().casefold()
            for binding in bindings
        ]
        if not all(refs):
            return "metric_binding_ref_missing"
        if len(refs) != len(set(refs)):
            return "metric_binding_duplicate_ref"
    if cardinality.get("same_metric_concept") is True:
        concepts = {
            binding["metric_concept"].casefold()
            for binding in bindings
        }
        if len(concepts) > 1:
            return "metric_binding_concept_mismatch"
    return "resolved"


def _dedupe_metric_bindings(
    bindings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for binding in _sort_metric_bindings(bindings):
        key = binding["binding_ref"].casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(binding)
    return output


def _sort_metric_bindings(
    bindings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        bindings,
        key=lambda binding: (
            _priority_sort_value(binding.get("priority")),
            binding["binding_ref"].casefold(),
            binding["target_table"].casefold(),
            binding["target_column"].casefold(),
        ),
    )


def _planned_metric_from_binding(
    binding: Mapping[str, Any],
    *,
    matched_user_term: str,
) -> ProjectedPlannedMetric:
    return {
        "metric_ref": _metric_ref(
            metric_concept=binding["metric_concept"],
            target_table=binding["target_table"],
            target_column=binding["target_column"],
        ),
        "metric_concept": binding["metric_concept"],
        "target_table": binding["target_table"],
        "target_column": binding["target_column"],
        "aggregate": None,
        "detection_source": "intent_semantic_evidence",
        "mapping_source": "metric_binding",
        "matched_user_term": matched_user_term,
        "priority": binding.get("priority"),
        "binding_ref": binding["binding_ref"],
        "binding_conditions": {
            "when_present": list(binding["when_present"]),
            "when_absent": list(binding["when_absent"]),
        },
        "binding_source": "entity_alias",
    }


def _metric_binding_diagnostic(
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "binding_ref": binding.get("binding_ref"),
        "target_table": binding.get("target_table"),
        "target_column": binding.get("target_column"),
        "when_present": list(binding.get("when_present", [])),
        "when_absent": list(binding.get("when_absent", [])),
        "priority": binding.get("priority"),
    }


def _metric_metadata(
    business_rule: Any,
) -> dict[str, str] | None:
    if not isinstance(business_rule, Mapping):
        return None
    metric = business_rule.get("metric")
    if not isinstance(metric, Mapping):
        return None
    if metric.get("aggregate") is not None:
        return None
    metric_concept = str(metric.get("metric_concept", "")).strip()
    target_table = str(metric.get("target_table", "")).strip()
    target_column = str(metric.get("target_column", "")).strip()
    if not (metric_concept and target_table and target_column):
        return None
    return {
        "metric_concept": metric_concept,
        "target_table": target_table,
        "target_column": target_column,
    }


def _metric_column_allowed(
    table_catalog: Any,
    *,
    target_table: str,
    target_column: str,
) -> bool:
    if not isinstance(table_catalog, list):
        return False
    for table in table_catalog:
        if not isinstance(table, Mapping):
            continue
        if not _same_text(_qualified_table_name(table), target_table):
            continue
        return target_column in _string_list(table.get("metric_columns"))
    return False


def _metric_ref(
    *,
    metric_concept: str,
    target_table: str,
    target_column: str,
) -> str:
    payload = "|".join((metric_concept, target_table, target_column))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"metric-{digest}"


def _binding_ref(
    *,
    metric_concept: str,
    target_table: str,
    target_column: str,
    when_present: list[str],
    when_absent: list[str],
) -> str:
    payload = "|".join(
        (
            metric_concept,
            target_table,
            target_column,
            ",".join(sorted(when_present, key=str.casefold)),
            ",".join(sorted(when_absent, key=str.casefold)),
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"binding-{digest}"


def _bind_metrics_to_analytical_operations(
    *,
    operations: list[ProjectedAnalyticalOperation],
    planned_metrics: list[ProjectedPlannedMetric],
) -> tuple[list[ProjectedAnalyticalOperation], dict[str, Any]]:
    if not operations:
        return operations, {
            "binding_required": False,
            "status": "not_applicable",
        }
    if (
        len(planned_metrics) != 1
        and not any(
            metric.get("mapping_source") == "metric_binding"
            for metric in planned_metrics
        )
    ):
        return deepcopy(operations), {
            "binding_required": True,
            "status": (
                "metric_absent" if not planned_metrics else "metric_ambiguous"
            ),
            "planned_metric_count": len(planned_metrics),
        }
    bound: list[ProjectedAnalyticalOperation] = []
    diagnostics: list[dict[str, Any]] = []
    for operation in operations:
        item = deepcopy(operation)
        if item.get("operation_type") == "ranking":
            cardinality = operation.get("binding_cardinality")
            if not isinstance(cardinality, Mapping):
                cardinality = _default_binding_cardinality()
            status = _metric_binding_cardinality_status(
                planned_metrics,
                cardinality=cardinality,
            )
            diagnostics.append(
                {
                    "operation_type": "ranking",
                    "status": status,
                    "planned_metric_count": len(planned_metrics),
                    "cardinality": dict(cardinality),
                }
            )
            if status == "resolved" and len(planned_metrics) == 1:
                metric_ref = planned_metrics[0].get("metric_ref")
                if isinstance(metric_ref, str) and metric_ref.strip():
                    item["metric_ref"] = metric_ref
        elif item.get("operation_type") == "comparison":
            cardinality = operation.get("binding_cardinality")
            if not isinstance(cardinality, Mapping):
                cardinality = _default_binding_cardinality()
            status = _metric_binding_cardinality_status(
                planned_metrics,
                cardinality=cardinality,
            )
            diagnostics.append(
                {
                    "operation_type": "comparison",
                    "status": status,
                    "planned_metric_count": len(planned_metrics),
                    "cardinality": dict(cardinality),
                }
            )
            if status == "resolved":
                metric_refs = _operand_metric_refs(planned_metrics)
                if len(metric_refs) == len(planned_metrics):
                    item["operand_metric_refs"] = metric_refs
                    item["multiple_metric_sources"] = (
                        len(_metric_source_tables(planned_metrics)) > 1
                    )
        bound.append(item)
    return bound, {
        "binding_required": True,
        "status": (
            "bound"
            if all(item["status"] == "resolved" for item in diagnostics)
            else "not_bound"
        ),
        "planned_metric_count": len(planned_metrics),
        "operations": diagnostics,
    }


def _operand_metric_refs(
    planned_metrics: list[ProjectedPlannedMetric],
) -> list[str]:
    refs = [
        metric["metric_ref"]
        for metric in planned_metrics
        if isinstance(metric.get("metric_ref"), str)
        and metric["metric_ref"].strip()
    ]
    return sorted(set(refs), key=str.casefold)


def _validate_comparison_dimension_compatibility(
    *,
    operations: list[ProjectedAnalyticalOperation],
    planned_metrics: list[ProjectedPlannedMetric],
    dimensions: list[ProjectedDimension],
    required_tables: list[ProjectedTable],
    authorized_joins: list[ProjectedJoin],
) -> tuple[list[ProjectedAnalyticalOperation], dict[str, Any]]:
    comparison_operations = [
        operation
        for operation in operations
        if operation.get("operation_type") == "comparison"
    ]
    if not comparison_operations:
        return operations, {"status": "not_applicable"}
    if not dimensions:
        return operations, {
            "status": "passed",
            "reason": "no_grouping_dimensions",
        }

    graph = _authorized_join_graph(required_tables, authorized_joins)
    failures: list[dict[str, Any]] = []
    for metric in planned_metrics:
        metric_table = str(metric.get("target_table", "")).strip()
        metric_ref = str(metric.get("metric_ref", "")).strip()
        if not metric_table or not metric_ref:
            failures.append(
                {
                    "metric_ref": metric_ref,
                    "target_table": metric_table,
                    "reason": "metric_target_incomplete",
                }
            )
            continue
        for dimension in dimensions:
            dimension_table = str(dimension.get("target_table", "")).strip()
            if not dimension_table:
                failures.append(
                    {
                        "metric_ref": metric_ref,
                        "dimension": dimension.get("canonical_value"),
                        "reason": "dimension_target_incomplete",
                    }
                )
                continue
            if not _tables_connected(
                graph,
                source=metric_table,
                target=dimension_table,
            ):
                failures.append(
                    {
                        "metric_ref": metric_ref,
                        "metric_table": metric_table,
                        "dimension": dimension.get("canonical_value"),
                        "dimension_table": dimension_table,
                        "reason": "dimension_unreachable",
                    }
                )

    if failures:
        return _drop_comparison_operand_refs(operations), {
            "status": "failed",
            "failures": failures,
        }
    return operations, {
        "status": "passed",
        "checked_metric_count": len(planned_metrics),
        "checked_dimension_count": len(dimensions),
    }


def _drop_comparison_operand_refs(
    operations: list[ProjectedAnalyticalOperation],
) -> list[ProjectedAnalyticalOperation]:
    output: list[ProjectedAnalyticalOperation] = []
    for operation in operations:
        item = deepcopy(operation)
        if item.get("operation_type") == "comparison":
            item.pop("operand_metric_refs", None)
            item.pop("multiple_metric_sources", None)
        output.append(item)
    return output


def _authorized_join_graph(
    required_tables: list[ProjectedTable],
    authorized_joins: list[ProjectedJoin],
) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    table_lookup = _table_reference_lookup(required_tables)
    for table in required_tables:
        qualified = table["qualified_name"].casefold()
        graph.setdefault(qualified, set())
    for join in authorized_joins:
        source = str(join.get("source_table", "")).strip().casefold()
        if not source:
            continue
        graph.setdefault(source, set())
        raw_rules = join.get("join_rules")
        if not isinstance(raw_rules, list):
            continue
        for rule in raw_rules:
            if not isinstance(rule, Mapping):
                continue
            for reference in _extract_table_references(rule):
                target = table_lookup.get(reference.casefold())
                if not target:
                    continue
                graph.setdefault(target, set())
                graph[source].add(target)
                graph[target].add(source)
    return graph


def _table_reference_lookup(
    tables: list[ProjectedTable],
) -> dict[str, str]:
    output: dict[str, str] = {}
    for table in tables:
        qualified = table["qualified_name"].casefold()
        bare = table["table_name"].casefold()
        output[qualified] = qualified
        output[bare] = qualified
    return output


def _tables_connected(
    graph: Mapping[str, set[str]],
    *,
    source: str,
    target: str,
) -> bool:
    source_key = source.casefold()
    target_key = target.casefold()
    if source_key == target_key:
        return True
    if source_key not in graph or target_key not in graph:
        return False
    visited: set[str] = set()
    pending = [source_key]
    while pending:
        current = pending.pop()
        if current == target_key:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(sorted(graph.get(current, set()) - visited))
    return False


def _metric_source_tables(
    planned_metrics: list[ProjectedPlannedMetric],
) -> set[str]:
    return {
        metric["target_table"].casefold()
        for metric in planned_metrics
        if isinstance(metric.get("target_table"), str)
        and metric["target_table"].strip()
    }


def _selected_intent_candidates(
    intent_resolution_result: Mapping[str, Any],
    *,
    selected_intent: Any,
) -> list[Mapping[str, Any]]:
    candidates: list[Mapping[str, Any]] = []
    best_candidate = intent_resolution_result.get("best_candidate")
    if isinstance(best_candidate, Mapping):
        candidates.append(best_candidate)
    candidates.extend(
        candidate
        for candidate in intent_resolution_result.get("candidates", [])
        if isinstance(candidate, Mapping)
        and (
            selected_intent is None
            or _same_text(candidate.get("intent_name"), selected_intent)
        )
    )
    return candidates


def _concepts_from_candidate(
    candidate: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    concepts: list[Mapping[str, Any]] = []
    for match in candidate.get("matches", []):
        if not isinstance(match, Mapping):
            continue
        details = match.get("match_details")
        if not isinstance(details, Mapping):
            continue
        for concept in details.get("concepts", []):
            if isinstance(concept, Mapping):
                concepts.append(concept)
    return concepts


def _resolve_analytical_operation(
    entities: Any,
    *,
    matched_user_term: str,
) -> ProjectedAnalyticalOperation | None:
    if not isinstance(entities, list):
        return None
    normalized_term = normalize_search_text(matched_user_term)
    candidates: list[tuple[float, ProjectedAnalyticalOperation]] = []
    for entity in entities:
        if not isinstance(entity, Mapping):
            continue
        if str(entity.get("entity_type", "")).casefold() != (
            "analytical_operation"
        ):
            continue
        user_term = str(entity.get("user_term", "")).strip()
        if normalize_search_text(user_term) != normalized_term:
            continue
        operation = _operation_metadata(entity.get("business_rule"))
        if operation is None:
            continue
        canonical_value = str(entity.get("canonical_value", "")).strip()
        if canonical_value != operation["operation_type"]:
            continue
        priority = _optional_int(entity.get("priority"))
        projected_operation = _project_analytical_operation(
            operation,
            canonical_value=canonical_value,
            matched_user_term=matched_user_term,
            priority=priority,
        )
        candidates.append(
            (
                _priority_sort_value(priority),
                projected_operation,
            )
        )
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            item[0],
            item[1]["canonical_value"].casefold(),
            item[1]["operation_type"],
            item[1].get("direction", ""),
        ),
    )[0][1]


def _project_analytical_operation(
    operation: Mapping[str, Any],
    *,
    canonical_value: str,
    matched_user_term: str,
    priority: int | None,
) -> ProjectedAnalyticalOperation:
    output: ProjectedAnalyticalOperation = {
        "operation_type": operation["operation_type"],
        "canonical_value": canonical_value,
        "binding_cardinality": operation["binding_cardinality"],
        "detection_source": "intent_semantic_evidence",
        "mapping_source": "entity_alias",
        "matched_user_term": matched_user_term,
        "priority": priority,
    }
    if operation["operation_type"] == "ranking":
        output["direction"] = operation["direction"]
        output["requested_limit"] = operation["requested_limit"]
    if operation["operation_type"] == "comparison":
        output["output_behavior"] = operation["output_behavior"]
        output["combination_strategy"] = operation["combination_strategy"]
        join_semantics = operation.get("join_semantics")
        if isinstance(join_semantics, str) and join_semantics.strip():
            output["join_semantics"] = join_semantics.strip()
    return output


def _operation_metadata(
    business_rule: Any,
) -> dict[str, Any] | None:
    if not isinstance(business_rule, Mapping):
        return None
    operation = business_rule.get("operation")
    if not isinstance(operation, Mapping):
        return None
    operation_type = operation.get("operation_type")
    if operation_type == "ranking":
        return _ranking_operation_metadata(operation)
    if operation_type == "comparison":
        return _comparison_operation_metadata(operation)
    return None


def _ranking_operation_metadata(
    operation: Mapping[str, Any],
) -> dict[str, Any] | None:
    direction = operation.get("direction")
    requested_limit = operation.get("requested_limit")
    if direction not in {"ascending", "descending"}:
        return None
    if requested_limit is not None:
        if (
            isinstance(requested_limit, bool)
            or not isinstance(requested_limit, int)
            or requested_limit <= 0
        ):
            return None
    cardinality = _binding_cardinality_metadata(
        operation.get("binding_cardinality")
    )
    if cardinality is None:
        return None
    return {
        "operation_type": "ranking",
        "direction": direction,
        "requested_limit": requested_limit,
        "binding_cardinality": cardinality,
    }


def _comparison_operation_metadata(
    operation: Mapping[str, Any],
) -> dict[str, Any] | None:
    if operation.get("output_behavior") != "side_by_side":
        return None
    if operation.get("combination_strategy") != "aggregate_then_combine":
        return None
    cardinality = _binding_cardinality_metadata(
        operation.get("binding_cardinality")
    )
    if cardinality is None:
        return None
    output: dict[str, Any] = {
        "operation_type": "comparison",
        "output_behavior": "side_by_side",
        "combination_strategy": "aggregate_then_combine",
        "binding_cardinality": cardinality,
    }
    join_semantics = operation.get("join_semantics")
    if join_semantics is not None:
        if not isinstance(join_semantics, str) or not join_semantics.strip():
            return None
        output["join_semantics"] = join_semantics.strip()
    return output


def _binding_cardinality_metadata(value: Any) -> dict[str, Any] | None:
    if value is None:
        return _default_binding_cardinality()
    if not isinstance(value, Mapping):
        return None
    mode = value.get("mode", "single")
    if mode not in {"single", "multiple"}:
        return None
    minimum = value.get("minimum", 1)
    maximum = value.get("maximum", 1)
    if (
        isinstance(minimum, bool)
        or isinstance(maximum, bool)
        or not isinstance(minimum, int)
        or not isinstance(maximum, int)
    ):
        return None
    if mode == "single" and (minimum != 1 or maximum != 1):
        return None
    if mode == "multiple" and (minimum < 1 or maximum < minimum):
        return None
    same_metric_concept = value.get("same_metric_concept", True)
    distinct_bindings = value.get("distinct_bindings", True)
    if not isinstance(same_metric_concept, bool):
        return None
    if not isinstance(distinct_bindings, bool):
        return None
    return {
        "mode": mode,
        "minimum": minimum,
        "maximum": maximum,
        "same_metric_concept": same_metric_concept,
        "distinct_bindings": distinct_bindings,
    }


def _default_binding_cardinality() -> dict[str, Any]:
    return {
        "mode": "single",
        "minimum": 1,
        "maximum": 1,
        "same_metric_concept": True,
        "distinct_bindings": True,
    }


def _semantic_signal_from_term(
    term: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    details = term.get("match_details")
    if not isinstance(details, Mapping):
        return None
    signal = details.get("semantic_signal")
    if isinstance(signal, Mapping):
        output = dict(signal)
        output.setdefault("term", term.get("term"))
        output.setdefault("normalized_term", term.get("normalized_term"))
        return output

    signals = term.get("semantic_signals")
    if isinstance(signals, list):
        for signal_item in signals:
            if isinstance(signal_item, Mapping):
                return signal_item
    return None


def _dimension_name_from_semantic_signal(
    signal: Mapping[str, Any],
) -> str | None:
    tokens = signal.get("matched_tokens")
    if isinstance(tokens, list):
        dimension_tokens = [
            str(token).strip()
            for token in tokens
            if isinstance(token, str) and token.strip()
        ]
        if dimension_tokens:
            return " ".join(dimension_tokens)

    normalized_term = signal.get("normalized_term")
    if isinstance(normalized_term, str):
        return _dimension_name_from_grouping_term(normalized_term)
    return None


def _grouping_terms_from_context(
    intent_resolution: Any,
    normalized_question: str,
) -> list[tuple[str, str]]:
    if not isinstance(intent_resolution, Mapping):
        return []

    catalog = intent_resolution.get("intent_catalog", [])
    if not isinstance(catalog, list):
        return []

    matches: list[tuple[str, str]] = []
    question = normalize_search_text(normalized_question)
    for entry in catalog:
        if not isinstance(entry, Mapping):
            continue
        rules = entry.get("rules")
        if not isinstance(rules, list):
            business_rule = entry.get("business_rule")
            raw_catalog = (
                business_rule.get("intent_catalog")
                if isinstance(business_rule, Mapping)
                else None
            )
            rules = (
                raw_catalog.get("rules")
                if isinstance(raw_catalog, Mapping)
                else []
            )
        if not isinstance(rules, list):
            continue
        for rule in rules:
            if not isinstance(rule, Mapping):
                continue
            concepts = rule.get("concepts", [])
            if not isinstance(concepts, list):
                continue
            for concept in concepts:
                if not isinstance(concept, Mapping):
                    continue
                if str(concept.get("concept_name", "")).casefold() != (
                    "dimension_grouping"
                ):
                    continue
                terms = concept.get("terms", [])
                if not isinstance(terms, list):
                    continue
                for term in terms:
                    if not isinstance(term, str) or not term.strip():
                        continue
                    normalized_term = normalize_search_text(term)
                    if normalized_term and normalized_term in question:
                        dimension = _dimension_name_from_grouping_term(
                            normalized_term
                        )
                        if dimension:
                            matches.append((normalized_term, dimension))
    return sorted(set(matches), key=lambda item: (item[1], item[0]))


def _dimension_name_from_grouping_term(term: str) -> str | None:
    tokens = tokenize_search_text(term)
    if not tokens:
        return None
    if tokens[0] == "por" and len(tokens) > 1:
        return " ".join(tokens[1:])
    return " ".join(tokens)


def _resolve_grouping_dimension(
    *,
    context: ContextSnapshot,
    matched_user_term: str,
    dimension_term: str,
    detection_source: str,
) -> ProjectedDimension | None:
    entity_dimension = _resolve_dimension_from_entities(
        context.get("entities", []),
        matched_user_term=matched_user_term,
        dimension_term=dimension_term,
        detection_source=detection_source,
    )
    if entity_dimension is not None:
        return entity_dimension

    return _resolve_dimension_from_catalog(
        context.get("table_catalog", []),
        matched_user_term=matched_user_term,
        dimension_term=dimension_term,
        detection_source=detection_source,
    )


def _resolve_dimension_from_entities(
    entities: Any,
    *,
    matched_user_term: str,
    dimension_term: str,
    detection_source: str,
) -> ProjectedDimension | None:
    if not isinstance(entities, list):
        return None

    explicit_candidates: list[tuple[float, ProjectedDimension]] = []
    fallback_candidates: list[tuple[float, ProjectedDimension]] = []
    dimension_tokens = _search_tokens(dimension_term)
    for entity in entities:
        if not isinstance(entity, Mapping):
            continue
        entity_type = str(entity.get("entity_type", "")).casefold()
        if entity_type == "intent_definition":
            continue
        target_table = entity.get("target_table")
        target_column = entity.get("target_column")
        if not (
            isinstance(target_table, str)
            and target_table.strip()
            and isinstance(target_column, str)
            and target_column.strip()
        ):
            continue

        text = " ".join(
            str(value)
            for value in (
                entity.get("entity_type"),
                entity.get("user_term"),
                entity.get("canonical_value"),
                target_column,
            )
            if value
        )
        score = _dimension_match_score(
            dimension_tokens,
            _search_tokens(text),
        )
        if score <= 0:
            continue
        candidate = (
            score,
            {
                "canonical_value": str(entity.get("canonical_value", "")),
                "matched_user_term": matched_user_term,
                "target_table": target_table,
                "target_column": target_column,
                "grouping_requested": True,
                "source": "entity_alias",
                "mapping_source": "entity_alias",
                "detection_source": detection_source,
                "priority": _optional_int(entity.get("priority")),
                "confidence": score,
            },
        )
        if entity_type == "dimension":
            explicit_candidates.append(candidate)
        else:
            fallback_candidates.append(candidate)

    candidates = explicit_candidates or fallback_candidates
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            -item[0],
            _priority_sort_value(item[1].get("priority")),
            item[1]["target_table"].casefold(),
            item[1]["target_column"].casefold(),
        ),
    )[0][1]


def _resolve_dimension_from_catalog(
    table_catalog: Any,
    *,
    matched_user_term: str,
    dimension_term: str,
    detection_source: str,
) -> ProjectedDimension | None:
    if not isinstance(table_catalog, list):
        return None

    dimension_tokens = _search_tokens(dimension_term)
    candidates: list[tuple[float, ProjectedDimension]] = []
    for table in table_catalog:
        if not isinstance(table, Mapping):
            continue
        target_table = _qualified_table_name(table)
        column = _best_dimension_column(table, dimension_tokens)
        if not column:
            continue
        table_text = " ".join(
            str(value)
            for value in (
                table.get("schema_name"),
                table.get("table_name"),
                table.get("description"),
                table.get("grain"),
                table.get("ai_hint"),
                column,
            )
            if value
        )
        table_identity_text = " ".join(
            str(value)
            for value in (
                table.get("schema_name"),
                table.get("table_name"),
                table.get("description"),
                table.get("grain"),
            )
            if value
        )
        score = _dimension_match_score(
            dimension_tokens,
            _search_tokens(table_text),
        )
        if score <= 0:
            continue
        if _dimension_match_score(
            dimension_tokens,
            _search_tokens(table_identity_text),
        ):
            score += 1.0
        candidates.append(
            (
                score,
                {
                    "canonical_value": dimension_term,
                    "matched_user_term": matched_user_term,
                    "target_table": target_table,
                    "target_column": column,
                    "grouping_requested": True,
                    "source": "table_catalog",
                    "mapping_source": "table_catalog",
                    "detection_source": detection_source,
                    "priority": _optional_int(table.get("priority")),
                    "confidence": score,
                },
            )
        )

    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            -item[0],
            _priority_sort_value(item[1].get("priority")),
            item[1]["target_table"].casefold(),
            item[1]["target_column"].casefold(),
        ),
    )[0][1]


def _best_dimension_column(
    table: Mapping[str, Any],
    dimension_tokens: set[str],
) -> str | None:
    column_names = _table_column_candidates(table)
    if not column_names:
        return None

    ranked: list[tuple[float, int, str]] = []
    for index, column in enumerate(column_names):
        column_tokens = _search_tokens(column)
        score = _dimension_match_score(dimension_tokens, column_tokens)
        if score <= 0:
            continue
        if column in _string_list(table.get("key_columns")):
            score += 0.25
        if column in _string_list(table.get("primary_key")):
            score += 0.1
        if any(
            token in {"name", "nome", "label", "descricao", "description"}
            for token in column_tokens
        ):
            score += 0.15
        ranked.append((score, index, column))

    if not ranked:
        return None
    return sorted(ranked, key=lambda item: (-item[0], item[1], item[2]))[0][2]


def _table_column_candidates(table: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for column in table.get("columns", []):
        if isinstance(column, Mapping) and isinstance(column.get("name"), str):
            names.append(column["name"].strip())
    for collection_name in ("key_columns", "primary_key"):
        names.extend(_string_list(table.get(collection_name)))

    output: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            output.append(name)
    return output


def _search_tokens(value: str) -> set[str]:
    return set(tokenize_search_text(value.replace("_", " ")))


def _dimension_match_score(
    dimension_tokens: set[str],
    candidate_tokens: set[str],
) -> float:
    if not dimension_tokens or not candidate_tokens:
        return 0.0
    matched = 0
    for dimension_token in dimension_tokens:
        if any(
            _tokens_equivalent(dimension_token, candidate_token)
            for candidate_token in candidate_tokens
        ):
            matched += 1
    if matched != len(dimension_tokens):
        return 0.0
    return matched / max(len(candidate_tokens), 1)


def _tokens_equivalent(left: str, right: str) -> bool:
    return left == right


def _include_dimension_columns(
    relevant_columns: dict[str, list[Any]],
    dimensions: list[ProjectedDimension],
) -> None:
    for dimension in dimensions:
        table = dimension.get("target_table")
        column = dimension.get("target_column")
        if not (
            isinstance(table, str)
            and table.strip()
            and isinstance(column, str)
            and column.strip()
        ):
            continue
        table_columns = relevant_columns.setdefault(table, [])
        if any(
            isinstance(item, Mapping)
            and str(item.get("name", "")).casefold() == column.casefold()
            for item in table_columns
        ):
            continue
        table_columns.append({"name": column})


def _include_metric_columns(
    relevant_columns: dict[str, list[Any]],
    planned_metrics: list[ProjectedPlannedMetric],
) -> None:
    for metric in planned_metrics:
        table = metric.get("target_table")
        column = metric.get("target_column")
        if not (
            isinstance(table, str)
            and table.strip()
            and isinstance(column, str)
            and column.strip()
        ):
            continue
        table_columns = relevant_columns.setdefault(table, [])
        if any(
            isinstance(item, Mapping)
            and str(item.get("name", "")).casefold() == column.casefold()
            for item in table_columns
        ):
            continue
        table_columns.append({"name": column})


def _dedupe_dimensions(
    dimensions: list[ProjectedDimension],
) -> list[ProjectedDimension]:
    output: list[ProjectedDimension] = []
    seen: set[tuple[str, str]] = set()
    for dimension in sorted(
        dimensions,
        key=lambda item: (
            _priority_sort_value(item.get("priority")),
            item["target_table"].casefold(),
            item["target_column"].casefold(),
        ),
    ):
        key = (
            dimension["target_table"].casefold(),
            dimension["target_column"].casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(dimension)
    return output


def _dedupe_analytical_operations(
    operations: list[ProjectedAnalyticalOperation],
) -> list[ProjectedAnalyticalOperation]:
    output: list[ProjectedAnalyticalOperation] = []
    seen: set[tuple[Any, ...]] = set()
    for operation in sorted(
        operations,
        key=lambda item: (
            _priority_sort_value(item.get("priority")),
            item["operation_type"],
            item.get("direction", ""),
            item.get("output_behavior", ""),
            item.get("combination_strategy", ""),
            item.get("requested_limit") or 0,
        ),
    ):
        key = _analytical_operation_key(operation)
        if key in seen:
            continue
        seen.add(key)
        output.append(operation)
    return output


def _analytical_operation_key(
    operation: ProjectedAnalyticalOperation,
) -> tuple[Any, ...]:
    if operation["operation_type"] == "ranking":
        return (
            operation["operation_type"],
            operation.get("direction"),
            operation.get("requested_limit"),
        )
    return (
        operation["operation_type"],
        operation.get("output_behavior"),
        operation.get("combination_strategy"),
        operation.get("join_semantics"),
        tuple(
            sorted(
                operation.get("binding_cardinality", {}).items(),
                key=lambda item: str(item[0]),
            )
        ),
    )


def _dedupe_planned_metrics(
    metrics: list[ProjectedPlannedMetric],
) -> list[ProjectedPlannedMetric]:
    output: list[ProjectedPlannedMetric] = []
    seen: set[str] = set()
    for metric in sorted(
        metrics,
        key=lambda item: (
            _priority_sort_value(item.get("priority")),
            item["metric_ref"].casefold(),
        ),
    ):
        key = metric["metric_ref"].casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(metric)
    return output


def _expand_required_tables_with_dimensions(
    required_table_names: list[str],
    dimensions: list[ProjectedDimension],
    planned_metrics: list[ProjectedPlannedMetric] | None = None,
) -> list[str]:
    output = [
        name
        for name in required_table_names
        if isinstance(name, str) and name.strip()
    ]
    seen = {name.casefold() for name in output}
    for dimension in dimensions:
        table = dimension.get("target_table")
        if not isinstance(table, str) or not table.strip():
            continue
        if table.casefold() in seen:
            continue
        seen.add(table.casefold())
        output.append(table)
    for metric in planned_metrics or []:
        table = metric.get("target_table")
        if not isinstance(table, str) or not table.strip():
            continue
        if table.casefold() in seen:
            continue
        seen.add(table.casefold())
        output.append(table)
    return output


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _project_tables(
    table_catalog: list[TableCatalogEntry],
    required_table_names: list[str],
) -> tuple[list[ProjectedTable], list[str], list[dict[str, Any]]]:
    if not isinstance(table_catalog, list):
        raise PlanningInputError(
            "context.table_catalog deve ser uma lista."
        )

    full_index: dict[str, TableCatalogEntry] = {}
    bare_index: dict[str, list[TableCatalogEntry]] = {}

    for table in table_catalog:
        if not isinstance(table, Mapping):
            raise PlanningInputError(
                "context.table_catalog contem item invalido."
            )

        schema = str(table.get("schema_name", "")).strip()
        name = str(table.get("table_name", "")).strip()
        if not schema or not name:
            raise PlanningInputError(
                "table_catalog possui tabela sem schema ou nome."
            )
        qualified = f"{schema}.{name}"
        full_index[qualified.casefold()] = deepcopy(dict(table))
        bare_index.setdefault(name.casefold(), []).append(
            deepcopy(dict(table))
        )

    selected: list[ProjectedTable] = []
    selected_keys: set[str] = set()
    missing: list[str] = []
    ambiguous: list[dict[str, Any]] = []

    for required_name in required_table_names:
        if not isinstance(required_name, str) or not required_name.strip():
            missing.append(str(required_name))
            continue

        normalized_required = required_name.strip()
        candidates = (
            [full_index[normalized_required.casefold()]]
            if "." in normalized_required
            and normalized_required.casefold() in full_index
            else (
                bare_index.get(
                    normalized_required.casefold(),
                    [],
                )
                if "." not in normalized_required
                else []
            )
        )

        if not candidates:
            missing.append(required_name)
            continue
        if len(candidates) > 1:
            ambiguous.append(
                {
                    "required_table": required_name,
                    "candidates": sorted(
                        _qualified_table_name(candidate)
                        for candidate in candidates
                    ),
                }
            )
            continue

        table = candidates[0]
        qualified_name = _qualified_table_name(table)
        if qualified_name.casefold() in selected_keys:
            continue
        selected_keys.add(qualified_name.casefold())
        selected.append(_project_table(table))

    selected.sort(
        key=lambda table: (
            _priority_sort_value(table.get("priority")),
            table["qualified_name"].casefold(),
        )
    )
    return selected, sorted(missing, key=str.casefold), ambiguous


def _project_table(
    table: Mapping[str, Any],
) -> ProjectedTable:
    schema = str(table.get("schema_name", "")).strip()
    name = str(table.get("table_name", "")).strip()
    return {
        "schema_name": schema,
        "table_name": name,
        "qualified_name": f"{schema}.{name}",
        "table_type": str(table.get("table_type", "")),
        "description": table.get("description"),
        "grain": deepcopy(table.get("grain")),
        "primary_key": deepcopy(table.get("primary_key")),
        "key_columns": deepcopy(table.get("key_columns")),
        "metric_columns": deepcopy(table.get("metric_columns")),
        "date_columns": deepcopy(table.get("date_columns")),
        "join_rules": deepcopy(table.get("join_rules")),
        "ai_hint": deepcopy(table.get("ai_hint")),
        "priority": _optional_int(table.get("priority")),
        "columns": deepcopy(table.get("columns", [])),
    }


def _project_joins(
    tables: list[ProjectedTable],
    selected_table_names: set[str],
) -> dict[str, Any]:
    joins: list[ProjectedJoin] = []
    diagnostics: list[dict[str, Any]] = []
    selected_references = {
        *selected_table_names,
        *(table["table_name"].casefold() for table in tables),
    }

    for table in tables:
        raw_join_rules = deepcopy(table.get("join_rules"))
        source_table = table["qualified_name"]
        if raw_join_rules in (None, [], {}):
            joins.append(
                {
                    "source_table": source_table,
                    "join_rules": raw_join_rules,
                    "interpretation": "empty",
                }
            )
            continue

        filtered = _filter_join_rules(
            raw_join_rules,
            selected_references,
        )
        if filtered["interpreted"]:
            joins.append(
                {
                    "source_table": source_table,
                    "join_rules": filtered["join_rules"],
                    "interpretation": "preserved_selected_table_rules",
                }
            )
        else:
            joins.append(
                {
                    "source_table": source_table,
                    "join_rules": raw_join_rules,
                    "interpretation": "preserved_uninterpreted",
                }
            )
            diagnostics.append(
                {
                    "source_table": source_table,
                    "reason": "join_rules_format_uninterpreted",
                }
            )

    return {
        "joins": joins,
        "diagnostics": diagnostics,
    }


def _filter_join_rules(
    raw_join_rules: Any,
    selected_table_names: set[str],
) -> dict[str, Any]:
    if not isinstance(raw_join_rules, list):
        return {
            "interpreted": False,
            "join_rules": raw_join_rules,
        }

    filtered: list[Any] = []
    interpreted_any = False
    for rule in raw_join_rules:
        if not isinstance(rule, Mapping):
            filtered.append(deepcopy(rule))
            continue

        referenced_tables = _extract_table_references(rule)
        if not referenced_tables:
            filtered.append(deepcopy(rule))
            continue

        interpreted_any = True
        if all(
            reference.casefold() in selected_table_names
            for reference in referenced_tables
        ):
            filtered.append(deepcopy(rule))

    return {
        "interpreted": interpreted_any,
        "join_rules": filtered,
    }


def _project_entities(
    entities: list[EntityAlias],
    *,
    intent_name: str,
    table_names: set[str],
    bare_table_names: set[str],
    selected_columns: set[str],
) -> list[ProjectedEntity]:
    if not isinstance(entities, list):
        raise PlanningInputError("context.entities deve ser uma lista.")

    projected: list[ProjectedEntity] = []
    for entity in entities:
        if not isinstance(entity, Mapping):
            raise PlanningInputError(
                "context.entities contem item invalido."
            )

        entity_type = str(entity.get("entity_type", "")).strip()
        if entity_type.casefold() == "intent_definition":
            continue

        reasons: list[str] = []
        if _same_text(entity.get("canonical_value"), intent_name):
            reasons.append("canonical_intent")

        target_table = entity.get("target_table")
        if _table_reference_matches(
            target_table,
            table_names,
            bare_table_names,
        ):
            reasons.append("target_table")

        target_column = entity.get("target_column")
        if (
            isinstance(target_column, str)
            and target_column.strip().casefold() in selected_columns
        ):
            reasons.append("target_column")

        if not reasons:
            continue

        projected.append(
            {
                "entity_type": entity_type,
                "user_term": str(entity.get("user_term", "")),
                "canonical_value": str(
                    entity.get("canonical_value", "")
                ),
                "target_table": entity.get("target_table"),
                "target_column": entity.get("target_column"),
                "sql_filter_hint": deepcopy(
                    entity.get("sql_filter_hint")
                ),
                "business_rule": deepcopy(
                    entity.get("business_rule")
                ),
                "priority": _optional_int(entity.get("priority")),
                "selection_reasons": sorted(set(reasons)),
            }
        )

    projected.sort(
        key=lambda entity: (
            _priority_sort_value(entity.get("priority")),
            entity["entity_type"].casefold(),
            entity["user_term"].casefold(),
        )
    )
    return projected


def _project_dre_mappings(
    dre_mappings: list[DreMapping],
    *,
    intent_name: str,
    table_names: set[str],
    bare_table_names: set[str],
    selected_columns: set[str],
) -> tuple[list[ProjectedDreMapping], dict[str, Any]]:
    if not isinstance(dre_mappings, list):
        raise PlanningInputError(
            "context.dre_mappings deve ser uma lista."
        )

    projected: list[ProjectedDreMapping] = []
    for mapping in dre_mappings:
        if not isinstance(mapping, Mapping):
            raise PlanningInputError(
                "context.dre_mappings contem item invalido."
            )

        hint = mapping.get("sql_filter_hint")
        evidence = _collect_generic_evidence(
            hint,
            intent_name=intent_name,
            table_names=table_names,
            bare_table_names=bare_table_names,
            selected_columns=selected_columns,
        )
        if not evidence:
            continue

        projected.append(
            {
                "dre_code": str(mapping.get("dre_code", "")),
                "nivel_1_bi": str(mapping.get("nivel_1_bi", "")),
                "business_description": str(
                    mapping.get("business_description", "")
                ),
                "sign_convention": deepcopy(
                    mapping.get("sign_convention")
                ),
                "category": str(mapping.get("category", "")),
                "is_revenue": bool(mapping.get("is_revenue", False)),
                "is_deduction": bool(
                    mapping.get("is_deduction", False)
                ),
                "is_cost": bool(mapping.get("is_cost", False)),
                "is_opex": bool(mapping.get("is_opex", False)),
                "is_financial_result": bool(
                    mapping.get("is_financial_result", False)
                ),
                "sql_filter_hint": deepcopy(hint),
                "sort_order": _optional_int(
                    mapping.get("sort_order")
                ),
                "selection_reasons": sorted(evidence),
            }
        )

    projected.sort(
        key=lambda item: (
            _priority_sort_value(item.get("sort_order")),
            item["dre_code"].casefold(),
            item["nivel_1_bi"].casefold(),
        )
    )
    return projected, {
        "policy": "explicit_hint_evidence_only",
        "included_count": len(projected),
        "empty_reason": (
            "no_explicit_context_evidence"
            if not projected
            else None
        ),
    }


def _collect_generic_evidence(
    payload: Any,
    *,
    intent_name: str,
    table_names: set[str],
    bare_table_names: set[str],
    selected_columns: set[str],
) -> set[str]:
    evidence: set[str] = set()

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key).casefold()
            if key_text == "intent_name" and _same_text(
                value,
                intent_name,
            ):
                evidence.add("hint_intent")
            if key_text in {"table", "target_table", "table_name"}:
                if _table_reference_matches(
                    value,
                    table_names,
                    bare_table_names,
                ):
                    evidence.add("hint_table")
            if key_text in {"column", "target_column", "column_name"}:
                if (
                    isinstance(value, str)
                    and value.strip().casefold() in selected_columns
                ):
                    evidence.add("hint_column")
            evidence.update(
                _collect_generic_evidence(
                    value,
                    intent_name=intent_name,
                    table_names=table_names,
                    bare_table_names=bare_table_names,
                    selected_columns=selected_columns,
                )
            )
    elif isinstance(payload, list):
        for item in payload:
            evidence.update(
                _collect_generic_evidence(
                    item,
                    intent_name=intent_name,
                    table_names=table_names,
                    bare_table_names=bare_table_names,
                    selected_columns=selected_columns,
                )
            )

    return evidence


def _selected_column_names(
    tables: list[ProjectedTable],
) -> set[str]:
    names: set[str] = set()
    for table in tables:
        for collection_name in (
            "columns",
            "key_columns",
            "metric_columns",
            "date_columns",
        ):
            value = table.get(collection_name)
            if collection_name == "columns" and isinstance(value, list):
                for column in value:
                    if isinstance(column, Mapping):
                        column_name = column.get("name")
                        if isinstance(column_name, str):
                            names.add(column_name.strip().casefold())
                continue
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        names.add(item.strip().casefold())
            elif isinstance(value, str):
                names.add(value.strip().casefold())
    return names


def _extract_table_references(
    value: Mapping[str, Any],
) -> set[str]:
    references: set[str] = set()
    for key, item in value.items():
        key_text = str(key).casefold()
        if key_text in {
            "table",
            "target_table",
            "left_table",
            "right_table",
            "from_table",
            "to_table",
            "schema_table",
        } and isinstance(item, str):
            references.add(item.strip().casefold())
        elif isinstance(item, Mapping):
            references.update(_extract_table_references(item))
    return references


def _qualified_table_name(
    table: Mapping[str, Any],
) -> str:
    return (
        f"{str(table.get('schema_name', '')).strip()}."
        f"{str(table.get('table_name', '')).strip()}"
    )


def _table_reference_matches(
    value: Any,
    table_names: set[str],
    bare_table_names: set[str],
) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False

    key = value.strip().casefold()
    return key in table_names or key in bare_table_names


def _priority_sort_value(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return math.inf
    try:
        priority = float(value)
    except (TypeError, ValueError):
        return math.inf
    return priority if math.isfinite(priority) else math.inf


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return int(number)


def _is_non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _same_text(left: Any, right: Any) -> bool:
    return (
        isinstance(left, str)
        and isinstance(right, str)
        and left.strip().casefold() == right.strip().casefold()
    )
