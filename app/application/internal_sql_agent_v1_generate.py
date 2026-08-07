from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any, cast

from app.application.internal_sql_agent_v1_shared import (
    IdGenerator,
    error,
    metadata,
    new_run_id,
    preflight_approved,
    preflight_repairable,
    principal_to_user,
    state_errors,
    status_from_final_status,
    string_field,
    summary,
    validate_common_request,
    with_response_fingerprints,
    _safe_int,
    _valid_question,
)
from app.application.internal_sql_agent_v1_types import (
    INTERNAL_SQL_AGENT_CONTRACT_VERSION,
    GenerateSqlV1Request,
    GenerateSqlV1Response,
    InternalSqlAgentError,
)
from app.graph.nodes.build_plan import build_plan
from app.graph.nodes.classify_intent import classify_intent
from app.graph.nodes.contract_gate import contract_gate
from app.graph.nodes.engine_preflight import create_engine_preflight_node
from app.graph.nodes.generate_sql import create_generate_sql_node
from app.graph.nodes.load_context import create_load_context_node
from app.graph.nodes.receive_question import receive_question
from app.graph.nodes.repair_sql import create_repair_sql_node
from app.graph.nodes.security_gate import security_gate
from app.graph.state import GraphState
from app.ports.context_repository import ContextRepository
from app.ports.engine_preflight import EnginePreflight
from app.ports.sql_generator import SqlGenerator
from app.ports.sql_repairer import SqlRepairer

class GenerateSqlUseCase:
    def __init__(
        self,
        *,
        context_repository: ContextRepository,
        sql_generator: SqlGenerator,
        engine_preflight: EnginePreflight,
        sql_repairer: SqlRepairer,
        id_generator: IdGenerator,
    ) -> None:
        if context_repository is None:
            raise RuntimeError("context_repository deve ser injetado.")
        if sql_generator is None:
            raise RuntimeError("sql_generator deve ser injetado.")
        if engine_preflight is None:
            raise RuntimeError("engine_preflight deve ser injetado.")
        if sql_repairer is None:
            raise RuntimeError("sql_repairer deve ser injetado.")
        if id_generator is None or not callable(id_generator):
            raise RuntimeError("id_generator deve ser injetado.")
        self._id_generator = id_generator
        self._receive_question = receive_question
        self._load_context = create_load_context_node(context_repository)
        self._classify_intent = classify_intent
        self._build_plan = build_plan
        self._generate_sql = create_generate_sql_node(sql_generator)
        self._security_gate = security_gate
        self._contract_gate = contract_gate
        self._engine_preflight = create_engine_preflight_node(engine_preflight)
        self._repair_sql = create_repair_sql_node(sql_repairer)

    def execute(self, request: GenerateSqlV1Request) -> GenerateSqlV1Response:
        validation = validate_generate_request(request)
        agent_run_id = string_field(request, "agent_run_id")
        run_id = new_run_id(self._id_generator)
        if validation:
            return generate_response(
                agent_run_id=agent_run_id,
                run_id=run_id,
                status="rejected",
                message="Generate SQL request rejected.",
                state={},
                errors=validation,
            )

        state: GraphState = {
            "question": str(request["question"]),
            "request_id": agent_run_id,
            "run_id": run_id,
            "user": principal_to_user(request.get("principal", {})),
            "options": {
                "use_cache": False,
                "max_repair_attempts": 2,
                "shadow_mode": True,
            },
        }
        try:
            state = self._apply(state, self._receive_question)
            if state.get("final_status") != "processing":
                return self._generate_terminal(agent_run_id, run_id, state)
            for node in (
                self._load_context,
                self._classify_intent,
                self._build_plan,
                self._generate_sql,
            ):
                state = self._apply(state, node)
                if state.get("final_status") != "processing":
                    return self._generate_terminal(agent_run_id, run_id, state)
            state = self._run_gate_preflight_repair_loop(state)
            return self._generate_terminal(agent_run_id, run_id, state)
        except Exception:
            return generate_response(
                agent_run_id=agent_run_id,
                run_id=run_id,
                status="infrastructure_error",
                message="Generate SQL could not be completed.",
                state=state,
                errors=[
                    error(
                        "INTERNAL_GENERATE_SQL_FAILED",
                        "generate_sql",
                        "Generate SQL could not be completed.",
                        retryable=True,
                    )
                ],
            )

    def _run_gate_preflight_repair_loop(
        self,
        state: GraphState,
    ) -> GraphState:
        current = deepcopy(state)
        while True:
            for node in (
                self._security_gate,
                self._contract_gate,
                self._engine_preflight,
            ):
                current = self._apply(current, node)
                if current.get("final_status") != "processing":
                    break
            if preflight_approved(current):
                current["final_status"] = "approved"
                current["current_stage"] = "engine_preflight"
                current["failure_stage"] = ""
                return current
            if preflight_repairable(current):
                repaired = self._apply(current, self._repair_sql)
                if repaired.get("final_status") == "processing":
                    current = repaired
                    continue
                return repaired
            return current

    def _generate_terminal(
        self,
        agent_run_id: str,
        run_id: str,
        state: GraphState,
    ) -> GenerateSqlV1Response:
        final_status = state.get("final_status")
        status = status_from_final_status(final_status)
        message = (
            "SQL generated for review."
            if status == "success"
            else (
                "Generate SQL request rejected."
                if status == "rejected"
                else "Generate SQL could not be completed."
            )
        )
        return generate_response(
            agent_run_id=agent_run_id,
            run_id=run_id,
            status=status,
            message=message,
            state=state,
            errors=state_errors(state),
        )

    @staticmethod
    def _apply(state: GraphState, node: Callable[[GraphState], GraphState]) -> GraphState:
        patch = node(deepcopy(state))
        merged = deepcopy(state)
        merged.update(deepcopy(patch))
        return merged

