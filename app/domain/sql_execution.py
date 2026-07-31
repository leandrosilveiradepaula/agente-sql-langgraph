from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, cast

from app.domain.engine_preflight_sanitization import (
    safe_message,
    safe_optional_text,
    safe_provider_name,
    safe_warnings,
)
from app.domain.engine_preflight_types import EnginePreflightResult
from app.domain.planning import QueryPlan
from app.domain.sql_analysis import SqlAnalysisError, analyze_sql
from app.domain.sql_contract import SqlContractResult
from app.domain.sql_execution_types import (
    SQL_EXECUTION_CONTRACT_VERSION,
    SqlExecutionColumn,
    SqlExecutionDiagnostic,
    SqlExecutionErrorCode,
    SqlExecutionFailureCategory,
    SqlExecutionInputError,
    SqlExecutionLimits,
    SqlExecutionProviderError,
    SqlExecutionProviderResult,
    SqlExecutionRequest,
    SqlExecutionResult,
    SqlExecutionRow,
    SqlExecutionStatus,
)
from app.domain.sql_security import SqlSecurityResult


_INFRASTRUCTURE_CATEGORIES: set[SqlExecutionFailureCategory] = {
    "provider_failed",
    "timeout",
    "authentication_failed",
    "unexpected_error",
}

MAX_TIMEOUT_SECONDS = 300
MAX_ROWS = 10000
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
MAX_CELL_BYTES = 1024 * 1024


def build_sql_execution_request(
    *,
    current_sql: str,
    query_plan: QueryPlan,
    security_result: SqlSecurityResult,
    contract_result: SqlContractResult,
    engine_preflight_result: EnginePreflightResult,
    request_id: str,
    run_id: str,
    options: Mapping[str, Any] | None,
) -> SqlExecutionRequest:
    if not isinstance(current_sql, str) or not current_sql.strip():
        raise SqlExecutionInputError(
            "SQL_EXECUTION_REQUEST_INVALID",
            "current_sql esta ausente para execucao.",
        )
    analysis = _analyze_read_only(current_sql)
    if (
        not isinstance(security_result, Mapping)
        or security_result.get("status") != "approved"
    ):
        raise SqlExecutionInputError(
            "SQL_EXECUTION_SECURITY_NOT_APPROVED",
            "Execucao exige Security Gate aprovado.",
            category="not_authorized",
        )
    if (
        not isinstance(contract_result, Mapping)
        or contract_result.get("status") != "approved"
    ):
        raise SqlExecutionInputError(
            "SQL_EXECUTION_CONTRACT_NOT_APPROVED",
            "Execucao exige Contract Gate aprovado.",
            category="not_authorized",
        )
    _validate_preflight(engine_preflight_result)
    if not isinstance(query_plan, Mapping) or not query_plan:
        raise SqlExecutionInputError(
            "SQL_EXECUTION_REQUEST_INVALID",
            "query_plan esta ausente para execucao.",
        )

    planning_context = query_plan.get("planning_context")
    if not isinstance(planning_context, Mapping):
        raise SqlExecutionInputError(
            "SQL_EXECUTION_REQUEST_INVALID",
            "query_plan.planning_context esta ausente.",
        )

    context_version = _required_text(query_plan, "context_version")
    intent_name = _required_text(query_plan, "intent_name")
    limits = _limits(options)
    attempt = _positive_int(
        options.get("execution_attempt") if isinstance(options, Mapping) else None,
        default=1,
    )
    request: SqlExecutionRequest = {
        "contract_version": SQL_EXECUTION_CONTRACT_VERSION,
        "current_sql": current_sql,
        "sql_fingerprint": _sql_fingerprint(current_sql),
        "request_id": _required_external_text(request_id, "request_id"),
        "run_id": _required_external_text(run_id, "run_id"),
        "context_version": context_version,
        "intent_name": intent_name,
        "query_plan_fingerprint": _stable_fingerprint(query_plan),
        "preflight_fingerprint": _preflight_fingerprint(
            engine_preflight_result,
        ),
        "limits": limits,
        "attempt": attempt,
        "execution_id": _execution_id(
            request_id=request_id,
            run_id=run_id,
            attempt=attempt,
            sql_fingerprint=_sql_fingerprint(current_sql),
        ),
        "dialect": _optional_hint(planning_context, "dialect"),
        "engine_hint": _engine_hint(query_plan, planning_context),
        "request_fingerprint": "",
    }
    request["request_fingerprint"] = request_fingerprint(request)
    if engine_preflight_result.get("query_plan_fingerprint") != request[
        "query_plan_fingerprint"
    ]:
        raise SqlExecutionInputError(
            "SQL_EXECUTION_REQUEST_INVALID",
            "Fingerprint do QueryPlan diverge do preflight aprovado.",
        )

    if security_result.get("sql_fingerprint") not in {
        None,
        "",
        request["sql_fingerprint"],
    }:
        raise SqlExecutionInputError(
            "SQL_EXECUTION_REQUEST_INVALID",
            "Fingerprint do Security Gate diverge da SQL atual.",
        )
    if contract_result.get("sql_fingerprint") not in {
        None,
        "",
        request["sql_fingerprint"],
    }:
        raise SqlExecutionInputError(
            "SQL_EXECUTION_REQUEST_INVALID",
            "Fingerprint do Contract Gate diverge da SQL atual.",
        )
    if engine_preflight_result.get("sql_fingerprint") not in {
        None,
        "",
        request["sql_fingerprint"],
    }:
        raise SqlExecutionInputError(
            "SQL_EXECUTION_REQUEST_INVALID",
            "Fingerprint do Engine Preflight diverge da SQL atual.",
        )
    if analysis["sql_fingerprint"] != request["sql_fingerprint"]:
        raise SqlExecutionInputError(
            "SQL_EXECUTION_REQUEST_INVALID",
            "Fingerprint da analise diverge da SQL atual.",
        )
    return deepcopy(request)


