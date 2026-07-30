from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from app.domain.engine_preflight_sanitization import (
    safe_message,
    safe_optional_text,
    safe_provider_name,
    safe_warnings,
)
from app.domain.engine_preflight_types import (
    DEFAULT_ENGINE_PREFLIGHT_TIMEOUT_MS,
    ENGINE_PREFLIGHT_CONTRACT_VERSION,
    EnginePreflightCapabilities,
    EnginePreflightError,
    EnginePreflightErrorCode,
    EnginePreflightFailureCategory,
    EnginePreflightFinding,
    EnginePreflightInputError,
    EnginePreflightProviderError,
    EnginePreflightProviderResult,
    EnginePreflightRequest,
    EnginePreflightResult,
    EnginePreflightStatus,
)
from app.domain.planning import QueryPlan
from app.domain.sql_analysis import SqlAnalysisError, analyze_sql
from app.domain.sql_contract import SqlContractResult
from app.domain.sql_security import SqlSecurityResult


_REPAIRABLE_CATEGORIES: set[EnginePreflightFailureCategory] = {
    "syntax_error",
    "schema_not_found",
    "table_not_found",
    "column_not_found",
    "ambiguous_column",
    "function_not_found",
    "invalid_grouping",
    "invalid_ordering",
    "type_mismatch",
    "invalid_cast",
    "invalid_join",
    "invalid_cte",
    "invalid_subquery",
    "dialect_error",
    "planning_error",
    "unknown_sql_error",
}

_INFRASTRUCTURE_CATEGORIES: set[EnginePreflightFailureCategory] = {
    "provider_unavailable",
    "authentication_failed",
    "timeout",
    "connection_failed",
    "protocol_error",
    "adapter_error",
}

_CATEGORY_TO_CODE: dict[
    EnginePreflightFailureCategory,
    EnginePreflightErrorCode,
] = {
    "syntax_error": "ENGINE_PREFLIGHT_SYNTAX_ERROR",
    "schema_not_found": "ENGINE_PREFLIGHT_SCHEMA_NOT_FOUND",
    "table_not_found": "ENGINE_PREFLIGHT_TABLE_NOT_FOUND",
    "column_not_found": "ENGINE_PREFLIGHT_COLUMN_NOT_FOUND",
    "ambiguous_column": "ENGINE_PREFLIGHT_AMBIGUOUS_COLUMN",
    "function_not_found": "ENGINE_PREFLIGHT_FUNCTION_NOT_FOUND",
    "invalid_grouping": "ENGINE_PREFLIGHT_INVALID_GROUPING",
    "invalid_ordering": "ENGINE_PREFLIGHT_INVALID_ORDERING",
    "type_mismatch": "ENGINE_PREFLIGHT_TYPE_MISMATCH",
    "invalid_cast": "ENGINE_PREFLIGHT_INVALID_CAST",
    "invalid_join": "ENGINE_PREFLIGHT_INVALID_JOIN",
    "invalid_cte": "ENGINE_PREFLIGHT_INVALID_CTE",
    "invalid_subquery": "ENGINE_PREFLIGHT_INVALID_SUBQUERY",
    "dialect_error": "ENGINE_PREFLIGHT_DIALECT_ERROR",
    "planning_error": "ENGINE_PREFLIGHT_PLANNING_ERROR",
    "unknown_sql_error": "ENGINE_PREFLIGHT_UNKNOWN_SQL_ERROR",
    "provider_unavailable": "ENGINE_PREFLIGHT_PROVIDER_UNAVAILABLE",
    "authentication_failed": "ENGINE_PREFLIGHT_AUTHENTICATION_FAILED",
    "timeout": "ENGINE_PREFLIGHT_TIMEOUT",
    "connection_failed": "ENGINE_PREFLIGHT_CONNECTION_FAILED",
    "protocol_error": "ENGINE_PREFLIGHT_PROTOCOL_ERROR",
    "adapter_error": "ENGINE_PREFLIGHT_PROVIDER_FAILED",
}

