from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Protocol

from app.application.internal_sql_agent_v1_types import (
    ExecuteApprovedSqlShadowV1Request,
    GenerateSqlV1Request,
)
from app.http.http_request import (
    HttpRequestError,
    default_http_request_limits,
    parse_http_request_json,
    validate_http_body_transport,
    validate_http_request_limits,
)
from app.http.http_request_types import HttpRequestEnvelope
from app.http.http_response import (
    default_http_response_limits,
    validate_http_response_limits,
)
from app.http.http_response_types import HttpResponseEnvelope
from app.http.security_headers import security_headers


class GenerateSqlService(Protocol):
    def execute(self, request: GenerateSqlV1Request) -> Mapping[str, Any]:
        ...


class ExecuteApprovedSqlShadowService(Protocol):
    def execute(
        self,
        request: ExecuteApprovedSqlShadowV1Request,
    ) -> Mapping[str, Any]:
        ...


_GENERATE_ROUTE = "/v1/internal/sql-agent/generate"
_EXECUTE_APPROVED_SHADOW_ROUTE = (
    "/v1/internal/sql-agent/execute-approved-shadow"
)
_ALLOWED_ROUTES = {
    _GENERATE_ROUTE,
    _EXECUTE_APPROVED_SHADOW_ROUTE,
}
_STATUS_BY_HTTP_ERROR = {
    "HTTP_BODY_TOO_LARGE": 413,
    "HTTP_CONTENT_TYPE_REQUIRED": 415,
    "HTTP_UNSUPPORTED_MEDIA_TYPE": 415,
    "HTTP_CHARSET_UNSUPPORTED": 415,
    "HTTP_METHOD_NOT_ALLOWED": 405,
    "HTTP_NOT_ACCEPTABLE": 406,
    "HTTP_ROUTE_NOT_FOUND": 404,
}


class InternalSqlAgentV1HttpHandler:
    def __init__(
        self,
        *,
        generate_use_case: GenerateSqlService,
        execute_approved_shadow_use_case: ExecuteApprovedSqlShadowService,
        request_limits: Mapping[str, Any] | None = None,
        response_limits: Mapping[str, Any] | None = None,
    ) -> None:
        if generate_use_case is None or not callable(
            getattr(generate_use_case, "execute", None)
        ):
            raise RuntimeError("generate_use_case deve ser injetado.")
        if execute_approved_shadow_use_case is None or not callable(
            getattr(execute_approved_shadow_use_case, "execute", None)
        ):
            raise RuntimeError(
                "execute_approved_shadow_use_case deve ser injetado."
            )
        if request_limits is None:
            request_limits = default_http_request_limits()
        if response_limits is None:
            response_limits = default_http_response_limits()
        self._generate = generate_use_case
        self._execute_shadow = execute_approved_shadow_use_case
        self._request_limits = validate_http_request_limits(request_limits)
        self._response_limits = validate_http_response_limits(response_limits)

    def handle(self, request: HttpRequestEnvelope) -> HttpResponseEnvelope:
        try:
            envelope = deepcopy(request)
            _validate_internal_route(envelope)
            validate_http_body_transport(
                envelope,
                limits=self._request_limits,
            )
            payload = parse_http_request_json(
                envelope,
                limits=self._request_limits,
            )
            path = str(envelope.get("path", ""))
            if path == _GENERATE_ROUTE:
                response = self._generate.execute(
                    deepcopy(payload)  # type: ignore[arg-type]
                )
            else:
                response = self._execute_shadow.execute(
                    deepcopy(payload)  # type: ignore[arg-type]
                )
            if not _valid_internal_response(response):
                return self._error_response(
                    "INTERNAL_HTTP_RESPONSE_INVALID",
                    status_code=500,
                    status="infrastructure_error",
                )
            return _to_http_response(
                response,
                response_limits=self._response_limits,
            )
        except HttpRequestError as error:
            return self._error_response(
                error.code,
                status_code=_STATUS_BY_HTTP_ERROR.get(error.code, 400),
                status="rejected",
                allow=error.code == "HTTP_METHOD_NOT_ALLOWED",
            )
        except Exception:
            return self._error_response(
                "INTERNAL_HTTP_UNEXPECTED_ERROR",
                status_code=500,
                status="infrastructure_error",
            )

    def _error_response(
        self,
        code: str,
        *,
        status_code: int,
        status: str,
        allow: bool = False,
    ) -> HttpResponseEnvelope:
        response = {
            "contract_version": "1",
            "response_id": "",
            "agent_run_id": "",
            "run_id": "",
            "status": status,
            "message": (
                "Internal request rejected."
                if status == "rejected"
                else "Internal request could not be completed."
            ),
            "errors": [
                {
                    "code": _safe_code(code),
                    "stage": "internal_http",
                    "message": "Internal request could not be processed.",
                    "retryable": status == "infrastructure_error",
                }
            ],
            "metadata": {"lineage": {}},
            "response_fingerprint": "",
        }
        http = _to_http_response(
            _with_response_ids(response),
            response_limits=self._response_limits,
            status_code=status_code,
        )
        if allow:
            http["headers"]["Allow"] = "POST"
        return http


