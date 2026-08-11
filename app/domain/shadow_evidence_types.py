from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Literal, TypedDict, cast

from app.domain.result_normalization import canonical_json, stable_fingerprint


SHADOW_EVIDENCE_CONTRACT_VERSION = "v1.0.0-shadow-evidence"

ShadowEventType = Literal["generate", "execute_approved_shadow"]
ShadowStatus = Literal["started", "success", "rejected", "infrastructure_error"]
ShadowRepositoryStatus = Literal[
    "created",
    "updated",
    "finalized",
    "already_exists",
    "not_found",
    "rejected",
    "error",
]
ShadowRepositoryReadStatus = Literal["ok", "not_found", "unavailable"]


class ShadowRepositoryDiagnostic(TypedDict, total=False):
    code: str
    message: str
    failure_category: str
    safe_details: dict[str, str | int | bool | None]


class ShadowFingerprints(TypedDict, total=False):
    question: str
    n8n_sql: str
    langgraph_sql: str
    approved_sql: str
    repaired_sql_proposal: str
    evidence_payload: str
    response_result: str


class ShadowN8nBaseline(TypedDict, total=False):
    sql: str | None
    status: str | None
    error: str | None
    timing_ms: int | None
    workflow_version: str | None
    output: dict[str, Any] | list[Any] | None
    fingerprints: dict[str, str]


class ShadowExecutionFuture(TypedDict, total=False):
    status: str | None
    row_count: int | None
    fingerprints: dict[str, str]
    divergence: dict[str, Any]
    costs: dict[str, Any]
    latency_ms: int | None
    metrics: dict[str, Any]


class ShadowRunRecord(TypedDict, total=False):
    shadow_record_id: str
    agent_run_id: str
    run_id: str
    event_type: ShadowEventType
    contract_version: str
    status: ShadowStatus
    created_at: str
    completed_at: str | None
    question: str | None
    approved_sql_original: str | None
    generated_sql: str | None
    repaired_sql_proposal: str | None
    requires_reapproval: bool
    principal: dict[str, Any]
    correlation_metadata: dict[str, Any]
    options: dict[str, Any]
    semantic_context: dict[str, Any] | None
    n8n_baseline: ShadowN8nBaseline
    langgraph_evidence: dict[str, Any]
    execution_future: ShadowExecutionFuture
    fingerprints: ShadowFingerprints
    lineage: dict[str, Any]
    langgraph_version: str | None
    langgraph_commit: str | None
    evidence_fingerprint: str


class ShadowRepositoryResult(TypedDict):
    status: ShadowRepositoryStatus
    shadow_record_id: str | None
    agent_run_id: str | None
    run_id: str | None
    evidence_fingerprint: str | None
    diagnostic: ShadowRepositoryDiagnostic | None
    duration_ms: int | None


class ShadowRepositoryFetchResult(TypedDict):
    status: ShadowRepositoryReadStatus
    record: ShadowRunRecord | None
    diagnostic: ShadowRepositoryDiagnostic | None


class ShadowRepositoryListResult(TypedDict):
    status: Literal["ok", "unavailable"]
    records: list[ShadowRunRecord]
    diagnostic: ShadowRepositoryDiagnostic | None


class FinalizeShadowRunRequest(TypedDict):
    shadow_record_id: str
    status: ShadowStatus
    completed_at: str
    evidence_fingerprint: str


class ShadowEvidenceValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


_BLOCKED_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "dsn",
    "headers",
    "password",
    "raw_response",
    "secret",
    "secrets",
    "token",
    "tokens",
}


