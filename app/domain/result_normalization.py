from __future__ import annotations

import base64
import hashlib
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.domain.engine_preflight_sanitization import safe_optional_text
from app.domain.result_normalization_types import (
    RESULT_NORMALIZATION_CONTRACT_VERSION,
    NormalizationDiagnostic,
    NormalizedCell,
    NormalizedColumn,
    NormalizedQueryResult,
    NormalizedRow,
    NormalizedValueType,
    ResultLineage,
    ResultNormalizationLimits,
)
from app.domain.sql_execution_types import (
    SQL_EXECUTION_CONTRACT_VERSION,
    SqlExecutionResult,
)


class ResultNormalizationError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        diagnostic: NormalizationDiagnostic | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.diagnostic = diagnostic
        super().__init__(message)


def normalize_execution_result(
    execution_result: SqlExecutionResult,
    *,
    limits: ResultNormalizationLimits,
) -> NormalizedQueryResult:
    original = deepcopy(execution_result)
    try:
        _validate_execution_result(original)
        _validate_limits(limits)
        columns = _normalized_columns(original["columns"], limits)
        rows = _normalized_rows(original["rows"], columns, limits)
        lineage = _lineage(original, columns, rows)
        metrics = {
            "row_count": len(rows),
            "column_count": len(columns),
            "total_cells": len(rows) * len(columns),
            "estimated_bytes": _estimated_bytes(
                {"columns": columns, "rows": rows, "lineage": lineage}
            ),
            "max_nesting_depth": limits["max_nesting_depth"],
            "diagnostic_count": 0,
        }
        if metrics["estimated_bytes"] > limits["max_serialized_bytes"]:
            raise ResultNormalizationError(
                "RESULT_NORMALIZATION_LIMIT_EXCEEDED",
                "Resultado normalizado excede limite de bytes.",
                diagnostic={
                    "code": "RESULT_NORMALIZATION_LIMIT_EXCEEDED",
                    "message": "Resultado normalizado excede limite de bytes.",
                    "row_ordinal": None,
                    "column_ordinal": None,
                    "normalized_type": None,
                    "size": metrics["estimated_bytes"],
                    "fingerprint": None,
                },
            )
        fingerprint_payload = {
            "contract_version": RESULT_NORMALIZATION_CONTRACT_VERSION,
            "columns": columns,
            "rows": rows,
            "lineage": lineage,
            "metrics": metrics,
        }
        result_fingerprint = stable_fingerprint(fingerprint_payload)
        lineage["normalized_result_fingerprint"] = result_fingerprint
        lineage["estimated_bytes"] = metrics["estimated_bytes"]
        return {
            "status": "success",
            "contract_version": RESULT_NORMALIZATION_CONTRACT_VERSION,
            "columns": columns,
            "rows": rows,
            "lineage": lineage,
            "metrics": metrics,
            "diagnostics": [],
            "warnings": [],
            "error_code": None,
            "result_fingerprint": result_fingerprint,
        }
    except ResultNormalizationError as error:
        diagnostic = error.diagnostic or {
            "code": error.code,
            "message": error.message,
            "row_ordinal": None,
            "column_ordinal": None,
            "normalized_type": None,
            "size": None,
            "fingerprint": None,
        }
        return _rejected_result(original, error.code, diagnostic)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def stable_fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _validate_execution_result(result: Mapping[str, Any]) -> None:
    if not isinstance(result, Mapping):
        raise ResultNormalizationError(
            "RESULT_NORMALIZATION_EXECUTION_INVALID",
            "Resultado de execucao deve ser objeto.",
        )
    if result.get("status") != "success" or result.get("executed") is not True:
        raise ResultNormalizationError(
            "RESULT_NORMALIZATION_EXECUTION_INVALID",
            "Normalizacao exige execucao success e executed=True.",
        )
    if result.get("truncated") is True:
        raise ResultNormalizationError(
            "RESULT_NORMALIZATION_EXECUTION_INVALID",
            "Resultado truncado nao pode ser normalizado.",
        )
    for field in (
        "request_fingerprint",
        "response_fingerprint",
        "sql_fingerprint",
    ):
        value = result.get(field)
        if not isinstance(value, str) or not value:
            raise ResultNormalizationError(
                "RESULT_NORMALIZATION_EXECUTION_INVALID",
                f"{field} ausente no resultado de execucao.",
            )
    columns = result.get("columns")
    rows = result.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise ResultNormalizationError(
            "RESULT_NORMALIZATION_SHAPE_INVALID",
            "Colunas e linhas devem ser listas.",
        )
    row_count = result.get("row_count")
    if isinstance(row_count, bool) or row_count != len(rows):
        raise ResultNormalizationError(
            "RESULT_NORMALIZATION_SHAPE_INVALID",
            "row_count diverge das linhas.",
        )