def request_fingerprint(request: SqlExecutionRequest) -> str:
    payload = deepcopy(request)
    payload.pop("request_fingerprint", None)
    return _stable_fingerprint(payload)


def response_fingerprint(value: Mapping[str, Any]) -> str:
    return _stable_fingerprint(value)


def normalize_sql_execution_result(
    *,
    request: SqlExecutionRequest,
    provider_result: SqlExecutionProviderResult,
) -> SqlExecutionResult:
    if not isinstance(provider_result, Mapping):
        return create_sql_execution_error_result(
            request=request,
            code="SQL_EXECUTION_RESPONSE_INVALID",
            message="Resposta do executor deve ser objeto.",
            category="response_invalid",
            status="rejected",
        )

    status = provider_result.get("status")
    if status not in {"success", "rejected", "error"}:
        return create_sql_execution_error_result(
            request=request,
            code="SQL_EXECUTION_RESPONSE_INVALID",
            message="Status do executor e invalido.",
            category="response_invalid",
            status="rejected",
        )

    provider_name = safe_provider_name(
        provider_result.get("provider_name"),
        forbidden_texts=(request["current_sql"],),
    )
    provider_version = safe_optional_text(
        provider_result.get("provider_version"),
        forbidden_texts=(request["current_sql"],),
    )
    fingerprint_error = _provider_fingerprint_error(
        request=request,
        provider_result=provider_result,
    )
    if fingerprint_error is not None:
        return create_sql_execution_error_result(
            request=request,
            code="SQL_EXECUTION_RESPONSE_INVALID",
            message=fingerprint_error,
            category="response_invalid",
            status="rejected",
            provider_name=provider_name,
            provider_version=provider_version,
        )
    duration_ms = _optional_non_negative_int(
        provider_result.get("duration_ms")
    )
    if "duration_ms" in provider_result and duration_ms is None:
        return create_sql_execution_error_result(
            request=request,
            code="SQL_EXECUTION_RESPONSE_INVALID",
            message="duration_ms do executor e invalido.",
            category="response_invalid",
            status="rejected",
            provider_name=provider_name,
            provider_version=provider_version,
        )
    if status != "success":
        if _has_success_payload(provider_result):
            return create_sql_execution_error_result(
                request=request,
                code="SQL_EXECUTION_RESPONSE_INVALID",
                message="Executor rejeitou com payload de sucesso.",
                category="response_invalid",
                status="rejected",
                provider_name=provider_name,
                provider_version=provider_version,
                duration_ms=duration_ms,
            )
        category = _failure_category(provider_result, status)
        code = _error_code(provider_result, category)
        return create_sql_execution_error_result(
            request=request,
            code=code,
            message=safe_message(
                provider_result.get("message"),
                forbidden_texts=(request["current_sql"],),
            ),
            category=category,
            status=(
                "infrastructure_error"
                if category in _INFRASTRUCTURE_CATEGORIES
                else "rejected"
            ),
            provider_name=provider_name,
            provider_version=provider_version,
            duration_ms=duration_ms,
            warnings=safe_warnings(
                provider_result.get("warnings"),
                forbidden_texts=(request["current_sql"],),
            ),
        )

    if provider_result.get("executed") is not True:
        return create_sql_execution_error_result(
            request=request,
            code="SQL_EXECUTION_RESPONSE_INVALID",
            message="Executor aprovou sem confirmar execucao.",
            category="response_invalid",
            status="rejected",
            provider_name=provider_name,
            provider_version=provider_version,
            duration_ms=duration_ms,
        )
    if provider_result.get("truncated") is True:
        return create_sql_execution_error_result(
            request=request,
            code="SQL_EXECUTION_RESPONSE_INVALID",
            message="Resposta truncada nao e aceita nesta politica.",
            category="response_invalid",
            status="rejected",
            provider_name=provider_name,
            provider_version=provider_version,
            duration_ms=duration_ms,
        )

    try:
        rows = _rows(provider_result.get("rows"))
        columns = _columns(provider_result.get("columns"))
    except TypeError:
        return create_sql_execution_error_result(
            request=request,
            code="SQL_EXECUTION_RESPONSE_INVALID",
            message="Linhas ou colunas do executor sao invalidas.",
            category="response_invalid",
            status="rejected",
            provider_name=provider_name,
            provider_version=provider_version,
            duration_ms=duration_ms,
        )
    row_count = _row_count(provider_result.get("row_count"), rows)
    if row_count is None:
        return create_sql_execution_error_result(
            request=request,
            code="SQL_EXECUTION_RESPONSE_INVALID",
            message="row_count do executor e invalido.",
            category="response_invalid",
            status="rejected",
            provider_name=provider_name,
            provider_version=provider_version,
            duration_ms=duration_ms,
        )
    if row_count != len(rows):
        return create_sql_execution_error_result(
            request=request,
            code="SQL_EXECUTION_RESPONSE_INVALID",
            message="row_count diverge das linhas retornadas.",
            category="response_invalid",
            status="rejected",
            provider_name=provider_name,
            provider_version=provider_version,
            duration_ms=duration_ms,
        )

    shape_error = _shape_error(columns, rows)
    if shape_error is not None:
        return create_sql_execution_error_result(
            request=request,
            code="SQL_EXECUTION_RESPONSE_INVALID",
            message=shape_error,
            category="response_invalid",
            status="rejected",
            provider_name=provider_name,
            provider_version=provider_version,
            duration_ms=duration_ms,
        )

    limit_error = _limit_error(request["limits"], columns, rows)
    if limit_error is not None:
        code, category, message = limit_error
        return create_sql_execution_error_result(
            request=request,
            code=code,
            message=message,
            category=category,
            status="rejected",
            provider_name=provider_name,
            provider_version=provider_version,
            duration_ms=duration_ms,
        )

    bytes_received = _bytes_received(
        provider_result.get("bytes_received"),
        columns,
        rows,
    )
    if bytes_received is None:
        return create_sql_execution_error_result(
            request=request,
            code="SQL_EXECUTION_RESPONSE_INVALID",
            message="bytes_received do executor e invalido.",
            category="response_invalid",
            status="rejected",
            provider_name=provider_name,
            provider_version=provider_version,
            duration_ms=duration_ms,
        )
    response_summary = {
        "columns": columns,
        "row_count": row_count,
        "bytes_received": bytes_received,
        "truncated": bool(provider_result.get("truncated", False)),
        "provider_name": provider_name,
        "provider_version": provider_version,
    }
    diagnostic = _diagnostic(
        request=request,
        provider_name=provider_name,
        provider_version=provider_version,
        response_fingerprint_value=response_fingerprint(response_summary),
        reason="sql_execution_success",
        duration_ms=duration_ms,
        executed=bool(provider_result.get("executed", True)),
        statement_type=_statement_type(provider_result, request),
    )
    return {
        "status": "success",
        "columns": columns,
        "rows": rows,
        "row_count": row_count,
        "truncated": bool(provider_result.get("truncated", False)),
        "bytes_received": bytes_received,
        "duration_ms": duration_ms,
        "provider_name": provider_name,
        "provider_version": provider_version,
        "request_fingerprint": request["request_fingerprint"],
        "response_fingerprint": diagnostic["response_fingerprint"],
        "sql_fingerprint": request["sql_fingerprint"],
        "diagnostics": [diagnostic],
        "warnings": safe_warnings(
            provider_result.get("warnings"),
            forbidden_texts=(request["current_sql"],),
        ),
        "executed": bool(provider_result.get("executed", True)),
        "statement_type": diagnostic["statement_type"],
        "error_code": None,
        "failure_category": "none",
        "metrics": {
            "row_count": row_count,
            "rows_received": len(rows),
            "rows_preserved": len(rows),
            "bytes_received": bytes_received,
            "duration_ms": duration_ms,
        },
    }


