from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from app.domain.result_normalization_types import NormalizedQueryResult
from app.domain.result_serialization import serialize_normalized_result
from app.graph.state import AgentError, GraphState


def serialize_result(state: GraphState) -> GraphState:
    normalized_result = state.get("normalized_result")
    options = state.get("options") if isinstance(state.get("options"), Mapping) else {}
    try:
        max_bytes = _max_serialized_bytes(options)
        if not isinstance(normalized_result, Mapping):
            result = serialize_normalized_result(
                _empty_normalized_result(),
                max_serialized_bytes=max_bytes,
            )
        else:
            result = serialize_normalized_result(
                deepcopy(normalized_result),
                max_serialized_bytes=max_bytes,
            )
    except Exception as error:
        return _error_state(
            state,
            code="RESULT_SERIALIZATION_UNEXPECTED_ERROR",
            message="Erro inesperado ao serializar resultado.",
            details={"exception_type": type(error).__name__},
            final_status="infrastructure_error",
            serialized_result=None,
        )
    if result["status"] == "success":
        return {
            "serialized_result": result,
            "current_stage": "serialize_result",
            "final_status": "approved",
            "failure_stage": "",
        }
    return _error_state(
        state,
        code=result["error_code"] or "RESULT_SERIALIZATION_INPUT_INVALID",
        message="Resultado normalizado nao pode ser serializado.",
        details={
            "diagnostic": result["diagnostics"][0] if result["diagnostics"] else {},
            "result_fingerprint": result.get("result_fingerprint"),
        },
        final_status="rejected",
        serialized_result=result,
    )


def _max_serialized_bytes(options: Mapping) -> int:
    raw = options.get("result_normalization_limits")
    if isinstance(raw, Mapping):
        value = raw.get("max_serialized_bytes")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    execution_limits = options.get("sql_execution_limits")
    if isinstance(execution_limits, Mapping):
        value = execution_limits.get("max_response_bytes")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    raise ValueError("Limite de serializacao ausente.")


def _error_state(
    state: GraphState,
    *,
    code: str,
    message: str,
    details: dict,
    final_status: str,
    serialized_result,
) -> GraphState:
    return {
        **({"serialized_result": serialized_result} if serialized_result is not None else {}),
        "errors": [
            *state.get("errors", []),
            _agent_error(code=code, message=message, details=details),
        ],
        "current_stage": "serialize_result",
        "final_status": final_status,
        "failure_stage": "serialize_result",
    }


def _agent_error(*, code: str, message: str, details: dict) -> AgentError:
    return {
        "code": code,
        "message": message,
        "source": "result_serialization",
        "stage": "serialize_result",
        "repairable": False,
        "details": details,
    }


def _empty_normalized_result() -> NormalizedQueryResult:
    return {
        "status": "rejected",
        "contract_version": "",
        "columns": [],
        "rows": [],
        "lineage": {},
        "metrics": {
            "row_count": 0,
            "column_count": 0,
            "total_cells": 0,
            "estimated_bytes": 0,
            "max_nesting_depth": 0,
            "diagnostic_count": 0,
        },
        "diagnostics": [],
        "warnings": [],
        "error_code": "RESULT_NORMALIZATION_EXECUTION_INVALID",
        "result_fingerprint": None,
    }
