from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import cast

from app.domain.run_audit_types import AuditResult
from app.domain.run_record import (
    build_audit_event,
)
from app.domain.run_record_types import RunRecord
from app.graph.state import AgentError, GraphState
from app.ports.audit_sink import AuditSink


def create_record_audit_node(
    audit_sink: AuditSink,
) -> Callable[[GraphState], GraphState]:
    def record_audit(state: GraphState) -> GraphState:
        previous = state.get("audit_result")
        if _audit_ok(previous):
            return {
                "current_stage": "record_audit",
                "finalization_status": "audited",
            }
        if isinstance(previous, Mapping):
            return _error_state(
                state,
                code="AUDIT_REQUEST_INVALID",
                message=(
                    "Resultado de auditoria anterior bloqueia nova "
                    "tentativa."
                ),
                category="request_invalid",
                result=previous,
            )
        record = state.get("run_record")
        persistence_result = state.get("persistence_result")
        if not isinstance(record, Mapping) or not _persistence_ok(
            persistence_result
        ):
            return _error_state(
                state,
                code="AUDIT_REQUEST_INVALID",
                message="Auditoria exige RunRecord e persistencia aprovada.",
                category="request_invalid",
            )
        try:
            event = build_audit_event(
                cast(RunRecord, record),
                persistence_record_id=str(
                    persistence_result.get("record_id", "")
                ),
                limits=(
                    state.get("options", {}).get("run_finalization_limits", {})
                    if isinstance(state.get("options"), dict)
                    else {}
                ),
                actor_profile=str(
                    (
                        state.get("user", {})
                        if isinstance(state.get("user"), Mapping)
                        else {}
                    ).get("profile", "")
                ),
            )
            result = audit_sink.write(deepcopy(event))
        except TimeoutError:
            return _error_state(
                state,
                code="AUDIT_TIMEOUT",
                message="Auditoria excedeu o timeout.",
                category="timeout",
            )
        except PermissionError:
            return _error_state(
                state,
                code="AUDIT_AUTHENTICATION_FAILED",
                message="Auditoria falhou por autenticacao.",
                category="authentication_failed",
            )
        except Exception as error:
            return _error_state(
                state,
                code="AUDIT_UNEXPECTED_ERROR",
                message="Erro inesperado na auditoria.",
                category="unexpected_error",
                details={"exception_type": type(error).__name__},
            )
        validation_error = _validate_result(result, event)
        if validation_error:
            return _error_state(
                state,
                code=validation_error,
                message="Resultado de auditoria invalido.",
                category=(
                    "fingerprint_mismatch"
                    if validation_error == "AUDIT_FINGERPRINT_MISMATCH"
                    else "request_invalid"
                ),
                result=result,
            )
        if result["status"] in {"written", "already_written"}:
            return {
                "audit_result": deepcopy(result),
                "current_stage": "record_audit",
                "finalization_status": "audited",
            }
        return _error_state(
            state,
            code=(
                "AUDIT_CONFLICT"
                if result["failure_category"] == "conflict"
                else (
                    result.get("diagnostic", {}) or {}
                ).get("code", "AUDIT_UNEXPECTED_ERROR")
            ),
            message="Auditoria rejeitada.",
            category=result["failure_category"],
            result=result,
        )

    return record_audit


def _persistence_ok(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("status") in {"persisted", "already_persisted"}
        and isinstance(value.get("record_id"), str)
    )


def _audit_ok(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("status") in {"written", "already_written"}
    )


def _validate_result(result: object, event: Mapping[str, object]) -> str | None:
    if not isinstance(result, Mapping):
        return "AUDIT_REQUEST_INVALID"
    if result.get("status") not in {
        "written",
        "already_written",
        "rejected",
        "error",
    }:
        return "AUDIT_REQUEST_INVALID"
    if result.get("status") in {"written", "already_written"}:
        if result.get("failure_category") != "none":
            return "AUDIT_REQUEST_INVALID"
        if result.get("diagnostic") is not None:
            return "AUDIT_REQUEST_INVALID"
        if result.get("event_fingerprint") != event.get("fingerprint"):
            return "AUDIT_FINGERPRINT_MISMATCH"
    if result.get("status") in {"rejected", "error"}:
        if result.get("event_id") is not None:
            return "AUDIT_REQUEST_INVALID"
    return None


def _error_state(
    state: GraphState,
    *,
    code: str,
    message: str,
    category: str,
    result: object | None = None,
    details: dict | None = None,
) -> GraphState:
    safe_result: AuditResult = (
        {
            **deepcopy(result),
            "failure_category": category,
        }
        if isinstance(result, Mapping)
        else {
            "status": "error",
            "event_id": None,
            "event_fingerprint": None,
            "idempotency_key": "",
            "failure_category": category,
            "diagnostic": {
                "code": code,
                "message": message,
                "failure_category": category,
            },
            "duration_ms": None,
        }
    )
    error: AgentError = {
        "code": code,
        "message": message,
        "source": "run_audit",
        "stage": "record_audit",
        "repairable": False,
        "details": {
            "failure_category": category,
            **(details or {}),
        },
    }
    return {
        "audit_result": safe_result,
        "errors": [*state.get("errors", []), error],
        "current_stage": "record_audit",
        "final_status": "infrastructure_error",
        "failure_stage": state.get("failure_stage") or "record_audit",
        "finalization_status": "audit_failed",
    }