def create_internal_sql_agent_v1_http_handler(
    *,
    generate_use_case: GenerateSqlService,
    execute_approved_shadow_use_case: ExecuteApprovedSqlShadowService,
    request_limits: Mapping[str, Any] | None = None,
    response_limits: Mapping[str, Any] | None = None,
) -> InternalSqlAgentV1HttpHandler:
    return InternalSqlAgentV1HttpHandler(
        generate_use_case=generate_use_case,
        execute_approved_shadow_use_case=execute_approved_shadow_use_case,
        request_limits=request_limits,
        response_limits=response_limits,
    )


def _validate_internal_route(request: HttpRequestEnvelope) -> None:
    method = str(request.get("method", "")).upper()
    if method != "POST":
        raise HttpRequestError("HTTP_METHOD_NOT_ALLOWED")
    path = str(request.get("path", ""))
    if path not in _ALLOWED_ROUTES:
        raise HttpRequestError("HTTP_ROUTE_NOT_FOUND")
    headers = request.get("headers", {})
    if isinstance(headers, Mapping):
        for key in headers:
            if isinstance(key, str) and key.casefold() == "cookie":
                raise HttpRequestError("HTTP_JSON_INVALID")
        _validate_content_type(headers)
        _validate_accept(headers)


def _validate_content_type(headers: Mapping[str, str]) -> None:
    value = _header(headers, "content-type")
    if value is None or not value.strip():
        raise HttpRequestError("HTTP_CONTENT_TYPE_REQUIRED")
    parts = [part.strip().lower() for part in value.split(";")]
    if parts[0] != "application/json":
        raise HttpRequestError("HTTP_UNSUPPORTED_MEDIA_TYPE")
    for parameter in parts[1:]:
        if not parameter:
            continue
        if parameter != "charset=utf-8":
            if parameter.startswith("charset="):
                raise HttpRequestError("HTTP_CHARSET_UNSUPPORTED")
            raise HttpRequestError("HTTP_UNSUPPORTED_MEDIA_TYPE")


def _validate_accept(headers: Mapping[str, str]) -> None:
    value = _header(headers, "accept")
    if value is None or not value.strip():
        return
    for item in value.split(","):
        media_type = item.split(";", 1)[0].strip().lower()
        if media_type in {"application/json", "*/*"}:
            return
    raise HttpRequestError("HTTP_NOT_ACCEPTABLE")


def _header(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.casefold() == name.casefold():
            return value
    return None


def _valid_internal_response(response: object) -> bool:
    if not isinstance(response, Mapping):
        return False
    required = {
        "contract_version",
        "response_id",
        "agent_run_id",
        "run_id",
        "status",
        "message",
        "errors",
        "metadata",
        "response_fingerprint",
    }
    if not required <= set(response):
        return False
    if response.get("contract_version") != "1":
        return False
    if response.get("status") not in {
        "success",
        "rejected",
        "infrastructure_error",
    }:
        return False
    if not isinstance(response.get("errors"), list):
        return False
    if not isinstance(response.get("metadata"), Mapping):
        return False
    fingerprint = response.get("response_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        return False
    payload = deepcopy(dict(response))
    payload.pop("response_fingerprint", None)
    from app.domain.result_normalization import stable_fingerprint

    return stable_fingerprint(payload) == fingerprint


def _to_http_response(
    response: Mapping[str, Any],
    *,
    response_limits: Mapping[str, int],
    status_code: int | None = None,
) -> HttpResponseEnvelope:
    body = json.dumps(
        deepcopy(dict(response)),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(body) > response_limits["max_response_body_bytes"]:
        body = b'{"contract_version":"1","status":"infrastructure_error","errors":[{"code":"HTTP_RESPONSE_TOO_LARGE"}]}'
        status_code = 503
    headers = security_headers()
    for source, header in [
        ("agent_run_id", "X-Request-ID"),
        ("run_id", "X-Run-ID"),
        ("response_id", "X-Response-ID"),
    ]:
        value = response.get(source)
        if _safe_header_value(
            value,
            response_limits["max_header_value_length"],
        ):
            headers[header] = str(value)
    return {
        "status_code": (
            status_code
            if status_code is not None
            else _status_code_for_response(response)
        ),
        "headers": headers,
        "body": body,
    }


def _status_code_for_response(response: Mapping[str, Any]) -> int:
    status = response.get("status")
    if status == "success":
        return 200
    if status == "rejected":
        return 422
    if status == "infrastructure_error":
        return 503
    return 500


def _with_response_ids(response: dict[str, Any]) -> dict[str, Any]:
    from app.domain.result_normalization import stable_fingerprint

    response["response_id"] = stable_fingerprint(
        {
            "contract_version": response["contract_version"],
            "agent_run_id": response["agent_run_id"],
            "run_id": response["run_id"],
            "status": response["status"],
            "message": response["message"],
        }
    )
    payload = deepcopy(response)
    payload.pop("response_fingerprint", None)
    response["response_fingerprint"] = stable_fingerprint(payload)
    return response


def _safe_code(value: object) -> str:
    text = str(value or "").upper()
    return "".join(
        char if char.isalnum() or char == "_" else "_"
        for char in text
    )[:96] or "UNKNOWN"


def _safe_header_value(value: object, max_length: int) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if len(value.encode("utf-8")) > max_length:
        return False
    return all(char.isalnum() or char in "._:-" for char in value)