def _validate_limits(limits: Mapping[str, Any]) -> None:
    for field in (
        "max_rows",
        "max_columns",
        "max_total_cells",
        "max_nesting_depth",
        "max_collection_items",
        "max_serialized_bytes",
        "max_diagnostic_entries",
    ):
        value = limits.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ResultNormalizationError(
                "RESULT_NORMALIZATION_LIMIT_EXCEEDED",
                "Limites de normalizacao devem ser inteiros positivos.",
            )


def _normalized_columns(
    raw_columns: list[Mapping[str, Any]],
    limits: ResultNormalizationLimits,
) -> list[NormalizedColumn]:
    if len(raw_columns) > limits["max_columns"]:
        raise ResultNormalizationError(
            "RESULT_NORMALIZATION_LIMIT_EXCEEDED",
            "Quantidade de colunas excede limite.",
        )
    seen: set[str] = set()
    columns: list[NormalizedColumn] = []
    for ordinal, raw in enumerate(raw_columns):
        if not isinstance(raw, Mapping):
            raise ResultNormalizationError(
                "RESULT_NORMALIZATION_SHAPE_INVALID",
                "Coluna deve ser objeto.",
            )
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ResultNormalizationError(
                "RESULT_NORMALIZATION_SHAPE_INVALID",
                "Nome de coluna deve ser texto nao vazio.",
            )
        clean_name = name.strip()
        if clean_name in seen:
            raise ResultNormalizationError(
                "RESULT_NORMALIZATION_SHAPE_INVALID",
                "Coluna duplicada nao pode ser normalizada.",
                diagnostic={
                    "code": "RESULT_NORMALIZATION_SHAPE_INVALID",
                    "message": "Coluna duplicada nao pode ser normalizada.",
                    "row_ordinal": None,
                    "column_ordinal": ordinal,
                    "normalized_type": None,
                    "size": None,
                    "fingerprint": None,
                },
            )
        seen.add(clean_name)
        provider_type = safe_optional_text(raw.get("type"))
        columns.append(
            {
                "ordinal": ordinal,
                "original_name": clean_name,
                "provider_type_name": provider_type,
                "normalized_type": "null",
                "nullable": None,
                "precision": None,
                "scale": None,
                "timezone": None,
                "metadata": {},
            }
        )
    return columns


def _normalized_rows(
    raw_rows: list[Mapping[str, Any]],
    columns: list[NormalizedColumn],
    limits: ResultNormalizationLimits,
) -> list[NormalizedRow]:
    if len(raw_rows) > limits["max_rows"]:
        raise ResultNormalizationError(
            "RESULT_NORMALIZATION_LIMIT_EXCEEDED",
            "Quantidade de linhas excede limite.",
        )
    if len(raw_rows) * len(columns) > limits["max_total_cells"]:
        raise ResultNormalizationError(
            "RESULT_NORMALIZATION_LIMIT_EXCEEDED",
            "Quantidade de celulas excede limite.",
        )
    names = [column["original_name"] for column in columns]
    expected = set(names)
    rows: list[NormalizedRow] = []
    observed_types: dict[int, set[NormalizedValueType]] = {
        index: set() for index in range(len(columns))
    }
    nullable: dict[int, bool] = {index: False for index in range(len(columns))}
    for row_ordinal, raw in enumerate(raw_rows):
        if not isinstance(raw, Mapping) or set(raw.keys()) != expected:
            raise ResultNormalizationError(
                "RESULT_NORMALIZATION_SHAPE_INVALID",
                "Linha diverge das colunas declaradas.",
                diagnostic={
                    "code": "RESULT_NORMALIZATION_SHAPE_INVALID",
                    "message": "Linha diverge das colunas declaradas.",
                    "row_ordinal": row_ordinal,
                    "column_ordinal": None,
                    "normalized_type": None,
                    "size": None,
                    "fingerprint": None,
                },
            )
        cells: list[NormalizedCell] = []
        for column_ordinal, name in enumerate(names):
            cell = _normalize_value(
                raw[name],
                row_ordinal=row_ordinal,
                column_ordinal=column_ordinal,
                limits=limits,
                seen=set(),
                depth=0,
            )
            cells.append(cell)
            observed_types[column_ordinal].add(cell["type"])
            if cell["type"] == "null":
                nullable[column_ordinal] = True
        rows.append({"ordinal": row_ordinal, "cells": cells})
    for column in columns:
        ordinal = column["ordinal"]
        types = sorted(observed_types[ordinal])
        non_null_types = [item for item in types if item != "null"]
        if len(non_null_types) > 1:
            raise ResultNormalizationError(
                "RESULT_NORMALIZATION_VALUE_INVALID",
                "Coluna contem tipos mistos nao normalizaveis.",
                diagnostic={
                    "code": "RESULT_NORMALIZATION_VALUE_INVALID",
                    "message": "Coluna contem tipos mistos nao normalizaveis.",
                    "row_ordinal": None,
                    "column_ordinal": ordinal,
                    "normalized_type": "mixed",
                    "size": None,
                    "fingerprint": None,
                },
            )
        column["normalized_type"] = (
            non_null_types[0] if non_null_types else "null"
        )
        column["nullable"] = nullable[ordinal]
        if "datetime" in types:
            column["timezone"] = any(
                row["cells"][ordinal].get("timezone") is True for row in rows
            )
        if "decimal" in types:
            scales = [
                abs(value.as_tuple().exponent)
                for row_index, raw in enumerate(raw_rows)
                for value in [raw[names[ordinal]]]
                if isinstance(value, Decimal)
            ]
            column["scale"] = max(scales) if scales else None
    return rows


