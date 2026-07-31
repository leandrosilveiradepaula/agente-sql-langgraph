from __future__ import annotations

from typing import Any, Literal, TypedDict


APPLICATION_RESPONSE_CONTRACT_VERSION = "v1.0.0-application-response"

ApplicationResponseStatus = Literal[
    "success",
    "rejected",
    "infrastructure_error",
]
ApplicationResponseOutcome = Literal[
    "success",
    "rejected",
    "infrastructure_error",
]
ApplicationResponseFinalizationStatus = Literal[
    "completed",
    "persistence_failed",
    "audit_failed",
    "observability_degraded",
    "record_failed",
    "incomplete",
]
ApplicationResponseErrorCode = Literal[
    "APPLICATION_RESPONSE_BUILD_FAILED",
    "APPLICATION_RESPONSE_INPUT_INVALID",
    "APPLICATION_RESPONSE_LIMIT_EXCEEDED",
    "APPLICATION_RESPONSE_FINALIZATION_INCOMPLETE",
]


class ApplicationResponseLimits(TypedDict):
    max_response_bytes: int
    max_errors: int
    max_warnings: int
    max_message_length: int
    max_error_message_length: int
    max_warning_message_length: int
    max_lineage_fields: int
    max_data_rows: int
    max_data_columns: int
    max_metadata_fields: int


class ApplicationResponsePagination(TypedDict):
    mode: Literal["none"]
    has_more: bool
    next_cursor: None
    total_rows: int | None
    returned_rows: int


class ApplicationResponseResult(TypedDict):
    contract_version: str
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    result_fingerprint: str


class ApplicationResponseData(TypedDict):
    result: ApplicationResponseResult
    pagination: ApplicationResponsePagination


class ApplicationResponseLineage(TypedDict, total=False):
    context_fingerprint: str
    query_plan_fingerprint: str
    current_sql_fingerprint: str
    preflight_fingerprint: str
    execution_request_fingerprint: str
    execution_response_fingerprint: str
    normalized_result_fingerprint: str
    serialized_result_fingerprint: str
    run_record_fingerprint: str
    persistence_record_id: str
    persistence_fingerprint: str
    audit_event_id: str
    audit_fingerprint: str


class ApplicationResponseMetadata(TypedDict, total=False):
    context_version: str
    intent: str | None
    row_count: int
    column_count: int
    result_bytes: int
    truncated: bool
    repair_attempts: int
    duration_ms: int | None
    persisted: bool
    audited: bool
    observability_degraded: bool
    provider: str
    contract_versions: dict[str, str]
    original_outcome: ApplicationResponseOutcome
    finalization_status: ApplicationResponseFinalizationStatus
    lineage: ApplicationResponseLineage


class ApplicationResponseDiagnostic(TypedDict, total=False):
    diagnostic_id: str
    fingerprint: str


class ApplicationResponseError(TypedDict, total=False):
    code: str
    category: str
    stage: str
    message: str
    retryable: bool
    field: str
    diagnostic: ApplicationResponseDiagnostic


class ApplicationResponseWarning(TypedDict, total=False):
    code: str
    category: str
    stage: str
    message: str


class ApplicationResponseFinalization(TypedDict, total=False):
    status: ApplicationResponseFinalizationStatus
    run_record_built: bool
    persisted: bool
    persistence_record_id: str | None
    audited: bool
    audit_event_id: str | None
    observability_emitted: bool
    observability_degraded: bool
    error_codes: list[str]


class ApplicationResponse(TypedDict, total=False):
    contract_version: str
    response_id: str
    request_id: str
    run_id: str
    status: ApplicationResponseStatus
    original_outcome: ApplicationResponseOutcome
    message: str
    data: ApplicationResponseData | None
    errors: list[ApplicationResponseError]
    warnings: list[ApplicationResponseWarning]
    metadata: ApplicationResponseMetadata
    finalization: ApplicationResponseFinalization
    response_fingerprint: str