def create_sql_execution_error_result(
    *,
    request: SqlExecutionRequest | None,
    code: SqlExecutionErrorCode,
    message: str,
    category: SqlExecutionFailureCategory,
    status: SqlExecutionStatus,
    provider_name: str = "unknown",
    provider_version: str | None = None,
    duration_ms: int | None = None,
    warnings: list[str] | None = None,
) -> SqlExecutionResult:
    safe_request = request or _empty_request()
    diagnostic = _diagnostic(
        request=safe_request,
        provider_name=provider_name,
        provider_version=provider_version,
        response_fingerprint_value=None,
        reason=f"sql_execution_{category}",
        duration_ms=duration_ms,
        executed=False,
        statement_type=None,
    )
    return {
        "status": status,
        "columns": [],
        "rows": [],
        "row_count": 0,
        "truncated": False,
        "bytes_received": 0,
        "duration_ms": duration_ms,
        "provider_name": provider_name,
        "provider_version": provider_version,
        "request_fingerprint": safe_request["request_fingerprint"],
        "response_fingerprint": None,
        "sql_fingerprint": safe_request["sql_fingerprint"],
        "diagnostics": [diagnostic],
        "warnings": warnings or [],
        "executed": False,
        "statement_type": None,
        "error_code": code,
        "failure_category": category,
        "metrics": {
            "row_count": 0,
            "rows_received": 0,
            "rows_preserved": 0,
            "bytes_received": 0,
            "duration_ms": duration_ms,
        },
    }