def _normalize_value(
    value: Any,
    *,
    row_ordinal: int,
    column_ordinal: int,
    limits: ResultNormalizationLimits,
    seen: set[int],
    depth: int,
) -> NormalizedCell:
    if depth > limits["max_nesting_depth"]:
        raise _value_error(
            "Profundidade de estrutura excede limite.",
            row_ordinal,
            column_ordinal,
            "json",
        )
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, bool):
        return {"type": "boolean", "value": value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"type": "integer", "value": value}
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise _value_error(
                "Decimal nao finito nao pode ser normalizado.",
                row_ordinal,
                column_ordinal,
                "decimal",
            )
        return {"type": "decimal", "value": format(value, "f")}
    if isinstance(value, float):
        if math.isnan(value):
            return {"type": "float", "value": None, "special": "NaN"}
        if math.isinf(value):
            return {
                "type": "float",
                "value": None,
                "special": "Infinity" if value > 0 else "-Infinity",
            }
        if value == 0.0 and math.copysign(1.0, value) < 0:
            return {"type": "float", "value": "-0.0", "special": "-0.0"}
        return {"type": "float", "value": value, "special": None}
    if isinstance(value, str):
        return {"type": "string", "value": value}
    if isinstance(value, datetime):
        return {
            "type": "datetime",
            "value": value.isoformat(),
            "timezone": value.tzinfo is not None,
        }
    if isinstance(value, date):
        return {"type": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {
            "type": "time",
            "value": value.isoformat(),
            "timezone": value.tzinfo is not None,
        }
    if isinstance(value, (bytes, bytearray)):
        return {
            "type": "binary",
            "value": base64.b64encode(bytes(value)).decode("ascii"),
            "encoding": "base64",
        }
    if isinstance(value, UUID):
        return {"type": "uuid", "value": str(value)}
    if isinstance(value, (Mapping, list, tuple)):
        return {
            "type": "json",
            "value": _normalize_json_value(
                value,
                row_ordinal=row_ordinal,
                column_ordinal=column_ordinal,
                limits=limits,
                seen=seen,
                depth=depth,
            ),
        }
    raise _value_error(
        "Tipo de celula nao suportado.",
        row_ordinal,
        column_ordinal,
        type(value).__name__,
    )


def _normalize_json_value(
    value: Any,
    *,
    row_ordinal: int,
    column_ordinal: int,
    limits: ResultNormalizationLimits,
    seen: set[int],
    depth: int,
) -> Any:
    if isinstance(value, (Mapping, list, tuple)):
        identifier = id(value)
        if identifier in seen:
            raise _value_error(
                "Estrutura ciclica nao pode ser normalizada.",
                row_ordinal,
                column_ordinal,
                "json",
            )
        seen.add(identifier)
    if isinstance(value, Mapping):
        if len(value) > limits["max_collection_items"]:
            raise _value_error(
                "Colecao excede limite de itens.",
                row_ordinal,
                column_ordinal,
                "json",
            )
        if any(not isinstance(key, str) for key in value.keys()):
            raise _value_error(
                "Objeto JSON exige chaves textuais.",
                row_ordinal,
                column_ordinal,
                "json",
            )
        normalized: dict[str, Any] = {}
        for key in sorted(value.keys()):
            normalized[key] = _normalize_json_value(
                value[key],
                row_ordinal=row_ordinal,
                column_ordinal=column_ordinal,
                limits=limits,
                seen=seen,
                depth=depth + 1,
            )
        seen.discard(id(value))
        return normalized
    if isinstance(value, (list, tuple)):
        if len(value) > limits["max_collection_items"]:
            raise _value_error(
                "Colecao excede limite de itens.",
                row_ordinal,
                column_ordinal,
                "json",
            )
        normalized_list = [
            _normalize_json_value(
                item,
                row_ordinal=row_ordinal,
                column_ordinal=column_ordinal,
                limits=limits,
                seen=seen,
                depth=depth + 1,
            )
            for item in value
        ]
        seen.discard(id(value))
        return normalized_list
    cell = _normalize_value(
        value,
        row_ordinal=row_ordinal,
        column_ordinal=column_ordinal,
        limits=limits,
        seen=seen,
        depth=depth + 1,
    )
    return {"type": cell["type"], "value": cell.get("value"), **({
        "special": cell.get("special")
    } if cell.get("special") else {})}


def _value_error(
    message: str,
    row_ordinal: int,
    column_ordinal: int,
    normalized_type: str,
) -> ResultNormalizationError:
    return ResultNormalizationError(
        "RESULT_NORMALIZATION_VALUE_INVALID",
        message,
        diagnostic={
            "code": "RESULT_NORMALIZATION_VALUE_INVALID",
            "message": message,
            "row_ordinal": row_ordinal,
            "column_ordinal": column_ordinal,
            "normalized_type": normalized_type,
            "size": None,
            "fingerprint": None,
        },
    )


def _lineage(
    result: Mapping[str, Any],
    columns: list[NormalizedColumn],
    rows: list[NormalizedRow],
) -> ResultLineage:
    return {
        "request_id": str(result.get("request_id", "")),
        "run_id": str(result.get("run_id", "")),
        "context_version": str(result.get("context_version", "")),
        "intent_name": str(result.get("intent_name", "")),
        "sql_fingerprint": str(result["sql_fingerprint"]),
        "query_plan_fingerprint": str(result.get("query_plan_fingerprint", "")),
        "preflight_fingerprint": str(result.get("preflight_fingerprint", "")),
        "execution_request_fingerprint": str(result["request_fingerprint"]),
        "execution_response_fingerprint": result.get("response_fingerprint"),
        "execution_provider_name": str(result.get("provider_name", "unknown")),
        "execution_provider_version": result.get("provider_version"),
        "execution_duration_ms": result.get("duration_ms"),
        "normalized_result_fingerprint": "",
        "row_count": len(rows),
        "column_count": len(columns),
        "estimated_bytes": 0,
        "truncated": bool(result.get("truncated", False)),
        "execution_contract_version": SQL_EXECUTION_CONTRACT_VERSION,
        "normalization_contract_version": RESULT_NORMALIZATION_CONTRACT_VERSION,
    }


def _estimated_bytes(value: Any) -> int:
    return len(canonical_json(value).encode("utf-8"))


def _rejected_result(
    execution_result: Mapping[str, Any],
    code: str,
    diagnostic: NormalizationDiagnostic,
) -> NormalizedQueryResult:
    diagnostics = [diagnostic]
    return {
        "status": "rejected",
        "contract_version": RESULT_NORMALIZATION_CONTRACT_VERSION,
        "columns": [],
        "rows": [],
        "lineage": {
            "request_id": str(execution_result.get("request_id", "")),
            "run_id": str(execution_result.get("run_id", "")),
            "sql_fingerprint": str(execution_result.get("sql_fingerprint", "")),
            "execution_request_fingerprint": str(
                execution_result.get("request_fingerprint", "")
            ),
            "execution_response_fingerprint": execution_result.get(
                "response_fingerprint"
            ),
            "normalization_contract_version": RESULT_NORMALIZATION_CONTRACT_VERSION,
        },
        "metrics": {
            "row_count": 0,
            "column_count": 0,
            "total_cells": 0,
            "estimated_bytes": 0,
            "max_nesting_depth": 0,
            "diagnostic_count": len(diagnostics),
        },
        "diagnostics": diagnostics,
        "warnings": [],
        "error_code": code,
        "result_fingerprint": None,
    }
