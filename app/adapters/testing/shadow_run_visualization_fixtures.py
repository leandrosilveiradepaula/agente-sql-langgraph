from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.domain.shadow_evidence_types import (
    ShadowRunRecord,
    build_execute_shadow_record,
    build_generate_shadow_record,
)
from app.domain.result_normalization import stable_fingerprint


SYNTHETIC_QUESTION = "Synthetic question for shadow visualization tests"
SYNTHETIC_SQL = "SELECT synthetic_id FROM synthetic_schema.synthetic_table"
SYNTHETIC_REPAIR_SQL = (
    "SELECT synthetic_id FROM synthetic_schema.synthetic_table "
    "WHERE synthetic_flag = 1"
)


def generate_without_repair() -> ShadowRunRecord:
    return _generate_record(
        run_id="lg-run-generate-ok",
        status="success",
        state_overrides={
            "final_status": "approved",
        },
    )


def generate_with_repair() -> ShadowRunRecord:
    before = SYNTHETIC_SQL
    after = SYNTHETIC_REPAIR_SQL
    return _generate_record(
        run_id="lg-run-generate-repair",
        sql=after,
        status="success",
        state_overrides={
            "current_sql": after,
            "generated_sql": before,
            "repair_attempts": 1,
            "repair_history": [
                {
                    "attempt": 1,
                    "failed_stage": "engine_preflight",
                    "failure_category": "column_not_found",
                    "provider_code": "SYNTHETIC_COLUMN",
                    "error_code": None,
                    "sql_before_fingerprint": stable_fingerprint(before),
                    "sql_after_fingerprint": stable_fingerprint(after),
                    "request_fingerprint": "fp-repair-request",
                    "response_fingerprint": "fp-repair-response",
                    "repair_applied": True,
                    "reason": "sql_repair_applied",
                    "provider_name": "synthetic_repairer",
                    "duration_ms": 5,
                    "errors": [],
                    "warnings": [],
                }
            ],
            "final_status": "approved",
        },
    )


def generate_with_two_repairs() -> ShadowRunRecord:
    first = SYNTHETIC_SQL
    second = SYNTHETIC_REPAIR_SQL
    third = (
        "SELECT synthetic_id FROM synthetic_schema.synthetic_table "
        "WHERE synthetic_flag = 1 AND synthetic_status = 'active'"
    )
    return _generate_record(
        run_id="lg-run-generate-two-repairs",
        sql=third,
        status="success",
        state_overrides={
            "current_sql": third,
            "generated_sql": first,
            "repair_attempts": 2,
            "repair_history": [
                {
                    "attempt": 1,
                    "failed_stage": "engine_preflight",
                    "failure_category": "column_not_found",
                    "provider_code": "SYNTHETIC_COLUMN",
                    "error_code": None,
                    "sql_before_fingerprint": stable_fingerprint(first),
                    "sql_after_fingerprint": stable_fingerprint(second),
                    "request_fingerprint": "fp-repair-request-1",
                    "response_fingerprint": "fp-repair-response-1",
                    "repair_applied": True,
                    "reason": "sql_repair_applied",
                    "provider_name": "synthetic_repairer",
                    "duration_ms": 5,
                    "errors": [],
                    "warnings": [],
                },
                {
                    "attempt": 2,
                    "failed_stage": "engine_preflight",
                    "failure_category": "predicate_required",
                    "provider_code": "SYNTHETIC_PREDICATE",
                    "error_code": None,
                    "sql_before_fingerprint": stable_fingerprint(second),
                    "sql_after_fingerprint": stable_fingerprint(third),
                    "request_fingerprint": "fp-repair-request-2",
                    "response_fingerprint": "fp-repair-response-2",
                    "repair_applied": True,
                    "reason": "sql_repair_applied",
                    "provider_name": "synthetic_repairer",
                    "duration_ms": 7,
                    "errors": [],
                    "warnings": [],
                },
            ],
            "final_status": "approved",
        },
    )


