from __future__ import annotations

from typing import Literal, TypedDict


ObservabilityStatus = Literal["emitted", "degraded"]
ObservabilityErrorCode = Literal[
    "OBSERVABILITY_EMIT_FAILED",
    "OBSERVABILITY_TIMEOUT",
    "OBSERVABILITY_UNEXPECTED_ERROR",
]


class ObservabilityAttribute(TypedDict):
    key: str
    value: str | int | bool | None
    metric_label: bool


class ObservabilityMetric(TypedDict):
    name: str
    value: int | float
    labels: dict[str, str]


class ObservabilitySpan(TypedDict, total=False):
    name: str
    stage: str
    status: str
    duration_ms: int | None
    attributes: list[ObservabilityAttribute]


class ObservabilityDiagnostic(TypedDict, total=False):
    code: ObservabilityErrorCode
    message: str


class ObservabilityEvent(TypedDict, total=False):
    operation_name: str
    stage: str
    status: str
    outcome: str
    duration_ms: int | None
    metrics: list[ObservabilityMetric]
    spans: list[ObservabilitySpan]
    attributes: list[ObservabilityAttribute]
    error_codes: list[str]
    warning_codes: list[str]
    fingerprint: str


class ObservabilityResult(TypedDict):
    status: ObservabilityStatus
    event_fingerprint: str | None
    diagnostic: ObservabilityDiagnostic | None
    duration_ms: int | None