def build_generate_shadow_record(
    *,
    shadow_record_id: str,
    agent_run_id: str,
    run_id: str,
    created_at: str,
    completed_at: str | None,
    status: str,
    request: Mapping[str, Any],
    state: Mapping[str, Any],
    response: Mapping[str, Any],
    langgraph_version: str | None = None,
    langgraph_commit: str | None = None,
) -> ShadowRunRecord:
    question = _optional_text(request.get("question"))
    generated_sql = _optional_text(state.get("generated_sql"))
    current_sql = _optional_text(state.get("current_sql"))
    repaired_sql = (
        current_sql
        if current_sql and generated_sql and current_sql.strip() != generated_sql.strip()
        else None
    )
    langgraph_evidence = {
        "intent": state.get("intent"),
        "plan": state.get("query_plan"),
        "generated_sql": generated_sql,
        "current_sql": current_sql,
        "repaired_sql_proposal": repaired_sql,
        "gates": response.get("gates"),
        "security_result": state.get("security_result"),
        "contract_result": state.get("contract_result"),
        "preflight_result": state.get("engine_preflight_result"),
        "repair_history": state.get("repair_history", []),
        "repair_attempts": state.get("repair_attempts", 0),
        "warnings": state.get("warnings", []),
        "errors": response.get("errors", []),
        "final_status": state.get("final_status"),
        "timings": _timings_from_state(state),
        "provider_metadata": _provider_metadata(state),
        "response": response,
    }
    return _build_record(
        shadow_record_id=shadow_record_id,
        agent_run_id=agent_run_id,
        run_id=run_id,
        event_type="generate",
        created_at=created_at,
        completed_at=completed_at,
        status=status,
        question=question,
        approved_sql_original=None,
        generated_sql=current_sql or generated_sql,
        repaired_sql_proposal=repaired_sql,
        requires_reapproval=False,
        request=request,
        state=state,
        langgraph_evidence=langgraph_evidence,
        langgraph_version=langgraph_version,
        langgraph_commit=langgraph_commit,
    )


def build_execute_shadow_record(
    *,
    shadow_record_id: str,
    agent_run_id: str,
    run_id: str,
    created_at: str,
    completed_at: str | None,
    status: str,
    request: Mapping[str, Any],
    state: Mapping[str, Any],
    response: Mapping[str, Any],
    langgraph_version: str | None = None,
    langgraph_commit: str | None = None,
) -> ShadowRunRecord:
    approved_sql = _optional_text(response.get("approved_sql_original")) or _optional_text(
        request.get("approved_sql")
    )
    repaired_sql = _optional_text(response.get("repaired_sql_proposal"))
    langgraph_evidence = {
        "approved_sql_original": approved_sql,
        "validation": response.get("validation"),
        "security_result": state.get("security_result"),
        "contract_result": state.get("contract_result"),
        "preflight_result": state.get("engine_preflight_result"),
        "repair_history": state.get("repair_history", []),
        "repaired_sql_proposal": repaired_sql,
        "requires_reapproval": bool(response.get("requires_reapproval")),
        "warnings": state.get("warnings", []),
        "errors": response.get("errors", []),
        "final_status": state.get("final_status"),
        "timings": _timings_from_state(state),
        "response": response,
    }
    return _build_record(
        shadow_record_id=shadow_record_id,
        agent_run_id=agent_run_id,
        run_id=run_id,
        event_type="execute_approved_shadow",
        created_at=created_at,
        completed_at=completed_at,
        status=status,
        question=None,
        approved_sql_original=approved_sql,
        generated_sql=None,
        repaired_sql_proposal=repaired_sql,
        requires_reapproval=bool(response.get("requires_reapproval")),
        request=request,
        state=state,
        langgraph_evidence=langgraph_evidence,
        langgraph_version=langgraph_version,
        langgraph_commit=langgraph_commit,
    )


def sanitize_shadow_evidence(value: Any) -> Any:
    sanitized = _sanitize_value(value)
    try:
        canonical_json(sanitized)
    except (TypeError, ValueError) as error:
        raise ShadowEvidenceValidationError(
            "SHADOW_EVIDENCE_JSON_INVALID",
            "Shadow evidence must be strict JSON.",
        ) from error
    return sanitized