def _validate_preflight(
    engine_preflight_result: EnginePreflightResult,
) -> None:
    if not isinstance(engine_preflight_result, Mapping):
        raise SqlExecutionInputError(
            "SQL_EXECUTION_PREFLIGHT_NOT_APPROVED",
            "Execucao exige Engine Preflight aprovado.",
            category="not_authorized",
        )
    if engine_preflight_result.get("failure_category") == (
        "capability_unavailable"
    ):
        raise SqlExecutionInputError(
            "SQL_EXECUTION_CAPABILITY_UNAVAILABLE",
            "Capability de preflight indisponivel nao autoriza execucao.",
            category="not_authorized",
        )
    if engine_preflight_result.get("failure_category") not in {None, "none"}:
        raise SqlExecutionInputError(
            "SQL_EXECUTION_PREFLIGHT_NOT_APPROVED",
            "Preflight aprovado com categoria de falha nao autoriza execucao.",
            category="not_authorized",
        )
    if engine_preflight_result.get("error_code"):
        raise SqlExecutionInputError(
            "SQL_EXECUTION_PREFLIGHT_NOT_APPROVED",
            "Preflight aprovado com codigo de erro nao autoriza execucao.",
            category="not_authorized",
        )
    if engine_preflight_result.get("repairable") is True:
        raise SqlExecutionInputError(
            "SQL_EXECUTION_PREFLIGHT_NOT_APPROVED",
            "Preflight aprovado reparavel nao autoriza execucao.",
            category="not_authorized",
        )
    if engine_preflight_result.get("errors"):
        raise SqlExecutionInputError(
            "SQL_EXECUTION_PREFLIGHT_NOT_APPROVED",
            "Preflight aprovado com erros nao autoriza execucao.",
            category="not_authorized",
        )
    if engine_preflight_result.get("findings"):
        raise SqlExecutionInputError(
            "SQL_EXECUTION_PREFLIGHT_NOT_APPROVED",
            "Preflight aprovado com findings nao autoriza execucao.",
            category="not_authorized",
        )
    if (
        engine_preflight_result.get("status") != "approved"
        or engine_preflight_result.get("approved") is not True
    ):
        raise SqlExecutionInputError(
            "SQL_EXECUTION_PREFLIGHT_NOT_APPROVED",
            "Execucao exige Engine Preflight aprovado.",
            category="not_authorized",
        )
    if engine_preflight_result.get("executed") is not False:
        raise SqlExecutionInputError(
            "SQL_EXECUTION_PREFLIGHT_NOT_APPROVED",
            "Preflight que executou SQL nao autoriza execucao.",
            category="not_authorized",
        )
    if engine_preflight_result.get("rows_returned") != 0:
        raise SqlExecutionInputError(
            "SQL_EXECUTION_PREFLIGHT_NOT_APPROVED",
            "Preflight que retornou linhas nao autoriza execucao.",
            category="not_authorized",
        )
    if engine_preflight_result.get("statement_planned") is not True:
        raise SqlExecutionInputError(
            "SQL_EXECUTION_PREFLIGHT_NOT_APPROVED",
            "Preflight sem planejamento aprovado nao autoriza execucao.",
            category="not_authorized",
        )


