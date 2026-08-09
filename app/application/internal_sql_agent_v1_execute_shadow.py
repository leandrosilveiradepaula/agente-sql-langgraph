from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any, cast

from app.application.internal_sql_agent_v1_shared import (
    IdGenerator,
    error,
    metadata,
    new_run_id,
    not_run_result,
    now_utc_iso,
    persist_shadow_record,
    preflight_approved,
    preflight_repairable,
    principal_to_user,
    shadow_record_id,
    state_errors,
    status_from_final_status,
    string_field,
    summary,
    validate_common_request,
    with_response_fingerprints,
    _valid_question,
)
from app.application.internal_sql_agent_v1_types import (
    INTERNAL_SQL_AGENT_CONTRACT_VERSION,
    ExecuteApprovedSqlShadowV1Request,
    ExecuteApprovedSqlShadowV1Response,
    InternalSqlAgentError,
)
from app.domain.result_normalization import stable_fingerprint
from app.domain.shadow_evidence_types import build_execute_shadow_record
from app.domain.sql_analysis import SqlAnalysisError, analyze_sql
from app.graph.nodes.contract_gate import contract_gate
from app.graph.nodes.engine_preflight import create_engine_preflight_node
from app.graph.nodes.repair_sql import create_repair_sql_node
from app.graph.nodes.security_gate import security_gate
from app.graph.state import GraphState
from app.ports.engine_preflight import EnginePreflight
from app.ports.shadow_evidence_repository import ShadowEvidenceRepository
from app.ports.sql_repairer import SqlRepairer