def validate_shadow_run_record(record: ShadowRunRecord) -> ShadowRunRecord:
    sanitized = cast(ShadowRunRecord, sanitize_shadow_evidence(record))
    required = {
        "shadow_record_id",
        "agent_run_id",
        "run_id",
        "event_type",
        "contract_version",
        "status",
        "created_at",
        "requires_reapproval",
        "n8n_baseline",
        "langgraph_evidence",
        "execution_future",
        "fingerprints",
        "lineage",
        "evidence_fingerprint",
    }
    missing = [field for field in required if field not in sanitized]
    if missing:
        raise ShadowEvidenceValidationError(
            "SHADOW_RECORD_REQUIRED_FIELD_MISSING",
            "Shadow record is missing required fields.",
        )
    if sanitized["contract_version"] != SHADOW_EVIDENCE_CONTRACT_VERSION:
        raise ShadowEvidenceValidationError(
            "SHADOW_RECORD_CONTRACT_UNSUPPORTED",
            "Shadow record contract version is unsupported.",
        )
    if sanitized["event_type"] not in {"generate", "execute_approved_shadow"}:
        raise ShadowEvidenceValidationError(
            "SHADOW_RECORD_EVENT_INVALID",
            "Shadow record event type is invalid.",
        )
    if sanitized["status"] not in {"started", "success", "rejected", "infrastructure_error"}:
        raise ShadowEvidenceValidationError(
            "SHADOW_RECORD_STATUS_INVALID",
            "Shadow record status is invalid.",
        )
    expected = stable_fingerprint(_fingerprint_payload(sanitized))
    if sanitized["evidence_fingerprint"] != expected:
        raise ShadowEvidenceValidationError(
            "SHADOW_RECORD_FINGERPRINT_MISMATCH",
            "Shadow record fingerprint does not match payload.",
        )
    return deepcopy(sanitized)


def strict_json_dumps(value: Any) -> str:
    return canonical_json(sanitize_shadow_evidence(value))


def _build_record(
    *,
    shadow_record_id: str,
    agent_run_id: str,
    run_id: str,
    event_type: ShadowEventType,
    created_at: str,
    completed_at: str | None,
    status: str,
    question: str | None,
    approved_sql_original: str | None,
    generated_sql: str | None,
    repaired_sql_proposal: str | None,
    requires_reapproval: bool,
    request: Mapping[str, Any],
    state: Mapping[str, Any],
    langgraph_evidence: Mapping[str, Any],
    langgraph_version: str | None,
    langgraph_commit: str | None,
) -> ShadowRunRecord:
    status_value = cast(ShadowStatus, status if status in {"success", "rejected", "infrastructure_error"} else "infrastructure_error")
    n8n_baseline: ShadowN8nBaseline = {"fingerprints": {}}
    execution_future: ShadowExecutionFuture = {"fingerprints": {}}
    record: ShadowRunRecord = {
        "shadow_record_id": shadow_record_id,
        "agent_run_id": agent_run_id,
        "run_id": run_id,
        "event_type": event_type,
        "contract_version": SHADOW_EVIDENCE_CONTRACT_VERSION,
        "status": status_value,
        "created_at": created_at,
        "completed_at": completed_at,
        "question": question,
        "approved_sql_original": approved_sql_original,
        "generated_sql": generated_sql,
        "repaired_sql_proposal": repaired_sql_proposal,
        "requires_reapproval": bool(requires_reapproval),
        "principal": dict(cast(Mapping[str, Any], request.get("principal", {}))),
        "correlation_metadata": dict(cast(Mapping[str, Any], request.get("correlation_metadata", {}))),
        "options": dict(cast(Mapping[str, Any], state.get("options", {}))),
        "semantic_context": cast(dict[str, Any] | None, state.get("context")),
        "n8n_baseline": n8n_baseline,
        "langgraph_evidence": dict(langgraph_evidence),
        "execution_future": execution_future,
        "fingerprints": _fingerprints(
            question=question,
            n8n_sql=None,
            langgraph_sql=generated_sql,
            approved_sql=approved_sql_original,
            repaired_sql_proposal=repaired_sql_proposal,
            response_result=langgraph_evidence,
        ),
        "lineage": _lineage_from_state(state),
        "langgraph_version": langgraph_version,
        "langgraph_commit": langgraph_commit,
        "evidence_fingerprint": "",
    }
    sanitized = cast(ShadowRunRecord, sanitize_shadow_evidence(record))
    sanitized["fingerprints"]["evidence_payload"] = stable_fingerprint(
        _fingerprint_payload(sanitized)
    )
    sanitized["evidence_fingerprint"] = stable_fingerprint(
        _fingerprint_payload(sanitized)
    )
    return validate_shadow_run_record(sanitized)


