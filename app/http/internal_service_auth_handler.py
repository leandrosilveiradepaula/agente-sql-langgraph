from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.http.http_request_types import HttpRequestEnvelope
from app.http.http_response_types import HttpResponseEnvelope
from app.http.security_headers import security_headers
from app.security.internal_service_auth import (
    InternalServiceAuthConfig,
    authenticate_internal_service,
    strip_internal_auth_headers,
)


class InternalServiceAuthHttpHandler:
    def __init__(
        self,
        *,
        inner: Any,
        auth_config: InternalServiceAuthConfig,
    ) -> None:
        if inner is None or not callable(getattr(inner, "handle", None)):
            raise RuntimeError("inner HTTP handler must be injected.")
        self._inner = inner
        self._auth_config = auth_config

    def handle(self, request: HttpRequestEnvelope) -> HttpResponseEnvelope:
        result = authenticate_internal_service(
            request.get("headers", {}),
            config=self._auth_config,
        )
        if result.get("status") == "misconfigured":
            return _safe_error_response("SERVICE_AUTH_MISCONFIGURED", 503)
        if result.get("status") != "authenticated":
            return _safe_error_response("UNAUTHORIZED_SERVICE", 401)

        forwarded = deepcopy(request)
        forwarded["headers"] = strip_internal_auth_headers(request.get("headers", {}))
        return self._inner.handle(forwarded)


def protect_internal_service_http_handler(
    *,
    inner: Any,
    auth_config: InternalServiceAuthConfig,
) -> InternalServiceAuthHttpHandler:
    return InternalServiceAuthHttpHandler(inner=inner, auth_config=auth_config)


def _safe_error_response(code: str, status_code: int) -> HttpResponseEnvelope:
    body = json.dumps(
        {"error": {"code": code}},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    headers = security_headers()
    headers["Content-Type"] = "application/json; charset=utf-8"
    if status_code == 401:
        headers["WWW-Authenticate"] = "Bearer"
    return {"status_code": status_code, "headers": headers, "body": body}
