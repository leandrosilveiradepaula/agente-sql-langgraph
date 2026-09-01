from __future__ import annotations

from typing import Any, Literal, TypedDict

from app.domain.context import (
    AgentRule,
    CatalogColumn,
    DreMapping,
    EntityAlias,
    QueryPattern,
    TableCatalogEntry,
)


PLANNER_VERSION = "v1.0.0-deterministic-context-planner"

PlanningDecisionReason = Literal[
    "single_pattern_selected",
    "exact_example_match",
    "lexical_similarity_selected",
    "token_coverage_selected",
    "priority_selected",
    "stable_name_tiebreak_selected",
    "intent_missing",
    "pattern_not_found",
    "pattern_ambiguous",
    "contract_error",
]

PlanningErrorCode = Literal[
    "PLANNING_INTENT_MISSING",
    "PLANNING_PATTERN_NOT_FOUND",
    "PLANNING_PATTERN_AMBIGUOUS",
    "PLANNING_REQUIRED_RULE_NOT_FOUND",
    "PLANNING_REQUIRED_TABLE_NOT_FOUND",
    "PLANNING_CONTEXT_INVALID",
    "PLANNING_UNEXPECTED_ERROR",
]

PlanningStatus = Literal[
    "planned",
    "rejected",
    "contract_error",
]


class SelectedPattern(TypedDict, total=False):
    intent_name: str
    pattern_name: str
    priority: float | None
    required_tables: list[str]
    required_rules: list[str]
    business_question_examples: list[str]
    sql_pattern: str
    notes: str | None


class PatternSelectionCriteria(TypedDict):
    exact_example_match: bool
    best_similarity: float
    best_coverage: float
    matched_example: str | None
    priority: float | None
    pattern_name: str


class PatternCandidateDiagnostic(TypedDict):
    intent_name: str
    pattern_name: str
    examples_count: int
    criteria: PatternSelectionCriteria


class PatternSelectionDiagnostic(TypedDict):
    selected_pattern: SelectedPattern | None
    candidates: list[PatternCandidateDiagnostic]
    decision_reason: PlanningDecisionReason
    tie_detected: bool
    fallback_used: str | None
    planner_version: str


class PatternSelectionResult(TypedDict):
    status: PlanningStatus
    selected_pattern: SelectedPattern | None
    diagnostic: PatternSelectionDiagnostic
    error_code: PlanningErrorCode | None
    error_message: str | None


class ProjectedRule(TypedDict):
    rule_group: str
    rule_name: str
    rule_content: Any
    applies_to_intents: list[str]
    validation_hint: Any
    severity: str
    priority: int | None
    selection_reasons: list[str]


class ProjectedTable(TypedDict, total=False):
    schema_name: str
    table_name: str
    qualified_name: str
    table_type: str
    description: str | None
    grain: Any
    primary_key: Any
    key_columns: Any
    metric_columns: Any
    date_columns: Any
    join_rules: Any
    ai_hint: Any
    priority: int | None
    columns: list[CatalogColumn]


class ProjectedJoin(TypedDict):
    source_table: str
    join_rules: Any
    interpretation: Literal[
        "empty",
        "preserved_uninterpreted",
        "preserved_selected_table_rules",
    ]


class ProjectedEntity(TypedDict, total=False):
    entity_type: str
    user_term: str
    canonical_value: str
    target_table: str | None
    target_column: str | None
    sql_filter_hint: Any
    business_rule: Any
    priority: int | None
    selection_reasons: list[str]


class ProjectedDreMapping(TypedDict, total=False):
    dre_code: str
    nivel_1_bi: str
    business_description: str
    sign_convention: Any
    category: str
    is_revenue: bool
    is_deduction: bool
    is_cost: bool
    is_opex: bool
    is_financial_result: bool
    sql_filter_hint: Any
    sort_order: int | None
    selection_reasons: list[str]


class ProjectedDimension(TypedDict, total=False):
    canonical_value: str
    matched_user_term: str
    target_table: str
    target_column: str
    grouping_requested: bool
    source: str
    detection_source: str
    mapping_source: str
    priority: int | None
    confidence: float | None


class ProjectedAnalyticalOperation(TypedDict, total=False):
    operation_type: Literal["ranking"]
    canonical_value: str
    direction: Literal["ascending", "descending"]
    requested_limit: int | None
    metric_ref: str
    detection_source: str
    mapping_source: str
    matched_user_term: str
    priority: int | None


class ProjectedPlannedMetric(TypedDict, total=False):
    metric_ref: str
    metric_concept: str
    target_table: str
    target_column: str
    aggregate: None
    detection_source: str
    mapping_source: str
    matched_user_term: str
    priority: int | None


class ProjectionDiagnostic(TypedDict):
    missing_required_rules: list[str]
    missing_required_tables: list[str]
    ambiguous_required_tables: list[dict[str, Any]]
    join_diagnostics: list[dict[str, Any]]
    dre_diagnostic: dict[str, Any]
    dimension_diagnostic: dict[str, Any]
    analytical_operation_diagnostic: dict[str, Any]
    planned_metric_diagnostic: dict[str, Any]


class PlanningContextProjection(TypedDict):
    context_version: str
    context_fingerprint: str
    intent_name: str
    normalized_question: str
    selected_pattern: SelectedPattern
    rules: list[ProjectedRule]
    required_tables: list[ProjectedTable]
    relevant_columns: dict[str, list[CatalogColumn]]
    authorized_joins: list[ProjectedJoin]
    relevant_entities: list[ProjectedEntity]
    relevant_dre_mappings: list[ProjectedDreMapping]
    detected_dimensions: list[ProjectedDimension]
    analytical_operations: list[ProjectedAnalyticalOperation]
    planned_metrics: list[ProjectedPlannedMetric]
    allowed_schemas: list[str]
    component_configs: dict[str, dict[str, Any]]
    diagnostics: ProjectionDiagnostic


class QueryPlan(TypedDict):
    planner_version: str
    context_version: str
    context_fingerprint: str
    intent_name: str
    intent_confidence: float | None
    normalized_question: str
    selected_pattern: SelectedPattern
    planning_context: PlanningContextProjection
    selection_diagnostic: PatternSelectionDiagnostic
    sql_pattern_metadata: str


class PlanningBuildResult(TypedDict):
    status: PlanningStatus
    query_plan: QueryPlan | None
    selection_result: PatternSelectionResult
    projection: PlanningContextProjection | None
    error_code: PlanningErrorCode | None
    error_message: str | None


def selected_pattern_from_query_pattern(
    pattern: QueryPattern,
) -> SelectedPattern:
    return {
        "intent_name": pattern.get("intent_name", ""),
        "pattern_name": pattern.get("pattern_name", ""),
        "priority": (
            float(pattern["priority"])
            if pattern.get("priority") is not None
            else None
        ),
        "required_tables": list(pattern.get("required_tables", [])),
        "required_rules": list(pattern.get("required_rules", [])),
        "business_question_examples": list(
            pattern.get("business_question_examples", [])
        ),
        "sql_pattern": pattern.get("sql_pattern", ""),
        "notes": pattern.get("notes"),
    }
