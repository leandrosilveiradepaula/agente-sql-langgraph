from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from time import perf_counter
from typing import Any, Literal, TypedDict

from app.domain.planning import QueryPlan
from app.domain.sql_analysis import (
    SQL_ANALYZER_VERSION,
    SqlAnalysisError,
    SqlColumnReference,
    SqlJoinReference,
    SqlObjectReference,
    SqlStatementAnalysis,
    analyze_sql,
    normalized_sql_tokens,
)


SQL_CONTRACT_GATE_VERSION = "v1.1.0-planned-filter-contract-gate"

SqlContractStatus = Literal["approved", "rejected", "error"]
VerificationStatus = Literal[
    "satisfied",
    "violated",
    "unverifiable",
    "not_applicable",
]

SqlContractErrorCode = Literal[
    "SQL_CONTRACT_INPUT_INVALID",
    "SQL_CONTRACT_ANALYSIS_FAILED",
    "SQL_CONTRACT_REQUIRED_TABLE_MISSING",
    "SQL_CONTRACT_UNPLANNED_TABLE",
    "SQL_CONTRACT_UNKNOWN_COLUMN",
    "SQL_CONTRACT_AMBIGUOUS_COLUMN",
    "SQL_CONTRACT_INVALID_ALIAS",
    "SQL_CONTRACT_RULE_VIOLATED",
    "SQL_CONTRACT_JOIN_VIOLATED",
    "SQL_CONTRACT_LIMIT_VIOLATED",
    "SQL_CONTRACT_WILDCARD_VIOLATED",
    "SQL_CONTRACT_GROUPING_DIMENSION_MISMATCH",
    "SQL_CONTRACT_REQUIRED_FILTER_VIOLATED",
    "SQL_CONTRACT_FILTER_BINDING_INVALID",
    "SQL_CONTRACT_FILTER_UNVERIFIABLE",
]


class SqlContractPolicy(TypedDict):
    gate_version: str
    required_tables: list[str]
    allowed_tables: list[str]
    allowed_columns: dict[str, list[str]]
    required_rules: list[str]
    wildcard_policy: Literal["allow", "warn", "reject"]
    table_wildcard_policy: Literal["allow", "warn", "reject"]
    limit_policy: Literal["allow", "forbid", "require", "unspecified"]


class SqlContractCheck(TypedDict):
    name: str
    status: Literal["passed", "failed", "warning"]
    details: dict[str, Any]


class SqlContractFinding(TypedDict):
    code: SqlContractErrorCode
    severity: Literal["error", "warning"]
    message: str
    details: dict[str, Any]


class RuleVerificationResult(TypedDict):
    rule_name: str
    status: VerificationStatus
    reason: str
    checked_items: list[str]


class TableVerificationResult(TypedDict):
    table: str
    status: VerificationStatus
    reason: str


class ColumnVerificationResult(TypedDict):
    column: str
    table: str | None
    status: VerificationStatus
    reason: str


class JoinVerificationResult(TypedDict):
    left_table: str | None
    right_table: str | None
    status: VerificationStatus
    reason: str


class FilterVerificationResult(TypedDict):
    filter_ref: str
    binding_ref: str
    filter_concept: str
    scope: str
    status: VerificationStatus
    reason: str
    expected: dict[str, Any]
    matched_predicate_count: int


class SqlContractResult(TypedDict):
    status: SqlContractStatus
    gate_version: str
    analyzer_version: str
    planner_version: str
    context_version: str
    context_fingerprint: str
    sql_fingerprint: str
    checks: list[SqlContractCheck]
    findings: list[SqlContractFinding]
    required_tables: list[TableVerificationResult]
    referenced_tables: list[TableVerificationResult]
    columns: list[ColumnVerificationResult]
    joins: list[JoinVerificationResult]
    filters: list[FilterVerificationResult]
    rules: list[RuleVerificationResult]
    unverifiable_rules: list[RuleVerificationResult]
    errors: list[SqlContractFinding]
    warnings: list[str]
    duration_ms: int


class SqlContractInputError(ValueError):
    pass


_STRUCTURED_RULE_KEYS = {
    "required_sql_fragments",
    "forbidden_sql_fragments",
    "required_filters",
    "forbidden_filters",
    "required_groupings",
    "forbidden_keywords",
    "limit_policy",
    "required_tables",
    "required_columns",
    "required_joins",
    "select_star_policy",
    "wildcard_policy",
}


def build_sql_contract_policy(
    query_plan: QueryPlan,
) -> SqlContractPolicy:
    planning_context = _planning_context(query_plan)
    required_tables = _required_tables(planning_context)
    rules = _rules(planning_context)
    return {
        "gate_version": SQL_CONTRACT_GATE_VERSION,
        "required_tables": sorted(required_tables),
        "allowed_tables": sorted(required_tables),
        "allowed_columns": _allowed_columns(planning_context),
        "required_rules": sorted(
            {
                str(rule.get("rule_name", "")).strip().casefold()
                for rule in rules
                if _is_required_rule(rule)
            }
        ),
        "wildcard_policy": _wildcard_policy(rules, table=False),
        "table_wildcard_policy": _wildcard_policy(rules, table=True),
        "limit_policy": _limit_policy(rules),
    }


def run_sql_contract_gate(
    *,
    current_sql: str,
    query_plan: QueryPlan,
    analysis: SqlStatementAnalysis | None = None,
) -> tuple[SqlContractResult, SqlStatementAnalysis | None]:
    start = perf_counter()
    checks: list[SqlContractCheck] = []
    findings: list[SqlContractFinding] = []
    try:
        policy = build_sql_contract_policy(query_plan)
        # Persisted analyses intentionally omit raw tokens and string literals.
        # Re-analyze current_sql locally when full structural evidence is needed.
        sql_analysis = (
            analysis
            if analysis is not None and analysis.get("tokens")
            else analyze_sql(current_sql)
        )
        sql_token_norms = normalized_sql_tokens(
            current_sql,
            include_string_values=True,
        )
    except SqlAnalysisError as error:
        finding = _finding(
            "SQL_CONTRACT_ANALYSIS_FAILED",
            "Nao foi possivel analisar SQL para contrato.",
            details={
                "analysis_error_code": error.code,
            },
        )
        return (
            _result(
                status="rejected",
                query_plan=query_plan,
                analysis=None,
                checks=[
                    _check("sql_analysis", "failed", {"code": error.code})
                ],
                findings=[finding],
                tables=[],
                referenced=[],
                columns=[],
                joins=[],
                filters=[],
                rules=[],
                duration_ms=_duration(start),
            ),
            None,
        )
    except SqlContractInputError as error:
        finding = _finding(
            "SQL_CONTRACT_INPUT_INVALID",
            str(error),
        )
        return (
            _result(
                status="error",
                query_plan=query_plan,
                analysis=None,
                checks=[],
                findings=[finding],
                tables=[],
                referenced=[],
                columns=[],
                joins=[],
                filters=[],
                rules=[],
                duration_ms=_duration(start),
            ),
            None,
        )

    table_results = _verify_tables(sql_analysis, policy, findings)
    column_results = _verify_columns(sql_analysis, policy, findings)
    grouping_results = _verify_grouping_dimensions(
        sql_analysis,
        query_plan,
        policy,
        findings,
    )
    analytical_operation_results = _verify_analytical_operations(
        current_sql,
        sql_analysis,
        query_plan,
        findings,
    )
    join_results = _verify_joins(sql_analysis, query_plan, findings)
    filter_results = _verify_planned_filters(sql_analysis, query_plan, policy, findings)
    rule_results = _verify_rules(
        sql_token_norms=sql_token_norms,
        analysis=sql_analysis,
        query_plan=query_plan,
        policy=policy,
        findings=findings,
    )
    _verify_limit(sql_analysis, policy, findings)
    _verify_wildcards(sql_analysis, policy, findings)

    checks.extend(
        [
            _check(
                "tables",
                _check_status(table_results),
                {"count": len(table_results)},
            ),
            _check(
                "columns",
                _check_status(column_results),
                {"count": len(column_results)},
            ),
            _check(
                "grouping_dimensions",
                _check_status(grouping_results),
                {"count": len(grouping_results)},
            ),
            _check(
                "analytical_operations",
                _check_status(analytical_operation_results),
                {"count": len(analytical_operation_results)},
            ),
            _check(
                "joins",
                _check_status(join_results),
                {"count": len(join_results)},
            ),
            _check("filters", _check_status(filter_results), {"count": len(filter_results)}),
            _check(
                "rules",
                _check_status(rule_results),
                {"count": len(rule_results)},
            ),
        ]
    )

    status: SqlContractStatus = (
        "rejected" if any(item["severity"] == "error" for item in findings)
        else "approved"
    )
    return (
        _result(
            status=status,
            query_plan=query_plan,
            analysis=sql_analysis,
            checks=checks,
            findings=findings,
            tables=[
                item
                for item in table_results
                if item["table"] in policy["required_tables"]
            ],
            referenced=table_results,
            columns=column_results,
            joins=join_results,
            filters=filter_results,
            rules=rule_results,
            duration_ms=_duration(start),
        ),
        deepcopy(sql_analysis),
    )


