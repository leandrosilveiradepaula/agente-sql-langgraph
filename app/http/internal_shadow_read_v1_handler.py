from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Protocol
from urllib.parse import parse_qs

from app.application.internal_shadow_read_v1 import (
    DEFAULT_SHADOW_RUN_LIST_LIMIT,
    SHADOW_READ_CONTRACT_VERSION,
    ShadowReadError,
    validate_shadow_read_id,
    validate_shadow_run_list_limit,
)
from app.http.http_request_types import HttpRequestEnvelope
from app.http.http_response import (
    default_http_response_limits,
    validate_http_response_limits,
)
from app.http.http_response_types import HttpResponseEnvelope
from app.http.security_headers import security_headers


class GetShadowRunSafeViewService(Protocol):
    def execute(self, shadow_record_id: str) -> Mapping[str, Any]:
        ...


class ListAgentShadowRunsService(Protocol):
    def execute(self, agent_run_id: str, *, limit: int) -> Mapping[str, Any]:
        ...


class GetShadowRunVisualizationService(Protocol):
    def execute(self, shadow_record_id: str) -> Mapping[str, Any]:
        ...


_SHADOW_RUNS_PREFIX = "/v1/internal/shadow-runs/"
_AGENT_RUNS_PREFIX = "/v1/internal/agent-runs/"


class InternalShadowReadV1HttpHandler:
    def __init__(
        self,
        *,
        get_shadow_run_use_case: GetShadowRunSafeViewService,
        list_agent_shadow_runs_use_case: ListAgentShadowRunsService,
        get_shadow_run_visualization_use_case: GetShadowRunVisualizationService,
        response_limits: Mapping[str, Any] | None = None,
    ) -> None:
        if get_shadow_run_use_case is None or not callable(
            getattr(get_shadow_run_use_case, "execute", None)
        ):
            raise RuntimeError("get shadow run use case must be injected.")
        if list_agent_shadow_runs_use_case is None or not callable(
            getattr(list_agent_shadow_runs_use_case, "execute", None)
        ):
            raise RuntimeError("list shadow runs use case must be injected.")
        if get_shadow_run_visualization_use_case is None or not callable(
            getattr(get_shadow_run_visualization_use_case, "execute", None)
        ):
            raise RuntimeError("visualization use case must be injected.")
        self._get_shadow_run = get_shadow_run_use_case
        self._list_shadow_runs = list_agent_shadow_runs_use_case
        self._get_visualization = get_shadow_run_visualization_use_case
        self._response_limits = validate_http_response_limits(
            response_limits or default_http_response_limits()
        )

    def handle(self, request: HttpRequestEnvelope) -> HttpResponseEnvelope:
        try:
            envelope = deepcopy(request)
            _reject_sensitive_headers(envelope.get("headers", {}))
            _validate_accept(envelope.get("headers", {}))
            if str(envelope.get("method", "")).upper() != "GET":
                return self._error_response(
                    "HTTP_METHOD_NOT_ALLOWED",
                    status_code=405,
                    allow=True,
                )
            route = _parse_route(str(envelope.get("path", "")))
            if route["kind"] == "shadow_run":
                shadow_record_id = validate_shadow_read_id(
                    route["shadow_record_id"],
                    field="shadow_record_id",
                )
                return _json_response(
                    self._get_shadow_run.execute(shadow_record_id),
                    response_limits=self._response_limits,
                )
            if route["kind"] == "visualization":
                shadow_record_id = validate_shadow_read_id(
                    route["shadow_record_id"],
                    field="shadow_record_id",
                )
                return _json_response(
                    self._get_visualization.execute(shadow_record_id),
                    response_limits=self._response_limits,
                )
            if route["kind"] == "agent_list":
                agent_run_id = validate_shadow_read_id(
                    route["agent_run_id"],
                    field="agent_run_id",
                )
                limit = _limit_from_query(str(envelope.get("query_string", "")))
                return _json_response(
                    self._list_shadow_runs.execute(agent_run_id, limit=limit),
                    response_limits=self._response_limits,
                )
            return self._error_response("HTTP_ROUTE_NOT_FOUND", status_code=404)
        except ShadowReadError as error:
            return self._error_response(error.code, status_code=error.status_code)
        except Exception:
            return self._error_response(
                "INTERNAL_SHADOW_READ_UNEXPECTED_ERROR",
                status_code=500,
            )

    def _error_response(
        self,
        code: str,
        *,
        status_code: int,
        allow: bool = False,
    ) -> HttpResponseEnvelope:
        response = _json_response(
            {
                "contract_version": SHADOW_READ_CONTRACT_VERSION,
                "error": {"code": _safe_code(code)},
            },
            response_limits=self._response_limits,
            status_code=status_code,
        )
        if allow:
            response["headers"]["Allow"] = "GET"
        return response