_DEFAULT_CAPABILITIES: EnginePreflightCapabilities = {
    "syntax": True,
    "schema_resolution": True,
    "table_resolution": True,
    "column_resolution": True,
    "alias_resolution": True,
    "function_resolution": True,
    "grouping_validation": True,
    "ordering_validation": True,
    "type_validation": True,
    "cast_validation": True,
    "join_planning": True,
    "cte_validation": True,
    "subquery_validation": True,
    "dialect_validation": True,
    "explain_without_analyze": True,
    "executes_query": False,
}


def build_engine_preflight_request(
    *,
    current_sql: str,
    query_plan: QueryPlan,
    security_result: SqlSecurityResult,
    contract_result: SqlContractResult,
    options: Mapping[str, Any] | None = None,
) -> EnginePreflightRequest:
    if not isinstance(current_sql, str) or not current_sql.strip():
        raise EnginePreflightInputError(
            "ENGINE_PREFLIGHT_SQL_MISSING",
            "current_sql esta ausente para Engine Preflight.",
        )
    if not isinstance(query_plan, Mapping) or not query_plan:
        raise EnginePreflightInputError(
            "ENGINE_PREFLIGHT_PLAN_MISSING",
            "query_plan esta ausente para Engine Preflight.",
        )
    if (
        not isinstance(security_result, Mapping)
        or security_result.get("status") != "approved"
    ):
        raise EnginePreflightInputError(
            "ENGINE_PREFLIGHT_SECURITY_NOT_APPROVED",
            "Engine Preflight exige Security Gate aprovado.",
        )
    if (
        not isinstance(contract_result, Mapping)
        or contract_result.get("status") != "approved"
    ):
        raise EnginePreflightInputError(
            "ENGINE_PREFLIGHT_CONTRACT_NOT_APPROVED",
            "Engine Preflight exige Contract Gate aprovado.",
        )

    planning_context = query_plan.get("planning_context")
    if not isinstance(planning_context, Mapping):
        raise EnginePreflightInputError(
            "ENGINE_PREFLIGHT_PLAN_MISSING",
            "query_plan.planning_context esta ausente.",
        )

    sql = current_sql.strip()
    request: EnginePreflightRequest = {
        "contract_version": ENGINE_PREFLIGHT_CONTRACT_VERSION,
        "sql": sql,
        "sql_fingerprint": _sql_fingerprint(sql),
        "context_version": _required_text(query_plan, "context_version"),
        "context_fingerprint": _required_text(
            query_plan,
            "context_fingerprint",
        ),
        "intent_name": _required_text(query_plan, "intent_name"),
        "allowed_schemas": _allowed_schemas(planning_context),
        "planned_tables": _planned_tables(planning_context),
        "dialect": _optional_hint(planning_context, "dialect"),
        "engine_hint": _engine_hint(query_plan, planning_context),
        "timeout_ms": _timeout_ms(options),
        "attempt": _attempt(options),
        "capabilities_requested": deepcopy(_DEFAULT_CAPABILITIES),
    }
    request["request_fingerprint"] = request_fingerprint(request)
    return deepcopy(request)


def request_fingerprint(request: EnginePreflightRequest) -> str:
    payload = deepcopy(request)
    payload.pop("request_fingerprint", None)
    return _stable_fingerprint(payload)


