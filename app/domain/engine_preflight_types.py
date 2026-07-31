from __future__ import annotations

from typing import Any, Literal, TypedDict


ENGINE_PREFLIGHT_CONTRACT_VERSION = (
    "v1.0.0-engine-preflight-validation"
)
DEFAULT_ENGINE_PREFLIGHT_TIMEOUT_MS = 5000

EnginePreflightStatus = Literal[
    "not_run",
    "approved",
    "rejected",
    "error",
]

EnginePreflightFailureCategory = Literal[
    "none",
    "syntax_error",
    "schema_not_found",
    "table_not_found",
    "column_not_found",
    "ambiguous_column",
    "function_not_found",
    "invalid_grouping",
    "invalid_ordering",
    "type_mismatch",
    "invalid_cast",
    "invalid_join",
    "invalid_cte",
    "invalid_subquery",
    "dialect_error",
    "planning_error",
    "unknown_sql_error",
    "provider_unavailable",
    "authentication_failed",
    "timeout",
    "connection_failed",
    "protocol_error",
    "capability_unavailable",
    "adapter_error",
]

EnginePreflightErrorCode = Literal[
    "ENGINE_PREFLIGHT_SQL_MISSING",
    "ENGINE_PREFLIGHT_PLAN_MISSING",
    "ENGINE_PREFLIGHT_SECURITY_NOT_APPROVED",
    "ENGINE_PREFLIGHT_CONTRACT_NOT_APPROVED",
    "ENGINE_PREFLIGHT_REQUEST_INVALID",
    "ENGINE_PREFLIGHT_SYNTAX_ERROR",
    "ENGINE_PREFLIGHT_SCHEMA_NOT_FOUND",
    "ENGINE_PREFLIGHT_TABLE_NOT_FOUND",
    "ENGINE_PREFLIGHT_COLUMN_NOT_FOUND",
    "ENGINE_PREFLIGHT_AMBIGUOUS_COLUMN",
    "ENGINE_PREFLIGHT_FUNCTION_NOT_FOUND",
    "ENGINE_PREFLIGHT_INVALID_GROUPING",
    "ENGINE_PREFLIGHT_INVALID_ORDERING",
    "ENGINE_PREFLIGHT_TYPE_MISMATCH",
    "ENGINE_PREFLIGHT_INVALID_CAST",
    "ENGINE_PREFLIGHT_INVALID_JOIN",
    "ENGINE_PREFLIGHT_INVALID_CTE",
    "ENGINE_PREFLIGHT_INVALID_SUBQUERY",
    "ENGINE_PREFLIGHT_DIALECT_ERROR",
    "ENGINE_PREFLIGHT_PLANNING_ERROR",
    "ENGINE_PREFLIGHT_UNKNOWN_SQL_ERROR",
    "ENGINE_PREFLIGHT_PROVIDER_UNAVAILABLE",
    "ENGINE_PREFLIGHT_TIMEOUT",
    "ENGINE_PREFLIGHT_AUTHENTICATION_FAILED",
    "ENGINE_PREFLIGHT_CONNECTION_FAILED",
    "ENGINE_PREFLIGHT_PROTOCOL_ERROR",
    "ENGINE_PREFLIGHT_CAPABILITY_UNAVAILABLE",
    "ENGINE_PREFLIGHT_PROVIDER_FAILED",
    "ENGINE_PREFLIGHT_RESPONSE_INVALID",
    "ENGINE_PREFLIGHT_UNEXPECTED_ERROR",
]


class EnginePreflightCapabilities(TypedDict):
    supports_parse: bool
    supports_plan: bool
    supports_explain: bool
    supports_explain_analyze: bool
    syntax: bool
    schema_resolution: bool
    table_resolution: bool
    column_resolution: bool
    alias_resolution: bool
    function_resolution: bool
    grouping_validation: bool
    ordering_validation: bool
    type_validation: bool
    cast_validation: bool
    join_planning: bool
    cte_validation: bool
    subquery_validation: bool
    dialect_validation: bool
    explain_without_analyze: bool
    executes_query: bool
    returns_rows: bool
    supports_sqlstate: bool
    supports_error_position: bool
    supports_related_object: bool
    supported_dialects: list[str]


class EnginePreflightRequest(TypedDict, total=False):
    contract_version: str
    sql: str
    sql_fingerprint: str
    context_version: str
    context_fingerprint: str
    query_plan_fingerprint: str
    intent_name: str
    allowed_schemas: list[str]
    planned_tables: list[str]
    dialect: str | None
    engine_hint: str | None
    timeout_ms: int
    attempt: int
    request_fingerprint: str
    capabilities_requested: EnginePreflightCapabilities


class EnginePreflightFinding(TypedDict, total=False):
    code: EnginePreflightErrorCode
    category: EnginePreflightFailureCategory
    severity: Literal["error", "warning"]
    message: str
    repairable: bool
    provider_code: str | None
    sqlstate: str | None
    position: int | None
    line: int | None
    column: int | None
    related_object: str | None
    sanitized_hint: str | None
    details: dict[str, Any]


class EnginePreflightError(TypedDict, total=False):
    code: EnginePreflightErrorCode
    category: EnginePreflightFailureCategory
    message: str
    repairable: bool
    provider_code: str | None
    sqlstate: str | None
    position: int | None
    line: int | None
    column: int | None
    related_object: str | None
    sanitized_hint: str | None
    details: dict[str, Any]


class EnginePreflightDiagnostic(TypedDict):
    preflight_contract_version: str
    request_fingerprint: str
    sql_fingerprint: str
    context_version: str
    context_fingerprint: str
    query_plan_fingerprint: str
    provider_name: str
    provider_version: str | None
    duration_ms: int
    attempt: int
    capabilities_used: EnginePreflightCapabilities
    statement_planned: bool
    executed: bool
    rows_returned: int
    reason: str


class EnginePreflightProviderResult(TypedDict, total=False):
    status: Literal["approved", "rejected", "error"]
    provider_name: str
    provider_version: str
    duration_ms: int
    failure_category: EnginePreflightFailureCategory
    error_code: EnginePreflightErrorCode
    message: str
    repairable: bool
    provider_code: str
    sqlstate: str
    position: int
    line: int
    column: int
    related_object: str
    hint: str
    warnings: list[str]
    capabilities: EnginePreflightCapabilities
    statement_planned: bool
    executed: bool
    rows_returned: int


class EnginePreflightResult(TypedDict):
    status: EnginePreflightStatus
    approved: bool
    repairable: bool
    failure_category: EnginePreflightFailureCategory
    findings: list[EnginePreflightFinding]
    errors: list[EnginePreflightError]
    warnings: list[str]
    provider_name: str
    provider_version: str | None
    preflight_contract_version: str
    sql_fingerprint: str
    request_fingerprint: str
    context_version: str
    context_fingerprint: str
    query_plan_fingerprint: str
    duration_ms: int
    attempt: int
    capabilities_used: EnginePreflightCapabilities
    statement_planned: bool
    rows_returned: int
    executed: bool
    diagnostic: EnginePreflightDiagnostic


class EnginePreflightInputError(ValueError):
    def __init__(
        self,
        code: EnginePreflightErrorCode,
        message: str,
    ) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class EnginePreflightProviderError(RuntimeError):
    pass
