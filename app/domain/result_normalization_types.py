from __future__ import annotations

from typing import Any, Literal, TypedDict


RESULT_NORMALIZATION_CONTRACT_VERSION = (
    "v1.0.0-deterministic-result-normalization"
)
RESULT_SERIALIZATION_CONTRACT_VERSION = (
    "v1.0.0-deterministic-result-serialization"
)

NormalizedValueType = Literal[
    "null",
    "boolean",
    "integer",
    "decimal",
    "float",
    "string",
    "date",
    "datetime",
    "time",
    "binary",
    "json",
    "uuid",
]

NormalizationStatus = Literal["success", "rejected", "error"]
SerializationStatus = Literal["success", "rejected", "error"]

NormalizationErrorCode = Literal[
    "RESULT_NORMALIZATION_EXECUTION_INVALID",
    "RESULT_NORMALIZATION_LIMIT_EXCEEDED",
    "RESULT_NORMALIZATION_SHAPE_INVALID",
    "RESULT_NORMALIZATION_VALUE_INVALID",
    "RESULT_NORMALIZATION_UNEXPECTED_ERROR",
]

SerializationErrorCode = Literal[
    "RESULT_SERIALIZATION_INPUT_INVALID",
    "RESULT_SERIALIZATION_LIMIT_EXCEEDED",
    "RESULT_SERIALIZATION_VALUE_INVALID",
    "RESULT_SERIALIZATION_UNEXPECTED_ERROR",
]


class ResultNormalizationLimits(TypedDict):
    max_rows: int
    max_columns: int
    max_total_cells: int
    max_nesting_depth: int
    max_collection_items: int
    max_serialized_bytes: int
    max_diagnostic_entries: int


class ResultLineage(TypedDict, total=False):
    request_id: str
    run_id: str
    context_version: str
    intent_name: str
    sql_fingerprint: str
    query_plan_fingerprint: str
    preflight_fingerprint: str
    execution_request_fingerprint: str
    execution_response_fingerprint: str | None
    execution_provider_name: str
    execution_provider_version: str | None
    execution_duration_ms: int | None
    normalized_result_fingerprint: str
    serialized_result_fingerprint: str
    row_count: int
    column_count: int
    estimated_bytes: int
    truncated: bool
    execution_contract_version: str
    normalization_contract_version: str
    serialization_contract_version: str


class NormalizedColumn(TypedDict, total=False):
    ordinal: int
    original_name: str
    provider_type_name: str | None
    normalized_type: NormalizedValueType
    nullable: bool | None
    precision: int | None
    scale: int | None
    timezone: bool | None
    metadata: dict[str, Any]


class NormalizedCell(TypedDict, total=False):
    type: NormalizedValueType
    value: Any
    special: str | None
    timezone: bool | None
    encoding: str | None


class NormalizedRow(TypedDict):
    ordinal: int
    cells: list[NormalizedCell]


class NormalizationDiagnostic(TypedDict, total=False):
    code: NormalizationErrorCode
    message: str
    row_ordinal: int | None
    column_ordinal: int | None
    normalized_type: str | None
    size: int | None
    fingerprint: str | None


class NormalizationMetrics(TypedDict):
    row_count: int
    column_count: int
    total_cells: int
    estimated_bytes: int
    max_nesting_depth: int
    diagnostic_count: int


class NormalizedQueryResult(TypedDict):
    status: NormalizationStatus
    contract_version: str
    columns: list[NormalizedColumn]
    rows: list[NormalizedRow]
    lineage: ResultLineage
    metrics: NormalizationMetrics
    diagnostics: list[NormalizationDiagnostic]
    warnings: list[str]
    error_code: NormalizationErrorCode | None
    result_fingerprint: str | None


class SerializedColumn(TypedDict, total=False):
    ordinal: int
    original_name: str
    provider_type_name: str | None
    normalized_type: NormalizedValueType
    nullable: bool | None
    precision: int | None
    scale: int | None
    timezone: bool | None
    metadata: dict[str, Any]


class SerializedRow(TypedDict):
    ordinal: int
    cells: list[dict[str, Any]]


class SerializationDiagnostic(TypedDict, total=False):
    code: SerializationErrorCode
    message: str
    row_ordinal: int | None
    column_ordinal: int | None
    normalized_type: str | None
    size: int | None
    fingerprint: str | None


class SerializedQueryResult(TypedDict):
    status: SerializationStatus
    contract_version: str
    columns: list[SerializedColumn]
    rows: list[SerializedRow]
    lineage: ResultLineage
    diagnostics: list[SerializationDiagnostic]
    warnings: list[str]
    error_code: SerializationErrorCode | None
    result_fingerprint: str | None
    canonical_json: str | None
