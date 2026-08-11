from __future__ import annotations

from typing import Any

from app.http.http_request_types import HttpRequestEnvelope
from app.http.http_response_types import HttpResponseEnvelope
from app.http.internal_shadow_read_v1_handler import (
    is_internal_shadow_read_v1_route,
)


_SQL_AGENT_ROUTES = {
    "/v1/internal/sql-agent/generate",
    "/v1/internal/sql-agent/execute-approved-shadow",
}


class InternalV1HttpRouter:
    def __init__(self, *, sql_handler: Any, shadow_read_handler: Any) -> None:
        if sql_handler is None or not callable(getattr(sql_handler, "handle", None)):
            raise RuntimeError("internal SQL handler must be injected.")
        if shadow_read_handler is None or not callable(
            getattr(shadow_read_handler, "handle", None)
        ):
            raise RuntimeError("internal shadow read handler must be injected.")
        self._sql_handler = sql_handler
        self._shadow_read_handler = shadow_read_handler

    def handle(self, request: HttpRequestEnvelope) -> HttpResponseEnvelope:
        path = str(request.get("path", ""))
        if path in _SQL_AGENT_ROUTES:
            return self._sql_handler.handle(request)
        if is_internal_shadow_read_v1_route(path):
            return self._shadow_read_handler.handle(request)
        return self._sql_handler.handle(request)


def create_internal_v1_http_router(
    *,
    sql_handler: Any,
    shadow_read_handler: Any,
) -> InternalV1HttpRouter:
    return InternalV1HttpRouter(
        sql_handler=sql_handler,
        shadow_read_handler=shadow_read_handler,
    )
