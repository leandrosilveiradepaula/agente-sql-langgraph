from __future__ import annotations

import json
import math
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.integrations.watson.flow_contracts import WatsonFlowPurpose
from app.integrations.watson.flow_limits import WatsonFlowLimits


@dataclass(frozen=True, slots=True)
class WatsonFlowNormalizedResult:
    status: str
    purpose: WatsonFlowPurpose
    success: bool
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    query_id: str | None
    duration_ms: int | None
    error_code: str | None
    failure_category: str
    repairable: bool
    diagnostics: tuple[dict[str, Any], ...]


_ENVELOPE_PATHS = (
    (),
    ("result",),
    ("output",),
    ("result", "output"),
    ("output", "result"),
    ("data",),
)

_REPAIRABLE_PROVIDER_CODES = {
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


def normalize_watson_flow_response(
    raw_output: object,
    purpose: WatsonFlowPurpose,
    limits: WatsonFlowLimits,
) -> WatsonFlowNormalizedResult:
    if purpose not in {"preflight", "execution"}:
        return _invalid(purpose, "WATSON_FLOW_INVALID_RESPONSE", "purpose invalido")
    try:
        _validate_size_and_shape(raw_output, limits)
    except ValueError as error:
        return _invalid(
            purpose,
            str(error) or "WATSON_FLOW_INVALID_RESPONSE",
            "Resposta Watson invalida.",
        )

    candidates = _candidates(raw_output)
    if not candidates:
        return _invalid(
            purpose,
            "WATSON_FLOW_INVALID_RESPONSE",
            "Nenhum envelope suportado encontrado.",
        )
    normalized: list[WatsonFlowNormalizedResult] = []
    for path, value in candidates:
        try:
            normalized.append(_normalize_candidate(path, value, purpose, limits))
        except ValueError as error:
            normalized.append(
                _invalid(
                    purpose,
                    str(error) or "WATSON_FLOW_INVALID_RESPONSE",
                    "Envelope Watson invalido.",
                )
            )
    successes = [item for item in normalized if item.status != "invalid_response"]
    if not successes:
        return normalized[0]
    first = successes[0]
    for item in successes[1:]:
        if _comparable(item) != _comparable(first):
            return _invalid(
                purpose,
                "WATSON_FLOW_AMBIGUOUS_RESPONSE",
                "Envelopes Watson conflitantes.",
            )
    return first


def _normalize_candidate(
    path: tuple[str, ...],
    value: object,
    purpose: WatsonFlowPurpose,
    limits: WatsonFlowLimits,
) -> WatsonFlowNormalizedResult:
    if not isinstance(value, Mapping):
        return _invalid(
            purpose,
            "WATSON_FLOW_INVALID_RESPONSE",
            f"Envelope {'.'.join(path) or 'raw'} nao e objeto.",
        )
    raw_success = value.get("success")
    if not isinstance(raw_success, bool):
        return _invalid(
            purpose,
            "WATSON_FLOW_INVALID_RESPONSE",
            "success deve ser bool real.",
        )
    if raw_success is False:
        if _has_rows(value):
            return _invalid(
                purpose,
                "WATSON_FLOW_INVALID_RESPONSE",
                "Erro Watson trouxe payload de sucesso.",
            )
        code, category, repairable = _error_classification(value)
        return WatsonFlowNormalizedResult(
            status="functional_error",
            purpose=purpose,
            success=False,
            columns=[],
            rows=[],
            row_count=0,
            truncated=False,
            query_id=None,
            duration_ms=_duration(value, limits),
            error_code=code,
            failure_category=category,
            repairable=repairable if purpose == "preflight" else False,
            diagnostics=(_diagnostic(code, "Watson Flow retornou erro funcional."),),
        )

    rows_value = value.get("data", value.get("rows", []))
    rows = _rows(rows_value, limits)
    columns = _columns(value.get("columns"), rows, limits)
    if rows and not columns:
        return _invalid(purpose, "WATSON_FLOW_INVALID_RESPONSE", "Colunas ausentes.")
    if _shape_error(columns, rows):
        return _invalid(purpose, "WATSON_FLOW_INVALID_RESPONSE", "Shape divergente.")
    row_count = _row_count(value.get("row_count", value.get("rowCount")), rows)
    if row_count != len(rows):
        return _invalid(purpose, "WATSON_FLOW_INVALID_RESPONSE", "row_count divergente.")
    if _has_error_message(value):
        return _invalid(
            purpose,
            "WATSON_FLOW_INVALID_RESPONSE",
            "Sucesso Watson contem mensagem de erro.",
        )
    return WatsonFlowNormalizedResult(
        status="success",
        purpose=purpose,
        success=True,
        columns=deepcopy(columns),
        rows=deepcopy(rows),
        row_count=row_count,
        truncated=_strict_bool(value.get("truncated"), default=False),
        query_id=_optional_text(
            value.get("query_id", value.get("queryId", value.get("id"))),
            limits.max_query_id_bytes,
        ),
        duration_ms=_duration(value, limits),
        error_code=None,
        failure_category="none",
        repairable=False,
        diagnostics=(),
    )


def _candidates(raw: object) -> list[tuple[tuple[str, ...], object]]:
    values: list[tuple[tuple[str, ...], object]] = []
    for path in _ENVELOPE_PATHS:
        found, value = _at_path(raw, path)
        if found:
            if isinstance(value, str) and value.strip().startswith(("{", "[")):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            if isinstance(value, Mapping) and "success" in value:
                values.append((path, value))
    return values


def _at_path(raw: object, path: tuple[str, ...]) -> tuple[bool, object]:
    current = raw
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return False, None
        current = current[key]
    return True, current


def _rows(value: object, limits: WatsonFlowLimits) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
    if len(value) > limits.max_rows:
        raise ValueError("WATSON_FLOW_RESPONSE_TOO_LARGE")
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
        clean: dict[str, Any] = {}
        for key, raw in item.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
            if _has_control(key):
                raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
            if len(key.encode("utf-8")) > limits.max_column_name_bytes:
                raise ValueError("WATSON_FLOW_RESPONSE_TOO_LARGE")
            clean[key] = _cell(raw, limits)
        rows.append(clean)
    return rows


def _columns(value: object, rows: list[dict[str, Any]], limits: WatsonFlowLimits) -> list[dict[str, Any]]:
    if value is None:
        names = list(rows[0].keys()) if rows else []
    elif isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, Mapping):
                raw = item.get("name")
            else:
                raw = item
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
            name = raw.strip()
            if _has_control(name):
                raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
            names.append(name)
    else:
        raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
    if len(names) > limits.max_columns or len(names) * max(len(rows), 1) > limits.max_cells:
        raise ValueError("WATSON_FLOW_RESPONSE_TOO_LARGE")
    seen: set[str] = set()
    columns: list[dict[str, Any]] = []
    for name in names:
        if name in seen:
            raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
        seen.add(name)
        if len(name.encode("utf-8")) > limits.max_column_name_bytes:
            raise ValueError("WATSON_FLOW_RESPONSE_TOO_LARGE")
        columns.append({"name": name})
    return columns


