from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from app.domain.result_normalization import canonical_json, stable_fingerprint
from app.domain.run_audit_types import AuditEvent
from app.domain.run_observability_types import (
    ObservabilityAttribute,
    ObservabilityEvent,
    ObservabilityMetric,
)
from app.domain.run_persistence_types import PersistRunRequest
from app.domain.run_record_types import (
    RUN_RECORD_CONTRACT_VERSION,
    RunErrorRecord,
    RunFinalizationLimits,
    RunLineage,
    RunMetrics,
    RunOutcome,
    RunRecord,
    RunStageRecord,
    RunWarningRecord,
)


class RunRecordError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def build_run_record(
    state: Mapping[str, Any],
    *,
    limits: RunFinalizationLimits,
) -> RunRecord:
    safe_limits = validate_finalization_limits(limits)
    if isinstance(state.get("run_record"), Mapping):
        raise RunRecordError(
            "RUN_RECORD_ALREADY_EXISTS",
            "RunRecord ja existe no estado.",
        )

    outcome = infer_run_outcome(str(state.get("final_status", "")))
    errors = _error_records(state, safe_limits["max_error_records"])
    warnings = _warning_records(state, safe_limits["max_warning_records"])
    lineage = _lineage(state)
    metrics = _metrics(state, lineage)
    stages = _stage_records(state, safe_limits["max_stage_records"])
    serialized_result = _serialized_result_payload(
        state,
        safe_limits["max_persisted_payload_bytes"],
    )
    previous_stage = str(state.get("current_stage", ""))
    record_without_fingerprint: RunRecord = {
        "contract_version": RUN_RECORD_CONTRACT_VERSION,
        "request_id": str(state.get("request_id", "")),
        "run_id": str(state.get("run_id", "")),
        "status": "built",
        "outcome": outcome,
        "original_final_status": str(state.get("final_status", "")),
        "failure_stage": str(state.get("failure_stage", "")),
        "previous_stage": previous_stage,
        "lineage": lineage,
        "metrics": metrics,
        "stages": stages,
        "errors": errors,
        "warnings": warnings,
        "serialized_result": serialized_result,
        "error_code": None,
    }
    fingerprint = stable_fingerprint(record_without_fingerprint)
    return {
        **deepcopy(record_without_fingerprint),
        "fingerprint": fingerprint,
    }


def validate_finalization_limits(
    limits: Mapping[str, Any],
) -> RunFinalizationLimits:
    required = {
        "max_persisted_payload_bytes": (1, 5_000_000),
        "max_stage_records": (1, 100),
        "max_error_records": (1, 100),
        "max_warning_records": (1, 100),
        "max_audit_error_codes": (1, 50),
        "max_observability_attributes": (1, 100),
        "max_attribute_length": (1, 256),
        "max_provider_name_length": (1, 128),
    }
    output: dict[str, int] = {}
    for name, (minimum, maximum) in required.items():
        value = limits.get(name)
        if not isinstance(value, int) or isinstance(value, bool):
            raise RunRecordError(
                "RUN_RECORD_INPUT_INVALID",
                f"Limite {name} deve ser inteiro.",
            )
        if value < minimum or value > maximum:
            raise RunRecordError(
                "RUN_RECORD_LIMIT_EXCEEDED",
                f"Limite {name} fora da faixa permitida.",
            )
        output[name] = value
    return output  # type: ignore[return-value]


def default_finalization_limits() -> RunFinalizationLimits:
    return {
        "max_persisted_payload_bytes": 262_144,
        "max_stage_records": 32,
        "max_error_records": 32,
        "max_warning_records": 32,
        "max_audit_error_codes": 16,
        "max_observability_attributes": 32,
        "max_attribute_length": 128,
        "max_provider_name_length": 64,
    }


def infer_run_outcome(final_status: str) -> RunOutcome:
    if final_status == "approved":
        return "success"
    if final_status in {"rejected", "invalid_request"}:
        return "rejected"
    return "infrastructure_error"


def build_persist_run_request(record: RunRecord) -> PersistRunRequest:
    fingerprint = _required_fingerprint(record)
    return {
        "run_record": deepcopy(record),
        "run_record_fingerprint": fingerprint,
        "idempotency_key": _idempotency_key(
            str(record.get("run_id", "")),
            fingerprint,
            str(record.get("contract_version", "")),
        ),
        "contract_version": str(record.get("contract_version", "")),
    }