class ExecuteApprovedSqlShadowUseCase:
    def __init__(
        self,
        *,
        engine_preflight: EnginePreflight,
        sql_repairer: SqlRepairer,
        id_generator: IdGenerator,
        shadow_repository: ShadowEvidenceRepository | None = None,
        langgraph_version: str | None = None,
        langgraph_commit: str | None = None,
    ) -> None:
        if engine_preflight is None:
            raise RuntimeError("engine_preflight deve ser injetado.")
        if sql_repairer is None:
            raise RuntimeError("sql_repairer deve ser injetado.")
        if id_generator is None or not callable(id_generator):
            raise RuntimeError("id_generator deve ser injetado.")
        self._id_generator = id_generator
        self._shadow_repository = shadow_repository
        self._langgraph_version = langgraph_version
        self._langgraph_commit = langgraph_commit
        self._security_gate = security_gate
        self._contract_gate = contract_gate
        self._engine_preflight = create_engine_preflight_node(engine_preflight)
        self._repair_sql = create_repair_sql_node(sql_repairer)

    def execute(
        self,
        request: ExecuteApprovedSqlShadowV1Request,
    ) -> ExecuteApprovedSqlShadowV1Response:
        validation = validate_execute_shadow_request(request)
        agent_run_id = string_field(request, "agent_run_id")
        run_id = new_run_id(self._id_generator)
        created_at = now_utc_iso()
        approved_sql = (
            str(request.get("approved_sql", ""))
            if isinstance(request, Mapping)
            else ""
        )
        if validation:
            response = execute_response(
                agent_run_id=agent_run_id,
                run_id=run_id,
                status="rejected",
                message="Execute approved SQL shadow request rejected.",
                approved_sql_original=approved_sql if approved_sql else None,
                state={},
                repaired_sql_proposal=None,
                requires_reapproval=False,
                errors=validation,
            )
            self._persist_shadow(
                request if isinstance(request, Mapping) else {},
                {},
                response,
                created_at,
            )
            return response
        try:
            query_plan = _build_synthetic_query_plan_from_approved_sql(approved_sql)
            state: GraphState = {
                "request_id": agent_run_id,
                "run_id": run_id,
                "question": "",
                "normalized_question": "",
                "user": principal_to_user(request.get("principal", {})),
                "options": {
                    "use_cache": False,
                    "max_repair_attempts": 1,
                    "shadow_mode": True,
                },
                "current_sql": approved_sql,
                "generated_sql": approved_sql,
                "query_plan": query_plan,
                "repair_attempts": 0,
                "max_repair_attempts": 1,
                "repair_history": [],
                "security_result": not_run_result(),
                "contract_result": not_run_result(),
                "engine_preflight_result": not_run_result(),
                "errors": [],
                "warnings": [],
                "current_stage": "execute_approved_sql_shadow",
                "final_status": "processing",
                "failure_stage": "",
            }
            state = self._apply(state, self._security_gate)
            if state.get("final_status") == "processing":
                state = self._apply(state, self._contract_gate)
            if state.get("final_status") == "processing":
                state = self._apply(state, self._engine_preflight)
            if preflight_approved(state):
                state["final_status"] = "approved"
                response = execute_response(
                    agent_run_id=agent_run_id,
                    run_id=run_id,
                    status="success",
                    message="Approved SQL validated in offline shadow.",
                    approved_sql_original=approved_sql,
                    state=state,
                    repaired_sql_proposal=None,
                    requires_reapproval=False,
                    errors=[],
                )
                self._persist_shadow(request, state, response, created_at)
                return response
            if preflight_repairable(state):
                repaired = self._apply(state, self._repair_sql)
                proposal = (
                    str(repaired.get("current_sql", ""))
                    if repaired.get("final_status") == "processing"
                    else None
                )
                proposal = (
                    proposal
                    if proposal and proposal.strip() != approved_sql.strip()
                    else None
                )
                response = execute_response(
                    agent_run_id=agent_run_id,
                    run_id=run_id,
                    status="rejected",
                    message=(
                        "Repair proposal requires new human approval."
                        if proposal
                        else "Approved SQL shadow validation rejected."
                    ),
                    approved_sql_original=approved_sql,
                    state=repaired,
                    repaired_sql_proposal=proposal,
                    requires_reapproval=proposal is not None,
                    errors=state_errors(repaired),
                )
                self._persist_shadow(request, repaired, response, created_at)
                return response
            response = execute_response(
                agent_run_id=agent_run_id,
                run_id=run_id,
                status=status_from_final_status(state.get("final_status")),
                message=(
                    "Approved SQL shadow validation rejected."
                    if state.get("final_status") == "rejected"
                    else "Approved SQL shadow could not be completed."
                ),
                approved_sql_original=approved_sql,
                state=state,
                repaired_sql_proposal=None,
                requires_reapproval=False,
                errors=state_errors(state),
            )
            self._persist_shadow(request, state, response, created_at)
            return response
        except Exception:
            response = execute_response(
                agent_run_id=agent_run_id,
                run_id=run_id,
                status="infrastructure_error",
                message="Approved SQL shadow could not be completed.",
                approved_sql_original=approved_sql,
                state={},
                repaired_sql_proposal=None,
                requires_reapproval=False,
                errors=[
                    error(
                        "INTERNAL_EXECUTE_APPROVED_SHADOW_FAILED",
                        "execute_approved_sql_shadow",
                        "Approved SQL shadow could not be completed.",
                        retryable=True,
                    )
                ],
            )
            self._persist_shadow(
                request if isinstance(request, Mapping) else {},
                {},
                response,
                created_at,
            )
            return response

    def _persist_shadow(
        self,
        request: Mapping[str, Any],
        state: Mapping[str, Any],
        response: Mapping[str, Any],
        created_at: str,
    ) -> None:
        record = build_execute_shadow_record(
            shadow_record_id=shadow_record_id(
                agent_run_id=str(response.get("agent_run_id", "")),
                run_id=str(response.get("run_id", "")),
                event_type="execute_approved_shadow",
            ),
            agent_run_id=str(response.get("agent_run_id", "")),
            run_id=str(response.get("run_id", "")),
            created_at=created_at,
            completed_at=now_utc_iso(),
            status=str(response.get("status", "infrastructure_error")),
            request=request,
            state=state,
            response=response,
            langgraph_version=self._langgraph_version,
            langgraph_commit=self._langgraph_commit,
        )
        persist_shadow_record(self._shadow_repository, record)

    @staticmethod
    def _apply(state: GraphState, node: Callable[[GraphState], GraphState]) -> GraphState:
        patch = node(deepcopy(state))
        merged = deepcopy(state)
        merged.update(deepcopy(patch))
        return merged


