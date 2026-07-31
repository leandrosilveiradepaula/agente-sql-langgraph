from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from app.asgi.asgi_error_response import asgi_error_http_response
from app.asgi.asgi_limits import validate_asgi_adapter_limits
from app.asgi.asgi_types import (
    AsgiAdapterLimits,
    AsgiError,
    AsgiMessage,
    AsgiReceive,
    AsgiScope,
    AsgiSend,
    HeaderPairs,
)
from app.http.http_request_types import HttpRequestEnvelope
from app.http.http_response_types import HttpResponseEnvelope
from app.http.sql_agent_http_handler import SqlAgentHttpHandler


class AsgiSqlAgentApplication:
    def __init__(
        self,
        *,
        http_handler: SqlAgentHttpHandler,
        asgi_limits: Mapping[str, Any],
    ) -> None:
        if http_handler is None or not callable(getattr(http_handler, "handle", None)):
            raise RuntimeError("http_handler deve ser injetado.")
        self._http_handler = http_handler
        self._limits = validate_asgi_adapter_limits(asgi_limits)

    async def __call__(
        self,
        scope: AsgiScope,
        receive: AsgiReceive,
        send: AsgiSend,
    ) -> None:
        scope_type = _scope_type(scope)
        if scope_type == "lifespan":
            await _handle_lifespan(receive, send)
            return
        if scope_type == "websocket":
            await send({"type": "websocket.close", "code": 1003})
            return
        if scope_type != "http":
            return
        try:
            request = await build_http_request_envelope(
                scope,
                receive,
                limits=self._limits,
            )
            http_response = self._http_handler.handle(deepcopy(request))
            if not validate_http_response_envelope(
                http_response,
                limits=self._limits,
            ):
                raise AsgiError("ASGI_HANDLER_RESULT_INVALID", status_code=500)
            await send_asgi_response(
                http_response,
                send,
                limits=self._limits,
            )
        except asyncio.CancelledError:
            raise
        except AsgiError as error:
            if error.code == "ASGI_CLIENT_DISCONNECTED":
                return
            if not getattr(error, "response_started", False):
                await send_asgi_response(
                    asgi_error_http_response(
                        code=error.code,
                        status_code=error.status_code,
                    ),
                    send,
                    limits=self._limits,
                )
        except Exception:
            await send_asgi_response(
                asgi_error_http_response(
                    code="ASGI_ADAPTER_UNEXPECTED_ERROR",
                    status_code=500,
                ),
                send,
                limits=self._limits,
            )


async def build_http_request_envelope(
    scope: AsgiScope,
    receive: AsgiReceive,
    *,
    limits: AsgiAdapterLimits,
) -> HttpRequestEnvelope:
    safe_scope = _validate_http_scope(scope, limits=limits)
    body = await read_asgi_http_body(receive, limits=limits)
    return {
        "method": safe_scope["method"],
        "path": safe_scope["path"],
        "query_string": safe_scope["query_string"],
        "headers": safe_scope["headers"],  # type: ignore[typeddict-item]
        "body": body,
    }  # type: ignore[return-value]