def _verify_tables(
    analysis: SqlStatementAnalysis,
    policy: SqlContractPolicy,
    findings: list[SqlContractFinding],
) -> list[TableVerificationResult]:
    referenced = _resolved_tables(analysis, policy)
    results: list[TableVerificationResult] = []
    for table in policy["required_tables"]:
        present = table in referenced
        if not present:
            findings.append(
                _finding(
                    "SQL_CONTRACT_REQUIRED_TABLE_MISSING",
                    "Tabela requerida pelo plano nao foi usada.",
                    details={"table": table},
                )
            )
        results.append(
            {
                "table": table,
                "status": "satisfied" if present else "violated",
                "reason": "present" if present else "missing_required_table",
            }
        )
    for table in referenced:
        if table not in set(policy["allowed_tables"]):
            findings.append(
                _finding(
                    "SQL_CONTRACT_UNPLANNED_TABLE",
                    "SQL referencia tabela fora do QueryPlan.",
                    details={"table": table},
                )
            )
            results.append(
                {
                    "table": table,
                    "status": "violated",
                    "reason": "not_in_query_plan",
                }
            )
    return sorted(results, key=lambda item: item["table"])


def _verify_columns(
    analysis: SqlStatementAnalysis,
    policy: SqlContractPolicy,
    findings: list[SqlContractFinding],
) -> list[ColumnVerificationResult]:
    results: list[ColumnVerificationResult] = []
    allowed = {
        table: set(columns)
        for table, columns in policy["allowed_columns"].items()
    }
    aliases = _analysis_aliases(analysis, policy)
    expression_aliases = set(analysis.get("expression_aliases", []))
    for column in analysis["column_references"]:
        if column.get("is_wildcard"):
            continue
        column_name = column["column"].casefold()
        if (
            column_name in expression_aliases
            and column.get("clause") in {"select", "group", "order"}
        ):
            results.append(
                {
                    "column": column_name,
                    "table": None,
                    "status": "not_applicable",
                    "reason": "expression_alias",
                }
            )
            continue
        resolved_table = _resolve_column_table(
            column,
            allowed,
            aliases,
        )
        if resolved_table["status"] == "violated":
            code: SqlContractErrorCode = (
                "SQL_CONTRACT_AMBIGUOUS_COLUMN"
                if resolved_table["reason"] == "ambiguous_unqualified_column"
                else (
                    "SQL_CONTRACT_INVALID_ALIAS"
                    if resolved_table["reason"] == "unknown_alias"
                    else "SQL_CONTRACT_UNKNOWN_COLUMN"
                )
            )
            findings.append(
                _finding(
                    code,
                    "Referencia de coluna nao aderente ao QueryPlan.",
                    details={
                        "column": column_name,
                        "reason": resolved_table["reason"],
                    },
                )
            )
        results.append(
            {
                "column": column_name,
                "table": resolved_table.get("table"),
                "status": resolved_table["status"],
                "reason": resolved_table["reason"],
            }
        )
    return sorted(
        results,
        key=lambda item: (
            str(item.get("table") or ""),
            item["column"],
            item["reason"],
        ),
    )


def _verify_planned_filters(
    analysis: SqlStatementAnalysis,
    query_plan: QueryPlan,
    policy: SqlContractPolicy,
    findings: list[SqlContractFinding],
) -> list[FilterVerificationResult]:
    context = _planning_context(query_plan)
    planned = context.get("planned_filters", [])
    bindings = context.get("resolved_filter_bindings", [])
    if not isinstance(planned, list) or not isinstance(bindings, list):
        raise SqlContractInputError("planned_filters e resolved_filter_bindings devem ser listas.")
    aliases = _analysis_aliases(analysis, policy)
    allowed = {table: set(columns) for table, columns in policy["allowed_columns"].items()}
    results: list[FilterVerificationResult] = []
    for obligation in planned:
        if not isinstance(obligation, Mapping) or obligation.get("required") is not True:
            continue
        filter_ref = _clean_text(obligation.get("filter_ref"))
        binding_ref = _clean_text(obligation.get("binding_ref"))
        concept = _clean_text(obligation.get("filter_concept"))
        scope = _clean_text(obligation.get("scope"))
        matches = [
            item for item in bindings
            if isinstance(item, Mapping) and _clean_text(item.get("binding_ref")) == binding_ref
        ]
        reason = ""
        status: VerificationStatus = "violated"
        expected: dict[str, Any] = {}
        matched_count = 0
        binding = matches[0] if len(matches) == 1 else None
        if not filter_ref or not binding_ref or not concept or scope not in {"row", "where"}:
            reason = "planned_filter_invalid"
        elif len(matches) != 1:
            reason = "binding_missing" if not matches else "binding_ambiguous"
        elif not _valid_filter_binding(binding, obligation, allowed):
            reason = "binding_invalid_or_incoherent"
        else:
            assert binding is not None
            target_table = _clean_text(binding.get("target_table")).casefold()
            target_column = _clean_text(binding.get("target_column")).casefold()
            operator = _clean_text(binding.get("operator"))
            expected = {
                "target_table": target_table,
                "target_column": target_column,
                "operator": operator,
                "literal_type": _value_type(binding.get("value")),
            }
            relevant = []
            unverifiable = False
            for predicate in analysis.get("predicates", []):
                resolved = _resolve_column_table(
                    {
                        "column": str(predicate.get("column") or ""),
                        "qualifier": predicate.get("qualifier"),
                        "schema": None,
                        "table": predicate.get("qualifier"),
                        "raw": "", "clause": "where", "is_wildcard": False,
                    },
                    allowed,
                    aliases,
                )
                if resolved.get("table") != target_table or predicate.get("column") != target_column:
                    continue
                relevant.append(predicate)
                if not predicate.get("supported"):
                    unverifiable = True
                    continue
                if predicate.get("operator") == operator and _same_literal(
                    predicate.get("value"), binding.get("value")
                ):
                    matched_count += 1
            if matched_count == 1:
                status, reason = "satisfied", "required_filter_present"
            elif matched_count > 1:
                status, reason = "unverifiable", "predicate_ambiguous"
            elif unverifiable:
                status, reason = "unverifiable", "predicate_not_verifiable"
            elif relevant:
                reason = "predicate_value_or_operator_mismatch"
            else:
                reason = "required_filter_missing"
        result: FilterVerificationResult = {
            "filter_ref": filter_ref, "binding_ref": binding_ref,
            "filter_concept": concept, "scope": scope,
            "status": status, "reason": reason, "expected": expected,
            "matched_predicate_count": matched_count,
        }
        results.append(result)
        if status != "satisfied":
            code: SqlContractErrorCode = (
                "SQL_CONTRACT_FILTER_BINDING_INVALID"
                if reason.startswith("binding_") or reason.endswith("invalid") or reason == "planned_filter_invalid"
                else "SQL_CONTRACT_FILTER_UNVERIFIABLE"
                if status == "unverifiable"
                else "SQL_CONTRACT_REQUIRED_FILTER_VIOLATED"
            )
            findings.append(_finding(code, "Filtro obrigatorio nao foi comprovado pela SQL.", details={
                "filter_ref": filter_ref, "binding_ref": binding_ref, "reason": reason,
            }))
    return sorted(results, key=lambda item: (item["filter_ref"], item["binding_ref"]))


def _valid_filter_binding(
    binding: Mapping[str, Any] | None,
    obligation: Mapping[str, Any],
    allowed: Mapping[str, set[str]],
) -> bool:
    if binding is None:
        return False
    table = _clean_text(binding.get("target_table")).casefold()
    column = _clean_text(binding.get("target_column")).casefold()
    return bool(
        table in allowed and column in allowed[table]
        and _clean_text(binding.get("operator")) in {"=", "<>", "<", "<=", ">", ">="}
        and _clean_text(binding.get("filter_concept")) == _clean_text(obligation.get("filter_concept"))
        and _clean_text(binding.get("scope")) == _clean_text(obligation.get("scope"))
        and binding.get("required") is True
        and _value_type(binding.get("value")) in {"string", "number", "boolean"}
    )


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    return "unsupported"


def _same_literal(observed: Any, expected: Any) -> bool:
    return _value_type(observed) == _value_type(expected) and observed == expected


def _verify_grouping_dimensions(
    analysis: SqlStatementAnalysis,
    query_plan: QueryPlan,
    policy: SqlContractPolicy,
    findings: list[SqlContractFinding],
) -> list[ColumnVerificationResult]:
    dimensions = _planned_grouping_dimensions(query_plan)
    if not dimensions:
        return []

    allowed = {
        table: set(columns)
        for table, columns in policy["allowed_columns"].items()
    }
    aliases = _analysis_aliases(analysis, policy)
    observed = [
        _observed_grouping_column(column, allowed, aliases)
        for column in analysis["column_references"]
        if column.get("clause") == "group" and not column.get("is_wildcard")
    ]

    results: list[ColumnVerificationResult] = []
    for dimension in dimensions:
        target_table = dimension["target_table"].casefold()
        target_column = dimension["target_column"].casefold()
        matched = any(
            item["column"] == target_column
            and _same_table_reference(target_table, item["table"])
            for item in observed
        )
        if matched:
            results.append(
                {
                    "column": target_column,
                    "table": target_table,
                    "status": "satisfied",
                    "reason": "planned_grouping_dimension_present",
                }
            )
            continue
        findings.append(
            _finding(
                "SQL_CONTRACT_GROUPING_DIMENSION_MISMATCH",
                "GROUP BY nao preserva dimensao planejada pelo QueryPlan.",
                details={
                    "canonical_value": dimension["canonical_value"],
                    "expected_table": dimension["target_table"],
                    "expected_column": dimension["target_column"],
                    "observed_groupings": observed,
                },
            )
        )
        results.append(
            {
                "column": target_column,
                "table": target_table,
                "status": "violated",
                "reason": "planned_grouping_dimension_missing",
            }
        )
    return sorted(
        results,
        key=lambda item: (
            str(item.get("table") or ""),
            item["column"],
            item["reason"],
        ),
    )


