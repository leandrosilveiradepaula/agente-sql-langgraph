from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Protocol

from app.application.application_request_types import ApplicationRequest
from app.domain.application_response_types import ApplicationResponse
from app.http.http_request import (
    HttpRequestError,
    default_http_request_limits,
    parse_http_request_json,
    validate_http_request_limits,
    validate_method_route_and_headers,
)
from app.http.http_request_types import HttpRequestEnvelope
from app.http.http_response import (
    application_response_to_http_response,
    default_http_response_limits,
    minimal_http_application_response,
    validate_http_response_limits,
)
from app.http.http_response_types import HttpResponseEnvelope


class ApplicationService(Protocol):
    def execute(self, request: ApplicationRequest) -> ApplicationResponse:
        ...


_STATUS_BY_HTTP_ERROR = {
    "HTTP_BODY_TOO_LARGE": 413,
    "HTTP_CONTENT_TYPE_REQUIRED": 415,
    "HTTP_UNSUPPORTED_MEDIA_TYPE": 415,
    "HTTP_CHARSET_UNSUPPORTED": 415,
    "HTTP_METHOD_NOT_ALLOWED": 405,
    "HTTP_NOT_ACCEPTABLE": 406,
    "HTTP_ROUTE_NOT_FOUND": 404,
}


class SqlAgentHttpHandler:
    def __init__(
        self,
        *,
        application_service: ApplicationService,
        request_limits: Mapping[str, Any] | None = None,
        response_limits: Mapping[str, Any] | None = None,
    ) -> None:
        if application_service is None or not callable(
            getattr(application_service, "execute", None)
        ):
            raise RuntimeError(
                "application_service deve ser injetado explicitamente."
            )
        if request_limits is None:
            raise RuntimeError("request_limits deve ser injetado.")
        if response_limits is None:
            raise RuntimeError("response_limits deve ser injetado.")
        self._application_service = application_service
        self._request_limits = validate_http_request_limits(request_limits)
        self._response_limits = validate_http_response_limits(response_limits)

    def handle(
        self,
        request: HttpRequestEnvelope,
    ) -> HttpResponseEnvelope:
        try:
            envelope = deepcopy(request)
            validate_method_route_and_headers(
                envelope,
                limits=self._request_limits,
            )
            payload = parse_http_request_json(
                envelope,
                limits=self._request_limits,
            )
            response = self._application_service.execute(
                deepcopy(payload)  # type: ignore[arg-type]
            )
            if not _valid_application_response_shape(response):
                return self._error_response(
                    "HTTP_ADAPTER_UNEXPECTED_ERROR",
                    status_code=500,
                    status="infrastructure_error",
                )
            return application_response_to_http_response(
                response,
                limits=self._response_limits,
            )
        except HttpRequestError as error:
            return self._error_response(
                error.code,
                status_code=_STATUS_BY_HTTP_ERROR.get(error.code, 400),
                status="rejected",
            )
        except Exception:
            return self._error_response(
                "HTTP_ADAPTER_UNEXPECTED_ERROR",
                status_code=500,
                status="infrastructure_error",
            )

    def _error_response(
        self,
        code: str,
        *,
        status_code: int,
        status: str,
    ) -> HttpResponseEnvelope:
        headers_extra = (
            {"Allow": "POST"} if code == "HTTP_METHOD_NOT_ALLOWED" else None
        )
        response = application_response_to_http_response(
            minimal_http_application_response(  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                code=code,
            ),
            limits=self._response_limits,
            status_code=status_code,
        )
        if headers_extra:
            response["headers"].update(headers_extra)
        return response


def create_sql_agent_http_handler(
    *,
    application_service: ApplicationService,
    request_limits: Mapping[str, Any],
    response_limits: Mapping[str, Any],
) -> SqlAgentHttpHandler:
    return SqlAgentHttpHandler(
        application_service=application_service,
        request_limits=request_limits,
        response_limits=response_limits,
    )


def _valid_application_response_shape(response: object) -> bool:
    return (
        isinstance(response, Mapping)
        and response.get("contract_version") == "v1.0.0-application-response"
        and response.get("status")
        in {"success", "rejected", "infrastructure_error"}
        and isinstance(response.get("response_fingerprint"), str)
        and bool(response.get("response_fingerprint"))
        and isinstance(response.get("response_id"), str)
    )
