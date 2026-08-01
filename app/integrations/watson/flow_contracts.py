from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Literal, TypedDict

from app.integrations.watson.flow_limits import (
    WatsonFlowContractError,
    WatsonFlowLimits,
    default_watson_flow_limits,
)
from app.integrations.watson.iam_contracts import SensitiveBearerToken


WatsonFlowPurpose = Literal["preflight", "execution"]
WatsonFlowRunStatus = Literal[
    "success",
    "http_error",
    "unavailable",
    "timeout",
    "invalid_response",
    "authentication_failed",
    "rate_limited",
    "unexpected_error",
]


class WatsonFlowRunRequest(TypedDict):
    flow_id: str
    bearer_token: SensitiveBearerToken
    payload: dict[str, object]
    request_id: str
    run_id: str
    invocation_id: str
    timeout_seconds: int
    purpose: WatsonFlowPurpose


class WatsonFlowRunResult(TypedDict, total=False):
    status: WatsonFlowRunStatus
    http_status: int | None
    raw_output: object
    retry_after_seconds: int | None
    invocation_id: str
    duration_ms: int | None
    public_error_code: str
    public_error_message: str
    diagnostics: dict[str, Any]


class RedactedWatsonFlowRunResult(dict):
    def __repr__(self) -> str:
        safe = dict(self)
        if "raw_output" in safe:
            safe["raw_output"] = "<redacted>"
        return dict.__repr__(safe)

    def __str__(self) -> str:
        return self.__repr__()


def watson_flow_run_request(
    *,
    flow_id: str,
    bearer_token: SensitiveBearerToken,
    payload: Mapping[str, object],
    request_id: str,
    run_id: str,
    invocation_id: str,
    timeout_seconds: int,
    purpose: WatsonFlowPurpose,
    limits: WatsonFlowLimits | None = None,
) -> WatsonFlowRunRequest:
    safe_limits = limits or default_watson_flow_limits()
    if purpose not in {"preflight", "execution"}:
        raise WatsonFlowContractError("purpose invalido.")
    if not isinstance(bearer_token, SensitiveBearerToken):
        raise WatsonFlowContractError("bearer_token invalido.")
    for field_name, value, maximum in (
        ("flow_id", flow_id, safe_limits.max_flow_id_bytes),
        ("request_id", request_id, 256),
        ("run_id", run_id, 256),
        ("invocation_id", invocation_id, 256),
    ):
        _validate_text(value, field_name, maximum)
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0 or timeout_seconds > 300:
        raise WatsonFlowContractError("timeout_seconds invalido.")
    safe_payload = deepcopy(dict(payload))
    if set(safe_payload.keys()) != {"sql_query"}:
        raise WatsonFlowContractError("payload Watson deve conter somente sql_query.")
    if not isinstance(safe_payload["sql_query"], str):
        raise WatsonFlowContractError("sql_query deve ser texto.")
    return {
        "flow_id": flow_id,
        "bearer_token": bearer_token,
        "payload": safe_payload,
        "request_id": request_id,
        "run_id": run_id,
        "invocation_id": invocation_id,
        "timeout_seconds": timeout_seconds,
        "purpose": purpose,
    }


def watson_flow_success(
    raw_output: object,
    *,
    invocation_id: str,
    duration_ms: int | None = None,
) -> WatsonFlowRunResult:
    _validate_text(invocation_id, "invocation_id", 256)
    _validate_optional_non_negative(duration_ms, "duration_ms")
    return RedactedWatsonFlowRunResult({
        "status": "success",
        "raw_output": deepcopy(raw_output),
        "invocation_id": invocation_id,
        "duration_ms": duration_ms,
        "diagnostics": {},
    })


def watson_flow_failure(
    status: WatsonFlowRunStatus,
    *,
    invocation_id: str,
    http_status: int | None = None,
    retry_after_seconds: int | None = None,
    duration_ms: int | None = None,
    diagnostics: Mapping[str, Any] | None = None,
    limits: WatsonFlowLimits | None = None,
) -> WatsonFlowRunResult:
    if status == "success":
        raise WatsonFlowContractError("Use watson_flow_success para sucesso.")
    safe_limits = limits or default_watson_flow_limits()
    _validate_text(invocation_id, "invocation_id", 256)
    _validate_optional_non_negative(duration_ms, "duration_ms")
    if http_status is not None and (
        isinstance(http_status, bool)
        or not isinstance(http_status, int)
        or http_status < 100
        or http_status > 599
    ):
        raise WatsonFlowContractError("http_status invalido.")
    if retry_after_seconds is not None and (
        isinstance(retry_after_seconds, bool)
        or not isinstance(retry_after_seconds, int)
        or retry_after_seconds < 0
        or retry_after_seconds > safe_limits.max_retry_after_seconds
    ):
        raise WatsonFlowContractError("retry_after_seconds invalido.")
    code = {
        "http_error": "WATSON_FLOW_HTTP_ERROR",
        "unavailable": "WATSON_FLOW_UNAVAILABLE",
        "timeout": "WATSON_FLOW_TIMEOUT",
        "invalid_response": "WATSON_FLOW_INVALID_RESPONSE",
        "authentication_failed": "WATSON_FLOW_AUTHENTICATION_FAILED",
        "rate_limited": "WATSON_FLOW_RATE_LIMITED",
        "unexpected_error": "WATSON_FLOW_UNEXPECTED_ERROR",
    }[status]
    return RedactedWatsonFlowRunResult({
        "status": status,
        "http_status": http_status,
        "retry_after_seconds": retry_after_seconds,
        "invocation_id": invocation_id,
        "duration_ms": duration_ms,
        "public_error_code": code,
        "public_error_message": "Watson Flow falhou de forma estruturada.",
        "diagnostics": _sanitized_diagnostics(diagnostics),
    })


def _validate_text(value: object, name: str, maximum_bytes: int) -> None:
    if not isinstance(value, str) or not value.strip():
        raise WatsonFlowContractError(f"{name} deve ser texto nao vazio.")
    if len(value.encode("utf-8")) > maximum_bytes:
        raise WatsonFlowContractError(f"{name} excede limite.")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise WatsonFlowContractError(f"{name} contem controle.")


def _validate_optional_non_negative(value: int | None, name: str) -> None:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value < 0
    ):
        raise WatsonFlowContractError(f"{name} invalido.")


def _sanitized_diagnostics(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    output: dict[str, Any] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or key.casefold() in {
            "authorization",
            "headers",
            "body",
            "token",
            "access_token",
            "sql",
        }:
            continue
        if isinstance(raw, (str, int, bool)) or raw is None:
            text = str(raw).casefold()
            if "bearer" in text or "token" in text or "select " in text:
                continue
            output[key[:64]] = raw
    return output