def normalize_engine_preflight_result(
    *,
    request: EnginePreflightRequest,
    provider_result: EnginePreflightProviderResult,
) -> EnginePreflightResult:
    if not isinstance(provider_result, Mapping):
        return _invalid_provider_response(
            request,
            message="Resposta do provider deve ser objeto.",
        )

    status = provider_result.get("status")
    if status not in {"approved", "rejected", "error"}:
        return _invalid_provider_response(
            request,
            message="Status do provider e invalido.",
        )

    category = _provider_category(provider_result, status)
    infrastructure = category in _INFRASTRUCTURE_CATEGORIES or status == "error"
    approved = status == "approved"
    result_status: EnginePreflightStatus = (
        "approved"
        if approved
        else ("error" if infrastructure else "rejected")
    )
    repairable = (
        bool(provider_result.get("repairable"))
        if "repairable" in provider_result
        else category in _REPAIRABLE_CATEGORIES
    )
    if infrastructure:
        repairable = False

    code = _provider_code(provider_result, category, infrastructure)
    message = safe_message(provider_result.get("message"))
    provider_name = safe_provider_name(provider_result.get("provider_name"))
    provider_version = safe_optional_text(
        provider_result.get("provider_version")
    )
    capabilities = _capabilities(provider_result.get("capabilities"))
    duration_ms = _non_negative_int(provider_result.get("duration_ms"))
    statement_planned = (
        approved
        or bool(provider_result.get("statement_planned"))
    )
    executed = bool(provider_result.get("executed", False))
    rows_returned = _non_negative_int(provider_result.get("rows_returned"))
    if executed:
        category = "adapter_error"
        result_status = "error"
        approved = False
        repairable = False
        code = "ENGINE_PREFLIGHT_PROVIDER_FAILED"
        message = "Provider informou execucao da consulta durante preflight."
    if rows_returned != 0:
        rows_returned = 0

    finding = (
        _finding(
            code=code,
            category=category,
            message=message,
            repairable=repairable,
            provider_result=provider_result,
        )
        if not approved
        else None
    )
    findings = [finding] if finding else []
    diagnostic = _diagnostic(
        request=request,
        provider_name=provider_name,
        provider_version=provider_version,
        duration_ms=duration_ms,
        capabilities=capabilities,
        statement_planned=statement_planned,
        executed=False,
        rows_returned=0,
        reason=(
            "engine_preflight_approved"
            if approved
            else f"engine_preflight_{category}"
        ),
    )
    return {
        "status": result_status,
        "approved": approved,
        "repairable": repairable,
        "failure_category": "none" if approved else category,
        "findings": findings,
        "errors": [
            _error_from_finding(item)
            for item in findings
            if item["severity"] == "error"
        ],
        "warnings": safe_warnings(provider_result.get("warnings")),
        "provider_name": provider_name,
        "provider_version": provider_version,
        "preflight_contract_version": ENGINE_PREFLIGHT_CONTRACT_VERSION,
        "sql_fingerprint": request["sql_fingerprint"],
        "request_fingerprint": request["request_fingerprint"],
        "context_version": request["context_version"],
        "context_fingerprint": request["context_fingerprint"],
        "duration_ms": duration_ms,
        "attempt": request["attempt"],
        "capabilities_used": capabilities,
        "statement_planned": statement_planned,
        "rows_returned": 0,
        "executed": False,
        "diagnostic": diagnostic,
    }


def create_engine_preflight_provider_error_result(
    *,
    request: EnginePreflightRequest | None,
    code: EnginePreflightErrorCode,
    category: EnginePreflightFailureCategory,
    message: str,
    attempt: int,
) -> EnginePreflightResult:
    safe_request = request or _empty_request(attempt=attempt)
    provider_result: EnginePreflightProviderResult = {
        "status": "error",
        "provider_name": "unknown",
        "failure_category": category,
        "error_code": code,
        "message": message,
        "repairable": False,
        "executed": False,
        "rows_returned": 0,
    }
    return normalize_engine_preflight_result(
        request=safe_request,
        provider_result=provider_result,
    )


def _invalid_provider_response(
    request: EnginePreflightRequest,
    *,
    message: str,
) -> EnginePreflightResult:
    provider_result: EnginePreflightProviderResult = {
        "status": "error",
        "provider_name": "unknown",
        "failure_category": "adapter_error",
        "error_code": "ENGINE_PREFLIGHT_RESPONSE_INVALID",
        "message": message,
        "repairable": False,
        "executed": False,
        "rows_returned": 0,
    }
    return normalize_engine_preflight_result(
        request=request,
        provider_result=provider_result,
    )