def generate_rejected_security() -> ShadowRunRecord:
    return _generate_record(
        run_id="lg-run-generate-security",
        status="rejected",
        state_overrides={
            "security_result": {
                "status": "rejected",
                "errors": [
                    {
                        "code": "SQL_SECURITY_NON_READ_ONLY",
                        "message": "Synthetic security rejection.",
                    }
                ],
                "warnings": [],
                "duration_ms": 1,
            },
            "contract_result": {"status": "not_run", "errors": [], "warnings": []},
            "engine_preflight_result": {
                "status": "not_run",
                "errors": [],
                "warnings": [],
            },
            "errors": [
                {
                    "code": "SQL_SECURITY_NON_READ_ONLY",
                    "stage": "security_gate",
                    "message": "Synthetic security rejection.",
                }
            ],
            "current_stage": "security_gate",
            "failure_stage": "security_gate",
            "final_status": "rejected",
        },
    )


def generate_rejected_contract() -> ShadowRunRecord:
    return _generate_record(
        run_id="lg-run-generate-contract",
        status="rejected",
        state_overrides={
            "contract_result": {
                "status": "rejected",
                "errors": [
                    {
                        "code": "SQL_CONTRACT_TABLE_NOT_ALLOWED",
                        "message": "Synthetic contract rejection.",
                    }
                ],
                "warnings": [],
                "duration_ms": 1,
            },
            "engine_preflight_result": {
                "status": "not_run",
                "errors": [],
                "warnings": [],
            },
            "errors": [
                {
                    "code": "SQL_CONTRACT_TABLE_NOT_ALLOWED",
                    "stage": "contract_gate",
                    "message": "Synthetic contract rejection.",
                }
            ],
            "current_stage": "contract_gate",
            "failure_stage": "contract_gate",
            "final_status": "rejected",
        },
    )


def execute_approved_valid() -> ShadowRunRecord:
    return _execute_record(
        run_id="lg-run-execute-ok",
        status="success",
        state_overrides={"final_status": "approved"},
    )


def execute_approved_repair_reapproval() -> ShadowRunRecord:
    return _execute_record(
        run_id="lg-run-execute-repair",
        status="rejected",
        repaired_sql=SYNTHETIC_REPAIR_SQL,
        requires_reapproval=True,
        state_overrides={
            "engine_preflight_result": {
                "status": "rejected",
                "approved": False,
                "repairable": True,
                "failure_category": "column_not_found",
                "errors": [
                    {
                        "code": "ENGINE_PREFLIGHT_COLUMN_NOT_FOUND",
                        "repairable": True,
                    }
                ],
                "warnings": [],
                "executed": False,
                "rows_returned": 0,
                "duration_ms": 3,
            },
            "repair_history": [
                {
                    "attempt": 1,
                    "failed_stage": "engine_preflight",
                    "failure_category": "column_not_found",
                    "error_code": None,
                    "sql_before_fingerprint": "fp-approved-before",
                    "sql_after_fingerprint": "fp-approved-after",
                    "request_fingerprint": "fp-approved-repair-request",
                    "response_fingerprint": "fp-approved-repair-response",
                    "repair_applied": True,
                    "reason": "sql_repair_applied",
                    "provider_name": "synthetic_repairer",
                    "duration_ms": 5,
                    "errors": [],
                    "warnings": [],
                }
            ],
            "repair_attempts": 1,
            "current_stage": "repair_sql",
            "failure_stage": "engine_preflight",
            "final_status": "processing",
        },
    )


def persistence_failure() -> ShadowRunRecord:
    return _generate_record(
        run_id="lg-run-persistence-failure",
        status="infrastructure_error",
        state_overrides={
            "errors": [
                {
                    "code": "SHADOW_REPOSITORY_UNAVAILABLE",
                    "stage": "persist_shadow",
                    "message": "Synthetic persistence failure.",
                }
            ],
            "current_stage": "persist_shadow",
            "failure_stage": "persist_shadow",
            "final_status": "infrastructure_error",
        },
    )


def internal_error_sanitized() -> ShadowRunRecord:
    return _generate_record(
        run_id="lg-run-internal-error",
        status="infrastructure_error",
        state_overrides={
            "context": None,
            "context_version": None,
            "context_fingerprint": None,
            "intent": None,
            "query_plan": None,
            "generated_sql": None,
            "current_sql": None,
            "security_result": {"status": "not_run", "errors": [], "warnings": []},
            "contract_result": {"status": "not_run", "errors": [], "warnings": []},
            "engine_preflight_result": {
                "status": "not_run",
                "errors": [],
                "warnings": [],
            },
            "errors": [
                {
                    "code": "INTERNAL_GENERATE_SQL_FAILED",
                    "stage": "generate_sql",
                    "message": "Synthetic sanitized failure.",
                }
            ],
            "current_stage": "generate_sql",
            "failure_stage": "generate_sql",
            "final_status": "infrastructure_error",
        },
    )