def validate_execute_shadow_request(
    request: object,
) -> list[InternalSqlAgentError]:
    errors = validate_common_request(request)
    if not isinstance(request, Mapping):
        return errors
    if not _valid_question(request.get("approved_sql")):
        errors.append(
            error(
                "INTERNAL_APPROVED_SQL_REQUIRED",
                "request",
                "Approved SQL is required.",
            )
        )
    for key in request:
        if key not in {
            "contract_version",
            "agent_run_id",
            "approved_sql",
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


def _build_synthetic_query_plan_from_approved_sql(sql: str) -> dict[str, Any]:
    """
    Technical adapter for current gates only.

    The plan is derived from approved SQL, is not the original generation plan,
    and must not be treated as independent semantic equivalence evidence.
    """
    try:
        analysis = analyze_sql(sql)
    except SqlAnalysisError as error:
        raise ValueError("Approved SQL cannot be analyzed.") from error
    tables = _tables_from_analysis(analysis)
    columns = _columns_from_analysis(analysis, tables)
    selected_pattern = {
        "intent_name": "execute_approved_sql_shadow",
        "pattern_name": "approved_sql_shadow",
        "priority": 1.0,
        "required_tables": tables,
        "required_rules": [],
        "business_question_examples": [],
        "sql_pattern": "",
        "notes": None,
    }
    required_tables = [
        {
            "schema_name": table.split(".", 1)[0] if "." in table else "",
            "table_name": table.split(".")[-1],
            "qualified_name": table,
            "table_type": "table",
            "description": None,
            "grain": None,
            "primary_key": [],
            "key_columns": [],
            "metric_columns": [],
            "date_columns": [],
            "join_rules": [],
            "ai_hint": None,
            "priority": 1,
        }
        for table in tables
    ]
    planning_context = {
        "context_version": "internal-http-v1-shadow",
        "context_fingerprint": stable_fingerprint(
            {"source": "approved_sql_shadow", "tables": tables}
        ),
        "intent_name": "execute_approved_sql_shadow",
        "normalized_question": "",
        "selected_pattern": selected_pattern,
        "rules": [],
        "required_tables": required_tables,
        "relevant_columns": {
            table: [{"name": column} for column in columns]
            for table in tables
        },
        "authorized_joins": [],
        "relevant_entities": [],
        "relevant_dre_mappings": [],
        "allowed_schemas": sorted(
            {
                table.split(".", 1)[0]
                for table in tables
                if "." in table
            }
        ),
        "component_configs": {},
        "diagnostics": {
            "missing_required_rules": [],
            "missing_required_tables": [],
            "ambiguous_required_tables": [],
            "join_diagnostics": [],
            "dre_diagnostic": {},
        },
    }
    return {
        "planner_version": "v1.0.0-internal-approved-sql-shadow-plan",
        "context_version": planning_context["context_version"],
        "context_fingerprint": planning_context["context_fingerprint"],
        "intent_name": "execute_approved_sql_shadow",
        "intent_confidence": None,
        "normalized_question": "",
        "selected_pattern": selected_pattern,
        "planning_context": planning_context,
        "selection_diagnostic": {
            "selected_pattern": selected_pattern,
            "candidates": [],
            "decision_reason": "single_pattern_selected",
            "tie_detected": False,
            "fallback_used": None,
            "planner_version": "v1.0.0-internal-approved-sql-shadow-plan",
        },
        "sql_pattern_metadata": "internal-approved-sql-shadow",
    }


def _tables_from_analysis(analysis: Mapping[str, Any]) -> list[str]:
    output: list[str] = []
    for item in analysis.get("object_references", []):
        if not isinstance(item, Mapping):
            continue
        if item.get("is_cte") or item.get("is_function"):
            continue
        table = str(item.get("table", "")).strip().casefold()
        schema = item.get("schema")
        if not table:
            continue
        qualified = (
            f"{str(schema).strip().casefold()}.{table}"
            if isinstance(schema, str) and schema.strip()
            else table
        )
        if qualified not in output:
            output.append(qualified)
    if not output:
        raise ValueError("Approved SQL must reference at least one table.")
    return output


def _columns_from_analysis(
    analysis: Mapping[str, Any],
    tables: list[str],
) -> list[str]:
    del tables
    columns: set[str] = set()
    for item in analysis.get("column_references", []):
        if not isinstance(item, Mapping):
            continue
        if item.get("is_wildcard"):
            continue
        column = str(item.get("column", "")).strip().casefold()
        if column:
            columns.add(column)
    return sorted(columns)


def execute_response(
    *,
    agent_run_id: str,
    run_id: str,
    status: str,
    message: str,
    approved_sql_original: str | None,
    state: Mapping[str, Any],
    repaired_sql_proposal: str | None,
    requires_reapproval: bool,
    errors: list[InternalSqlAgentError],
) -> ExecuteApprovedSqlShadowV1Response:
    response: ExecuteApprovedSqlShadowV1Response = {
        "contract_version": INTERNAL_SQL_AGENT_CONTRACT_VERSION,
        "response_id": "",
        "agent_run_id": agent_run_id,
        "run_id": run_id,
        "status": cast(Any, status),
        "message": message,
        "approved_sql_original": approved_sql_original,
        "validation": {
            "security": summary(state.get("security_result")),
            "contract": summary(state.get("contract_result")),
            "preflight": summary(state.get("engine_preflight_result")),
        },
        "repaired_sql_proposal": repaired_sql_proposal,
        "requires_reapproval": bool(requires_reapproval),
        "errors": deepcopy(errors),
        "metadata": metadata(state),
        "response_fingerprint": "",
    }
    return with_response_fingerprints(response)