def _analyze_read_only(current_sql: str):
    try:
        analysis = analyze_sql(current_sql)
    except SqlAnalysisError as error:
        raise SqlExecutionInputError(
            "SQL_EXECUTION_REQUEST_INVALID",
            "current_sql nao pode ser analisada para execucao.",
        ) from error
    if not (
        analysis["statement_type"] == "select"
        or (
            analysis["statement_type"] == "with"
            and analysis["with_body_is_select"]
        )
    ):
        raise SqlExecutionInputError(
            "SQL_EXECUTION_NOT_AUTHORIZED",
            "Execucao permite somente SQL de leitura.",
            category="not_authorized",
        )
    if analysis["has_select_into"]:
        raise SqlExecutionInputError(
            "SQL_EXECUTION_NOT_AUTHORIZED",
            "SELECT INTO nao e autorizado para execucao controlada.",
            category="not_authorized",
        )
    return analysis


def _limits(options: Mapping[str, Any] | None) -> SqlExecutionLimits:
    if not isinstance(options, Mapping):
        raise SqlExecutionInputError(
            "SQL_EXECUTION_REQUEST_INVALID",
            "Limites de execucao devem ser informados explicitamente.",
        )
    raw = options.get("sql_execution_limits")
    if not isinstance(raw, Mapping):
        raise SqlExecutionInputError(
            "SQL_EXECUTION_REQUEST_INVALID",
            "options.sql_execution_limits deve ser objeto.",
        )
    limits: SqlExecutionLimits = {
        "timeout_seconds": _positive_int(
            raw.get("timeout_seconds"),
            maximum=MAX_TIMEOUT_SECONDS,
        ),
        "max_rows": _positive_int(raw.get("max_rows"), maximum=MAX_ROWS),
        "max_response_bytes": _positive_int(
            raw.get("max_response_bytes"),
            maximum=MAX_RESPONSE_BYTES,
        ),
        "max_cell_bytes": _positive_int(
            raw.get("max_cell_bytes"),
            maximum=MAX_CELL_BYTES,
        ),
    }
    return limits