def generate_negative_timing() -> ShadowRunRecord:
    return _generate_record(
        run_id="lg-run-generate-negative-timing",
        status="success",
        state_overrides={
            "engine_preflight_result": {
                "status": "approved",
                "approved": True,
                "repairable": False,
                "errors": [],
                "warnings": [],
                "executed": False,
                "duration_ms": -42,
                "request_fingerprint": "fp-negative-timing",
            },
        },
    )


def generate_with_secret_metadata() -> ShadowRunRecord:
    return _generate_record(
        run_id="lg-run-generate-secret-metadata",
        status="success",
        state_overrides={
            "security_result": {
                "status": "approved",
                "errors": [],
                "warnings": [],
                "executed": False,
                "duration_ms": 1,
                "sql_fingerprint": "fp-security-synthetic",
                "password": "sensitive-password-value",
                "token": "sensitive-token-value",
                "authorization": "sensitive-authorization-value",
                "cookie": "sensitive-cookie-value",
                "dsn": "sensitive-dsn-value",
                "approved_sql": "sensitive-approved-sql-value",
                "repaired_sql": "sensitive-repaired-sql-value",
                "question": "sensitive-question-value",
                "raw_response": "sensitive-raw-response-value",
            },
        },
    )


def generate_for_agent(agent_run_id: str, run_id: str) -> ShadowRunRecord:
    return _generate_record(
        agent_run_id=agent_run_id,
        run_id=run_id,
        status="success",
        state_overrides={"final_status": "approved"},
    )


def examples() -> dict[str, ShadowRunRecord]:
    return {
        "generate": generate_with_repair(),
        "execute": execute_approved_repair_reapproval(),
    }


def all_records() -> dict[str, ShadowRunRecord]:
    return {
        "generate_without_repair": generate_without_repair(),
        "generate_with_repair": generate_with_repair(),
        "generate_with_two_repairs": generate_with_two_repairs(),
        "generate_rejected_security": generate_rejected_security(),
        "generate_rejected_contract": generate_rejected_contract(),
        "execute_approved_valid": execute_approved_valid(),
        "execute_approved_repair_reapproval": execute_approved_repair_reapproval(),
        "persistence_failure": persistence_failure(),
        "internal_error_sanitized": internal_error_sanitized(),
        "generate_negative_timing": generate_negative_timing(),
        "generate_with_secret_metadata": generate_with_secret_metadata(),
    }


def _request(agent_run_id: str = "agent-run-visualization") -> dict[str, Any]:
    return {
        "contract_version": "1",
        "agent_run_id": agent_run_id,
        "question": SYNTHETIC_QUESTION,
        "principal": {"id": "synthetic-user", "profile": "tester"},
        "correlation_metadata": {"source": "shadow-run-visualization-test"},
    }


def _execute_request(
    agent_run_id: str = "agent-run-visualization",
    sql: str = SYNTHETIC_SQL,
) -> dict[str, Any]:
    return {
        "contract_version": "1",
        "agent_run_id": agent_run_id,
        "approved_sql": sql,
        "principal": {"id": "synthetic-user", "profile": "tester"},
        "correlation_metadata": {"source": "shadow-run-visualization-test"},
    }


def _base_state(
    *,
    agent_run_id: str,
    run_id: str,
    sql: str,
) -> dict[str, Any]:
    return {
        "question": SYNTHETIC_QUESTION,
        "request_id": agent_run_id,
        "run_id": run_id,
        "current_sql": sql,
        "generated_sql": sql,
        "context_version": "synthetic-context-v1",
        "context_fingerprint": "fp-context-synthetic",
        "sql_fingerprint": "fp-sql-synthetic",
        "intent": "synthetic_intent",
        "query_plan": {
            "planner_version": "synthetic-planner-v1",
            "context_version": "synthetic-context-v1",
            "context_fingerprint": "fp-context-synthetic",
            "intent_name": "synthetic_intent",
            "selected_pattern": {"pattern_name": "synthetic_pattern"},
            "planning_context": {"allowed_schemas": ["synthetic_schema"]},
        },
        "context": {
            "version": "synthetic-context-v1",
            "fingerprint": "fp-context-synthetic",
        },
        "security_result": {
            "status": "approved",
            "errors": [],
            "warnings": [],
            "executed": False,
            "duration_ms": 1,
            "sql_fingerprint": "fp-security-synthetic",
        },
        "contract_result": {
            "status": "approved",
            "errors": [],
            "warnings": [],
            "executed": False,
            "duration_ms": 1,
            "sql_fingerprint": "fp-contract-synthetic",
        },
        "engine_preflight_result": {
            "status": "approved",
            "approved": True,
            "repairable": False,
            "failure_category": "none",
            "errors": [],
            "warnings": [],
            "executed": False,
            "rows_returned": 0,
            "duration_ms": 3,
            "request_fingerprint": "fp-preflight-synthetic",
        },
        "repair_history": [],
        "repair_attempts": 0,
        "options": {"shadow_mode": True},
        "warnings": [],
        "errors": [],
        "current_stage": "engine_preflight",
        "failure_stage": "",
        "final_status": "approved",
    }


