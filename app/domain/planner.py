from __future__ import annotations

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
    ProjectedEntity,
    ProjectedJoin,
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

    required_tables, missing_tables, ambiguous_tables = (
        _project_tables(
            context.get("table_catalog", []),
            selected_pattern.get("required_tables", []),
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
        if any(
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
