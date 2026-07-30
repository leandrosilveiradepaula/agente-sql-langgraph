from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from time import perf_counter
from typing import Any, Literal, TypedDict

from app.domain.planning import QueryPlan
from app.domain.sql_analysis import (
    SQL_ANALYZER_VERSION,
    SqlAnalysisError,
    SqlObjectReference,
    SqlStatementAnalysis,
    analyze_sql,
)


SQL_SECURITY_GATE_VERSION = "v1.0.0-query-plan-security-gate"

SqlSecurityStatus = Literal["approved", "rejected", "error"]

SqlSecurityErrorCode = Literal[
    "SQL_SECURITY_INPUT_INVALID",
    "SQL_SECURITY_ANALYSIS_FAILED",
    "SQL_SECURITY_MULTIPLE_STATEMENTS",
    "SQL_SECURITY_NON_READ_ONLY",
    "SQL_SECURITY_FORBIDDEN_COMMAND",
    "SQL_SECURITY_SELECT_INTO",
    "SQL_SECURITY_FORBIDDEN_FUNCTION",
    "SQL_SECURITY_UNAUTHORIZED_SCHEMA",
    "SQL_SECURITY_UNAUTHORIZED_TABLE",
    "SQL_SECURITY_AMBIGUOUS_TABLE",
    "SQL_SECURITY_UNSUPPORTED_STRUCTURE",
]


class SqlSecurityPolicy(TypedDict):
    gate_version: str
    allowed_schemas: list[str]
    authorized_tables: list[str]
    allow_bare_table_when_unambiguous: bool
    forbidden_keywords: list[str]
    forbidden_functions: list[str]


class SqlSecurityCheck(TypedDict):
    name: str
    status: Literal["passed", "failed", "not_run"]
    details: dict[str, Any]


class SqlSecurityFinding(TypedDict):
    code: SqlSecurityErrorCode
    severity: Literal["error", "warning"]
    message: str
    details: dict[str, Any]


class SqlSecurityResult(TypedDict):
    status: SqlSecurityStatus
    gate_version: str
    analyzer_version: str
    sql_fingerprint: str
    statement_count: int
    statement_type: str | None
    checks: list[SqlSecurityCheck]
    findings: list[SqlSecurityFinding]
    objects: list[SqlObjectReference]
    schemas: list[str]
    tables: list[str]
    errors: list[SqlSecurityFinding]
    warnings: list[str]
    duration_ms: int


class SqlSecurityInputError(ValueError):
    pass


_FORBIDDEN_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
    "copy",
    "call",
    "do",
    "merge",
    "execute",
    "prepare",
    "deallocate",
    "set",
    "reset",
    "show",
    "vacuum",
    "analyze",
    "lock",
    "discard",
    "reindex",
    "cluster",
    "refresh",
    "program",
}

_FORBIDDEN_FUNCTIONS = {
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "lo_import",
    "lo_export",
    "dblink",
}


def build_sql_security_policy(
    query_plan: QueryPlan,
) -> SqlSecurityPolicy:
    planning_context = _planning_context(query_plan)
    tables = _authorized_tables(planning_context)
    schemas = sorted(
        {
            table.split(".", 1)[0]
            for table in tables
            if "." in table
        }
        | {
            str(schema).strip().casefold()
            for schema in planning_context.get("allowed_schemas", [])
            if isinstance(schema, str) and schema.strip()
        }
    )
    return {
        "gate_version": SQL_SECURITY_GATE_VERSION,
        "allowed_schemas": schemas,
        "authorized_tables": sorted(tables),
        "allow_bare_table_when_unambiguous": True,
        "forbidden_keywords": sorted(_FORBIDDEN_KEYWORDS),
        "forbidden_functions": sorted(_FORBIDDEN_FUNCTIONS),
    }