def _verify_joins(
    analysis: SqlStatementAnalysis,
    query_plan: QueryPlan,
    findings: list[SqlContractFinding],
) -> list[JoinVerificationResult]:
    authorized = _authorized_join_rules(query_plan)
    if not analysis["joins"]:
        return []
    results: list[JoinVerificationResult] = []
    for join in analysis["joins"]:
        left_table = _resolve_join_table(join.get("left_table"), analysis)
        right_table = _resolve_join_table(join.get("right_table"), analysis)
        if _has_uninterpreted_join_policy(authorized, left_table, right_table):
            results.append(
                {
                    "left_table": left_table,
                    "right_table": right_table,
                    "status": "unverifiable",
                    "reason": "authorized_join_rule_uninterpreted",
                }
            )
            continue
        if _join_allowed(authorized, left_table, right_table):
            results.append(
                {
                    "left_table": left_table,
                    "right_table": right_table,
                    "status": "satisfied",
                    "reason": "join_matches_authorized_rule",
                }
            )
            continue
        findings.append(
            _finding(
                "SQL_CONTRACT_JOIN_VIOLATED",
                "Join usado nao foi autorizado pelo QueryPlan.",
                details={
                    "left_table": left_table,
                    "right_table": right_table,
                },
            )
        )
        results.append(
            {
                "left_table": left_table,
                "right_table": right_table,
                "status": "violated",
                "reason": "join_not_authorized",
            }
        )
    return results


def _verify_analytical_operations(
    current_sql: str,
    analysis: SqlStatementAnalysis,
    query_plan: QueryPlan,
    findings: list[SqlContractFinding],
) -> list[RuleVerificationResult]:
    del current_sql
    operations = _planned_analytical_operations(query_plan)
    metric_binding_results = _verify_metric_bindings(query_plan, findings)
    if not operations:
        return metric_binding_results

    planned_metrics = _planned_metrics(query_plan)
    results: list[RuleVerificationResult] = list(metric_binding_results)
    for operation in operations:
        operation_type = operation["operation_type"]
        if operation_type == "ranking":
            results.extend(
                _verify_ranking_operation(
                    analysis,
                    operation,
                    planned_metrics,
                    findings,
                )
            )
            continue
        if operation_type == "comparison":
            results.extend(
                _verify_comparison_operation(
                    analysis,
                    operation,
                    planned_metrics,
                    _planned_grouping_dimensions(query_plan),
                    findings,
                )
            )
            continue
        results.append(
            _rule_result(
                operation_type,
                "unverifiable",
                "unsupported_analytical_operation",
                [],
            )
        )
    return results


def _verify_ranking_operation(
    analysis: SqlStatementAnalysis,
    operation: Mapping[str, Any],
    planned_metrics: list[dict[str, Any]],
    findings: list[SqlContractFinding],
) -> list[RuleVerificationResult]:
    metric_ref = _clean_text(operation.get("metric_ref"))
    if not metric_ref:
        return [
            _rule_result(
                "ranking",
                "unverifiable",
                "ranking_metric_ref_missing",
                [],
            )
        ]
    matching_metrics = [
        metric
        for metric in planned_metrics
        if metric["metric_ref"] == metric_ref
    ]
    if not matching_metrics:
        return [
            _rule_result(
                "ranking",
                "unverifiable",
                "ranking_planned_metric_missing",
                ["metric_ref"],
            )
        ]
    if len(matching_metrics) > 1:
        return [
            _rule_result(
                "ranking",
                "unverifiable",
                "ranking_planned_metric_ambiguous",
                ["metric_ref"],
            )
        ]

    root_scope = _root_query_scope(analysis)
    if root_scope is None:
        return [
            _rule_result(
                "ranking",
                "unverifiable",
                "ranking_root_scope_unavailable",
                ["metric_ref"],
            )
        ]

    metric = matching_metrics[0]
    select_match = _root_metric_select_item_match(root_scope, metric)
    checked_items = [
        "metric_ref",
        "planned_metric",
        "root_scope",
        "metric_select_item",
    ]
    if select_match["status"] == "missing":
        _ranking_finding(
            findings,
            "ranking_metric_select_item_missing",
            operation,
            metric,
        )
        return [
            _rule_result(
                "ranking",
                "violated",
                "ranking_metric_select_item_missing",
                checked_items,
            )
        ]
    if select_match["status"] == "unverifiable":
        return [
            _rule_result(
                "ranking",
                "unverifiable",
                str(select_match["reason"]),
                checked_items,
            )
        ]

    order_items = root_scope.get("order_by_items")
    if not isinstance(order_items, list) or not order_items:
        _ranking_finding(
            findings,
            "ranking_root_order_by_missing",
            operation,
            metric,
        )
        return [
            _rule_result(
                "ranking",
                "violated",
                "ranking_root_order_by_missing",
                [*checked_items, "root_order_by"],
            )
        ]

    metric_select_index = select_match["index"]
    order_matches = [
        item
        for item in order_items
        if isinstance(item, Mapping)
        and item.get("resolved_select_item_index") == metric_select_index
    ]
    if not order_matches:
        _ranking_finding(
            findings,
            "ranking_order_target_mismatch",
            operation,
            metric,
        )
        return [
            _rule_result(
                "ranking",
                "violated",
                "ranking_order_target_mismatch",
                [*checked_items, "root_order_by"],
            )
        ]
    if len(order_matches) > 1:
        return [
            _rule_result(
                "ranking",
                "unverifiable",
                "ranking_order_target_ambiguous",
                [*checked_items, "root_order_by"],
            )
        ]

    expected_direction = (
        "desc" if operation["direction"] == "descending" else "asc"
    )
    observed_direction = _clean_text(order_matches[0].get("direction"))
    if observed_direction != expected_direction:
        _ranking_finding(
            findings,
            "ranking_order_direction_mismatch",
            operation,
            metric,
            observed_direction=observed_direction,
            expected_direction=expected_direction,
        )
        return [
            _rule_result(
                "ranking",
                "violated",
                "ranking_order_direction_mismatch",
                [*checked_items, "root_order_by", "direction"],
            )
        ]

    results = [
        _rule_result(
            "ranking",
            "satisfied",
            "ranking_metric_order_satisfied",
            [*checked_items, "root_order_by", "direction"],
        )
    ]
    if operation.get("requested_limit") is not None:
        results.append(
            _rule_result(
                "ranking_limit",
                "unverifiable",
                "ranking_limit_validation_pending",
                ["requested_limit"],
            )
        )
    return results


