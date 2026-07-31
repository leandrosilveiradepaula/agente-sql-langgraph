from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import cast

from app.domain.run_persistence_types import PersistRunResult
from app.domain.run_record import RunRecordError, build_persist_run_request
from app.domain.run_record_types import RunRecord
from app.graph.state import AgentError, GraphState
from app.ports.run_repository import RunRepository


def create_persist_run_node(
    run_repository: RunRepository,
) -> Callable[[GraphState], GraphState]:
    def persist_run(state: GraphState) -> GraphState:
        previous = state.get("persistence_result")
        if _persistence_ok(previous):
            return {
                "current_stage": "persist_run",
                "finalization_status": "persisted",
            }
        if isinstance(previous, Mapping):
            return _error_state(
                state,
                code="PERSIST_RUN_REQUEST_INVALID",
                message=(
                    "Resultado de persistencia anterior bloqueia nova "
                    "tentativa."
                ),
                category="request_invalid",
                result=previous,
            )
        record = state.get("run_record")
        if not isinstance(record, Mapping):
            return _error_state(
                state,
                code="PERSIST_RUN_REQUEST_INVALID",
                message="RunRecord ausente para persistencia.",
                category="request_invalid",
            )
        try:
            request = build_persist_run_request(cast(RunRecord, record))
            result = run_repository.save(deepcopy(request))
        except TimeoutError:
            return _error_state(
                state,
                code="PERSIST_RUN_TIMEOUT",
                message="Persistencia excedeu o timeout.",
                category="timeout",
            )
        except PermissionError:
            return _error_state(
                state,
                code="PERSIST_RUN_AUTHENTICATION_FAILED",
                message="Persistencia falhou por autenticacao.",
                category="authentication_failed",
            )
        except RunRecordError as error:
            return _error_state(
                state,
                code=error.code,
                message=error.message,
                category="request_invalid",
            )
        except Exception as error:
            return _error_state(
                state,
                code="PERSIST_RUN_UNEXPECTED_ERROR",
                message="Erro inesperado na persistencia.",
                category="unexpected_error",
                details={"exception_type": type(error).__name__},
            )

        validation_error = _validate_result(result, record)
        if validation_error:
            return _error_state(
                state,
                code=validation_error,
                message="Resultado de persistencia invalido.",
                category=(
                    "fingerprint_mismatch"
                    if validation_error
                    == "PERSIST_RUN_FINGERPRINT_MISMATCH"
                    else "request_invalid"
                ),
                result=result,
            )
        if result["status"] in {"persisted", "already_persisted"}:
            return {
                "persistence_result": deepcopy(result),
                "current_stage": "persist_run",
                "finalization_status": "persisted",
            }
        return _error_state(
            state,
            code=(
                "PERSIST_RUN_CONFLICT"
                if result["failure_category"] == "conflict"
                else (
                    result.get("diagnostic", {}) or {}
                ).get("code", "PERSIST_RUN_UNEXPECTED_ERROR")
            ),
            message="Persistencia rejeitada ou indisponivel.",
            category=result["failure_category"],
            result=result,
        )

    return persist_run


def _persistence_ok(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("status") in {"persisted", "already_persisted"}
        and isinstance(value.get("record_id"), str)
    )


def _validate_result(
    result: object,
    record: Mapping[str, object],
) -> str | None:
    if not isinstance(result, Mapping):
        return "PERSIST_RUN_REQUEST_INVALID"
    if result.get("status") not in {
        "persisted",
        "already_persisted",
        "rejected",
        "error",
    }:
        return "PERSIST_RUN_REQUEST_INVALID"
    if result.get("idempotency_key") is None:
        return "PERSIST_RUN_REQUEST_INVALID"
    if result.get("status") in {"persisted", "already_persisted"}:
        if result.get("failure_category") != "none":
            return "PERSIST_RUN_REQUEST_INVALID"
        if result.get("diagnostic") is not None:
            return "PERSIST_RUN_REQUEST_INVALID"
        if result.get("persisted_fingerprint") != record.get("fingerprint"):
            return "PERSIST_RUN_FINGERPRINT_MISMATCH"
        if not isinstance(result.get("record_id"), str):
            return "PERSIST_RUN_REQUEST_INVALID"
    if result.get("status") in {"rejected", "error"}:
        if result.get("record_id") is not None:
            return "PERSIST_RUN_REQUEST_INVALID"
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
    safe_result: PersistRunResult = (
        {
            **deepcopy(result),
            "failure_category": category,
        }
        if isinstance(result, Mapping)
        else {
            "status": "error",
            "record_id": None,
            "persisted_fingerprint": None,
            "idempotency_key": "",
            "failure_category": category,
            "diagnostic": {
                "code": code,
                "message": message,
                "failure_category": category,
                "safe_details": {},
            },
            "duration_ms": None,
        }
    )
    error: AgentError = {
        "code": code,
        "message": message,
        "source": "run_persistence",
        "stage": "persist_run",
        "repairable": False,
        "details": {
            "failure_category": category,
            **(details or {}),
        },
    }
    return {
        "persistence_result": safe_result,
        "errors": [*state.get("errors", []), error],
        "current_stage": "persist_run",
        "final_status": "infrastructure_error",
        "failure_stage": state.get("failure_stage") or "persist_run",
        "finalization_status": "persistence_failed",
    }
