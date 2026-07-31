from __future__ import annotations

from typing import Literal, TypedDict

from app.domain.run_record_types import RunRecord


PersistenceStatus = Literal[
    "persisted",
    "already_persisted",
    "rejected",
    "error",
]
PersistenceFailureCategory = Literal[
    "none",
    "request_invalid",
    "fingerprint_mismatch",
    "conflict",
    "timeout",
    "authentication_failed",
    "unavailable",
    "unexpected_error",
]
PersistenceErrorCode = Literal[
    "PERSIST_RUN_REQUEST_INVALID",
    "PERSIST_RUN_FINGERPRINT_MISMATCH",
    "PERSIST_RUN_CONFLICT",
    "PERSIST_RUN_TIMEOUT",
    "PERSIST_RUN_AUTHENTICATION_FAILED",
    "PERSIST_RUN_UNAVAILABLE",
    "PERSIST_RUN_UNEXPECTED_ERROR",
]


class PersistenceDiagnostic(TypedDict, total=False):
    code: PersistenceErrorCode
    message: str
    failure_category: PersistenceFailureCategory
    safe_details: dict[str, str | int | bool | None]


class PersistRunRequest(TypedDict):
    run_record: RunRecord
    run_record_fingerprint: str
    idempotency_key: str
    contract_version: str


class PersistRunResult(TypedDict):
    status: PersistenceStatus
    record_id: str | None
    persisted_fingerprint: str | None
    idempotency_key: str
    failure_category: PersistenceFailureCategory
    diagnostic: PersistenceDiagnostic | None
    duration_ms: int | None
