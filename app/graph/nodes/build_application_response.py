from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy

from app.domain.application_response import (
    ApplicationResponseBuildError,
    build_application_response,
    build_minimal_failure_response,
    default_application_response_limits,
)
from app.graph.state import GraphState


ApplicationResponseBuilder = Callable[..., dict]


def create_build_application_response_node(
    response_builder: ApplicationResponseBuilder = build_application_response,
) -> Callable[[GraphState], GraphState]:
    def build_application_response_node(state: GraphState) -> GraphState:
        if isinstance(state.get("application_response"), Mapping):
            response = build_minimal_failure_response(
                request_id=str(state.get("request_id", "")),
                run_id=str(state.get("run_id", "")),
                original_outcome=state.get("original_outcome"),
                code="APPLICATION_RESPONSE_INPUT_INVALID",
            )
            return {
                "application_response": response,
                "current_stage": "build_application_response",
                "final_status": "infrastructure_error",
                "failure_stage": state.get("failure_stage")
                or "build_application_response",
            }
        try:
            limits = (
                state.get("options", {}).get(
                    "application_response_limits",
                    default_application_response_limits(),
                )
                if isinstance(state.get("options"), Mapping)
                else default_application_response_limits()
            )
            response = response_builder(
                request_id=str(state.get("request_id", "")),
                run_id=str(state.get("run_id", "")),
                original_outcome=state.get("original_outcome"),
                finalization_status=state.get("finalization_status"),
                serialized_result=state.get("serialized_result"),
                normalized_result=state.get("normalized_result"),
                execution_result=state.get("sql_execution_result"),
                run_record=state.get("run_record"),
                persistence_result=state.get("persistence_result"),
                audit_result=state.get("audit_result"),
                observability_result=state.get("observability_result"),
                errors=state.get("errors", []),
                warnings=state.get("warnings", []),
                limits=limits,
            )
        except ApplicationResponseBuildError:
            response = build_minimal_failure_response(
                request_id=str(state.get("request_id", "")),
                run_id=str(state.get("run_id", "")),
                original_outcome=state.get("original_outcome"),
                code="APPLICATION_RESPONSE_BUILD_FAILED",
            )
        except Exception:
            response = build_minimal_failure_response(
                request_id=str(state.get("request_id", "")),
                run_id=str(state.get("run_id", "")),
                original_outcome=state.get("original_outcome"),
                code="APPLICATION_RESPONSE_BUILD_FAILED",
            )
        return {
            "application_response": deepcopy(response),
            "current_stage": "build_application_response",
        }

    return build_application_response_node
