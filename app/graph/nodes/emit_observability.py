from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import cast

from app.domain.run_observability_types import ObservabilityResult
from app.domain.run_record import (
    build_observability_event,
)
from app.domain.run_record_types import RunRecord
from app.graph.state import AgentError, GraphState
from app.ports.observability_sink import ObservabilitySink


def create_emit_observability_node(
    observability_sink: ObservabilitySink,
) -> Callable[[GraphState], GraphState]:
    def emit_observability(state: GraphState) -> GraphState:
        previous = state.get("observability_result")
        if isinstance(previous, Mapping):
            return {
                "current_stage": "emit_observability",
                "observability_degraded": previous.get("status")
                == "degraded",
            }
        record = state.get("run_record")
        try:
            event = build_observability_event(
                cast(RunRecord, record) if isinstance(record, Mapping) else None,
                limits=(
                    state.get("options", {}).get("run_finalization_limits", {})
                    if isinstance(state.get("options"), dict)
                    else {}
                ),
                finalization_status=str(
                    state.get("finalization_status", "")
                ),
                persistence_duration_ms=_duration(
                    state.get("persistence_result")
                ),
                audit_duration_ms=_duration(state.get("audit_result")),
            )
            result = observability_sink.emit(deepcopy(event))
        except TimeoutError:
            return _degraded_state(
                state,
                code="OBSERVABILITY_TIMEOUT",
                message="Observabilidade excedeu o timeout.",
            )
        except Exception as error:
            return _degraded_state(
                state,
                code="OBSERVABILITY_UNEXPECTED_ERROR",
                message="Erro inesperado na observabilidade.",
                details={"exception_type": type(error).__name__},
            )
        if result["status"] == "emitted":
            return {
                "observability_result": deepcopy(result),
                "current_stage": "emit_observability",
                "final_status": _final_status_after_observability(state),
                "finalization_status": "observed",
                "observability_degraded": False,
            }
        return _degraded_state(
            state,
            code=(
                (result.get("diagnostic") or {}).get(
                    "code",
                    "OBSERVABILITY_EMIT_FAILED",
                )
            ),
            message="Observabilidade degradada.",
            result=result,
        )

    return emit_observability


def _duration(value: object) -> int | None:
    if isinstance(value, Mapping) and isinstance(value.get("duration_ms"), int):
        return value.get("duration_ms")
    return None


def _original_final_status(state: GraphState) -> str:
    outcome = state.get("original_outcome")
    if outcome == "success":
        return "approved"
    if outcome == "rejected":
        if state.get("failure_stage") == "receive_question":
            return "invalid_request"
        return "rejected"
    return "infrastructure_error"


def _final_status_after_observability(state: GraphState) -> str:
    if state.get("finalization_status") in {
        "persistence_failed",
        "audit_failed",
        "record_failed",
    }:
        return "infrastructure_error"
    return _original_final_status(state)


def _degraded_state(
    state: GraphState,
    *,
    code: str,
    message: str,
    result: object | None = None,
    details: dict | None = None,
) -> GraphState:
    safe_result: ObservabilityResult = (
        deepcopy(result)
        if isinstance(result, Mapping)
        else {
            "status": "degraded",
            "event_fingerprint": None,
            "diagnostic": {
                "code": code,
                "message": message,
            },
            "duration_ms": None,
        }
    )
    warning = f"{code}: observability degraded"
    error: AgentError = {
        "code": code,
        "message": message,
        "source": "run_observability",
        "stage": "emit_observability",
        "repairable": False,
        "details": details or {},
    }
    final_status = (
        "infrastructure_error"
        if state.get("finalization_status")
        in {"persistence_failed", "audit_failed", "record_failed"}
        else _original_final_status(state)
    )
    return {
        "observability_result": safe_result,
        "warnings": [*state.get("warnings", []), warning],
        "errors": (
            [*state.get("errors", []), error]
            if final_status == "infrastructure_error"
            else state.get("errors", [])
        ),
        "current_stage": "emit_observability",
        "final_status": final_status,
        "finalization_status": "observability_degraded",
        "observability_degraded": True,
    }