def _limit_error(
    limits: SqlExecutionLimits,
    columns: list[SqlExecutionColumn],
    rows: list[SqlExecutionRow],
) -> tuple[
    SqlExecutionErrorCode,
    SqlExecutionFailureCategory,
    str,
] | None:
    if len(rows) > limits["max_rows"]:
        return (
            "SQL_EXECUTION_ROW_LIMIT_EXCEEDED",
            "row_limit_exceeded",
            "Executor retornou mais linhas que o permitido.",
        )
    for row in rows:
        for value in row.values():
            if len(_cell_bytes(value)) > limits["max_cell_bytes"]:
                return (
                    "SQL_EXECUTION_CELL_LIMIT_EXCEEDED",
                    "cell_limit_exceeded",
                    "Executor retornou celula acima do limite.",
                )
    if _payload_size(columns, rows) > limits["max_response_bytes"]:
        return (
            "SQL_EXECUTION_BYTE_LIMIT_EXCEEDED",
            "byte_limit_exceeded",
            "Executor retornou resposta acima do limite em bytes.",
        )
    return None


def _shape_error(
    columns: list[SqlExecutionColumn],
    rows: list[SqlExecutionRow],
) -> str | None:
    column_names = [column["name"] for column in columns]
    if rows and not column_names:
        return "Linhas retornadas sem colunas declaradas."
    expected = set(column_names)
    for row in rows:
        if set(row.keys()) != expected:
            return "Linha retornada diverge das colunas declaradas."
    return None


def _rows(value: Any) -> list[SqlExecutionRow]:
    if not isinstance(value, list):
        return []
    rows: list[SqlExecutionRow] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise TypeError("row must be mapping")
        rows.append(
            {
                str(key): deepcopy(row_value)
                for key, row_value in item.items()
            }
        )
    return rows


def _columns(value: Any) -> list[SqlExecutionColumn]:
    if not isinstance(value, list):
        return []
    columns: list[SqlExecutionColumn] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise TypeError("column must be mapping")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise TypeError("column name must be non-empty text")
        normalized_name = name.strip()
        if normalized_name in seen:
            raise TypeError("duplicate column name")
        seen.add(normalized_name)
        column: SqlExecutionColumn = {"name": normalized_name}
        if "type" in item:
            column["type"] = safe_optional_text(item.get("type"))
        columns.append(column)
    return columns


def _row_count(value: Any, rows: list[SqlExecutionRow]) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if value is not None:
        return None
    return len(rows)


def _bytes_received(
    value: Any,
    columns: list[SqlExecutionColumn],
    rows: list[SqlExecutionRow],
) -> int | None:
    actual_size = _payload_size(columns, rows)
    if value is None:
        return actual_size
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    if value != actual_size:
        return None
    return actual_size


