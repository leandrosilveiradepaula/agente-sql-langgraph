from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Literal, TypedDict

from app.integrations.watson.flow_limits import (
    WatsonFlowContractError,
    WatsonFlowLimits,
    default_watson_flow_limits,
)


IamTokenStatus = Literal[
    "success",
    "unavailable",
    "timeout",
    "invalid_response",
    "authentication_failed",
    "unexpected_error",
]


class IamTokenRequest(TypedDict, total=False):
    request_id: str
    run_id: str
    audience: str
    timeout_seconds: int
    force_refresh: bool


class SensitiveBearerToken:
    __slots__ = ("_value",)
    _value: str

    def __init__(
        self,
        value: str,
        *,
        limits: WatsonFlowLimits | None = None,
    ) -> None:
        safe_limits = limits or default_watson_flow_limits()
        if not isinstance(value, str) or not value:
            raise WatsonFlowContractError("Token sensivel invalido.")
        if len(value.encode("utf-8")) > safe_limits.max_access_token_bytes:
            raise WatsonFlowContractError("Token sensivel excede limite.")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise WatsonFlowContractError("Token sensivel contem controle.")
        object.__setattr__(self, "_value", value)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("SensitiveBearerToken e imutavel.")

    def reveal_for_client(self) -> str:
        return self._value

    def __deepcopy__(self, memo: dict[int, object]) -> "SensitiveBearerToken":
        del memo
        return self

    def __repr__(self) -> str:
        return "SensitiveBearerToken(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"


class IamTokenResult(TypedDict, total=False):
    status: IamTokenStatus
    token: SensitiveBearerToken
    token_type: str | None
    expires_in: int | None
    expires_at: int | None
    public_error_code: str
    public_error_message: str
    diagnostics: dict[str, Any]


_ERROR_MESSAGES = {
    "unavailable": "IAM token provider indisponivel.",
    "timeout": "IAM token provider excedeu o timeout.",
    "invalid_response": "IAM token provider retornou resposta invalida.",
    "authentication_failed": "IAM token provider recusou autenticacao.",
    "unexpected_error": "IAM token provider falhou.",
}


def iam_token_request(
    *,
    request_id: str,
    run_id: str,
    timeout_seconds: int,
    audience: str | None = None,
    force_refresh: bool = False,
) -> IamTokenRequest:
    if not _safe_text(request_id) or not _safe_text(run_id):
        raise WatsonFlowContractError("request_id/run_id invalidos.")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0 or timeout_seconds > 300:
        raise WatsonFlowContractError("timeout_seconds invalido.")
    if not isinstance(force_refresh, bool):
        raise WatsonFlowContractError("force_refresh deve ser bool.")
    request: IamTokenRequest = {
        "request_id": request_id,
        "run_id": run_id,
        "timeout_seconds": timeout_seconds,
        "force_refresh": force_refresh,
    }
    if audience is not None:
        if not _safe_text(audience):
            raise WatsonFlowContractError("audience invalida.")
        request["audience"] = audience
    return deepcopy(request)


def iam_token_success(
    token: SensitiveBearerToken,
    *,
    token_type: str | None = "Bearer",
    expires_in: int | None = None,
    expires_at: int | None = None,
) -> IamTokenResult:
    if not isinstance(token, SensitiveBearerToken):
        raise WatsonFlowContractError("token deve ser SensitiveBearerToken.")
    if token_type is not None and token_type != "Bearer":
        raise WatsonFlowContractError("token_type deve ser Bearer.")
    for name, value in (("expires_in", expires_in), ("expires_at", expires_at)):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
        ):
            raise WatsonFlowContractError(f"{name} invalido.")
    return {
        "status": "success",
        "token": token,
        "token_type": token_type,
        "expires_in": expires_in,
        "expires_at": expires_at,
        "diagnostics": {},
    }


def iam_token_failure(
    status: IamTokenStatus,
    *,
    diagnostics: Mapping[str, Any] | None = None,
) -> IamTokenResult:
    if status == "success" or status not in _ERROR_MESSAGES:
        raise WatsonFlowContractError("status de falha IAM invalido.")
    return {
        "status": status,
        "public_error_code": f"IAM_TOKEN_{status.upper()}",
        "public_error_message": _ERROR_MESSAGES[status],
        "diagnostics": _sanitized_diagnostics(diagnostics),
    }


def _sanitized_diagnostics(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    output: dict[str, Any] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or key.casefold() in {
            "token",
            "access_token",
            "authorization",
            "apikey",
            "api_key",
            "body",
            "headers",
        }:
            continue
        if isinstance(raw, (str, int, bool)) or raw is None:
            text = str(raw)
            lowered = text.casefold()
            if "bearer" in lowered or "apikey" in lowered or "token" in lowered:
                continue
            output[key[:64]] = raw
    return output


def _safe_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not any(
        ord(char) < 32 or ord(char) == 127 for char in value
    )