def run_sql_security_gate(
    *,
    current_sql: str,
    query_plan: QueryPlan,
    analysis: SqlStatementAnalysis | None = None,
) -> tuple[SqlSecurityResult, SqlStatementAnalysis | None]:
    start = perf_counter()
    checks: list[SqlSecurityCheck] = []
    findings: list[SqlSecurityFinding] = []
    try:
        policy = build_sql_security_policy(query_plan)
        sql_analysis = analysis or analyze_sql(current_sql)
    except SqlAnalysisError as error:
        finding = _finding(
            "SQL_SECURITY_ANALYSIS_FAILED",
            str(error),
            details={
                "analysis_error_code": error.code,
            },
        )
        return (
            _result(
                status="rejected",
                analysis=None,
                checks=[
                    _check(
                        "sql_analysis",
                        "failed",
                        {"code": error.code},
                    )
                ],
                findings=[finding],
                duration_ms=_duration(start),
            ),
            None,
        )
    except SqlSecurityInputError as error:
        finding = _finding(
            "SQL_SECURITY_INPUT_INVALID",
            str(error),
        )
        return (
            _result(
                status="error",
                analysis=None,
                checks=[],
                findings=[finding],
                duration_ms=_duration(start),
            ),
            None,
        )

    _check_statement_shape(sql_analysis, checks, findings)
    _check_forbidden_keywords(sql_analysis, policy, checks, findings)
    _check_forbidden_functions(sql_analysis, policy, checks, findings)
    _check_authorized_objects(sql_analysis, policy, checks, findings)

    status: SqlSecurityStatus = (
        "rejected" if any(item["severity"] == "error" for item in findings)
        else "approved"
    )
    return (
        _result(
            status=status,
            analysis=sql_analysis,
            checks=checks,
            findings=findings,
            duration_ms=_duration(start),
        ),
        deepcopy(sql_analysis),
    )


def _check_statement_shape(
    analysis: SqlStatementAnalysis,
    checks: list[SqlSecurityCheck],
    findings: list[SqlSecurityFinding],
) -> None:
    if analysis["statement_count"] != 1:
        findings.append(
            _finding(
                "SQL_SECURITY_MULTIPLE_STATEMENTS",
                "SQL deve conter exatamente um statement.",
            )
        )
        checks.append(_check("single_statement", "failed", {}))
    else:
        checks.append(_check("single_statement", "passed", {}))

    read_ok = (
        analysis["statement_type"] == "select"
        or (
            analysis["statement_type"] == "with"
            and analysis["with_body_is_select"]
        )
    )
    if not read_ok:
        findings.append(
            _finding(
                "SQL_SECURITY_NON_READ_ONLY",
                "SQL deve iniciar com SELECT ou WITH seguido de SELECT.",
                details={
                    "statement_type": analysis["statement_type"],
                },
            )
        )
        checks.append(_check("read_only_start", "failed", {}))
    else:
        checks.append(_check("read_only_start", "passed", {}))

    if analysis["has_select_into"]:
        findings.append(
            _finding(
                "SQL_SECURITY_SELECT_INTO",
                "SELECT INTO nao e permitido nesta fase.",
            )
        )
        checks.append(_check("select_into", "failed", {}))
    else:
        checks.append(_check("select_into", "passed", {}))


def _check_forbidden_keywords(
    analysis: SqlStatementAnalysis,
    policy: SqlSecurityPolicy,
    checks: list[SqlSecurityCheck],
    findings: list[SqlSecurityFinding],
) -> None:
    forbidden = set(policy["forbidden_keywords"])
    found = sorted(
        {
            token["normalized"]
            for token in analysis["tokens"]
            if token["kind"] == "word"
            and token["normalized"] in forbidden
        }
    )
    if found:
        findings.append(
            _finding(
                "SQL_SECURITY_FORBIDDEN_COMMAND",
                "SQL contem comando ou padrao proibido.",
                details={
                    "keywords": found,
                },
            )
        )
        checks.append(
            _check(
                "forbidden_keywords",
                "failed",
                {"keywords": found},
            )
        )
    else:
        checks.append(_check("forbidden_keywords", "passed", {}))


def _check_forbidden_functions(
    analysis: SqlStatementAnalysis,
    policy: SqlSecurityPolicy,
    checks: list[SqlSecurityCheck],
    findings: list[SqlSecurityFinding],
) -> None:
    forbidden = set(policy["forbidden_functions"])
    found = sorted(
        function
        for function in analysis.get("functions", [])
        if function in forbidden
    )
    if found:
        findings.append(
            _finding(
                "SQL_SECURITY_FORBIDDEN_FUNCTION",
                "SQL contem funcao administrativa proibida.",
                details={
                    "functions": found,
                },
            )
        )
        checks.append(
            _check("forbidden_functions", "failed", {"functions": found})
        )
    else:
        checks.append(_check("forbidden_functions", "passed", {}))


