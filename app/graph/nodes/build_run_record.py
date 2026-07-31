from __future__ import annotations

from copy import deepcopy

from app.domain.run_record import RunRecordError, build_run_record
from app.graph.state import AgentError, GraphState


def build_run_record_node(state: GraphState) -> GraphState:
    """
    Constroi RunRecord final a partir do estado terminal anterior.
    """

    original_outcome = state.get("original_outcome")
    original_final_status = state.get("final_status", "infrastructure_error")
    try:
        record = build_run_record(
            state,
            limits=(
                state.get("options", {}).get("run_finalization_limits", {})
                if isinstance(state.get("options"), dict)
                else {}
            ),
        )
    except RunRecordError as error:
        return _error_state(
            state,
            error.code,
            error.message,
            original_final_status=str(original_final_status),
        )
    except Exception as error:
        return _error_state(
            state,
            "RUN_RECORD_UNEXPECTED_ERROR",
            "Erro inesperado ao construir RunRecord.",
            original_final_status=str(original_final_status),
            details={"exception_type": type(error).__name__},
        )

    return {
        "original_outcome": original_outcome or record["outcome"],
        "run_record": deepcopy(record),
        "current_stage": "build_run_record",
        "finalization_status": "record_built",
        "observability_degraded": False,
    }


def _error_state(
    state: GraphState,
    code: str,
    message: str,
    *,
    original_final_status: str,
    details: dict | None = None,
) -> GraphState:
    error: AgentError = {
        "code": code,
        "message": message,
        "source": "run_record",
        "stage": "build_run_record",
        "repairable": False,
        "details": details or {},
    }
    return {
        "original_outcome": state.get("original_outcome")
        or (
            "success"
            if original_final_status == "approved"
            else (
                "rejected"
                if original_final_status in {"rejected", "invalid_request"}
                else "infrastructure_error"
            )
        ),
        "errors": [*state.get("errors", []), error],
        "current_stage": "build_run_record",
        "final_status": "infrastructure_error",
        "failure_stage": state.get("failure_stage") or "build_run_record",
        "finalization_status": "record_failed",
    }
