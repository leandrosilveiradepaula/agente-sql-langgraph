from __future__ import annotations

from typing import Any, Literal, TypedDict

from app.domain.result_normalization_types import SerializedQueryResult


RUN_RECORD_CONTRACT_VERSION = "v1.0.0-run-finalization"

RunOutcome = Literal["success", "rejected", "infrastructure_error"]
RunRecordStatus = Literal["built", "rejected"]
RunRecordErrorCode = Literal[
    "RUN_RECORD_ALREADY_EXISTS",
    "RUN_RECORD_LIMIT_EXCEEDED",
    "RUN_RECORD_INPUT_INVALID",
    "RUN_RECORD_UNEXPECTED_ERROR",
]
FinalizationStatus = Literal[
    "not_started",
    "record_built",
    "record_failed",
    "persisted",
    "persistence_failed",
    "audited",
    "audit_failed",
    "observed",
    "observability_degraded",
]


class RunFinalizationLimits(TypedDict):
    max_persisted_payload_bytes: int
    max_stage_records: int
    max_error_records: int
    max_warning_records: int
    max_audit_error_codes: int
    max_observability_attributes: int
    max_attribute_length: int
    max_provider_name_length: int


class RunLineage(TypedDict, total=False):
    context_version: str
    context_fingerprint: str
    intent_name: str | None
    intent_confidence: float | None
    query_plan_fingerprint: str
    generated_sql_fingerprint: str
    current_sql_fingerprint: str
    security_result_fingerprint: str
    security_status: str
    contract_result_fingerprint: str
    contract_status: str
    preflight_result_fingerprint: str
    preflight_status: str
    execution_request_fingerprint: str
    execution_response_fingerprint: str | None
    execution_result_fingerprint: str
    normalized_result_fingerprint: str
    serialized_result_fingerprint: str
    repair_attempts: int
    repair_history: list[dict[str, Any]]


class RunMetrics(TypedDict, total=False):
    row_count: int
    column_count: int
    bytes: int
    duration_ms: int | None
    execution_duration_ms: int | None
    truncated: bool
    repair_attempts: int


class RunStageRecord(TypedDict, total=False):
    stage_name: str
    status: str
    attempt: int
    duration_ms: int | None
    input_fingerprint: str
    output_fingerprint: str
    error_codes: list[str]
    warning_codes: list[str]


class RunErrorRecord(TypedDict, total=False):
    code: str
    source: str
    stage: str
    repairable: bool


class RunWarningRecord(TypedDict, total=False):
    code: str
    source: str
    stage: str


class RunRecord(TypedDict, total=False):
    contract_version: str
    request_id: str
    run_id: str
    status: RunRecordStatus
    outcome: RunOutcome
    original_final_status: str
    failure_stage: str
    previous_stage: str
    lineage: RunLineage
    metrics: RunMetrics
    stages: list[RunStageRecord]
    errors: list[RunErrorRecord]
    warnings: list[RunWarningRecord]
    serialized_result: SerializedQueryResult | None
    fingerprint: str
    error_code: RunRecordErrorCode | None