def _generate_record(
    *,
    run_id: str,
    status: str,
    sql: str = SYNTHETIC_SQL,
    agent_run_id: str = "agent-run-visualization",
    state_overrides: dict[str, Any] | None = None,
) -> ShadowRunRecord:
    state = _base_state(agent_run_id=agent_run_id, run_id=run_id, sql=sql)
    state.update(deepcopy(state_overrides or {}))
    response = {
        "agent_run_id": agent_run_id,
        "run_id": run_id,
        "status": status,
        "sql": sql if status == "success" else None,
        "intent": state.get("intent"),
        "gates": {
            "security": {"status": state["security_result"]["status"]},
            "contract": {"status": state["contract_result"]["status"]},
        },
        "preflight": {"status": state["engine_preflight_result"]["status"]},
        "repair_attempts": state.get("repair_attempts", 0),
        "errors": state.get("errors", []),
        "metadata": {
            "current_stage": state.get("current_stage", ""),
            "failure_stage": state.get("failure_stage", ""),
        },
    }
    return build_generate_shadow_record(
        shadow_record_id=f"shadow-{run_id}",
        agent_run_id=agent_run_id,
        run_id=run_id,
        created_at="2026-08-10T00:00:00+00:00",
        completed_at="2026-08-10T00:00:01+00:00",
        status=status,
        request=_request(agent_run_id),
        state=state,
        response=response,
        langgraph_version="synthetic-version",
        langgraph_commit="synthetic-commit",
    )


def _execute_record(
    *,
    run_id: str,
    status: str,
    approved_sql: str = SYNTHETIC_SQL,
    repaired_sql: str | None = None,
    requires_reapproval: bool = False,
    state_overrides: dict[str, Any] | None = None,
) -> ShadowRunRecord:
    agent_run_id = "agent-run-visualization"
    state = _base_state(
        agent_run_id=agent_run_id,
        run_id=run_id,
        sql=repaired_sql or approved_sql,
    )
    state.update(
        {
            "question": "",
            "normalized_question": "",
            "intent": "execute_approved_sql_shadow",
            "current_sql": repaired_sql or approved_sql,
            "generated_sql": approved_sql,
            "current_stage": "engine_preflight",
            "failure_stage": "",
            "final_status": "approved" if status == "success" else "rejected",
        }
    )
    state.update(deepcopy(state_overrides or {}))
    response = {
        "agent_run_id": agent_run_id,
        "run_id": run_id,
        "status": status,
        "approved_sql_original": approved_sql,
        "validation": {
            "security": {"status": state["security_result"]["status"]},
            "contract": {"status": state["contract_result"]["status"]},
            "preflight": {"status": state["engine_preflight_result"]["status"]},
        },
        "repaired_sql_proposal": repaired_sql,
        "requires_reapproval": requires_reapproval,
        "errors": state.get("errors", []),
        "metadata": {
            "current_stage": state.get("current_stage", ""),
            "failure_stage": state.get("failure_stage", ""),
        },
    }
    return build_execute_shadow_record(
        shadow_record_id=f"shadow-{run_id}",
        agent_run_id=agent_run_id,
        run_id=run_id,
        created_at="2026-08-10T00:00:02+00:00",
        completed_at="2026-08-10T00:00:03+00:00",
        status=status,
        request=_execute_request(agent_run_id, approved_sql),
        state=state,
        response=response,
        langgraph_version="synthetic-version",
        langgraph_commit="synthetic-commit",
    )