def _payload_size(
    columns: list[SqlExecutionColumn],
    rows: list[SqlExecutionRow],
) -> int:
    return len(
        _stable_json({"columns": columns, "rows": rows}).encode("utf-8")
    )


def _cell_bytes(value: Any) -> bytes:
    return _stable_json(value).encode("utf-8")


def _statement_type(
    provider_result: Mapping[str, Any],
    request: SqlExecutionRequest,
) -> str | None:
    provider_value = safe_optional_text(provider_result.get("statement_type"))
    if provider_value:
        return provider_value.casefold()
    try:
        return cast(
            str | None,
            analyze_sql(request["current_sql"])["statement_type"],
        )
    except SqlAnalysisError:
        return None


def _failure_category(
    provider_result: Mapping[str, Any],
    status: str,
) -> SqlExecutionFailureCategory:
    value = provider_result.get("failure_category")
    valid = {
        "not_authorized",
        "request_invalid",
        "response_invalid",
        "row_limit_exceeded",
        "byte_limit_exceeded",
        "cell_limit_exceeded",
        "provider_failed",
        "timeout",
        "authentication_failed",
        "unexpected_error",
    }
    if isinstance(value, str) and value in valid:
        return cast(SqlExecutionFailureCategory, value)
    return "provider_failed" if status == "error" else "response_invalid"


def _provider_fingerprint_error(
    *,
    request: SqlExecutionRequest,
    provider_result: Mapping[str, Any],
) -> str | None:
    request_value = provider_result.get("request_fingerprint")
    if (
        request_value is not None
        and request_value != request["request_fingerprint"]
    ):
        return "request_fingerprint do executor diverge da request."
    sql_value = provider_result.get("sql_fingerprint")
    if sql_value is not None and sql_value != request["sql_fingerprint"]:
        return "sql_fingerprint do executor diverge da request."
    return None


def _error_code(
    provider_result: Mapping[str, Any],
    category: SqlExecutionFailureCategory,
) -> SqlExecutionErrorCode:
    value = provider_result.get("error_code")
    if isinstance(value, str) and value.startswith("SQL_EXECUTION_"):
        return cast(SqlExecutionErrorCode, value)
    mapping: dict[SqlExecutionFailureCategory, SqlExecutionErrorCode] = {
        "not_authorized": "SQL_EXECUTION_NOT_AUTHORIZED",
        "request_invalid": "SQL_EXECUTION_REQUEST_INVALID",
        "response_invalid": "SQL_EXECUTION_RESPONSE_INVALID",
        "row_limit_exceeded": "SQL_EXECUTION_ROW_LIMIT_EXCEEDED",
        "byte_limit_exceeded": "SQL_EXECUTION_BYTE_LIMIT_EXCEEDED",
        "cell_limit_exceeded": "SQL_EXECUTION_CELL_LIMIT_EXCEEDED",
        "provider_failed": "SQL_EXECUTION_PROVIDER_FAILED",
        "timeout": "SQL_EXECUTION_TIMEOUT",
        "authentication_failed": "SQL_EXECUTION_AUTHENTICATION_FAILED",
        "unexpected_error": "SQL_EXECUTION_UNEXPECTED_ERROR",
        "none": "SQL_EXECUTION_RESPONSE_INVALID",
    }
    return mapping[category]


def _diagnostic(
    *,
    request: SqlExecutionRequest,
    provider_name: str,
    provider_version: str | None,
    response_fingerprint_value: str | None,
    reason: str,
    duration_ms: int | None,
    executed: bool,
    statement_type: str | None,
) -> SqlExecutionDiagnostic:
    return {
        "execution_contract_version": SQL_EXECUTION_CONTRACT_VERSION,
        "request_fingerprint": request["request_fingerprint"],
        "response_fingerprint": response_fingerprint_value,
        "sql_fingerprint": request["sql_fingerprint"],
        "provider_name": provider_name,
        "provider_version": provider_version,
        "reason": reason,
        "duration_ms": duration_ms,
        "executed": executed,
        "statement_type": statement_type,
    }