def create_internal_shadow_read_v1_http_handler(
    *,
    get_shadow_run_use_case: GetShadowRunSafeViewService,
    list_agent_shadow_runs_use_case: ListAgentShadowRunsService,
    get_shadow_run_visualization_use_case: GetShadowRunVisualizationService,
    response_limits: Mapping[str, Any] | None = None,
) -> InternalShadowReadV1HttpHandler:
    return InternalShadowReadV1HttpHandler(
        get_shadow_run_use_case=get_shadow_run_use_case,
        list_agent_shadow_runs_use_case=list_agent_shadow_runs_use_case,
        get_shadow_run_visualization_use_case=get_shadow_run_visualization_use_case,
        response_limits=response_limits,
    )


def is_internal_shadow_read_v1_route(path: str) -> bool:
    return path.startswith(_SHADOW_RUNS_PREFIX) or path.startswith(_AGENT_RUNS_PREFIX)


def _parse_route(path: str) -> dict[str, str]:
    parts = [part for part in path.split("/") if part]
    if len(parts) == 4 and parts[:3] == ["v1", "internal", "shadow-runs"]:
        return {"kind": "shadow_run", "shadow_record_id": parts[3]}
    if (
        len(parts) == 5
        and parts[:3] == ["v1", "internal", "shadow-runs"]
        and parts[4] == "visualization"
    ):
        return {"kind": "visualization", "shadow_record_id": parts[3]}
    if (
        len(parts) == 5
        and parts[:3] == ["v1", "internal", "agent-runs"]
        and parts[4] == "shadow-runs"
    ):
        return {"kind": "agent_list", "agent_run_id": parts[3]}
    return {"kind": "not_found"}


def _limit_from_query(query_string: str) -> int:
    parsed = parse_qs(query_string, keep_blank_values=True, strict_parsing=False)
    values = parsed.get("limit")
    if not values:
        return DEFAULT_SHADOW_RUN_LIST_LIMIT
    if len(values) != 1:
        raise ShadowReadError("SHADOW_RUN_LIMIT_INVALID", 400)
    try:
        value = int(values[0], 10)
    except ValueError as error:
        del error
        raise ShadowReadError("SHADOW_RUN_LIMIT_INVALID", 400) from None
    return validate_shadow_run_list_limit(value)


def _json_response(
    payload: Mapping[str, Any],
    *,
    response_limits: Mapping[str, int],
    status_code: int = 200,
) -> HttpResponseEnvelope:
    body = json.dumps(
        deepcopy(dict(payload)),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    selected_status = status_code
    if len(body) > response_limits["max_response_body_bytes"]:
        body = (
            b'{"contract_version":"1","error":{"code":"HTTP_RESPONSE_TOO_LARGE"}}'
        )
        selected_status = 503
    headers = security_headers()
    headers["Content-Type"] = "application/json; charset=utf-8"
    return {"status_code": selected_status, "headers": headers, "body": body}


def _reject_sensitive_headers(headers: object) -> None:
    if not isinstance(headers, Mapping):
        return
    for key in headers:
        if isinstance(key, str) and key.casefold() in {"authorization", "cookie"}:
            raise ShadowReadError("HTTP_IDENTITY_FIELD_FORBIDDEN", 400)


def _validate_accept(headers: object) -> None:
    if not isinstance(headers, Mapping):
        return
    value = None
    for key, item in headers.items():
        if isinstance(key, str) and key.casefold() == "accept":
            value = str(item)
            break
    if value is None or not value.strip():
        return
    for item in value.split(","):
        media_type = item.split(";", 1)[0].strip().lower()
        if media_type in {"application/json", "*/*"}:
            return
    raise ShadowReadError("HTTP_NOT_ACCEPTABLE", 406)


def _safe_code(value: object) -> str:
    text = str(value or "").upper()
    return "".join(
        char if ("A" <= char <= "Z" or "0" <= char <= "9" or char == "_") else "_"
        for char in text
    )[:96] or "UNKNOWN"
