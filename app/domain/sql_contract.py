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


SQL_CONTRACT_GATE_VERSION = "v1.0.0-query-plan-contract-gate"

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
        sql_analysis = analysis or analyze_sql(current_sql)
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
    del current_sql, analysis, findings
    operations = _planned_analytical_operations(query_plan)
    if not operations:
        return []

    results: list[RuleVerificationResult] = []
    for operation in operations:
        operation_type = operation["operation_type"]
        if operation_type != "ranking":
            results.append(
                _rule_result(
                    operation_type,
                    "unverifiable",
                    "unsupported_analytical_operation",
                    [],
                )
            )
            continue
        results.append(
            _rule_result(
                operation_type,
                "unverifiable",
                "ranking_metric_order_validation_pending",
                ["metric_ref"] if operation.get("metric_ref") else [],
            )
        )
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
        direction = _clean_text(item.get("direction"))
        canonical_value = _clean_text(item.get("canonical_value"))
        requested_limit = item.get("requested_limit")
        metric_ref = _clean_text(item.get("metric_ref"))
        if operation_type != "ranking":
            continue
        if canonical_value != operation_type:
            continue
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
    return sorted(
        operations,
        key=lambda operation: (
            operation["operation_type"],
            operation["direction"],
            operation["metric_ref"],
            operation["requested_limit"] or 0,
        ),
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
