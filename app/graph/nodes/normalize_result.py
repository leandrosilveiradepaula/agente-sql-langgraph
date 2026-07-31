from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from app.domain.result_normalization import normalize_execution_result
from app.domain.result_normalization_types import (
    ResultNormalizationLimits,
)
from app.domain.sql_execution_types import SqlExecutionResult
from app.graph.state import AgentError, GraphState


def normalize_result(state: GraphState) -> GraphState:
    execution_result = state.get("sql_execution_result")
    options = state.get("options") if isinstance(state.get("options"), Mapping) else {}
    try:
        limits = _limits(options)
        if not isinstance(execution_result, Mapping):
            result = normalize_execution_result(
                _empty_execution_result(),
                limits=limits,
            )
        else:
            result = normalize_execution_result(
                deepcopy(execution_result),
                limits=limits,
            )
    except Exception as error:
        return _error_state(
            state,
            code="RESULT_NORMALIZATION_UNEXPECTED_ERROR",
            message="Erro inesperado ao normalizar resultado.",
            details={"exception_type": type(error).__name__},
            final_status="infrastructure_error",
            normalized_result=None,
        )

    if result["status"] == "success":
        return {
            "normalized_result": result,
            "current_stage": "normalize_result",
            "final_status": "processing",
            "failure_stage": "",
        }
    return _error_state(
        state,
        code=result["error_code"] or "RESULT_NORMALIZATION_EXECUTION_INVALID",
        message="Resultado de execucao nao pode ser normalizado.",
        details={
            "diagnostic": result["diagnostics"][0] if result["diagnostics"] else {},
            "result_fingerprint": result.get("result_fingerprint"),
        },
        final_status="rejected",
        normalized_result=result,
    )


def _limits(options: Mapping) -> ResultNormalizationLimits:
    raw = options.get("result_normalization_limits")
    if isinstance(raw, Mapping):
        return {
            "max_rows": _positive_int(raw.get("max_rows")),
            "max_columns": _positive_int(raw.get("max_columns")),
            "max_total_cells": _positive_int(raw.get("max_total_cells")),
            "max_nesting_depth": _positive_int(raw.get("max_nesting_depth")),
            "max_collection_items": _positive_int(raw.get("max_collection_items")),
            "max_serialized_bytes": _positive_int(raw.get("max_serialized_bytes")),
            "max_diagnostic_entries": _positive_int(raw.get("max_diagnostic_entries")),
        }
    execution_limits = options.get("sql_execution_limits")
    if not isinstance(execution_limits, Mapping):
        raise ValueError("Limites de execucao ausentes para normalizacao.")
    max_rows = _positive_int(execution_limits.get("max_rows"))
    max_bytes = _positive_int(execution_limits.get("max_response_bytes"))
    return {
        "max_rows": max_rows,
        "max_columns": 256,
        "max_total_cells": max_rows * 256,
        "max_nesting_depth": 12,
        "max_collection_items": 1024,
        "max_serialized_bytes": max_bytes,
        "max_diagnostic_entries": 20,
    }


def _positive_int(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("Limite deve ser inteiro positivo.")
    return value


def _error_state(
    state: GraphState,
    *,
    code: str,
    message: str,
    details: dict,
    final_status: str,
    normalized_result,
) -> GraphState:
    return {
        **({"normalized_result": normalized_result} if normalized_result is not None else {}),
        "errors": [
            *state.get("errors", []),
            _agent_error(code=code, message=message, details=details),
        ],
        "current_stage": "normalize_result",
        "final_status": final_status,
        "failure_stage": "normalize_result",
    }


def _agent_error(*, code: str, message: str, details: dict) -> AgentError:
    return {
        "code": code,
        "message": message,
        "source": "result_normalization",
        "stage": "normalize_result",
        "repairable": False,
        "details": details,
    }


def _empty_execution_result() -> SqlExecutionResult:
    return {
        "status": "rejected",
        "request_id": "",
        "run_id": "",
        "context_version": "",
        "intent_name": "",
        "query_plan_fingerprint": "",
        "preflight_fingerprint": "",
        "columns": [],
        "rows": [],
        "row_count": 0,
        "truncated": False,
        "bytes_received": 0,
        "duration_ms": None,
        "provider_name": "unknown",
        "provider_version": None,
        "request_fingerprint": "",
        "response_fingerprint": None,
        "sql_fingerprint": "",
        "diagnostics": [],
        "warnings": [],
        "executed": False,
        "statement_type": None,
        "error_code": "SQL_EXECUTION_RESPONSE_INVALID",
        "failure_category": "response_invalid",
        "metrics": {
            "row_count": 0,
            "rows_received": 0,
            "rows_preserved": 0,
            "bytes_received": 0,
            "duration_ms": None,
        },
    }
