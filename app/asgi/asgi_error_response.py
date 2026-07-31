from __future__ import annotations

from app.http.http_response import (
    application_response_to_http_response,
    default_http_response_limits,
    minimal_http_application_response,
)
from app.http.http_response_types import HttpResponseEnvelope


def asgi_error_http_response(
    *,
    code: str,
    status_code: int,
) -> HttpResponseEnvelope:
    status = "rejected" if status_code < 500 else "infrastructure_error"
    return application_response_to_http_response(
        minimal_http_application_response(
            status=status,  # type: ignore[arg-type]
            code=code,
        ),
        limits=default_http_response_limits(),
        status_code=status_code,
    )