def build_audit_event(
    record: RunRecord,
    *,
    persistence_record_id: str,
    limits: RunFinalizationLimits,
    actor_profile: str = "",
) -> AuditEvent:
    fingerprint = _required_fingerprint(record)
    lineage = record.get("lineage", {})
    metrics = record.get("metrics", {})
    error_codes = _codes(record.get("errors", []))[
        : limits["max_audit_error_codes"]
    ]
    warning_codes = _codes(record.get("warnings", []))[
        : limits["max_audit_error_codes"]
    ]
    event_type = {
        "success": "sql_agent_run_completed",
        "rejected": "sql_agent_run_rejected",
        "infrastructure_error": "sql_agent_run_infrastructure_error",
    }[record["outcome"]]
    event: AuditEvent = {
        "event_id": _idempotency_key(
            str(record.get("run_id", "")),
            fingerprint,
            "audit",
        ),
        "event_type": event_type,
        "idempotency_key": _idempotency_key(
            str(record.get("run_id", "")),
            fingerprint,
            "audit-event",
        ),
        "request_id": str(record.get("request_id", "")),
        "run_id": str(record.get("run_id", "")),
        "actor": {"profile": _safe_text(actor_profile, 64)},
        "subject": {
            "request_id": str(record.get("request_id", "")),
            "run_id": str(record.get("run_id", "")),
        },
        "outcome": record["outcome"],
        "final_status": str(record.get("original_final_status", "")),
        "failure_stage": str(record.get("failure_stage", "")),
        "intent_name": lineage.get("intent_name"),
        "context_version": str(lineage.get("context_version", "")),
        "fingerprints": {
            "run_record": fingerprint,
            "context": lineage.get("context_fingerprint"),
            "query_plan": lineage.get("query_plan_fingerprint"),
            "current_sql": lineage.get("current_sql_fingerprint"),
            "serialized_result": lineage.get(
                "serialized_result_fingerprint"
            ),
        },
        "repair_attempts": int(lineage.get("repair_attempts", 0)),
        "row_count": int(metrics.get("row_count", 0)),
        "error_codes": error_codes,
        "warning_codes": warning_codes,
        "persistence_record_id": persistence_record_id,
        "fingerprint": "",
    }
    event["fingerprint"] = stable_fingerprint(
        {key: value for key, value in event.items() if key != "fingerprint"}
    )
    return event


def build_observability_event(
    record: RunRecord | None,
    *,
    limits: RunFinalizationLimits,
    finalization_status: str,
    persistence_duration_ms: int | None = None,
    audit_duration_ms: int | None = None,
) -> ObservabilityEvent:
    attributes: list[ObservabilityAttribute] = []
    metrics: list[ObservabilityMetric] = []
    outcome = "infrastructure_error"
    error_codes: list[str] = []
    warning_codes: list[str] = []
    row_count = 0
    column_count = 0
    payload_bytes = 0
    repair_attempts = 0
    execution_duration_ms = None
    if isinstance(record, Mapping):
        outcome = str(record.get("outcome", "infrastructure_error"))
        record_metrics = record.get("metrics", {})
        lineage = record.get("lineage", {})
        if isinstance(record_metrics, Mapping):
            row_count = int(record_metrics.get("row_count", 0))
            column_count = int(record_metrics.get("column_count", 0))
            payload_bytes = int(record_metrics.get("bytes", 0))
            execution_duration_ms = record_metrics.get(
                "execution_duration_ms"
            )
        if isinstance(lineage, Mapping):
            repair_attempts = int(lineage.get("repair_attempts", 0))
        error_codes = _codes(record.get("errors", []))
        warning_codes = _codes(record.get("warnings", []))

    labels = {"outcome": outcome, "finalization_status": finalization_status}
    metric_name = {
        "success": "run_completed_total",
        "rejected": "run_rejected_total",
        "infrastructure_error": "run_infrastructure_error_total",
    }.get(outcome, "run_infrastructure_error_total")
    metrics.extend(
        [
            {"name": metric_name, "value": 1, "labels": labels},
            {
                "name": "repair_attempts_total",
                "value": repair_attempts,
                "labels": labels,
            },
            {
                "name": "result_row_count",
                "value": row_count,
                "labels": labels,
            },
            {
                "name": "result_bytes",
                "value": payload_bytes,
                "labels": labels,
            },
        ]
    )
    if isinstance(execution_duration_ms, int):
        metrics.append(
            {
                "name": "execution_duration_ms",
                "value": execution_duration_ms,
                "labels": labels,
            }
        )
    if isinstance(persistence_duration_ms, int):
        metrics.append(
            {
                "name": "persistence_duration_ms",
                "value": persistence_duration_ms,
                "labels": labels,
            }
        )
    if isinstance(audit_duration_ms, int):
        metrics.append(
            {
                "name": "audit_duration_ms",
                "value": audit_duration_ms,
                "labels": labels,
            }
        )
    _add_attribute(
        attributes,
        "outcome",
        outcome,
        limits,
        metric_label=True,
    )
    _add_attribute(
        attributes,
        "finalization_status",
        finalization_status,
        limits,
        metric_label=True,
    )
    _add_attribute(attributes, "row_count", row_count, limits)
    _add_attribute(attributes, "column_count", column_count, limits)
    _add_attribute(attributes, "result_bytes", payload_bytes, limits)
    _add_attribute(attributes, "repair_attempts", repair_attempts, limits)
    event: ObservabilityEvent = {
        "operation_name": "sql_agent_run_finalization",
        "stage": "emit_observability",
        "status": finalization_status,
        "outcome": outcome,
        "duration_ms": None,
        "metrics": metrics,
        "spans": [
            {
                "name": "run_finalization",
                "stage": "emit_observability",
                "status": finalization_status,
                "duration_ms": None,
                "attributes": deepcopy(attributes),
            }
        ],
        "attributes": attributes,
        "error_codes": error_codes,
        "warning_codes": warning_codes,
        "fingerprint": "",
    }
    event["fingerprint"] = stable_fingerprint(
        {key: value for key, value in event.items() if key != "fingerprint"}
    )
    return event


