from __future__ import annotations

from typing import Any, Literal, TypedDict


SQL_EXECUTION_CONTRACT_VERSION = (
    "v1.0.0-controlled-sql-execution"
)

SqlExecutionStatus = Literal[
    "success",
    "rejected",
    "infrastructure_error",
]

SqlExecutionFailureCategory = Literal[
    "none",
    "not_authorized",
    "request_invalid",
    "response_invalid",
    "row_limit_exceeded",
    "byte_limit_exceeded",
    "cell_limit_exceeded",
    "provider_failed",
    "timeout",
    "authentication_failed",
    "unexpected_error",
]

SqlExecutionErrorCode = Literal[
    "SQL_EXECUTION_NOT_AUTHORIZED",
    "SQL_EXECUTION_SECURITY_NOT_APPROVED",
    "SQL_EXECUTION_CONTRACT_NOT_APPROVED",
    "SQL_EXECUTION_PREFLIGHT_NOT_APPROVED",
    "SQL_EXECUTION_CAPABILITY_UNAVAILABLE",
    "SQL_EXECUTION_REQUEST_INVALID",
    "SQL_EXECUTION_PROVIDER_FAILED",
    "SQL_EXECUTION_TIMEOUT",
    "SQL_EXECUTION_AUTHENTICATION_FAILED",
    "SQL_EXECUTION_RESPONSE_INVALID",
    "SQL_EXECUTION_ROW_LIMIT_EXCEEDED",
    "SQL_EXECUTION_BYTE_LIMIT_EXCEEDED",
    "SQL_EXECUTION_CELL_LIMIT_EXCEEDED",
    "SQL_EXECUTION_UNEXPECTED_ERROR",
]


class SqlExecutionLimits(TypedDict):
    timeout_seconds: int
    max_rows: int
    max_response_bytes: int
    max_cell_bytes: int


class SqlExecutionContext(TypedDict, total=False):
    request_id: str
    run_id: str
    context_version: str
    intent_name: str
    dialect: str | None
    engine_hint: str | None


class SqlExecutionRequest(TypedDict):
    contract_version: str
    current_sql: str
    sql_fingerprint: str
    request_id: str
    run_id: str
    context_version: str
    intent_name: str
    query_plan_fingerprint: str
    preflight_fingerprint: str
    limits: SqlExecutionLimits
    attempt: int
    execution_id: str
    dialect: str | None
    engine_hint: str | None
    request_fingerprint: str


class SqlExecutionColumn(TypedDict, total=False):
    name: str
    type: str | None


SqlExecutionRow = dict[str, Any]


class SqlExecutionDiagnostic(TypedDict):
    execution_contract_version: str
    request_fingerprint: str
    response_fingerprint: str | None
    sql_fingerprint: str
    provider_name: str
    provider_version: str | None
    reason: str
    duration_ms: int | None
    executed: bool
    statement_type: str | None


class SqlExecutionMetrics(TypedDict):
    row_count: int
    rows_received: int
    rows_preserved: int
    bytes_received: int
    duration_ms: int | None


class SqlExecutionProviderResult(TypedDict, total=False):
    status: Literal["success", "rejected", "error"]
    provider_name: str
    provider_version: str
    request_fingerprint: str
    sql_fingerprint: str
    columns: list[SqlExecutionColumn]
    rows: list[SqlExecutionRow]
    row_count: int
    bytes_received: int
    duration_ms: int
    truncated: bool
    message: str
    error_code: SqlExecutionErrorCode
    failure_category: SqlExecutionFailureCategory
    warnings: list[str]
    executed: bool
    statement_type: str


class SqlExecutionResult(TypedDict):
    status: SqlExecutionStatus
    request_id: str
    run_id: str
    context_version: str
    intent_name: str
    query_plan_fingerprint: str
    preflight_fingerprint: str
    columns: list[SqlExecutionColumn]
    rows: list[SqlExecutionRow]
    row_count: int
    truncated: bool
    bytes_received: int
    duration_ms: int | None
    provider_name: str
    provider_version: str | None
    request_fingerprint: str
    response_fingerprint: str | None
    sql_fingerprint: str
    diagnostics: list[SqlExecutionDiagnostic]
    warnings: list[str]
    executed: bool
    statement_type: str | None
    error_code: SqlExecutionErrorCode | None
    failure_category: SqlExecutionFailureCategory
    metrics: SqlExecutionMetrics


class SqlExecutionInputError(ValueError):
    def __init__(
        self,
        code: SqlExecutionErrorCode,
        message: str,
        *,
        category: SqlExecutionFailureCategory = "request_invalid",
    ) -> None:
        self.code = code
        self.message = message
        self.category = category
        super().__init__(message)


class SqlExecutionProviderError(RuntimeError):
    pass