async def read_asgi_http_body(
    receive: AsgiReceive,
    *,
    limits: AsgiAdapterLimits,
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    count = 0
    while True:
        message = await receive()
        if not isinstance(message, Mapping):
            raise AsgiError("ASGI_RECEIVE_EVENT_INVALID", status_code=400)
        message_type = message.get("type")
        if message_type == "http.disconnect":
            raise AsgiError("ASGI_CLIENT_DISCONNECTED", status_code=499)
        if message_type != "http.request":
            raise AsgiError("ASGI_RECEIVE_EVENT_INVALID", status_code=400)
        body = message.get("body", b"")
        more_body = message.get("more_body", False)
        if not isinstance(body, bytes) or not isinstance(more_body, bool):
            raise AsgiError("ASGI_RECEIVE_EVENT_INVALID", status_code=400)
        count += 1
        if count > limits["max_request_chunks"]:
            raise AsgiError("ASGI_BODY_TOO_MANY_CHUNKS", status_code=413)
        total += len(body)
        if total > limits["max_request_body_bytes"]:
            raise AsgiError("ASGI_BODY_TOO_LARGE", status_code=413)
        chunks.append(bytes(body))
        if not more_body:
            return b"".join(chunks)


async def send_asgi_response(
    response: HttpResponseEnvelope,
    send: AsgiSend,
    *,
    limits: AsgiAdapterLimits,
) -> None:
    prepared = prepare_asgi_response_events(response, limits=limits)
    await send(prepared[0])
    try:
        await send(prepared[1])
    except asyncio.CancelledError:
        raise
    except Exception as error:
        del error
        failure = AsgiError("ASGI_SEND_FAILED", status_code=500)
        failure.response_started = True  # type: ignore[attr-defined]
        raise failure


def prepare_asgi_response_events(
    response: HttpResponseEnvelope,
    *,
    limits: AsgiAdapterLimits,
) -> tuple[AsgiMessage, AsgiMessage]:
    if not validate_http_response_envelope(response, limits=limits):
        raise AsgiError("ASGI_HANDLER_RESULT_INVALID", status_code=500)
    body = bytes(response["body"])
    headers = _response_header_pairs(response["headers"], body, limits=limits)
    return (
        {
            "type": "http.response.start",
            "status": response["status_code"],
            "headers": headers,
        },
        {
            "type": "http.response.body",
            "body": body,
            "more_body": False,
        },
    )


def validate_http_response_envelope(
    response: object,
    *,
    limits: AsgiAdapterLimits,
) -> bool:
    if not isinstance(response, Mapping):
        return False
    status_code = response.get("status_code")
    headers = response.get("headers")
    body = response.get("body")
    if isinstance(status_code, bool) or not isinstance(status_code, int):
        return False
    if status_code < 100 or status_code > 599:
        return False
    if not isinstance(headers, Mapping) or len(headers) > limits["max_response_headers"]:
        return False
    if not isinstance(body, bytes):
        return False
    try:
        _response_header_pairs(headers, body, limits=limits)
    except AsgiError:
        return False
    return True


def _validate_http_scope(
    scope: AsgiScope,
    *,
    limits: AsgiAdapterLimits,
) -> dict[str, Any]:
    if not isinstance(scope, Mapping):
        raise AsgiError("ASGI_SCOPE_INVALID", status_code=400)
    if scope.get("type") != "http":
        raise AsgiError("ASGI_SCOPE_INVALID", status_code=400)
    asgi = scope.get("asgi")
    if asgi is not None:
        if not isinstance(asgi, Mapping):
            raise AsgiError("ASGI_SCOPE_INVALID", status_code=400)
        version = asgi.get("version")
        if version is not None and not _safe_text(version, 16):
            raise AsgiError("ASGI_SCOPE_INVALID", status_code=400)
    http_version = scope.get("http_version", "1.1")
    if not _safe_text(http_version, 16):
        raise AsgiError("ASGI_SCOPE_INVALID", status_code=400)
    method = scope.get("method")
    if not _safe_text(method, limits["max_method_bytes"]):
        raise AsgiError("ASGI_METHOD_INVALID", status_code=400)
    path = scope.get("path")
    if not _safe_text(path, limits["max_path_bytes"]):
        raise AsgiError("ASGI_PATH_INVALID", status_code=400)
    raw_path = scope.get("raw_path")
    if raw_path is not None and not isinstance(raw_path, bytes):
        raise AsgiError("ASGI_PATH_INVALID", status_code=400)
    query = scope.get("query_string", b"")
    if not isinstance(query, bytes):
        raise AsgiError("ASGI_QUERY_STRING_INVALID", status_code=400)
    if len(query) > limits["max_query_string_bytes"]:
        raise AsgiError("ASGI_QUERY_STRING_INVALID", status_code=400)
    try:
        query_text = query.decode("ascii")
    except UnicodeDecodeError as error:
        del error
        raise AsgiError("ASGI_QUERY_STRING_INVALID", status_code=400)
    scheme = scope.get("scheme", "http")
    if not _safe_text(scheme, limits["max_scheme_bytes"]):
        raise AsgiError("ASGI_SCOPE_INVALID", status_code=400)
    _validate_endpoint(scope.get("client"), limits["max_client_host_bytes"])
    _validate_endpoint(scope.get("server"), limits["max_server_host_bytes"])
    headers = _header_pairs(scope.get("headers", ()), limits=limits)
    return {
        "method": str(method),
        "path": str(path),
        "query_string": query_text,
        "headers": headers,
    }


def _scope_type(scope: object) -> str:
    if not isinstance(scope, Mapping):
        return "invalid"
    value = scope.get("type")
    return value if isinstance(value, str) else "invalid"


def _header_pairs(
    value: object,
    *,
    limits: AsgiAdapterLimits,
) -> HeaderPairs:
    if not isinstance(value, Sequence) or isinstance(value, (bytes, str)):
        raise AsgiError("ASGI_HEADERS_INVALID", status_code=400)
    if len(value) > limits["max_header_count"]:
        raise AsgiError("ASGI_HEADERS_TOO_LARGE", status_code=431)
    output: list[tuple[str, str]] = []
    content_lengths: list[str] = []
    for pair in value:
        if (
            not isinstance(pair, Sequence)
            or isinstance(pair, (bytes, str))
            or len(pair) != 2
        ):
            raise AsgiError("ASGI_HEADERS_INVALID", status_code=400)
        raw_name, raw_value = pair[0], pair[1]
        if not isinstance(raw_name, bytes) or not isinstance(raw_value, bytes):
            raise AsgiError("ASGI_HEADERS_INVALID", status_code=400)
        if len(raw_name) > limits["max_header_name_bytes"]:
            raise AsgiError("ASGI_HEADERS_TOO_LARGE", status_code=431)
        if len(raw_value) > limits["max_header_value_bytes"]:
            raise AsgiError("ASGI_HEADERS_TOO_LARGE", status_code=431)
        if _has_forbidden_header_byte(raw_name) or _has_forbidden_header_byte(raw_value):
            raise AsgiError("ASGI_HEADERS_INVALID", status_code=400)
        try:
            name = raw_name.decode("ascii")
            header_value = raw_value.decode("latin-1")
        except UnicodeDecodeError as error:
            del error
            raise AsgiError("ASGI_HEADERS_INVALID", status_code=400)
        if not name or name.lower() != name or name.startswith(":"):
            raise AsgiError("ASGI_HEADERS_INVALID", status_code=400)
        output.append((name, header_value))
        if name == "content-length":
            content_lengths.append(header_value.strip())
    if len(set(content_lengths)) > 1:
        raise AsgiError("ASGI_HEADERS_INVALID", status_code=400)
    return HeaderPairs(tuple(output))


def _response_header_pairs(
    headers: Mapping[str, str],
    body: bytes,
    *,
    limits: AsgiAdapterLimits,
) -> list[tuple[bytes, bytes]]:
    pairs: list[tuple[bytes, bytes]] = []
    content_lengths: list[str] = []
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise AsgiError("ASGI_HANDLER_RESULT_INVALID", status_code=500)
        name_bytes = name.lower().encode("ascii")
        value_bytes = value.encode("latin-1")
        if (
            not name
            or name.startswith(":")
            or _has_forbidden_header_byte(name_bytes)
            or _has_forbidden_header_byte(value_bytes)
        ):
            raise AsgiError("ASGI_HANDLER_RESULT_INVALID", status_code=500)
        if len(name_bytes) > limits["max_response_header_name_bytes"]:
            raise AsgiError("ASGI_HANDLER_RESULT_INVALID", status_code=500)
        if len(value_bytes) > limits["max_response_header_value_bytes"]:
            raise AsgiError("ASGI_HANDLER_RESULT_INVALID", status_code=500)
        if name.casefold() == "content-length":
            content_lengths.append(value.strip())
        pairs.append((name_bytes, value_bytes))
    if len(content_lengths) > 1:
        raise AsgiError("ASGI_HANDLER_RESULT_INVALID", status_code=500)
    calculated = str(len(body))
    if content_lengths:
        value = content_lengths[0]
        if not value.isdecimal() or int(value) != len(body):
            raise AsgiError("ASGI_HANDLER_RESULT_INVALID", status_code=500)
        return pairs
    if len(pairs) + 1 > limits["max_response_headers"]:
        raise AsgiError("ASGI_HANDLER_RESULT_INVALID", status_code=500)
    pairs.append((b"content-length", calculated.encode("ascii")))
    return pairs


def _safe_text(value: object, max_bytes: int) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if len(value.encode("utf-8")) > max_bytes:
        return False
    return not any(ord(char) < 32 or ord(char) == 127 for char in value)


def _validate_endpoint(value: object, max_host_bytes: int) -> None:
    if value is None:
        return
    if not isinstance(value, Sequence) or isinstance(value, (bytes, str)):
        raise AsgiError("ASGI_SCOPE_INVALID", status_code=400)
    if not value:
        raise AsgiError("ASGI_SCOPE_INVALID", status_code=400)
    host = value[0]
    if host is not None and not _safe_text(host, max_host_bytes):
        raise AsgiError("ASGI_SCOPE_INVALID", status_code=400)


def _has_forbidden_header_byte(value: bytes) -> bool:
    return any(byte in {0, 10, 13} or byte < 32 or byte == 127 for byte in value)


async def _handle_lifespan(receive: AsgiReceive, send: AsgiSend) -> None:
    while True:
        message = await receive()
        if not isinstance(message, Mapping):
            await send({"type": "lifespan.startup.failed", "message": "lifespan failed"})
            return
        message_type = message.get("type")
        if message_type == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message_type == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return
        else:
            await send({"type": "lifespan.startup.failed", "message": "lifespan failed"})
            return