def _lineage(state: Mapping[str, Any]) -> RunLineage:
    context = state.get("context", {})
    query_plan = state.get("query_plan", {})
    security_result = state.get("security_result", {})
    contract_result = state.get("contract_result", {})
    preflight_result = state.get("engine_preflight_result", {})
    execution_result = state.get("sql_execution_result", {})
    normalized_result = state.get("normalized_result", {})
    serialized_result = state.get("serialized_result", {})
    repair_history = state.get("repair_history", [])
    return {
        "context_version": str(state.get("context_version", "")),
        "context_fingerprint": (
            str(context.get("fingerprint", ""))
            if isinstance(context, Mapping)
            else ""
        ),
        "intent_name": state.get("intent"),
        "intent_confidence": state.get("intent_confidence"),
        "query_plan_fingerprint": (
            stable_fingerprint(query_plan)
            if isinstance(query_plan, Mapping) and query_plan
            else ""
        ),
        "generated_sql_fingerprint": _text_fingerprint(
            state.get("generated_sql")
        ),
        "current_sql_fingerprint": _text_fingerprint(state.get("current_sql")),
        "security_result_fingerprint": _mapping_fingerprint(security_result),
        "security_status": _status(security_result),
        "contract_result_fingerprint": _mapping_fingerprint(contract_result),
        "contract_status": _status(contract_result),
        "preflight_result_fingerprint": _mapping_fingerprint(preflight_result),
        "preflight_status": _status(preflight_result),
        "execution_request_fingerprint": _optional_text(
            execution_result,
            "request_fingerprint",
        ),
        "execution_response_fingerprint": _optional_text_or_none(
            execution_result,
            "response_fingerprint",
        ),
        "execution_result_fingerprint": _mapping_fingerprint(
            _execution_summary(execution_result)
        ),
        "normalized_result_fingerprint": _result_fingerprint(
            normalized_result
        ),
        "serialized_result_fingerprint": _result_fingerprint(
            serialized_result
        ),
        "repair_attempts": int(state.get("repair_attempts", 0) or 0),
        "repair_history": _repair_summary(repair_history),
    }


