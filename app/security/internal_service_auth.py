from __future__ import annotations

import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, TypedDict


INTERNAL_S2S_AUTHORIZATION_HEADER_MAX_BYTES = 1024
INTERNAL_S2S_TOKEN_MAX_BYTES = 512
INTERNAL_SERVICE_NAME = "product_original_bff"

InternalServiceAuthStatus = Literal[
    "authenticated",
    "unauthorized",
    "misconfigured",
]


class InternalServiceAuthResult(TypedDict, total=False):
    status: InternalServiceAuthStatus
    service_name: str
    error_code: str


@dataclass(frozen=True, slots=True)
class InternalServiceAuthConfig:
    expected_token: str = field(repr=False)
    service_name: str = INTERNAL_SERVICE_NAME

    def __post_init__(self) -> None:
        _validate_expected_token(self.expected_token)
        if self.service_name != INTERNAL_SERVICE_NAME:
            raise ValueError("internal service name is not supported.")


def authenticate_internal_service(
    headers: object,
    *,
    config: InternalServiceAuthConfig,
) -> InternalServiceAuthResult:
    if not isinstance(headers, Mapping):
        return _unauthorized()

    values = [
        value
        for name, value in headers.items()
        if isinstance(name, str) and name.casefold() == "authorization"
    ]
    if len(values) != 1:
        return _unauthorized()

    raw_value = values[0]
    if not isinstance(raw_value, str):
        return _unauthorized()

    encoded = raw_value.encode("utf-8")
    if len(encoded) > INTERNAL_S2S_AUTHORIZATION_HEADER_MAX_BYTES:
        return _unauthorized()

    prefix = "Bearer "
    if not raw_value.startswith(prefix):
        return _unauthorized()

    credential = raw_value[len(prefix) :]
    if not _valid_credential(credential):
        return _unauthorized()

    try:
        _validate_expected_token(config.expected_token)
    except ValueError:
        return {"status": "misconfigured", "error_code": "SERVICE_AUTH_MISCONFIGURED"}

    if not hmac.compare_digest(credential, config.expected_token):
        return _unauthorized()

    return {
        "status": "authenticated",
        "service_name": config.service_name,
    }


def strip_internal_auth_headers(headers: object) -> dict[str, str]:
    if not isinstance(headers, Mapping):
        return {}
    return {
        str(name): str(value)
        for name, value in headers.items()
        if isinstance(name, str)
        and name.casefold() not in {"authorization", "cookie"}
    }


def _unauthorized() -> InternalServiceAuthResult:
    return {
        "status": "unauthorized",
        "error_code": "UNAUTHORIZED_SERVICE",
    }


def _validate_expected_token(value: object) -> None:
    if not _valid_credential(value):
        raise ValueError("LANGGRAPH_S2S_TOKEN must be configured.")


def _valid_credential(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if value != value.strip():
        return False
    if any(char.isspace() for char in value):
        return False
    if any(ord(char) < 33 or ord(char) == 127 for char in value):
        return False
    return len(value.encode("utf-8")) <= INTERNAL_S2S_TOKEN_MAX_BYTES