def validate_generate_request(request: object) -> list[InternalSqlAgentError]:
    errors = validate_common_request(request)
    if not isinstance(request, Mapping):
        return errors
    if not _valid_question(request.get("question")):
        errors.append(
            error(
                "INTERNAL_GENERATE_QUESTION_REQUIRED",
                "request",
                "Question is required.",
            )
        )
    for key in request:
        if key not in {
            "contract_version",
            "agent_run_id",
            "question",
            "principal",
            "correlation_metadata",
        }:
            errors.append(
                error(
                    "INTERNAL_REQUEST_FIELD_FORBIDDEN",
                    "request",
                    "Request field is not allowed.",
                )
            )
    return errors

def generate_response(
    *,
    agent_run_id: str,
    run_id: str,
    status: str,
    message: str,
    state: Mapping[str, Any],
    errors: list[InternalSqlAgentError],
) -> GenerateSqlV1Response:
    response: GenerateSqlV1Response = {
        "contract_version": INTERNAL_SQL_AGENT_CONTRACT_VERSION,
        "response_id": "",
        "agent_run_id": agent_run_id,
        "run_id": run_id,
        "status": cast(Any, status),
        "message": message,
        "sql": state.get("current_sql")
        if status == "success" and isinstance(state.get("current_sql"), str)
        else None,
        "intent": (
            state.get("intent") if isinstance(state.get("intent"), str) else None
        ),
        "plan_status": "planned" if isinstance(state.get("query_plan"), Mapping) else None,
        "gates": {
            "security": summary(state.get("security_result")),
            "contract": summary(state.get("contract_result")),
        },
        "preflight": summary(state.get("engine_preflight_result")),
        "repair_attempts": _safe_int(state.get("repair_attempts")),
        "errors": deepcopy(errors),
        "metadata": metadata(state),
        "response_fingerprint": "",
    }
    return with_response_fingerprints(response)