def _verify_comparison_operation(
    analysis: SqlStatementAnalysis,
    operation: Mapping[str, Any],
    planned_metrics: list[dict[str, Any]],
    grouping_dimensions: list[dict[str, str]],
    findings: list[SqlContractFinding],
) -> list[RuleVerificationResult]:
    evidence: dict[str, Any] = {
        "operation_type": operation.get("operation_type"),
        "output_behavior": operation.get("output_behavior"),
        "combination_strategy": operation.get("combination_strategy"),
        "operand_metric_refs": operation.get("operand_metric_refs"),
        "multiple_metric_sources": operation.get("multiple_metric_sources"),
        "grouping_dimensions": grouping_dimensions,
        "join_semantics": operation.get("join_semantics"),
        "operand_scope_mapping": [],
        "gates": [],
    }
    results: list[RuleVerificationResult] = []

    def gate(name: str, status: VerificationStatus, reason: str) -> None:
        evidence["gates"].append(
            {
                "name": name,
                "status": _comparison_gate_status(status),
                "reason": reason,
            }
        )
        results.append(_rule_result(f"comparison_{name}", status, reason, [name]))

    def fail(name: str, reason: str) -> list[RuleVerificationResult]:
        gate(name, "violated", reason)
        _comparison_finding(findings, reason, evidence)
        return results

    refs = operation.get("operand_metric_refs")
    if not isinstance(refs, list) or not refs:
        return fail("cardinality", "comparison_cardinality_invalid")
    operand_refs = [_clean_text(ref) for ref in refs]
    if any(not ref for ref in operand_refs) or len(operand_refs) != len(set(operand_refs)):
        return fail("cardinality", "comparison_cardinality_invalid")
    cardinality_status = _comparison_cardinality_status(operation, len(operand_refs))
    if cardinality_status != "comparison_cardinality_valid":
        return fail("cardinality", cardinality_status)
    gate("cardinality", "satisfied", "comparison_cardinality_valid")

    metrics_by_ref: dict[str, list[dict[str, Any]]] = {}
    for metric in planned_metrics:
        metrics_by_ref.setdefault(metric["metric_ref"], []).append(metric)
    operand_metrics: list[dict[str, Any]] = []
    for ref in operand_refs:
        matches = metrics_by_ref.get(ref, [])
        if not matches:
            return fail("operand_resolution", "comparison_operand_missing")
        if len(matches) > 1:
            return fail("operand_resolution", "comparison_operand_ambiguous")
        operand_metrics.append(matches[0])
    gate("operand_resolution", "satisfied", "comparison_operands_resolved")

    valid_source_tables: list[str] = []
    for metric in operand_metrics:
        target_table = metric.get("target_table")
        if not isinstance(target_table, str) or not target_table.strip():
            return fail("source_authorization", "comparison_lineage_unproven")
        valid_source_tables.append(target_table.strip().casefold())

    planned_multiple_sources = operation.get("multiple_metric_sources")
    if not isinstance(planned_multiple_sources, bool):
        return fail(
            "multi_source_consistency",
            "comparison_multi_source_inconsistent",
        )
    source_tables = set(valid_source_tables)
    multiple_sources = len(source_tables) > 1
    evidence["derived_multiple_metric_sources"] = multiple_sources
    if planned_multiple_sources != multiple_sources:
        return fail(
            "multi_source_consistency",
            "comparison_multi_source_inconsistent",
        )
    gate(
        "multi_source_consistency",
        "satisfied",
        "comparison_multi_source_consistent",
    )

    if multiple_sources and _comparison_has_raw_metric_source_join(analysis, source_tables):
        return fail(
            "raw_source_join_absent",
            "comparison_raw_source_join_detected",
        )

    mappings: list[dict[str, Any]] = []
    for metric in operand_metrics:
        candidates = _comparison_operand_scope_candidates(
            analysis,
            metric,
            grouping_dimensions,
            allow_root=not multiple_sources,
        )
        if not candidates:
            return fail("source_authorization", "comparison_lineage_unproven")
        if len(candidates) > 1:
            return fail("source_authorization", "comparison_lineage_unproven")
        mapping = candidates[0]
        mappings.append(mapping)
        evidence["operand_scope_mapping"].append(mapping)
    gate("source_authorization", "satisfied", "comparison_sources_authorized")

    if any(mapping["reducing_aggregate"] is not True for mapping in mappings):
        return fail("reducing_aggregate", "comparison_operand_not_aggregated")
    gate("reducing_aggregate", "satisfied", "comparison_operands_aggregated")

    missing_grain = [
        mapping
        for mapping in mappings
        if not _comparison_mapping_has_expected_grain(mapping, grouping_dimensions)
    ]
    if missing_grain:
        return fail("dimension_grain", "comparison_dimension_grain_missing")
    gate(
        "dimension_grain",
        "satisfied" if grouping_dimensions else "not_applicable",
        "comparison_dimension_grain_satisfied"
        if grouping_dimensions
        else "comparison_has_no_grouping_dimensions",
    )

    gate(
        "raw_source_join_absent",
        "satisfied" if multiple_sources else "not_applicable",
        "comparison_raw_source_join_absent"
        if multiple_sources
        else "comparison_single_source",
    )

    if multiple_sources and not _comparison_aggregate_before_combine_proven(analysis, mappings):
        return fail(
            "aggregate_before_combine",
            "comparison_aggregate_before_combine_unproven",
        )
    gate(
        "aggregate_before_combine",
        "satisfied" if multiple_sources else "not_applicable",
        "comparison_aggregate_before_combine_satisfied"
        if multiple_sources
        else "comparison_single_source",
    )

    if not _comparison_root_outputs_all_operands(analysis, mappings):
        return fail("root_operand_presence", "comparison_root_operand_missing")
    gate("root_operand_presence", "satisfied", "comparison_root_operands_present")

    if grouping_dimensions and not _comparison_root_preserves_grouping(analysis, grouping_dimensions):
        return fail("root_grouping_presence", "comparison_dimension_grain_missing")
    gate(
        "root_grouping_presence",
        "satisfied" if grouping_dimensions else "not_applicable",
        "comparison_root_grouping_present"
        if grouping_dimensions
        else "comparison_has_no_grouping_dimensions",
    )

    join_status = _comparison_join_semantics_status(
        analysis,
        operation,
        mappings,
        multiple_sources=multiple_sources,
        has_grouping_dimensions=bool(grouping_dimensions),
    )
    if join_status != "comparison_join_semantics_satisfied":
        return fail("join_semantics", join_status)
    gate(
        "join_semantics",
        "satisfied" if multiple_sources and grouping_dimensions else "not_applicable",
        join_status,
    )

    gate("lineage", "satisfied", "comparison_lineage_satisfied")
    return results


def _verify_rules(
    *,
    sql_token_norms: list[str],
    analysis: SqlStatementAnalysis,
    query_plan: QueryPlan,
    policy: SqlContractPolicy,
    findings: list[SqlContractFinding],
) -> list[RuleVerificationResult]:
    del policy
    results: list[RuleVerificationResult] = []
    for rule in _rules(_planning_context(query_plan)):
        name = str(rule.get("rule_name", "")).strip()
        content = rule.get("rule_content")
        if not isinstance(content, Mapping):
            results.append(
                _rule_result(name, "unverifiable", "opaque_rule_content", [])
            )
            continue
        recognized = sorted(
            key for key in content if str(key) in _STRUCTURED_RULE_KEYS
        )
        if not recognized:
            results.append(
                _rule_result(name, "unverifiable", "no_structural_keys", [])
            )
            continue
        violations = _rule_violations(
            content,
            sql_token_norms,
            analysis,
        )
        if violations:
            findings.append(
                _finding(
                    "SQL_CONTRACT_RULE_VIOLATED",
                    "Regra estrutural do QueryPlan nao foi satisfeita.",
                    details={
                        "rule_name": name,
                        "violations": violations,
                    },
                )
            )
            results.append(
                _rule_result(name, "violated", "structured_rule_failed", recognized)
            )
        else:
            results.append(
                _rule_result(name, "satisfied", "structured_rule_satisfied", recognized)
            )
    return sorted(results, key=lambda item: item["rule_name"].casefold())


def _verify_limit(
    analysis: SqlStatementAnalysis,
    policy: SqlContractPolicy,
    findings: list[SqlContractFinding],
) -> None:
    limit_policy = policy["limit_policy"]
    if limit_policy == "forbid" and analysis["has_limit"]:
        findings.append(
            _finding(
                "SQL_CONTRACT_LIMIT_VIOLATED",
                "LIMIT foi proibido por regra do QueryPlan.",
            )
        )
    if limit_policy == "require" and not analysis["has_limit"]:
        findings.append(
            _finding(
                "SQL_CONTRACT_LIMIT_VIOLATED",
                "LIMIT foi exigido por regra do QueryPlan.",
            )
        )


def _verify_wildcards(
    analysis: SqlStatementAnalysis,
    policy: SqlContractPolicy,
    findings: list[SqlContractFinding],
) -> None:
    if analysis["has_select_star"]:
        _wildcard_finding(
            policy["wildcard_policy"],
            "SELECT * foi detectado.",
            findings,
        )
    if analysis["has_table_star"]:
        _wildcard_finding(
            policy["table_wildcard_policy"],
            "table.* foi detectado.",
            findings,
        )


def _rule_violations(
    content: Mapping[str, Any],
    sql_token_norms: list[str],
    analysis: SqlStatementAnalysis,
) -> list[str]:
    violations: list[str] = []
    for fragment in _text_list(content.get("required_sql_fragments")):
        if not _fragment_present(fragment, sql_token_norms):
            violations.append("required_sql_fragment_missing")
    for fragment in _text_list(content.get("required_filters")):
        if not _fragment_present(fragment, sql_token_norms):
            violations.append("required_filter_missing")
    for fragment in _text_list(content.get("required_groupings")):
        if not _fragment_present(fragment, sql_token_norms):
            violations.append("required_grouping_missing")
    for fragment in _text_list(content.get("forbidden_sql_fragments")):
        if _fragment_present(fragment, sql_token_norms):
            violations.append("forbidden_sql_fragment_present")
    for fragment in _text_list(content.get("forbidden_filters")):
        if _fragment_present(fragment, sql_token_norms):
            violations.append("forbidden_filter_present")
    for keyword in _text_list(content.get("forbidden_keywords")):
        if keyword.casefold() in set(analysis["token_norms"]):
            violations.append("forbidden_keyword_present")
    required_tables = {
        value.casefold()
        for value in _text_list(content.get("required_tables"))
    }
    if required_tables:
        used_tables = set(analysis["tables"])
        if not required_tables <= used_tables:
            violations.append("required_table_missing")
    required_columns = {
        value.casefold()
        for value in _text_list(content.get("required_columns"))
    }
    if required_columns:
        used_columns = {
            column["column"].casefold()
            for column in analysis["column_references"]
        }
        if not required_columns <= used_columns:
            violations.append("required_column_missing")
    return sorted(set(violations))


def _fragment_present(
    fragment: str,
    sql_token_norms: list[str],
) -> bool:
    try:
        fragment_tokens = normalized_sql_tokens(
            fragment,
            include_string_values=True,
        )
    except SqlAnalysisError:
        return fragment.casefold() in " ".join(sql_token_norms)
    if not fragment_tokens:
        return False
    if len(fragment_tokens) > len(sql_token_norms):
        return False
    width = len(fragment_tokens)
    return any(
        sql_token_norms[index : index + width] == fragment_tokens
        for index in range(0, len(sql_token_norms) - width + 1)
    )


def _resolve_column_table(
    column: SqlColumnReference,
    allowed: dict[str, set[str]],
    aliases: dict[str, str],
) -> dict[str, Any]:
    column_name = column["column"].casefold()
    schema = column.get("schema")
    table = column.get("table")
    qualifier = column.get("qualifier")
    if schema and table:
        qualified = f"{schema.casefold()}.{table.casefold()}"
        return _column_on_table(column_name, qualified, allowed)
    if qualifier:
        key = qualifier.casefold()
        if key in aliases:
            return _column_on_table(column_name, aliases[key], allowed)
        table_matches = [
            table_name
            for table_name in allowed
            if table_name.split(".")[-1] == key
        ]
        if len(table_matches) == 1:
            return _column_on_table(column_name, table_matches[0], allowed)
        return {
            "status": "violated",
            "table": None,
            "reason": "unknown_alias",
        }
    matches = [
        table_name
        for table_name, columns in allowed.items()
        if column_name in columns
    ]
    if len(matches) == 1:
        return {
            "status": "satisfied",
            "table": matches[0],
            "reason": "unqualified_column_unambiguous",
        }
    if len(matches) > 1:
        return {
            "status": "violated",
            "table": None,
            "reason": "ambiguous_unqualified_column",
        }
    return {
        "status": "violated",
        "table": None,
        "reason": "column_not_in_projected_catalog",
    }