def _cell(value: object, limits: WatsonFlowLimits) -> object:
    if value is None or isinstance(value, (bool, int, str, Decimal)):
        if isinstance(value, str) and len(value.encode("utf-8")) > limits.max_string_cell_bytes:
            raise ValueError("WATSON_FLOW_RESPONSE_TOO_LARGE")
        return deepcopy(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
        return value
    if isinstance(value, (list, tuple, Mapping)):
        raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
    raise ValueError("WATSON_FLOW_INVALID_RESPONSE")


def _validate_size_and_shape(value: object, limits: WatsonFlowLimits) -> None:
    seen: set[int] = set()
    members = _walk(value, depth=0, limits=limits, seen=seen)
    if members > limits.max_response_members:
        raise ValueError("WATSON_FLOW_RESPONSE_TOO_LARGE")
    try:
        size = len(json.dumps(value, default=str, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        raise ValueError("WATSON_FLOW_INVALID_RESPONSE") from None
    if size > limits.max_raw_response_bytes:
        raise ValueError("WATSON_FLOW_RESPONSE_TOO_LARGE")


def _walk(value: object, *, depth: int, limits: WatsonFlowLimits, seen: set[int]) -> int:
    if depth > limits.max_response_depth:
        raise ValueError("WATSON_FLOW_RESPONSE_TOO_LARGE")
    if isinstance(value, (Mapping, list, tuple)):
        identifier = id(value)
        if identifier in seen:
            raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
        seen.add(identifier)
        if isinstance(value, Mapping):
            count = len(value)
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
                count += _walk(item, depth=depth + 1, limits=limits, seen=seen)
        else:
            count = len(value)
            for item in value:
                count += _walk(item, depth=depth + 1, limits=limits, seen=seen)
        seen.discard(identifier)
        return count
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
    return 1


def _error_classification(value: Mapping[str, Any]) -> tuple[str, str, bool]:
    provider_code = value.get("error_code") or value.get("code")
    category = value.get("failure_category")
    code = (
        provider_code
        if isinstance(provider_code, str) and provider_code in _REPAIRABLE_PROVIDER_CODES
        else "WATSON_FLOW_EXECUTION_FAILED"
    )
    safe_category = (
        category
        if isinstance(category, str) and category in _REPAIRABLE_PROVIDER_CODES
        else "provider_failed"
    )
    repairable = code in _REPAIRABLE_PROVIDER_CODES or safe_category in _REPAIRABLE_PROVIDER_CODES
    return code, safe_category, repairable


def _duration(value: Mapping[str, Any], limits: WatsonFlowLimits) -> int | None:
    raw = value.get("execution_time_ms", value.get("executionTimeMs", value.get("elapsed_ms")))
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0 or raw > limits.max_duration_ms:
        raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
    return raw


def _row_count(value: object, rows: list[dict[str, Any]]) -> int:
    if value is None:
        return len(rows)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
    return value


def _strict_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
    return value


def _optional_text(value: object, max_bytes: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
    text = value.strip()
    if _has_control(text):
        raise ValueError("WATSON_FLOW_INVALID_RESPONSE")
    if len(text.encode("utf-8")) > max_bytes:
        raise ValueError("WATSON_FLOW_RESPONSE_TOO_LARGE")
    return text


def _shape_error(columns: list[dict[str, Any]], rows: list[dict[str, Any]]) -> bool:
    expected = {column["name"] for column in columns}
    return any(set(row.keys()) != expected for row in rows)


def _has_rows(value: Mapping[str, Any]) -> bool:
    rows = value.get("data", value.get("rows"))
    return isinstance(rows, list) and bool(rows)


def _has_error_message(value: Mapping[str, Any]) -> bool:
    return any(key in value and value.get(key) for key in ("error", "error_message", "message"))


def _comparable(result: WatsonFlowNormalizedResult) -> tuple[object, ...]:
    return (
        result.status,
        result.success,
        result.columns,
        result.rows,
        result.row_count,
        result.truncated,
        result.query_id,
        result.error_code,
        result.failure_category,
    )


def _diagnostic(code: str, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}


def _invalid(
    purpose: WatsonFlowPurpose,
    code: str,
    message: str,
) -> WatsonFlowNormalizedResult:
    return WatsonFlowNormalizedResult(
        status="invalid_response",
        purpose=purpose,
        success=False,
        columns=[],
        rows=[],
        row_count=0,
        truncated=False,
        query_id=None,
        duration_ms=None,
        error_code=code,
        failure_category="response_invalid",
        repairable=False,
        diagnostics=(_diagnostic(code, message),),
    )


def _has_control(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)