def _metrics(
    state: Mapping[str, Any],
    lineage: RunLineage,
) -> RunMetrics:
    execution_result = state.get("sql_execution_result", {})
    serialized_result = state.get("serialized_result", {})
    columns = (
        serialized_result.get("columns", [])
        if isinstance(serialized_result, Mapping)
        else []
    )
    if isinstance(serialized_result, Mapping) and serialized_result:
        bytes_value = _json_size(serialized_result)
    elif isinstance(execution_result, Mapping):
        bytes_value = int(execution_result.get("bytes_received", 0) or 0)
    else:
        bytes_value = 0
    return {
        "row_count": _row_count(state),
        "column_count": len(columns) if isinstance(columns, list) else 0,
        "bytes": bytes_value,
        "duration_ms": None,
        "execution_duration_ms": (
            execution_result.get("duration_ms")
            if isinstance(execution_result, Mapping)
            else None
        ),
        "truncated": bool(
            execution_result.get("truncated", False)
            if isinstance(execution_result, Mapping)
            else False
        ),
        "repair_attempts": int(lineage.get("repair_attempts", 0)),
    }


def _stage_records(
    state: Mapping[str, Any],
    limit: int,
) -> list[RunStageRecord]:
    stages: list[RunStageRecord] = []
    for stage_name, field_name in [
        ("security_gate", "security_result"),
        ("contract_gate", "contract_result"),
        ("engine_preflight", "engine_preflight_result"),
        ("execute_sql", "sql_execution_result"),
        ("normalize_result", "normalized_result"),
        ("serialize_result", "serialized_result"),
    ]:
        value = state.get(field_name)
        if not isinstance(value, Mapping):
            continue
        stages.append(
            {
                "stage_name": stage_name,
                "status": str(value.get("status", "unknown")),
                "attempt": int(state.get("repair_attempts", 0) or 0),
                "duration_ms": (
                    value.get("duration_ms")
                    if isinstance(value.get("duration_ms"), int)
                    else None
                ),
                "output_fingerprint": _mapping_fingerprint(value),
                "error_codes": _diagnostic_codes(value),
                "warning_codes": _warning_codes(value),
            }
        )
    if len(stages) > limit:
        raise RunRecordError(
            "RUN_RECORD_LIMIT_EXCEEDED",
            "Quantidade de estagios excede limite.",
        )
    return stages


def _serialized_result_payload(
    state: Mapping[str, Any],
    limit: int,
) -> Any:
    serialized_result = state.get("serialized_result")
    if not isinstance(serialized_result, Mapping):
        return None
    payload = deepcopy(serialized_result)
    size = _json_size(payload)
    if size > limit:
        raise RunRecordError(
            "RUN_RECORD_LIMIT_EXCEEDED",
            "Payload persistido excede limite.",
        )
    return payload


def _error_records(
    state: Mapping[str, Any],
    limit: int,
) -> list[RunErrorRecord]:
    errors = state.get("errors", [])
    if not isinstance(errors, list):
        return []
    if len(errors) > limit:
        raise RunRecordError(
            "RUN_RECORD_LIMIT_EXCEEDED",
            "Quantidade de erros excede limite.",
        )
    output: list[RunErrorRecord] = []
    for error in errors:
        if not isinstance(error, Mapping):
            continue
        output.append(
            {
                "code": _safe_text(error.get("code"), 96),
                "source": _safe_text(error.get("source"), 64),
                "stage": _safe_text(error.get("stage"), 64),
                "repairable": bool(error.get("repairable", False)),
            }
        )
    return output


def _warning_records(
    state: Mapping[str, Any],
    limit: int,
) -> list[RunWarningRecord]:
    warnings = state.get("warnings", [])
    if not isinstance(warnings, list):
        return []
    if len(warnings) > limit:
        raise RunRecordError(
            "RUN_RECORD_LIMIT_EXCEEDED",
            "Quantidade de warnings excede limite.",
        )
    return [
        {
            "code": _safe_text(warning, 96),
            "source": "langgraph",
            "stage": str(state.get("current_stage", "")),
        }
        for warning in warnings
    ]