def _column_on_table(
    column_name: str,
    table_name: str,
    allowed: dict[str, set[str]],
) -> dict[str, Any]:
    if table_name not in allowed:
        return {
            "status": "violated",
            "table": table_name,
            "reason": "table_not_in_query_plan",
        }
    if column_name not in allowed[table_name]:
        return {
            "status": "violated",
            "table": table_name,
            "reason": "column_not_in_projected_catalog",
        }
    return {
        "status": "satisfied",
        "table": table_name,
        "reason": "column_in_projected_catalog",
    }


def _planned_grouping_dimensions(
    query_plan: QueryPlan,
) -> list[dict[str, str]]:
    planning_context = _planning_context(query_plan)
    detected = planning_context.get("detected_dimensions", [])
    if not isinstance(detected, list):
        return []
    dimensions: list[dict[str, str]] = []
    for item in detected:
        if not isinstance(item, Mapping):
            continue
        if item.get("grouping_requested") is not True:
            continue
        target_table = _clean_text(item.get("target_table"))
        target_column = _clean_text(item.get("target_column"))
        if not target_table or not target_column:
            continue
        dimensions.append(
            {
                "canonical_value": _clean_text(item.get("canonical_value")),
                "target_table": target_table,
                "target_column": target_column,
            }
        )
    return sorted(
        dimensions,
        key=lambda dimension: (
            dimension["canonical_value"].casefold(),
            dimension["target_table"].casefold(),
            dimension["target_column"].casefold(),
        ),
    )


def _planned_analytical_operations(
    query_plan: QueryPlan,
) -> list[dict[str, Any]]:
    planning_context = _planning_context(query_plan)
    raw_operations = planning_context.get("analytical_operations", [])
    if not isinstance(raw_operations, list):
        return []
    operations: list[dict[str, Any]] = []
    for item in raw_operations:
        if not isinstance(item, Mapping):
            continue
        operation_type = _clean_text(item.get("operation_type"))
        canonical_value = _clean_text(item.get("canonical_value"))
        if canonical_value != operation_type:
            continue
        if operation_type == "ranking":
            direction = _clean_text(item.get("direction"))
            requested_limit = item.get("requested_limit")
            metric_ref = _clean_text(item.get("metric_ref"))
            if direction not in {"ascending", "descending"}:
                continue
            if requested_limit is not None and (
                isinstance(requested_limit, bool)
                or not isinstance(requested_limit, int)
                or requested_limit <= 0
            ):
                continue
            operations.append(
                {
                    "operation_type": operation_type,
                    "canonical_value": canonical_value,
                    "direction": direction,
                    "requested_limit": requested_limit,
                    "metric_ref": metric_ref,
                }
            )
            continue
        if operation_type == "comparison":
            if _clean_text(item.get("output_behavior")) != "side_by_side":
                continue
            if (
                _clean_text(item.get("combination_strategy"))
                != "aggregate_then_combine"
            ):
                continue
            operand_metric_refs = item.get("operand_metric_refs")
            if not isinstance(operand_metric_refs, list):
                continue
            multiple_metric_sources = item.get("multiple_metric_sources")
            if not isinstance(multiple_metric_sources, bool):
                continue
            operations.append(
                {
                    "operation_type": operation_type,
                    "canonical_value": canonical_value,
                    "output_behavior": "side_by_side",
                    "combination_strategy": "aggregate_then_combine",
                    "operand_metric_refs": [
                        _clean_text(ref) for ref in operand_metric_refs
                    ],
                    "multiple_metric_sources": multiple_metric_sources,
                    "join_semantics": _clean_text(item.get("join_semantics")),
                    "binding_cardinality": item.get("binding_cardinality"),
                }
            )
    return sorted(
        operations,
        key=lambda operation: (
            operation["operation_type"],
            operation.get("direction", ""),
            operation.get("metric_ref", ""),
            ",".join(operation.get("operand_metric_refs", [])),
            operation.get("requested_limit") or 0,
        ),
    )


def _planned_metrics(query_plan: QueryPlan) -> list[dict[str, Any]]:
    planning_context = _planning_context(query_plan)
    raw_metrics = planning_context.get("planned_metrics", [])
    if not isinstance(raw_metrics, list):
        return []
    metrics: list[dict[str, Any]] = []
    for item in raw_metrics:
        if not isinstance(item, Mapping):
            continue
        metric_ref = _clean_text(item.get("metric_ref"))
        metric_concept = _clean_text(item.get("metric_concept"))
        target_table = _clean_text(item.get("target_table"))
        target_column = _clean_text(item.get("target_column"))
        aggregate = item.get("aggregate")
        if (
            not metric_ref
            or not metric_concept
            or not target_table
            or not target_column
            or aggregate is not None
        ):
            continue
        metrics.append(
            {
                "metric_ref": metric_ref,
                "metric_concept": metric_concept,
                "target_table": target_table,
                "target_column": target_column,
                "mapping_source": _clean_text(item.get("mapping_source")),
                "binding_ref": _clean_text(item.get("binding_ref")),
            }
        )
    return sorted(
        metrics,
        key=lambda metric: (
            metric["metric_ref"],
            metric["metric_concept"],
            metric["target_table"].casefold(),
            metric["target_column"].casefold(),
        ),
    )


def _verify_metric_bindings(
    query_plan: QueryPlan,
    findings: list[SqlContractFinding],
) -> list[RuleVerificationResult]:
    planning_context = _planning_context(query_plan)
    raw_metrics = planning_context.get("planned_metrics", [])
    if not isinstance(raw_metrics, list):
        return []
    bound_metrics = [
        item
        for item in raw_metrics
        if isinstance(item, Mapping)
        and _clean_text(item.get("mapping_source")) == "metric_binding"
    ]
    if not bound_metrics:
        return []
    results: list[RuleVerificationResult] = []
    seen_refs: set[str] = set()
    for metric in bound_metrics:
        metric_ref = _clean_text(metric.get("metric_ref"))
        binding_ref = _clean_text(metric.get("binding_ref"))
        metric_concept = _clean_text(metric.get("metric_concept"))
        target_table = _clean_text(metric.get("target_table"))
        target_column = _clean_text(metric.get("target_column"))
        checked = [
            "metric_ref",
            "binding_ref",
            "metric_concept",
            "target_table",
            "target_column",
        ]
        if not (
            metric_ref
            and binding_ref
            and metric_concept
            and target_table
            and target_column
        ):
            _metric_binding_finding(
                findings,
                "metric_binding_incomplete",
                metric,
            )
            results.append(
                _rule_result(
                    "metric_binding",
                    "violated",
                    "metric_binding_incomplete",
                    checked,
                )
            )
            continue
        if binding_ref in seen_refs:
            _metric_binding_finding(
                findings,
                "metric_binding_duplicate_ref",
                metric,
            )
            results.append(
                _rule_result(
                    "metric_binding",
                    "violated",
                    "metric_binding_duplicate_ref",
                    ["binding_ref"],
                )
            )
            continue
        seen_refs.add(binding_ref)
        if not _metric_binding_target_is_authorized(
            planning_context,
            target_table=target_table,
            target_column=target_column,
        ):
            _metric_binding_finding(
                findings,
                "metric_binding_target_not_authorized",
                metric,
            )
            results.append(
                _rule_result(
                    "metric_binding",
                    "violated",
                    "metric_binding_target_not_authorized",
                    ["target_table", "target_column"],
                )
            )
            continue
        results.append(
            _rule_result(
                "metric_binding",
                "passed",
                "metric_binding_structurally_valid",
                checked,
            )
        )
    return results


def _metric_binding_target_is_authorized(
    planning_context: Mapping[str, Any],
    *,
    target_table: str,
    target_column: str,
) -> bool:
    target_table_key = target_table.casefold()
    target_column_key = target_column.casefold()
    for table in planning_context.get("required_tables", []):
        if not isinstance(table, Mapping):
            continue
        qualified = _clean_text(table.get("qualified_name"))
        schema_name = _clean_text(table.get("schema_name"))
        table_name = _clean_text(table.get("table_name"))
        if not qualified and schema_name and table_name:
            qualified = f"{schema_name}.{table_name}"
        if qualified.casefold() != target_table_key:
            continue
        metric_columns = table.get("metric_columns")
        if isinstance(metric_columns, list):
            return any(
                isinstance(column, str)
                and column.strip().casefold() == target_column_key
                for column in metric_columns
            )
        if isinstance(metric_columns, str):
            return metric_columns.strip().casefold() == target_column_key
        return False
    return False


def _metric_binding_finding(
    findings: list[SqlContractFinding],
    reason: str,
    metric: Mapping[str, Any],
) -> None:
    findings.append(
        _finding(
            "SQL_CONTRACT_RULE_VIOLATED",
            "Metric binding planejado é estruturalmente inválido.",
            details={
                "reason": reason,
                "metric_ref": metric.get("metric_ref"),
                "binding_ref": metric.get("binding_ref"),
                "target_table": metric.get("target_table"),
                "target_column": metric.get("target_column"),
            },
        )
    )


def _root_query_scope(
    analysis: SqlStatementAnalysis,
) -> Mapping[str, Any] | None:
    scopes = analysis.get("query_scopes", [])
    if not isinstance(scopes, list):
        return None
    roots = [
        scope
        for scope in scopes
        if isinstance(scope, Mapping) and scope.get("is_root") is True
    ]
    return roots[0] if len(roots) == 1 else None