def _fingerprint_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = deepcopy(dict(record))
    payload.pop("evidence_fingerprint", None)
    fingerprints = payload.get("fingerprints")
    if isinstance(fingerprints, dict):
        fingerprints.pop("evidence_payload", None)
    return payload


def _fingerprints(
    *,
    question: str | None,
    n8n_sql: str | None,
    langgraph_sql: str | None,
    approved_sql: str | None,
    repaired_sql_proposal: str | None,
    response_result: Any,
) -> ShadowFingerprints:
    output: ShadowFingerprints = {}
    for key, value in [
        ("question", question),
        ("n8n_sql", n8n_sql),
        ("langgraph_sql", langgraph_sql),
        ("approved_sql", approved_sql),
        ("repaired_sql_proposal", repaired_sql_proposal),
    ]:
        if isinstance(value, str) and value:
            output[key] = stable_fingerprint(value)  # type: ignore[literal-required]
    output["response_result"] = stable_fingerprint(sanitize_shadow_evidence(response_result))
    return output


def _lineage_from_state(state: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key in (
        "context_fingerprint",
        "context_version",
        "sql_fingerprint",
        "intent",
        "failure_stage",
        "current_stage",
    ):
        value = state.get(key)
        if value is not None:
            output[key] = value
    for source, target in (
        ("security_result", "security_fingerprint"),
        ("contract_result", "contract_fingerprint"),
        ("engine_preflight_result", "preflight_fingerprint"),
    ):
        value = state.get(source)
        if isinstance(value, Mapping):
            fingerprint = value.get("sql_fingerprint") or value.get("request_fingerprint")
            if isinstance(fingerprint, str) and fingerprint:
                output[target] = fingerprint
    return output


def _provider_metadata(state: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for source in ("generation_result", "repair_result", "engine_preflight_result"):
        value = state.get(source)
        if not isinstance(value, Mapping):
            continue
        provider = value.get("provider_name")
        version = value.get("provider_version")
        if isinstance(provider, str):
            output[f"{source}_provider_name"] = provider
        if isinstance(version, str):
            output[f"{source}_provider_version"] = version
    return output


def _timings_from_state(state: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for source in ("engine_preflight_result", "security_result", "contract_result"):
        value = state.get(source)
        if isinstance(value, Mapping) and isinstance(value.get("duration_ms"), int):
            output[f"{source}_duration_ms"] = value["duration_ms"]
    return output


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ShadowEvidenceValidationError(
                    "SHADOW_EVIDENCE_KEY_INVALID",
                    "Shadow evidence JSON object keys must be strings.",
                )
            if key.casefold() in _BLOCKED_KEYS:
                continue
            output[key] = _sanitize_value(item)
        return output
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ShadowEvidenceValidationError(
                "SHADOW_EVIDENCE_NON_FINITE_NUMBER",
                "Shadow evidence rejects NaN and Infinity.",
            )
        return value
    raise ShadowEvidenceValidationError(
        "SHADOW_EVIDENCE_VALUE_NOT_SERIALIZABLE",
        "Shadow evidence contains a non JSON-serializable value.",
    )