def _preflight_fingerprint(
    result: EnginePreflightResult,
) -> str:
    return _stable_fingerprint(
        {
            "request_fingerprint": result.get("request_fingerprint"),
            "sql_fingerprint": result.get("sql_fingerprint"),
            "status": result.get("status"),
            "statement_planned": result.get("statement_planned"),
            "executed": result.get("executed"),
            "rows_returned": result.get("rows_returned"),
        }
    )


def _execution_id(
    *,
    request_id: str,
    run_id: str,
    attempt: int,
    sql_fingerprint: str,
) -> str:
    return _stable_fingerprint(
        {
            "request_id": request_id,
            "run_id": run_id,
            "attempt": attempt,
            "sql_fingerprint": sql_fingerprint,
        }
    )


def _engine_hint(
    query_plan: Mapping[str, Any],
    planning_context: Mapping[str, Any],
) -> str | None:
    for value in (
        planning_context.get("engine_hint"),
        planning_context.get("engine"),
        query_plan.get("engine_hint"),
    ):
        hint = safe_optional_text(value)
        if hint:
            return hint
    selected_pattern = query_plan.get("selected_pattern")
    if isinstance(selected_pattern, Mapping):
        return safe_optional_text(selected_pattern.get("engine_hint"))
    return None


def _optional_hint(
    planning_context: Mapping[str, Any],
    field_name: str,
) -> str | None:
    return safe_optional_text(planning_context.get(field_name))


def _required_text(
    value: Mapping[str, Any],
    field_name: str,
) -> str:
    field_value = value.get(field_name)
    if not isinstance(field_value, str) or not field_value.strip():
        raise SqlExecutionInputError(
            "SQL_EXECUTION_REQUEST_INVALID",
            f"{field_name} deve ser texto nao vazio.",
        )
    return field_value.strip()


def _required_external_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SqlExecutionInputError(
            "SQL_EXECUTION_REQUEST_INVALID",
            f"{field_name} deve ser texto nao vazio.",
        )
    return value.strip()


def _positive_int(
    value: Any,
    *,
    default: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool):
        value = None
    if isinstance(value, int) and value > 0:
        if maximum is not None and value > maximum:
            raise SqlExecutionInputError(
                "SQL_EXECUTION_REQUEST_INVALID",
                "Limite de execucao excede maximo permitido.",
            )
        return value
    if default is not None:
        return default
    raise SqlExecutionInputError(
        "SQL_EXECUTION_REQUEST_INVALID",
        "Limite de execucao deve ser inteiro positivo.",
    )


def _optional_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _has_success_payload(provider_result: Mapping[str, Any]) -> bool:
    return (
        bool(provider_result.get("rows"))
        or bool(provider_result.get("columns"))
        or provider_result.get("row_count") not in {None, 0}
        or provider_result.get("executed") is True
    )


def _sql_fingerprint(sql: str) -> str:
    return hashlib.sha256(sql.strip().encode("utf-8")).hexdigest()


def _stable_fingerprint(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    )


def _empty_request() -> SqlExecutionRequest:
    request: SqlExecutionRequest = {
        "contract_version": SQL_EXECUTION_CONTRACT_VERSION,
        "current_sql": "",
        "sql_fingerprint": "",
        "request_id": "",
        "run_id": "",
        "context_version": "",
        "intent_name": "",
        "query_plan_fingerprint": "",
        "preflight_fingerprint": "",
        "limits": {
            "timeout_seconds": 1,
            "max_rows": 1,
            "max_response_bytes": 1,
            "max_cell_bytes": 1,
        },
        "attempt": 1,
        "execution_id": "",
        "dialect": None,
        "engine_hint": None,
        "request_fingerprint": "",
    }
    request["request_fingerprint"] = request_fingerprint(request)
    return request
