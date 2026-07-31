from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Protocol

from app.application.application_request_types import ApplicationRequest
from app.domain.application_response_types import (
    APPLICATION_RESPONSE_CONTRACT_VERSION,
    ApplicationResponse,
)
from app.domain.result_normalization import stable_fingerprint
from app.http.auth_header import (
    AuthorizationHeaderError,
    extract_bearer_credential,
)
from app.http.http_request import (
    HttpRequestError,
    default_http_request_limits,
    parse_http_request_json,
    validate_http_body_transport,
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
from app.ports.authenticator import Authenticator
from app.ports.authorizer import Authorizer
from app.security.auth_types import (
    AuthSecurityLimits,
    authentication_result,
    authorization_request,
    principal_to_application_user,
    validate_auth_security_limits,
    validate_authenticated_principal,
    validate_authentication_result,
    validate_authorization_decision,
)


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

_STATUS_BY_AUTHORIZATION_HEADER_ERROR = {
    "AUTHORIZATION_HEADER_INVALID": 401,
    "AUTHORIZATION_SCHEME_UNSUPPORTED": 401,
    "AUTHORIZATION_CREDENTIAL_REQUIRED": 401,
    "AUTHORIZATION_CREDENTIAL_TOO_LARGE": 401,
    "AUTHORIZATION_CREDENTIAL_INVALID_CHARACTER": 401,
    "AUTHORIZATION_HEADER_AMBIGUOUS": 401,
    "AUTHORIZATION_HEADER_REQUIRED": 401,
}


class SqlAgentHttpHandler:
    def __init__(
        self,
        *,
        application_service: ApplicationService,
        authenticator: Authenticator,
        authorizer: Authorizer,
        auth_limits: Mapping[str, Any] | None = None,
        request_limits: Mapping[str, Any] | None = None,
        response_limits: Mapping[str, Any] | None = None,
    ) -> None:
        if application_service is None or not callable(
            getattr(application_service, "execute", None)
        ):
            raise RuntimeError(
                "application_service deve ser injetado explicitamente."
            )
        if authenticator is None or not callable(
            getattr(authenticator, "authenticate", None)
        ):
            raise RuntimeError("authenticator deve ser injetado.")
        if authorizer is None or not callable(
            getattr(authorizer, "authorize", None)
        ):
            raise RuntimeError("authorizer deve ser injetado.")
        if auth_limits is None:
            raise RuntimeError("auth_limits deve ser injetado.")
        if request_limits is None:
            raise RuntimeError("request_limits deve ser injetado.")
        if response_limits is None:
            raise RuntimeError("response_limits deve ser injetado.")
        self._application_service = application_service
        self._authenticator = authenticator
        self._authorizer = authorizer
        self._auth_limits = validate_auth_security_limits(auth_limits)
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
            validate_http_body_transport(
                envelope,
                limits=self._request_limits,
            )
            credential = extract_bearer_credential(
                envelope,
                limits=self._auth_limits,
            )
            auth_result = _call_authenticator(
                self._authenticator,
                credential,
                method=str(envelope.get("method", "")).upper(),
            )
            auth_result = _validated_authentication_result(auth_result)
            principal = auth_result["principal"]
            if not validate_authenticated_principal(
                principal,
                limits=self._auth_limits,
            ):
                return self._error_response(
                    "AUTHENTICATION_PRINCIPAL_INVALID",
                    status_code=500,
                    status="infrastructure_error",
                )
            authz_request = authorization_request(
                method=str(envelope.get("method", "")).upper(),
                route="/v1/sql-agent/query",
                organization_id=principal.organization_id,
            )
            decision = _call_authorizer(
                self._authorizer,
                principal,
                authz_request,
            )
            decision = _validated_authorization_decision(decision)
            if decision["status"] != "allowed":
                code, status_code, response_status = _authorization_failure(
                    decision["status"]
                )
                return self._error_response(
                    code,
                    status_code=status_code,
                    status=response_status,
                )
            payload = parse_http_request_json(
                envelope,
                limits=self._request_limits,
            )
            if "user" in payload:
                return self._error_response(
                    "HTTP_IDENTITY_FIELD_FORBIDDEN",
                    status_code=400,
                    status="rejected",
                )
            payload["user"] = principal_to_application_user(principal)
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
        except AuthorizationHeaderError as error:
            return self._error_response(
                _public_authentication_code(error.code),
                status_code=_STATUS_BY_AUTHORIZATION_HEADER_ERROR.get(
                    error.code,
                    401,
                ),
                status="rejected",
                www_authenticate=True,
            )
        except AuthenticationFailure as error:
            return self._error_response(
                error.code,
                status_code=error.status_code,
                status=error.response_status,
                www_authenticate=error.status_code == 401,
            )
        except AuthorizationFailure as error:
            return self._error_response(
                error.code,
                status_code=error.status_code,
                status=error.response_status,
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
        www_authenticate: bool = False,
    ) -> HttpResponseEnvelope:
        headers_extra: dict[str, str] = {}
        if code == "HTTP_METHOD_NOT_ALLOWED":
            headers_extra["Allow"] = "POST"
        if www_authenticate:
            headers_extra["WWW-Authenticate"] = "Bearer"
        response = application_response_to_http_response(
            minimal_http_application_response(  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                code=code,
            ),
            limits=self._response_limits,
            status_code=status_code,
        )
        response["headers"].update(headers_extra)
        return response


def create_sql_agent_http_handler(
    *,
    application_service: ApplicationService,
    authenticator: Authenticator,
    authorizer: Authorizer,
    auth_limits: Mapping[str, Any],
    request_limits: Mapping[str, Any],
    response_limits: Mapping[str, Any],
) -> SqlAgentHttpHandler:
    return SqlAgentHttpHandler(
        application_service=application_service,
        authenticator=authenticator,
        authorizer=authorizer,
        auth_limits=auth_limits,
        request_limits=request_limits,
        response_limits=response_limits,
    )


class AuthenticationFailure(ValueError):
    def __init__(
        self,
        code: str,
        *,
        status_code: int,
        response_status: str,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.response_status = response_status
        super().__init__(code)


class AuthorizationFailure(ValueError):
    def __init__(
        self,
        code: str,
        *,
        status_code: int,
        response_status: str,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.response_status = response_status
        super().__init__(code)


def _validated_authentication_result(result: object):
    if not validate_authentication_result(result):
        raise AuthenticationFailure(
            "AUTHENTICATION_UNEXPECTED_ERROR",
            status_code=500,
            response_status="infrastructure_error",
        )
    status = result["status"]
    if status == "authenticated":
        return result
    if status == "invalid_credentials":
        raise AuthenticationFailure(
            "AUTHENTICATION_INVALID_CREDENTIALS",
            status_code=401,
            response_status="rejected",
        )
    if status == "unavailable":
        raise AuthenticationFailure(
            "AUTHENTICATION_SERVICE_UNAVAILABLE",
            status_code=503,
            response_status="infrastructure_error",
        )
    raise AuthenticationFailure(
        "AUTHENTICATION_UNEXPECTED_ERROR",
        status_code=500,
        response_status="infrastructure_error",
    )


def _call_authenticator(
    authenticator: Authenticator,
    credential,
    *,
    method: str,
):
    try:
        return authenticator.authenticate(
            credential,
            {
                "method": method,
                "route": "/v1/sql-agent/query",
            },
        )
    except AuthenticationFailure:
        raise
    except Exception as error:
        del error
        raise AuthenticationFailure(
            "AUTHENTICATION_UNEXPECTED_ERROR",
            status_code=500,
            response_status="infrastructure_error",
        )


def _call_authorizer(
    authorizer: Authorizer,
    principal,
    request,
):
    try:
        return authorizer.authorize(principal, request)
    except AuthorizationFailure:
        raise
    except Exception as error:
        del error
        raise AuthorizationFailure(
            "AUTHORIZATION_UNEXPECTED_ERROR",
            status_code=500,
            response_status="infrastructure_error",
        )


def _validated_authorization_decision(decision: object):
    if not validate_authorization_decision(decision):
        raise AuthorizationFailure(
            "AUTHORIZATION_UNEXPECTED_ERROR",
            status_code=500,
            response_status="infrastructure_error",
        )
    return decision


def _authorization_failure(status: str) -> tuple[str, int, str]:
    if status == "denied":
        return "AUTHORIZATION_DENIED", 403, "rejected"
    if status == "unavailable":
        return (
            "AUTHORIZATION_SERVICE_UNAVAILABLE",
            503,
            "infrastructure_error",
        )
    return "AUTHORIZATION_UNEXPECTED_ERROR", 500, "infrastructure_error"


def _public_authentication_code(code: str) -> str:
    if code == "AUTHORIZATION_HEADER_REQUIRED":
        return "AUTHENTICATION_REQUIRED"
    return "AUTHENTICATION_INVALID_CREDENTIALS"


def _valid_application_response_shape(response: object) -> bool:
    if not isinstance(response, Mapping):
        return False
    allowed_keys = {
        "contract_version",
        "response_id",
        "request_id",
        "run_id",
        "status",
        "original_outcome",
        "message",
        "data",
        "errors",
        "warnings",
        "metadata",
        "finalization",
        "response_fingerprint",
    }
    if set(response) - allowed_keys:
        return False
    if response.get("contract_version") != APPLICATION_RESPONSE_CONTRACT_VERSION:
        return False
    status = response.get("status")
    if status not in {"success", "rejected", "infrastructure_error"}:
        return False
    if response.get("original_outcome") not in {
        "success",
        "rejected",
        "infrastructure_error",
    }:
        return False
    for key in ["response_id", "request_id", "run_id", "message"]:
        if not isinstance(response.get(key), str):
            return False
    if not response.get("response_id") or not response.get("message"):
        return False
    if status == "success":
        if not _valid_public_data(response.get("data")):
            return False
    elif response.get("data") is not None:
        return False
    if not isinstance(response.get("errors"), list):
        return False
    if not isinstance(response.get("warnings"), list):
        return False
    if not isinstance(response.get("metadata"), Mapping):
        return False
    if "canonical_json" in response["metadata"]:
        return False
    if not isinstance(response.get("finalization"), Mapping):
        return False
    finalization_status = response["finalization"].get("status")
    if status == "success" and finalization_status not in {
        "completed",
        "observability_degraded",
    }:
        return False
    fingerprint = response.get("response_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        return False
    payload = deepcopy(dict(response))
    payload.pop("response_fingerprint", None)
    return stable_fingerprint(payload) == fingerprint


def _valid_public_data(data: object) -> bool:
    if not isinstance(data, Mapping) or set(data) != {"result", "pagination"}:
        return False
    result = data.get("result")
    pagination = data.get("pagination")
    if not isinstance(result, Mapping) or set(result) != {
        "contract_version",
        "columns",
        "rows",
        "result_fingerprint",
    }:
        return False
    if not isinstance(result.get("contract_version"), str):
        return False
    if not isinstance(result.get("columns"), list):
        return False
    if not isinstance(result.get("rows"), list):
        return False
    if not isinstance(result.get("result_fingerprint"), str):
        return False
    if not result.get("result_fingerprint"):
        return False
    if not isinstance(pagination, Mapping) or set(pagination) != {
        "mode",
        "has_more",
        "next_cursor",
        "total_rows",
        "returned_rows",
    }:
        return False
    if pagination.get("mode") != "none":
        return False
    if pagination.get("has_more") is not False:
        return False
    if pagination.get("next_cursor") is not None:
        return False
    for key in ["total_rows", "returned_rows"]:
        value = pagination.get(key)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            return False
    return True
