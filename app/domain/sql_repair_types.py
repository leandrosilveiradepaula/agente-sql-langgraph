from __future__ import annotations

from typing import Any, Literal, TypedDict


SQL_REPAIR_CONTRACT_VERSION = "v1.0.0-controlled-sql-repair-loop"

SqlRepairStatus = Literal[
    "not_run",
    "processing",
    "repaired",
    "rejected",
    "infrastructure_error",
]

SqlRepairReason = Literal[
    "not_run",
    "sql_repair_applied",
    "sql_repair_disabled",
    "sql_repair_limit_reached",
    "sql_repair_preflight_not_repairable",
    "sql_repair_request_invalid",
    "sql_repair_provider_failed",
    "sql_repair_response_empty",
    "sql_repair_response_invalid",
    "sql_repair_multiple_statements",
    "sql_repair_non_read_only",
    "sql_repair_unchanged_sql",
    "sql_repair_repeated_sql",
    "sql_repair_unexpected_error",
]

SQL_REPAIR_REASONS: frozenset[str] = frozenset(
    SqlRepairReason.__args__  # type: ignore[attr-defined]
)

SqlRepairErrorCode = Literal[
    "SQL_REPAIR_DISABLED",
    "SQL_REPAIR_LIMIT_REACHED",
    "SQL_REPAIR_PREFLIGHT_NOT_REPAIRABLE",
    "SQL_REPAIR_REQUEST_INVALID",
    "SQL_REPAIR_PROVIDER_FAILED",
    "SQL_REPAIR_RESPONSE_EMPTY",
    "SQL_REPAIR_RESPONSE_INVALID",
    "SQL_REPAIR_MULTIPLE_STATEMENTS",
    "SQL_REPAIR_NON_READ_ONLY",
    "SQL_REPAIR_UNCHANGED_SQL",
    "SQL_REPAIR_REPEATED_SQL",
    "SQL_REPAIR_UNEXPECTED_ERROR",
]


class SqlRepairFailure(TypedDict, total=False):
    stage: str
    category: str
    code: str
    message: str
    provider_code: str | None
    sqlstate: str | None
    position: int | None
    line: int | None
    column: int | None
    related_object: str | None
    sanitized_hint: str | None
    repairable: bool


class SqlRepairInstruction(TypedDict):
    name: str
    content: str


class SqlRepairHistoryEntry(TypedDict, total=False):
    attempt: int
    failed_stage: str
    failure_category: str
    provider_code: str | None
    error_code: str | None
    sql_before_fingerprint: str
    sql_after_fingerprint: str | None
    request_fingerprint: str
    response_fingerprint: str | None
    repair_applied: bool
    reason: SqlRepairReason
    provider_name: str
    provider_model: str | None
    token_usage: dict[str, int | str | None]
    duration_ms: int | None
    errors: list[dict[str, Any]]
    warnings: list[str]


class SqlRepairContext(TypedDict):
    context_version: str
    context_fingerprint: str
    planner_version: str
    intent_name: str
    selected_pattern: dict[str, Any]
    allowed_schemas: list[str]
    authorized_tables: list[dict[str, Any]]
    catalog_columns: dict[str, list[dict[str, Any]]]
    authorized_joins: list[dict[str, Any]]


class SqlRepairRequest(TypedDict):
    contract_version: str
    current_sql: str
    current_sql_fingerprint: str
    attempt: int
    max_attempts: int
    repair_context: SqlRepairContext
    failure: SqlRepairFailure
    previous_attempts: list[SqlRepairHistoryEntry]
    instructions: list[SqlRepairInstruction]
    output_constraints: list[str]
    request_fingerprint: str


class SqlRepairProviderResult(TypedDict, total=False):
    provider_name: str
    provider_model: str
    output_text: str
    raw_response: Any
    duration_ms: int
    token_usage: dict[str, int | str | None]
    warnings: list[str]


class SqlRepairDiagnostic(TypedDict):
    repair_contract_version: str
    request_fingerprint: str
    response_fingerprint: str | None
    sql_before_fingerprint: str
    sql_after_fingerprint: str | None
    repair_applied: bool
    reason: SqlRepairReason
    attempt: int
    max_attempts: int
    provider_name: str
    provider_model: str | None
    token_usage: dict[str, int | str | None]
    duration_ms: int | None


class SqlRepairResult(TypedDict):
    status: SqlRepairStatus
    sql: str | None
    error_code: SqlRepairErrorCode | None
    message: str
    repair_applied: bool
    reason: SqlRepairReason
    diagnostic: SqlRepairDiagnostic
    history_entry: SqlRepairHistoryEntry | None
    warnings: list[str]


class SqlRepairInputError(ValueError):
    def __init__(
        self,
        code: SqlRepairErrorCode,
        message: str,
        *,
        reason: SqlRepairReason = "sql_repair_request_invalid",
    ) -> None:
        self.code = code
        self.message = message
        self.reason = reason
        super().__init__(message)


class SqlRepairProviderError(RuntimeError):
    pass
