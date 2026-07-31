from __future__ import annotations

from typing import Literal, TypedDict


AuditOutcome = Literal["success", "rejected", "infrastructure_error"]
AuditStatus = Literal["written", "already_written", "rejected", "error"]
AuditFailureCategory = Literal[
    "none",
    "request_invalid",
    "fingerprint_mismatch",
    "conflict",
    "timeout",
    "authentication_failed",
    "unexpected_error",
]
AuditErrorCode = Literal[
    "AUDIT_REQUEST_INVALID",
    "AUDIT_FINGERPRINT_MISMATCH",
    "AUDIT_CONFLICT",
    "AUDIT_TIMEOUT",
    "AUDIT_AUTHENTICATION_FAILED",
    "AUDIT_UNEXPECTED_ERROR",
]


class AuditActor(TypedDict, total=False):
    profile: str


class AuditSubject(TypedDict):
    request_id: str
    run_id: str


class AuditDiagnostic(TypedDict, total=False):
    code: AuditErrorCode
    message: str
    failure_category: AuditFailureCategory


class AuditEvent(TypedDict, total=False):
    event_id: str
    event_type: str
    idempotency_key: str
    request_id: str
    run_id: str
    actor: AuditActor
    subject: AuditSubject
    outcome: AuditOutcome
    final_status: str
    failure_stage: str
    intent_name: str | None
    context_version: str
    fingerprints: dict[str, str | None]
    repair_attempts: int
    row_count: int
    error_codes: list[str]
    warning_codes: list[str]
    persistence_record_id: str
    fingerprint: str


class AuditResult(TypedDict):
    status: AuditStatus
    event_id: str | None
    event_fingerprint: str | None
    idempotency_key: str
    failure_category: AuditFailureCategory
    diagnostic: AuditDiagnostic | None
    duration_ms: int | None