def _root_metric_select_item_match(
    root_scope: Mapping[str, Any],
    metric: Mapping[str, Any],
) -> dict[str, Any]:
    select_items = root_scope.get("select_items", [])
    if not isinstance(select_items, list):
        return {"status": "missing", "index": None, "reason": "no_select_items"}
    safe_matches: list[int] = []
    unverifiable_matches: list[int] = []
    for index, item in enumerate(select_items):
        if not isinstance(item, Mapping):
            continue
        column_references = item.get("column_references", [])
        if not isinstance(column_references, list):
            continue
        identity = _select_item_metric_identity(column_references, metric)
        if identity == "safe_match":
            safe_matches.append(index)
        elif identity == "unverifiable_match":
            unverifiable_matches.append(index)
    if len(safe_matches) == 1 and not unverifiable_matches:
        return {
            "status": "matched",
            "index": safe_matches[0],
            "reason": "exclusive_metric_reference",
        }
    if len(safe_matches) > 1:
        return {
            "status": "unverifiable",
            "index": None,
            "reason": "ranking_metric_select_item_ambiguous",
        }
    if safe_matches or unverifiable_matches:
        return {
            "status": "unverifiable",
            "index": None,
            "reason": "ranking_metric_select_item_unverifiable",
        }
    return {
        "status": "missing",
        "index": None,
        "reason": "ranking_metric_select_item_missing",
    }


def _select_item_metric_identity(
    column_references: list[Any],
    metric: Mapping[str, Any],
) -> Literal["safe_match", "unverifiable_match", "no_target"]:
    target = _metric_physical_reference(metric)
    physical_references: set[tuple[str, str, str]] = set()
    has_unresolved_reference = False
    for column in column_references:
        if not isinstance(column, Mapping):
            continue
        physical_reference = _physical_column_reference(column)
        if physical_reference is None:
            has_unresolved_reference = True
            continue
        physical_references.add(physical_reference)
    if target not in physical_references:
        return "no_target"
    if has_unresolved_reference or physical_references != {target}:
        return "unverifiable_match"
    return "safe_match"


def _comparison_cardinality_status(
    operation: Mapping[str, Any],
    operand_count: int,
) -> str:
    cardinality = operation.get("binding_cardinality")
    if not isinstance(cardinality, Mapping):
        return "comparison_cardinality_invalid"
    minimum = cardinality.get("minimum")
    maximum = cardinality.get("maximum")
    if (
        isinstance(minimum, bool)
        or not isinstance(minimum, int)
        or minimum <= 0
        or isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or maximum < minimum
    ):
        return "comparison_cardinality_invalid"
    if operand_count < minimum or operand_count > maximum:
        return "comparison_cardinality_invalid"
    return "comparison_cardinality_valid"