def _repair_summary(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        output.append(
            {
                "attempt": int(item.get("attempt", 0) or 0),
                "failed_stage": _safe_text(item.get("failed_stage"), 64),
                "failure_category": _safe_text(
                    item.get("failure_category"),
                    64,
                ),
                "error_code": _safe_text(item.get("error_code"), 96),
                "sql_before_fingerprint": _safe_text(
                    item.get("sql_before_fingerprint"),
                    64,
                ),
                "sql_after_fingerprint": _safe_text(
                    item.get("sql_after_fingerprint"),
                    64,
                ),
                "request_fingerprint": _safe_text(
                    item.get("request_fingerprint"),
                    64,
                ),
                "response_fingerprint": _safe_text(
                    item.get("response_fingerprint"),
                    64,
                ),
                "repair_applied": bool(item.get("repair_applied", False)),
            }
        )
    return output


def _execution_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        "status": value.get("status"),
        "request_fingerprint": value.get("request_fingerprint"),
        "response_fingerprint": value.get("response_fingerprint"),
        "sql_fingerprint": value.get("sql_fingerprint"),
        "row_count": value.get("row_count"),
        "truncated": value.get("truncated"),
        "executed": value.get("executed"),
        "error_code": value.get("error_code"),
        "failure_category": value.get("failure_category"),
        "metrics": value.get("metrics"),
    }


def _row_count(state: Mapping[str, Any]) -> int:
    serialized_result = state.get("serialized_result")
    if isinstance(serialized_result, Mapping):
        rows = serialized_result.get("rows", [])
        if isinstance(rows, list):
            return len(rows)
    execution_result = state.get("sql_execution_result")
    if isinstance(execution_result, Mapping):
        return int(execution_result.get("row_count", 0) or 0)
    return 0


def _mapping_fingerprint(value: Any) -> str:
    if not isinstance(value, Mapping) or not value:
        return ""
    return stable_fingerprint(value)


def _text_fingerprint(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    return stable_fingerprint({"text": value})


def _result_fingerprint(value: Any) -> str:
    if isinstance(value, Mapping):
        result = value.get("result_fingerprint")
        if isinstance(result, str):
            return result
        return _mapping_fingerprint(value)
    return ""


def _optional_text(value: Any, key: str) -> str:
    if isinstance(value, Mapping):
        item = value.get(key)
        if isinstance(item, str):
            return item
    return ""


def _optional_text_or_none(value: Any, key: str) -> str | None:
    if isinstance(value, Mapping):
        item = value.get(key)
        if isinstance(item, str):
            return item
    return None


def _status(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("status", ""))
    return ""


def _diagnostic_codes(value: Mapping[str, Any]) -> list[str]:
    output: list[str] = []
    diagnostics = value.get("diagnostics", [])
    if isinstance(diagnostics, list):
        for diagnostic in diagnostics:
            if isinstance(diagnostic, Mapping) and diagnostic.get("code"):
                output.append(_safe_text(diagnostic.get("code"), 96))
    error_code = value.get("error_code")
    if error_code:
        output.append(_safe_text(error_code, 96))
    return output


def _warning_codes(value: Mapping[str, Any]) -> list[str]:
    warnings = value.get("warnings", [])
    if not isinstance(warnings, list):
        return []
    return [_safe_text(warning, 96) for warning in warnings]


def _codes(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    output: list[str] = []
    for item in items:
        if isinstance(item, Mapping):
            code = item.get("code")
            if code:
                output.append(_safe_text(code, 96))
    return output


def _required_fingerprint(record: RunRecord) -> str:
    fingerprint = record.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise RunRecordError(
            "RUN_RECORD_INPUT_INVALID",
            "RunRecord sem fingerprint.",
        )
    return fingerprint


def _idempotency_key(*parts: str) -> str:
    return stable_fingerprint({"idempotency_key": list(parts)})


def _json_size(value: Any) -> int:
    return len(canonical_json(value).encode("utf-8"))


def _safe_text(value: Any, max_length: int) -> str:
    if value is None:
        return ""
    text = str(value)
    blocked = [
        "authorization",
        "bearer",
        "api key",
        "cookie",
        "dsn",
        "header",
        "stack trace",
    ]
    lowered = text.casefold()
    if any(term in lowered for term in blocked):
        return "sanitized"
    return text[:max_length]


def _add_attribute(
    attributes: list[ObservabilityAttribute],
    key: str,
    value: str | int | bool | None,
    limits: RunFinalizationLimits,
    *,
    metric_label: bool = False,
) -> None:
    if len(attributes) >= limits["max_observability_attributes"]:
        return
    safe_value: str | int | bool | None = value
    if isinstance(value, str):
        safe_value = _safe_text(value, limits["max_attribute_length"])
    attributes.append(
        {
            "key": _safe_text(key, limits["max_attribute_length"]),
            "value": safe_value,
            "metric_label": metric_label,
        }
    )
