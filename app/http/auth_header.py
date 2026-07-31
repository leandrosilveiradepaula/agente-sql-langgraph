from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from app.http.http_request_types import HttpRequestEnvelope
from app.security.auth_types import (
    AuthSecurityLimits,
    BearerCredential,
)


class AuthorizationHeaderError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def extract_bearer_credential(
    request: HttpRequestEnvelope,
    *,
    limits: AuthSecurityLimits,
) -> BearerCredential:
    envelope = deepcopy(request)
    headers = envelope.get("headers", {})
    if not isinstance(headers, Mapping):
        raise AuthorizationHeaderError("AUTHORIZATION_HEADER_INVALID")
    values = [
        value
        for name, value in headers.items()
        if isinstance(name, str) and name.casefold() == "authorization"
    ]
    if not values:
        raise AuthorizationHeaderError("AUTHORIZATION_HEADER_REQUIRED")
    if len(values) > 1:
        raise AuthorizationHeaderError("AUTHORIZATION_HEADER_AMBIGUOUS")
    value = values[0]
    if not isinstance(value, str):
        raise AuthorizationHeaderError("AUTHORIZATION_HEADER_INVALID")
    if len(value.encode("utf-8")) > limits["max_authorization_header_bytes"]:
        raise AuthorizationHeaderError("AUTHORIZATION_HEADER_INVALID")
    if "," in value:
        raise AuthorizationHeaderError("AUTHORIZATION_HEADER_AMBIGUOUS")
    if not value.casefold().startswith("bearer "):
        raise AuthorizationHeaderError("AUTHORIZATION_SCHEME_UNSUPPORTED")
    if value[:7].casefold() != "bearer ":
        raise AuthorizationHeaderError("AUTHORIZATION_SCHEME_UNSUPPORTED")
    credential = value[7:]
    if not credential:
        raise AuthorizationHeaderError("AUTHORIZATION_CREDENTIAL_REQUIRED")
    if credential != credential.strip():
        raise AuthorizationHeaderError("AUTHORIZATION_HEADER_INVALID")
    if " " in credential or "\t" in credential:
        raise AuthorizationHeaderError("AUTHORIZATION_HEADER_INVALID")
    _validate_text(
        credential,
        limits["max_credential_bytes"],
        "credential",
    )
    return BearerCredential(credential)


def _validate_text(value: str, max_bytes: int, field: str) -> None:
    if len(value.encode("utf-8")) > max_bytes:
        code = (
            "AUTHORIZATION_CREDENTIAL_TOO_LARGE"
            if field == "credential"
            else "AUTHORIZATION_HEADER_INVALID"
        )
        raise AuthorizationHeaderError(code)
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        code = (
            "AUTHORIZATION_CREDENTIAL_INVALID_CHARACTER"
            if field == "credential"
            else "AUTHORIZATION_HEADER_INVALID"
        )
        raise AuthorizationHeaderError(code)
