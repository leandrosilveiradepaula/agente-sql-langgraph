from __future__ import annotations

from typing import Any, Literal, TypedDict

from app.domain.application_response_types import ApplicationResponseLimits
from app.domain.result_normalization_types import (
    ResultNormalizationLimits,
)
from app.domain.run_record_types import RunFinalizationLimits


APPLICATION_REQUEST_CONTRACT_VERSION = (
    "v1.0.0-application-service-request"
)

ApplicationRequestStatus = Literal["valid", "invalid"]
ApplicationRequestErrorCode = Literal[
    "APPLICATION_REQUEST_INVALID",
    "APPLICATION_REQUEST_QUESTION_REQUIRED",
    "APPLICATION_REQUEST_QUESTION_TOO_LARGE",
    "APPLICATION_REQUEST_CONTROL_CHARACTER",
    "APPLICATION_REQUEST_OPTIONS_INVALID",
    "APPLICATION_REQUEST_ID_INVALID",
    "APPLICATION_REQUEST_USER_INVALID",
]


class ApplicationRequestDiagnostic(TypedDict, total=False):
    code: ApplicationRequestErrorCode
    field: str
    message: str


class ApplicationRequestUser(TypedDict, total=False):
    id: str
    email: str
    profile: str
    organization_id: str


class ApplicationRequestOptions(TypedDict, total=False):
    use_cache: bool
    max_repair_attempts: int
    shadow_mode: bool
    sql_execution_limits: dict[str, int]
    result_normalization_limits: ResultNormalizationLimits
    run_finalization_limits: RunFinalizationLimits
    application_response_limits: ApplicationResponseLimits
    execution_attempt: int
    timeout_seconds: int


class ApplicationExecutionContext(TypedDict, total=False):
    correlation_id: str
    client_request_id: str
    metadata: dict[str, str | int | bool | None]


class ApplicationRequest(TypedDict, total=False):
    contract_version: str
    question: str
    request_id: str
    run_id: str
    user: ApplicationRequestUser
    options: ApplicationRequestOptions
    correlation_id: str
    client_request_id: str
    metadata: dict[str, str | int | bool | None]


class ApplicationServiceLimits(TypedDict):
    max_question_bytes: int
    max_user_id_length: int
    max_email_length: int
    max_profile_length: int
    max_organization_id_length: int
    max_metadata_entries: int
    max_metadata_key_length: int
    max_metadata_value_length: int
    max_request_id_length: int
    max_run_id_length: int
    max_correlation_id_length: int
    max_client_request_id_length: int


ApplicationRequestMapping = dict[str, Any]