def _comparison_operand_scope_candidates(
    analysis: SqlStatementAnalysis,
    metric: Mapping[str, Any],
    grouping_dimensions: list[dict[str, str]],
    *,
    allow_root: bool,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for scope in _query_scopes(analysis):
        if scope.get("is_root") is True and not allow_root:
            continue
        if _clean_text(metric.get("target_table")).casefold() not in {
            str(table).casefold()
            for table in scope.get("physical_tables", [])
        }:
            continue
        metric_item = _scope_metric_select_item_match(scope, metric)
        if metric_item is None:
            continue
        grain = _comparison_scope_grouping_grain(scope, grouping_dimensions)
        candidates.append(
            {
                "metric_ref": metric.get("metric_ref"),
                "scope_id": scope.get("scope_id"),
                "source_table": metric.get("target_table"),
                "source_column": metric.get("target_column"),
                "reducing_aggregate": (
                    _select_item_has_reducing_aggregate(metric_item)
                    if scope.get("is_root") is True and allow_root
                    else scope.get("has_reducing_aggregate") is True
                ),
                "grouping_grain": grain,
                "output_name": _select_output_name_for_contract(metric_item),
            }
        )
    return candidates


def _scope_metric_select_item_match(
    scope: Mapping[str, Any],
    metric: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    select_items = scope.get("select_items", [])
    if not isinstance(select_items, list):
        return None
    matches = [
        item
        for item in select_items
        if isinstance(item, Mapping)
        and _select_item_metric_identity(
            item.get("column_references", [])
            if isinstance(item.get("column_references"), list)
            else [],
            metric,
        )
        == "safe_match"
    ]
    return matches[0] if len(matches) == 1 else None


_CONTRACT_AGGREGATE_FUNCTIONS = {"avg", "count", "max", "min", "sum"}


def _select_item_has_reducing_aggregate(item: Mapping[str, Any]) -> bool:
    expression = _clean_text(item.get("expression"))
    if not expression:
        return False
    tokens = _contract_expression_tokens(expression)
    for index, token in enumerate(tokens[:-1]):
        if (
            token in _CONTRACT_AGGREGATE_FUNCTIONS
            and tokens[index + 1] == "("
            and not _contract_aggregate_invocation_is_window(tokens, index)
        ):
            return True
    return False


def _contract_aggregate_invocation_is_window(
    tokens: list[str],
    function_index: int,
) -> bool:
    end = _contract_matching_paren_index(tokens, function_index + 1)
    if end is None:
        return True
    next_index = end + 1
    if (
        _contract_token_at(tokens, next_index) == "filter"
        and _contract_token_at(tokens, next_index + 1) == "("
    ):
        filter_end = _contract_matching_paren_index(tokens, next_index + 1)
        if filter_end is None:
            return True
        next_index = filter_end + 1
    return _contract_token_at(tokens, next_index) == "over"


def _contract_expression_tokens(expression: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for character in expression:
        if character.isalnum() or character == "_":
            current.append(character.casefold())
            continue
        if current:
            tokens.append("".join(current))
            current = []
        if character in {"(", ")"}:
            tokens.append(character)
    if current:
        tokens.append("".join(current))
    return tokens


def _contract_matching_paren_index(
    tokens: list[str],
    open_index: int,
) -> int | None:
    if _contract_token_at(tokens, open_index) != "(":
        return None
    depth = 0
    for index in range(open_index, len(tokens)):
        token = tokens[index]
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _contract_token_at(tokens: list[str], index: int) -> str:
    if index < 0 or index >= len(tokens):
        return ""
    return tokens[index]


def _comparison_scope_grouping_grain(
    scope: Mapping[str, Any],
    grouping_dimensions: list[dict[str, str]],
) -> list[dict[str, str]]:
    if not grouping_dimensions:
        group_by_items = scope.get("group_by_items", [])
        return [] if not group_by_items else [{"unexpected_group_by": str(group_by_items)}]
    select_items = scope.get("select_items", [])
    if not isinstance(select_items, list):
        return []
    output: list[dict[str, str]] = []
    for dimension in grouping_dimensions:
        for item in select_items:
            if not isinstance(item, Mapping):
                continue
            if _select_item_references_dimension(item, dimension):
                output.append(
                    {
                        "canonical_value": dimension["canonical_value"],
                        "target_table": dimension["target_table"],
                        "target_column": dimension["target_column"],
                    }
                )
                break
    return output


def _comparison_mapping_has_expected_grain(
    mapping: Mapping[str, Any],
    grouping_dimensions: list[dict[str, str]],
) -> bool:
    grain = mapping.get("grouping_grain", [])
    if not grouping_dimensions:
        return grain == []
    if not isinstance(grain, list):
        return False
    expected = {
        (
            dimension["target_table"].casefold(),
            dimension["target_column"].casefold(),
        )
        for dimension in grouping_dimensions
    }
    observed = {
        (
            _clean_text(item.get("target_table")).casefold(),
            _clean_text(item.get("target_column")).casefold(),
        )
        for item in grain
        if isinstance(item, Mapping)
    }
    return expected <= observed


def _select_item_references_dimension(
    item: Mapping[str, Any],
    dimension: Mapping[str, str],
) -> bool:
    target_table = dimension["target_table"].casefold()
    target_column = dimension["target_column"].casefold()
    columns = item.get("column_references", [])
    if not isinstance(columns, list):
        return False
    for column in columns:
        if not isinstance(column, Mapping):
            continue
        physical = _physical_column_reference(column)
        if physical is None:
            continue
        schema, table, name = physical
        if f"{schema}.{table}" == target_table and name == target_column:
            return True
    return False


def _comparison_has_raw_metric_source_join(
    analysis: SqlStatementAnalysis,
    source_tables: set[str],
) -> bool:
    for scope in _query_scopes(analysis):
        physical_tables = {
            str(table).casefold()
            for table in scope.get("physical_tables", [])
        }
        if len(physical_tables & source_tables) >= 2 and int(
            scope.get("raw_table_join_count") or 0
        ) > 0:
            return True
    return False


def _comparison_aggregate_before_combine_proven(
    analysis: SqlStatementAnalysis,
    mappings: list[dict[str, Any]],
) -> bool:
    root = _root_query_scope(analysis)
    if root is None:
        return False
    mapped_scopes = {
        _clean_text(mapping.get("scope_id"))
        for mapping in mappings
        if _clean_text(mapping.get("scope_id"))
    }
    if len(mapped_scopes) != len(mappings):
        return False
    if int(root.get("aggregated_scope_join_count") or 0) <= 0:
        return False
    root_ref_map = _root_scope_reference_map(root, analysis)
    joined_child_scopes: set[str] = set()
    for join in root.get("joins", []):
        if not isinstance(join, Mapping):
            continue
        for side in ("left_table", "right_table"):
            scope_id = root_ref_map.get(_clean_text(join.get(side)).casefold())
            if scope_id:
                joined_child_scopes.add(scope_id)
    return mapped_scopes <= joined_child_scopes


def _comparison_root_outputs_all_operands(
    analysis: SqlStatementAnalysis,
    mappings: list[dict[str, Any]],
) -> bool:
    root = _root_query_scope(analysis)
    if root is None:
        return False
    lineage = root.get("output_lineage", [])
    if not isinstance(lineage, list):
        return False
    root_scope_id = _clean_text(root.get("scope_id"))
    select_items = root.get("select_items", [])
    if not isinstance(select_items, list):
        return False
    root_output_names = {
        _select_output_name_for_contract(item)
        for item in select_items
        if isinstance(item, Mapping)
    }
    for mapping in mappings:
        scope_id = _clean_text(mapping.get("scope_id"))
        output_name = _clean_text(mapping.get("output_name")).casefold()
        if not scope_id or not output_name:
            return False
        if scope_id == root_scope_id:
            if output_name not in root_output_names:
                return False
            continue
        if not any(
            isinstance(item, Mapping)
            and _clean_text(item.get("source_scope_id")) == scope_id
            and _clean_text(item.get("source_output")).casefold() == output_name
            for item in lineage
        ):
            return False
    return True


def _comparison_root_preserves_grouping(
    analysis: SqlStatementAnalysis,
    grouping_dimensions: list[dict[str, str]],
) -> bool:
    root = _root_query_scope(analysis)
    if root is None:
        return False
    select_items = root.get("select_items", [])
    lineage = root.get("output_lineage", [])
    if not isinstance(select_items, list) or not isinstance(lineage, list):
        return False
    root_outputs = {
        _select_output_name_for_contract(item)
        for item in select_items
        if isinstance(item, Mapping)
    }
    lineage_sources = {
        _clean_text(item.get("source_output")).casefold()
        for item in lineage
        if isinstance(item, Mapping)
    }
    available = {item for item in root_outputs | lineage_sources if item}
    return all(
        dimension["target_column"].casefold() in available
        for dimension in grouping_dimensions
    )


def _comparison_join_semantics_status(
    analysis: SqlStatementAnalysis,
    operation: Mapping[str, Any],
    mappings: list[dict[str, Any]],
    *,
    multiple_sources: bool,
    has_grouping_dimensions: bool,
) -> str:
    if not multiple_sources or not has_grouping_dimensions:
        return "comparison_join_semantics_satisfied"
    join_semantics = _clean_text(operation.get("join_semantics"))
    if not join_semantics:
        return "comparison_join_semantics_missing"
    expected = {
        "preserve_all_operand_categories": "full outer join",
        "common_operand_categories_only": "inner join",
    }.get(join_semantics)
    if expected is None:
        return "comparison_join_semantics_mismatch"
    root = _root_query_scope(analysis)
    if root is None:
        return "comparison_lineage_unproven"
    root_ref_map = _root_scope_reference_map(root, analysis)
    mapped_scopes = {
        _clean_text(mapping.get("scope_id"))
        for mapping in mappings
        if _clean_text(mapping.get("scope_id"))
    }
    for join in root.get("joins", []):
        if not isinstance(join, Mapping):
            continue
        left = root_ref_map.get(_clean_text(join.get("left_table")).casefold())
        right = root_ref_map.get(_clean_text(join.get("right_table")).casefold())
        if {left, right} <= mapped_scopes and {left, right}:
            return (
                "comparison_join_semantics_satisfied"
                if _clean_text(join.get("join_type")).casefold() == expected
                else "comparison_join_semantics_mismatch"
            )
    return "comparison_join_semantics_mismatch"


def _root_scope_reference_map(
    root: Mapping[str, Any],
    analysis: SqlStatementAnalysis,
) -> dict[str, str]:
    scopes = {
        _clean_text(scope.get("scope_id")): scope
        for scope in _query_scopes(analysis)
    }
    refs: dict[str, str] = {}
    subquery_children = [
        scope_id
        for scope_id in root.get("child_scopes", [])
        if isinstance(scope_id, str)
        and isinstance(scopes.get(scope_id), Mapping)
        and scopes[scope_id].get("scope_type") == "subquery"
    ]
    subquery_index = 0
    for item in root.get("object_references", []):
        if not isinstance(item, Mapping):
            continue
        scope_id = ""
        if item.get("is_cte"):
            scope_id = f"cte:{item.get('table')}"
        elif item.get("is_subquery"):
            if subquery_index >= len(subquery_children):
                continue
            scope_id = subquery_children[subquery_index]
            subquery_index += 1
        if scope_id not in scopes:
            continue
        for key in ("table", "alias"):
            value = _clean_text(item.get(key)).casefold()
            if value:
                refs[value] = scope_id
    return refs


def _query_scopes(analysis: SqlStatementAnalysis) -> list[Mapping[str, Any]]:
    scopes = analysis.get("query_scopes", [])
    if not isinstance(scopes, list):
        return []
    return [scope for scope in scopes if isinstance(scope, Mapping)]


def _select_output_name_for_contract(item: Mapping[str, Any]) -> str | None:
    alias = _clean_text(item.get("alias"))
    if alias:
        return alias.casefold()
    expression = _clean_text(item.get("expression")).casefold()
    if expression and _is_plain_identifier(expression):
        return expression
    columns = item.get("column_references", [])
    if isinstance(columns, list) and len(columns) == 1 and isinstance(columns[0], Mapping):
        return _clean_text(columns[0].get("column")).casefold()
    return None


def _is_plain_identifier(value: str) -> bool:
    if not value:
        return False
    first = value[0]
    return (first == "_" or first.isalpha()) and all(
        character == "_" or character.isalnum()
        for character in value
    )


def _comparison_gate_status(status: VerificationStatus) -> str:
    return {
        "satisfied": "PASS",
        "violated": "FAIL",
        "unverifiable": "FAIL",
        "not_applicable": "NOT_APPLICABLE",
    }[status]


def _comparison_finding(
    findings: list[SqlContractFinding],
    reason: str,
    evidence: Mapping[str, Any],
) -> None:
    findings.append(
        _finding(
            "SQL_CONTRACT_RULE_VIOLATED",
            "Operacao de comparison planejada nao foi satisfeita pela SQL.",
            details={
                "reason": reason,
                "comparison_evidence": deepcopy(dict(evidence)),
            },
        )
    )


def _select_column_matches_metric(
    column: Mapping[str, Any],
    metric: Mapping[str, Any],
) -> bool:
    target_column = _clean_text(metric.get("target_column")).casefold()
    if _clean_text(column.get("column")).casefold() != target_column:
        return False
    schema = _clean_text(column.get("schema"))
    table = _clean_text(column.get("table"))
    if not schema or not table:
        return False
    observed_table = f"{schema.casefold()}.{table.casefold()}"
    return observed_table == _clean_text(metric.get("target_table")).casefold()


def _metric_physical_reference(
    metric: Mapping[str, Any],
) -> tuple[str, str, str]:
    target_table = _clean_text(metric.get("target_table")).casefold()
    if "." in target_table:
        schema, table = target_table.rsplit(".", 1)
    else:
        schema, table = "", target_table
    return (
        schema,
        table,
        _clean_text(metric.get("target_column")).casefold(),
    )


def _physical_column_reference(
    column: Mapping[str, Any],
) -> tuple[str, str, str] | None:
    schema = _clean_text(column.get("schema"))
    table = _clean_text(column.get("table"))
    name = _clean_text(column.get("column"))
    if not schema or not table or not name:
        return None
    return (schema.casefold(), table.casefold(), name.casefold())


def _ranking_finding(
    findings: list[SqlContractFinding],
    reason: str,
    operation: Mapping[str, Any],
    metric: Mapping[str, Any],
    *,
    observed_direction: str | None = None,
    expected_direction: str | None = None,
) -> None:
    details: dict[str, Any] = {
        "reason": reason,
        "operation_type": operation.get("operation_type"),
        "metric_ref": operation.get("metric_ref"),
        "target_table": metric.get("target_table"),
        "target_column": metric.get("target_column"),
    }
    if observed_direction is not None:
        details["observed_direction"] = observed_direction
    if expected_direction is not None:
        details["expected_direction"] = expected_direction
    findings.append(
        _finding(
            "SQL_CONTRACT_RULE_VIOLATED",
            "Operacao analitica planejada nao foi satisfeita pela SQL.",
            details=details,
        )
    )


def _observed_grouping_column(
    column: SqlColumnReference,
    allowed: dict[str, set[str]],
    aliases: dict[str, str],
) -> dict[str, str | None]:
    resolved = _resolve_column_table(column, allowed, aliases)
    return {
        "column": column["column"].casefold(),
        "table": resolved.get("table"),
        "qualifier": column.get("qualifier"),
        "resolution": resolved["reason"],
    }


def _same_table_reference(
    expected_table: str,
    observed_table: str | None,
) -> bool:
    if not observed_table:
        return False
    expected = expected_table.casefold()
    observed = observed_table.casefold()
    return expected == observed


def _clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _resolved_tables(
    analysis: SqlStatementAnalysis,
    policy: SqlContractPolicy,
) -> set[str]:
    allowed = set(policy["allowed_tables"])
    by_bare: dict[str, list[str]] = {}
    for table in allowed:
        by_bare.setdefault(table.split(".")[-1], []).append(table)
    output: set[str] = set()
    for item in analysis["object_references"]:
        if (
            item.get("is_cte")
            or item.get("is_function")
            or item.get("is_subquery")
        ):
            continue
        schema = item.get("schema")
        table = str(item.get("table", "")).casefold()
        if schema:
            output.add(f"{str(schema).casefold()}.{table}")
            continue
        matches = by_bare.get(table, [])
        output.add(matches[0] if len(matches) == 1 else table)
    return output


def _analysis_aliases(
    analysis: SqlStatementAnalysis,
    policy: SqlContractPolicy,
) -> dict[str, str]:
    allowed = set(policy["allowed_tables"])
    by_bare: dict[str, list[str]] = {}
    for table in allowed:
        by_bare.setdefault(table.split(".")[-1], []).append(table)
    aliases: dict[str, str] = {}
    for item in analysis["object_references"]:
        alias = item.get("alias")
        if (
            not alias
            or item.get("is_cte")
            or item.get("is_function")
            or item.get("is_subquery")
        ):
            continue
        schema = item.get("schema")
        table = str(item.get("table", "")).casefold()
        resolved = (
            f"{str(schema).casefold()}.{table}"
            if schema
            else (
                by_bare[table][0]
                if len(by_bare.get(table, [])) == 1
                else table
            )
        )
        aliases[alias.casefold()] = resolved
    return aliases


def _authorized_join_rules(query_plan: QueryPlan) -> list[Mapping[str, Any]]:
    joins = _planning_context(query_plan).get("authorized_joins", [])
    return [item for item in joins if isinstance(item, Mapping)]


def _join_allowed(
    authorized: list[Mapping[str, Any]],
    left_table: str | None,
    right_table: str | None,
) -> bool:
    if left_table is None or right_table is None:
        return False
    pair = {left_table.casefold(), right_table.casefold()}
    for join in authorized:
        raw_rules = join.get("join_rules")
        if not isinstance(raw_rules, list):
            continue
        source = str(join.get("source_table", "")).casefold()
        for rule in raw_rules:
            if not isinstance(rule, Mapping):
                continue
            target = str(rule.get("target_table", "")).casefold()
            if pair == {source, target}:
                return True
    return False


def _has_uninterpreted_join_policy(
    authorized: list[Mapping[str, Any]],
    left_table: str | None,
    right_table: str | None,
) -> bool:
    del left_table, right_table
    return any(
        join.get("interpretation") == "preserved_uninterpreted"
        for join in authorized
    )


def _resolve_join_table(
    value: str | None,
    analysis: SqlStatementAnalysis,
) -> str | None:
    if not value:
        return None
    if "." in value:
        return value.casefold()
    for table in analysis["tables"]:
        if table.split(".")[-1] == value.casefold():
            return table
    return value.casefold()


def _planning_context(query_plan: QueryPlan) -> Mapping[str, Any]:
    if not isinstance(query_plan, Mapping):
        raise SqlContractInputError("query_plan deve ser objeto.")
    planning_context = query_plan.get("planning_context")
    if not isinstance(planning_context, Mapping):
        raise SqlContractInputError(
            "query_plan.planning_context esta ausente."
        )
    return planning_context


def _required_tables(planning_context: Mapping[str, Any]) -> set[str]:
    tables = planning_context.get("required_tables")
    if not isinstance(tables, list):
        raise SqlContractInputError(
            "planning_context.required_tables deve ser lista."
        )
    output: set[str] = set()
    for item in tables:
        if not isinstance(item, Mapping):
            continue
        qualified = item.get("qualified_name")
        schema = item.get("schema_name")
        table = item.get("table_name")
        if isinstance(qualified, str) and "." in qualified:
            output.add(qualified.strip().casefold())
        elif isinstance(schema, str) and isinstance(table, str):
            output.add(f"{schema.strip()}.{table.strip()}".casefold())
    if not output:
        raise SqlContractInputError(
            "Nenhuma tabela requerida foi encontrada no QueryPlan."
        )
    return output


def _allowed_columns(
    planning_context: Mapping[str, Any],
) -> dict[str, list[str]]:
    output: dict[str, set[str]] = {
        table: set()
        for table in _required_tables(planning_context)
    }
    relevant = planning_context.get("relevant_columns", {})
    if isinstance(relevant, Mapping):
        for table, columns in relevant.items():
            table_key = str(table).casefold()
            output.setdefault(table_key, set())
            if isinstance(columns, list):
                for column in columns:
                    if isinstance(column, Mapping):
                        name = column.get("name")
                        if isinstance(name, str) and name.strip():
                            output[table_key].add(name.strip().casefold())
    for table in planning_context.get("required_tables", []):
        if not isinstance(table, Mapping):
            continue
        table_key = str(table.get("qualified_name", "")).casefold()
        output.setdefault(table_key, set())
        for field_name in (
            "primary_key",
            "key_columns",
            "metric_columns",
            "date_columns",
        ):
            value = table.get(field_name)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        output[table_key].add(item.strip().casefold())
            elif isinstance(value, str) and value.strip():
                output[table_key].add(value.strip().casefold())
    return {
        table: sorted(columns)
        for table, columns in sorted(output.items())
    }


def _rules(planning_context: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rules = planning_context.get("rules", [])
    if not isinstance(rules, list):
        raise SqlContractInputError("planning_context.rules deve ser lista.")
    return [rule for rule in rules if isinstance(rule, Mapping)]


def _is_required_rule(rule: Mapping[str, Any]) -> bool:
    reasons = rule.get("selection_reasons", [])
    return isinstance(reasons, list) and "required_by_pattern" in reasons


def _limit_policy(rules: list[Mapping[str, Any]]) -> Literal[
    "allow",
    "forbid",
    "require",
    "unspecified",
]:
    for rule in rules:
        content = rule.get("rule_content")
        if not isinstance(content, Mapping):
            continue
        value = content.get("limit_policy")
        if isinstance(value, Mapping):
            value = value.get("mode") or value.get("policy")
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in {"allow", "allowed"}:
                return "allow"
            if normalized in {"forbid", "forbidden", "deny", "prohibit"}:
                return "forbid"
            if normalized in {"require", "required"}:
                return "require"
    return "unspecified"


def _wildcard_policy(
    rules: list[Mapping[str, Any]],
    *,
    table: bool,
) -> Literal["allow", "warn", "reject"]:
    keys = (
        ("table_wildcard_policy", "wildcard_policy")
        if table
        else ("select_star_policy", "wildcard_policy")
    )
    for rule in rules:
        content = rule.get("rule_content")
        if not isinstance(content, Mapping):
            continue
        for key in keys:
            value = content.get(key)
            if isinstance(value, Mapping):
                value = value.get("mode") or value.get("policy")
            if isinstance(value, str):
                normalized = value.strip().casefold()
                if normalized in {"allow", "allowed"}:
                    return "allow"
                if normalized in {"reject", "forbid", "deny"}:
                    return "reject"
                if normalized in {"warn", "warning"}:
                    return "warn"
    return "warn"


def _wildcard_finding(
    policy: Literal["allow", "warn", "reject"],
    message: str,
    findings: list[SqlContractFinding],
) -> None:
    if policy == "allow":
        return
    findings.append(
        _finding(
            "SQL_CONTRACT_WILDCARD_VIOLATED",
            message,
            severity="error" if policy == "reject" else "warning",
            details={"policy": policy},
        )
    )


def _rule_result(
    name: str,
    status: VerificationStatus,
    reason: str,
    checked_items: list[str],
) -> RuleVerificationResult:
    return {
        "rule_name": name,
        "status": status,
        "reason": reason,
        "checked_items": checked_items,
    }


def _check_status(
    items: list[
        TableVerificationResult
        | ColumnVerificationResult
        | JoinVerificationResult
        | RuleVerificationResult
    ],
) -> Literal["passed", "failed", "warning"]:
    if any(item["status"] == "violated" for item in items):
        return "failed"
    if any(item["status"] == "unverifiable" for item in items):
        return "warning"
    return "passed"


def _result(
    *,
    status: SqlContractStatus,
    query_plan: QueryPlan,
    analysis: SqlStatementAnalysis | None,
    checks: list[SqlContractCheck],
    findings: list[SqlContractFinding],
    tables: list[TableVerificationResult],
    referenced: list[TableVerificationResult],
    columns: list[ColumnVerificationResult],
    joins: list[JoinVerificationResult],
    filters: list[FilterVerificationResult],
    rules: list[RuleVerificationResult],
    duration_ms: int,
) -> SqlContractResult:
    errors = [
        finding
        for finding in findings
        if finding["severity"] == "error"
    ]
    warnings = [
        finding["message"]
        for finding in findings
        if finding["severity"] == "warning"
    ]
    warnings.extend(
        f"Regra nao verificavel: {rule['rule_name']}"
        for rule in rules
        if rule["status"] == "unverifiable"
    )
    return {
        "status": status,
        "gate_version": SQL_CONTRACT_GATE_VERSION,
        "analyzer_version": (
            analysis["analyzer_version"] if analysis else SQL_ANALYZER_VERSION
        ),
        "planner_version": str(query_plan.get("planner_version", "")),
        "context_version": str(query_plan.get("context_version", "")),
        "context_fingerprint": str(query_plan.get("context_fingerprint", "")),
        "sql_fingerprint": analysis["sql_fingerprint"] if analysis else "",
        "checks": deepcopy(checks),
        "findings": deepcopy(findings),
        "required_tables": deepcopy(tables),
        "referenced_tables": deepcopy(referenced),
        "columns": deepcopy(columns),
        "joins": deepcopy(joins),
        "filters": deepcopy(filters),
        "rules": deepcopy(rules),
        "unverifiable_rules": [
            deepcopy(rule)
            for rule in rules
            if rule["status"] == "unverifiable"
        ],
        "errors": deepcopy(errors),
        "warnings": sorted(set(warnings)),
        "duration_ms": duration_ms,
    }


def _finding(
    code: SqlContractErrorCode,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    severity: Literal["error", "warning"] = "error",
) -> SqlContractFinding:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "details": details or {},
    }


def _check(
    name: str,
    status: Literal["passed", "failed", "warning"],
    details: dict[str, Any],
) -> SqlContractCheck:
    return {
        "name": name,
        "status": status,
        "details": details,
    }


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        return [
            item.strip()
            for item in value
            if isinstance(item, str) and item.strip()
        ]
    return []


def _duration(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))