def _finding(
    *,
    code: EnginePreflightErrorCode,
    category: EnginePreflightFailureCategory,
    message: str,
    repairable: bool,
    provider_result: Mapping[str, Any],
) -> EnginePreflightFinding:
    return {
        "code": code,
        "category": category,
        "severity": "error",
        "message": message,
        "repairable": repairable,
        "provider_code": safe_optional_text(
            provider_result.get("provider_code")
        ),
        "sqlstate": safe_optional_text(provider_result.get("sqlstate")),
        "position": _optional_int(provider_result.get("position")),
        "line": _optional_int(provider_result.get("line")),
        "column": _optional_int(provider_result.get("column")),
        "related_object": safe_optional_text(
            provider_result.get("related_object")
        ),
        "sanitized_hint": safe_optional_text(provider_result.get("hint")),
        "details": {},
    }


def _error_from_finding(
    finding: EnginePreflightFinding,
) -> EnginePreflightError:
    return {
        "code": finding["code"],
        "category": finding["category"],
        "message": finding["message"],
        "repairable": finding["repairable"],
        "provider_code": finding.get("provider_code"),
        "sqlstate": finding.get("sqlstate"),
        "position": finding.get("position"),
        "line": finding.get("line"),
        "column": finding.get("column"),
        "related_object": finding.get("related_object"),
        "sanitized_hint": finding.get("sanitized_hint"),
        "details": {},
    }


def _provider_category(
    provider_result: Mapping[str, Any],
    status: str,
) -> EnginePreflightFailureCategory:
    category = provider_result.get("failure_category")
    valid_categories = _REPAIRABLE_CATEGORIES | _INFRASTRUCTURE_CATEGORIES
    if isinstance(category, str) and category in valid_categories | {"none"}:
        return category  # type: ignore[return-value]
    if status == "approved":
        return "none"
    if status == "error":
        return "adapter_error"
    return "unknown_sql_error"


def _provider_code(
    provider_result: Mapping[str, Any],
    category: EnginePreflightFailureCategory,
    infrastructure: bool,
) -> EnginePreflightErrorCode:
    code = provider_result.get("error_code")
    if isinstance(code, str) and code.startswith("ENGINE_PREFLIGHT_"):
        return code  # type: ignore[return-value]
    if category in _CATEGORY_TO_CODE:
        return _CATEGORY_TO_CODE[category]
    return (
        "ENGINE_PREFLIGHT_PROVIDER_FAILED"
        if infrastructure
        else "ENGINE_PREFLIGHT_UNKNOWN_SQL_ERROR"
    )


def _diagnostic(
    *,
    request: EnginePreflightRequest,
    provider_name: str,
    provider_version: str | None,
    duration_ms: int,
    capabilities: EnginePreflightCapabilities,
    statement_planned: bool,
    executed: bool,
    rows_returned: int,
    reason: str,
):
    return {
        "preflight_contract_version": ENGINE_PREFLIGHT_CONTRACT_VERSION,
        "request_fingerprint": request["request_fingerprint"],
        "sql_fingerprint": request["sql_fingerprint"],
        "context_version": request["context_version"],
        "context_fingerprint": request["context_fingerprint"],
        "provider_name": provider_name,
        "provider_version": provider_version,
        "duration_ms": duration_ms,
        "attempt": request["attempt"],
        "capabilities_used": deepcopy(capabilities),
        "statement_planned": statement_planned,
        "executed": executed,
        "rows_returned": rows_returned,
        "reason": reason,
    }


def _required_text(
    value: Mapping[str, Any],
    field_name: str,
) -> str:
    field_value = value.get(field_name)
    if not isinstance(field_value, str) or not field_value.strip():
        raise EnginePreflightInputError(
            "ENGINE_PREFLIGHT_REQUEST_INVALID",
            f"{field_name} deve ser texto nao vazio.",
        )
    return field_value.strip()


def _allowed_schemas(planning_context: Mapping[str, Any]) -> list[str]:
    values = planning_context.get("allowed_schemas", [])
    schemas = (
        {
            item.strip().casefold()
            for item in values
            if isinstance(item, str) and item.strip()
        }
        if isinstance(values, list)
        else set()
    )
    for table in _planned_tables(planning_context):
        if "." in table:
            schemas.add(table.split(".", 1)[0])
    return sorted(schemas)