def _check_authorized_objects(
    analysis: SqlStatementAnalysis,
    policy: SqlSecurityPolicy,
    checks: list[SqlSecurityCheck],
    findings: list[SqlSecurityFinding],
) -> None:
    authorized = set(policy["authorized_tables"])
    authorized_by_table: dict[str, list[str]] = {}
    for table in authorized:
        table_name = table.split(".")[-1]
        authorized_by_table.setdefault(table_name, []).append(table)

    for item in analysis["object_references"]:
        if item.get("is_cte"):
            continue
        if item.get("is_function"):
            findings.append(
                _finding(
                    "SQL_SECURITY_UNAUTHORIZED_TABLE",
                    "Funcao em FROM/JOIN nao faz parte das tabelas autorizadas.",
                    details={
                        "object": _safe_object(item),
                    },
                )
            )
            continue
        schema = item.get("schema")
        table = str(item.get("table", "")).casefold()
        if schema:
            qualified = f"{str(schema).casefold()}.{table}"
            if str(schema).casefold() not in set(policy["allowed_schemas"]):
                findings.append(
                    _finding(
                        "SQL_SECURITY_UNAUTHORIZED_SCHEMA",
                        "Schema referenciado nao esta autorizado.",
                        details={
                            "schema": str(schema).casefold(),
                        },
                    )
                )
            if qualified not in authorized:
                findings.append(
                    _finding(
                        "SQL_SECURITY_UNAUTHORIZED_TABLE",
                        "Tabela referenciada nao esta autorizada.",
                        details={
                            "table": qualified,
                        },
                    )
                )
            continue

        matches = authorized_by_table.get(table, [])
        if len(matches) > 1:
            findings.append(
                _finding(
                    "SQL_SECURITY_AMBIGUOUS_TABLE",
                    "Referencia de tabela sem schema e ambigua.",
                    details={
                        "table": table,
                        "matches": sorted(matches),
                    },
                )
            )
        elif len(matches) == 0:
            findings.append(
                _finding(
                    "SQL_SECURITY_UNAUTHORIZED_TABLE",
                    "Tabela referenciada nao esta autorizada.",
                    details={
                        "table": table,
                    },
                )
            )

    checks.append(
        _check(
            "authorized_objects",
            (
                "failed"
                if any(
                    finding["code"]
                    in {
                        "SQL_SECURITY_UNAUTHORIZED_SCHEMA",
                        "SQL_SECURITY_UNAUTHORIZED_TABLE",
                        "SQL_SECURITY_AMBIGUOUS_TABLE",
                    }
                    for finding in findings
                )
                else "passed"
            ),
            {
                "authorized_tables": sorted(authorized),
            },
        )
    )


def _planning_context(query_plan: QueryPlan) -> Mapping[str, Any]:
    if not isinstance(query_plan, Mapping):
        raise SqlSecurityInputError("query_plan deve ser objeto.")
    planning_context = query_plan.get("planning_context")
    if not isinstance(planning_context, Mapping):
        raise SqlSecurityInputError(
            "query_plan.planning_context esta ausente."
        )
    return planning_context


def _authorized_tables(planning_context: Mapping[str, Any]) -> set[str]:
    tables = planning_context.get("required_tables")
    if not isinstance(tables, list):
        raise SqlSecurityInputError(
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
        raise SqlSecurityInputError(
            "Nenhuma tabela autorizada foi encontrada no QueryPlan."
        )
    return output


def _result(
    *,
    status: SqlSecurityStatus,
    analysis: SqlStatementAnalysis | None,
    checks: list[SqlSecurityCheck],
    findings: list[SqlSecurityFinding],
    duration_ms: int,
) -> SqlSecurityResult:
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
    return {
        "status": status,
        "gate_version": SQL_SECURITY_GATE_VERSION,
        "analyzer_version": (
            analysis["analyzer_version"] if analysis else SQL_ANALYZER_VERSION
        ),
        "sql_fingerprint": analysis["sql_fingerprint"] if analysis else "",
        "statement_count": analysis["statement_count"] if analysis else 0,
        "statement_type": analysis["statement_type"] if analysis else None,
        "checks": deepcopy(checks),
        "findings": deepcopy(findings),
        "objects": deepcopy(analysis["object_references"]) if analysis else [],
        "schemas": deepcopy(analysis["schemas"]) if analysis else [],
        "tables": deepcopy(analysis["tables"]) if analysis else [],
        "errors": deepcopy(errors),
        "warnings": warnings,
        "duration_ms": duration_ms,
    }


def _finding(
    code: SqlSecurityErrorCode,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    severity: Literal["error", "warning"] = "error",
) -> SqlSecurityFinding:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "details": details or {},
    }


def _check(
    name: str,
    status: Literal["passed", "failed", "not_run"],
    details: dict[str, Any],
) -> SqlSecurityCheck:
    return {
        "name": name,
        "status": status,
        "details": details,
    }


def _safe_object(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": item.get("schema"),
        "table": item.get("table"),
        "alias": item.get("alias"),
        "source": item.get("source"),
    }


def _duration(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))