def _planned_tables(planning_context: Mapping[str, Any]) -> list[str]:
    values = planning_context.get("required_tables")
    if not isinstance(values, list):
        raise EnginePreflightInputError(
            "ENGINE_PREFLIGHT_REQUEST_INVALID",
            "planning_context.required_tables deve ser lista.",
        )
    tables: set[str] = set()
    for item in values:
        if not isinstance(item, Mapping):
            continue
        qualified = item.get("qualified_name")
        schema = item.get("schema_name")
        table = item.get("table_name")
        if isinstance(qualified, str) and qualified.strip():
            tables.add(qualified.strip().casefold())
        elif isinstance(schema, str) and isinstance(table, str):
            tables.add(f"{schema.strip()}.{table.strip()}".casefold())
    if not tables:
        raise EnginePreflightInputError(
            "ENGINE_PREFLIGHT_REQUEST_INVALID",
            "Nenhuma tabela planejada encontrada no QueryPlan.",
        )
    return sorted(tables)


def _engine_hint(
    query_plan: Mapping[str, Any],
    planning_context: Mapping[str, Any],
) -> str | None:
    for value in (
        planning_context.get("engine_hint"),
        planning_context.get("engine"),
        query_plan.get("engine_hint"),
    ):
        text = safe_optional_text(value)
        if text:
            return text
    selected_pattern = query_plan.get("selected_pattern")
    if isinstance(selected_pattern, Mapping):
        return safe_optional_text(selected_pattern.get("engine_hint"))
    return None


def _optional_hint(
    planning_context: Mapping[str, Any],
    field_name: str,
) -> str | None:
    return safe_optional_text(planning_context.get(field_name))


def _timeout_ms(options: Mapping[str, Any] | None) -> int:
    if not isinstance(options, Mapping):
        return DEFAULT_ENGINE_PREFLIGHT_TIMEOUT_MS
    value = options.get("engine_preflight_timeout_ms", options.get("timeout_ms"))
    if isinstance(value, bool):
        return DEFAULT_ENGINE_PREFLIGHT_TIMEOUT_MS
    if isinstance(value, int) and value > 0:
        return min(value, 60000)
    return DEFAULT_ENGINE_PREFLIGHT_TIMEOUT_MS


def _attempt(options: Mapping[str, Any] | None) -> int:
    if not isinstance(options, Mapping):
        return 1
    value = options.get("attempt")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return 1


def _capabilities(value: Any) -> EnginePreflightCapabilities:
    output = deepcopy(_DEFAULT_CAPABILITIES)
    if isinstance(value, Mapping):
        for key in output:
            if isinstance(value.get(key), bool):
                output[key] = bool(value[key])
    output["executes_query"] = False
    return output


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def _sql_fingerprint(sql: str) -> str:
    try:
        analyze_sql(sql)
    except SqlAnalysisError as error:
        raise EnginePreflightInputError(
            "ENGINE_PREFLIGHT_REQUEST_INVALID",
            "current_sql nao pode ser analisada para preflight.",
        ) from error
    return hashlib.sha256(sql.strip().encode("utf-8")).hexdigest()


def _empty_request(*, attempt: int) -> EnginePreflightRequest:
    request: EnginePreflightRequest = {
        "contract_version": ENGINE_PREFLIGHT_CONTRACT_VERSION,
        "sql": "",
        "sql_fingerprint": "",
        "context_version": "",
        "context_fingerprint": "",
        "intent_name": "",
        "allowed_schemas": [],
        "planned_tables": [],
        "dialect": None,
        "engine_hint": None,
        "timeout_ms": DEFAULT_ENGINE_PREFLIGHT_TIMEOUT_MS,
        "attempt": attempt,
        "capabilities_requested": deepcopy(_DEFAULT_CAPABILITIES),
    }
    request["request_fingerprint"] = request_fingerprint(request)
    return request


def _stable_fingerprint(value: Any) -> str:
    return hashlib.sha256(
        _stable_json(value).encode("utf-8")
    ).hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    )
