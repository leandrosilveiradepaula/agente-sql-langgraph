from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from app.http.http_request_types import (
    HttpRequestEnvelope,
    HttpRequestLimits,
)


_ALLOWED_REQUEST_HEADERS = {
    "accept",
    "content-length",
    "content-type",
    "x-correlation-id",
    "x-request-id",
}


class HttpRequestError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def default_http_request_limits() -> HttpRequestLimits:
    return {
        "max_request_body_bytes": 65_536,
        "max_json_depth": 12,
        "max_json_members": 200,
        "max_json_integer_digits": 64,
        "max_header_count": 32,
        "max_header_name_length": 64,
        "max_header_value_length": 512,
    }


def validate_http_request_limits(
    limits: Mapping[str, Any],
) -> HttpRequestLimits:
    defaults = default_http_request_limits()
    maximums = {
        "max_request_body_bytes": 1_000_000,
        "max_json_depth": 100,
        "max_json_members": 10_000,
        "max_json_integer_digits": 1_000,
        "max_header_count": 100,
        "max_header_name_length": 256,
        "max_header_value_length": 2_000,
    }
    output: dict[str, int] = {}
    for key, maximum in maximums.items():
        value = limits.get(key, defaults[key])
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Limite HTTP invalido.")
        if value <= 0 or value > maximum:
            raise ValueError("Limite HTTP fora da faixa.")
        output[key] = value
    return output  # type: ignore[return-value]


def parse_http_request_json(
    request: HttpRequestEnvelope,
    *,
    limits: HttpRequestLimits,
) -> dict[str, Any]:
    envelope = deepcopy(request)
    _validate_headers(envelope.get("headers", {}), limits)
    body = envelope.get("body", b"")
    if not isinstance(body, bytes):
        raise HttpRequestError("HTTP_BODY_REQUIRED")
    _validate_content_length(envelope.get("headers", {}), len(body), limits)
    if len(body) == 0:
        raise HttpRequestError("HTTP_BODY_REQUIRED")
    if len(body) > limits["max_request_body_bytes"]:
        raise HttpRequestError("HTTP_BODY_TOO_LARGE")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        del error
        raise HttpRequestError("HTTP_BODY_INVALID_UTF8")
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_int=lambda value: _parse_int(
                value,
                limits["max_json_integer_digits"],
            ),
        )
    except HttpRequestError:
        raise
    except Exception as error:
        del error
        raise HttpRequestError("HTTP_JSON_INVALID")
    if not isinstance(parsed, dict):
        raise HttpRequestError("HTTP_JSON_ROOT_INVALID")
    _validate_complexity(parsed, limits)
    return deepcopy(parsed)


def validate_method_route_and_headers(
    request: HttpRequestEnvelope,
    *,
    limits: HttpRequestLimits,
) -> None:
    method = str(request.get("method", "")).upper()
    path = str(request.get("path", ""))
    if path != "/v1/sql-agent/query":
        raise HttpRequestError("HTTP_ROUTE_NOT_FOUND")
    if method != "POST":
        raise HttpRequestError("HTTP_METHOD_NOT_ALLOWED")
    headers = request.get("headers", {})
    _validate_headers(headers, limits)
    _validate_content_type(headers)
    _validate_accept(headers)


def _validate_headers(
    headers: object,
    limits: HttpRequestLimits,
) -> None:
    if not isinstance(headers, Mapping):
        raise HttpRequestError("HTTP_JSON_INVALID")
    if len(headers) > limits["max_header_count"]:
        raise HttpRequestError("HTTP_JSON_TOO_COMPLEX")
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise HttpRequestError("HTTP_JSON_INVALID")
        if name.casefold() not in _ALLOWED_REQUEST_HEADERS:
            raise HttpRequestError("HTTP_JSON_INVALID")
        if len(name.encode("utf-8")) > limits["max_header_name_length"]:
            raise HttpRequestError("HTTP_JSON_TOO_COMPLEX")
        if len(value.encode("utf-8")) > limits["max_header_value_length"]:
            raise HttpRequestError("HTTP_JSON_TOO_COMPLEX")
        if _has_control(name) or _has_control(value):
            raise HttpRequestError("HTTP_JSON_INVALID")


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


def _validate_content_length(
    headers: Mapping[str, str],
    actual_size: int,
    limits: HttpRequestLimits,
) -> None:
    value = _header(headers, "content-length")
    if value is None:
        return
    values = [item.strip() for item in value.split(",")]
    if len(set(values)) > 1:
        raise HttpRequestError("HTTP_CONTENT_LENGTH_INVALID")
    try:
        declared = int(values[0])
    except ValueError as error:
        del error
        raise HttpRequestError("HTTP_CONTENT_LENGTH_INVALID")
    if declared < 0:
        raise HttpRequestError("HTTP_CONTENT_LENGTH_INVALID")
    if declared > limits["max_request_body_bytes"]:
        raise HttpRequestError("HTTP_BODY_TOO_LARGE")
    if actual_size > limits["max_request_body_bytes"]:
        raise HttpRequestError("HTTP_BODY_TOO_LARGE")
    if declared != actual_size:
        raise HttpRequestError("HTTP_CONTENT_LENGTH_INVALID")


def _validate_accept(headers: Mapping[str, str]) -> None:
    value = _header(headers, "accept")
    if value is None or not value.strip():
        return
    for item in value.split(","):
        if _accept_item_allows_json(item):
            return
    raise HttpRequestError("HTTP_NOT_ACCEPTABLE")


def _accept_item_allows_json(item: str) -> bool:
    parts = [part.strip().lower() for part in item.split(";")]
    media_type = parts[0]
    if media_type not in {"application/json", "*/*"}:
        return False
    quality = 1.0
    for parameter in parts[1:]:
        if not parameter:
            continue
        if not parameter.startswith("q="):
            continue
        try:
            quality = float(parameter[2:])
        except ValueError as error:
            del error
            raise HttpRequestError("HTTP_NOT_ACCEPTABLE")
        if quality < 0 or quality > 1:
            raise HttpRequestError("HTTP_NOT_ACCEPTABLE")
    return quality > 0


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise HttpRequestError("HTTP_JSON_DUPLICATE_KEY")
        output[key] = value
    return output


def _reject_constant(value: str) -> None:
    del value
    raise HttpRequestError("HTTP_JSON_INVALID")


def _parse_int(value: str, max_digits: int) -> int:
    digits = value.lstrip("-")
    if len(digits) > max_digits:
        raise HttpRequestError("HTTP_JSON_TOO_COMPLEX")
    return int(value)


def _validate_complexity(value: object, limits: HttpRequestLimits) -> None:
    members = 0

    def visit(item: object, depth: int) -> None:
        nonlocal members
        if depth > limits["max_json_depth"]:
            raise HttpRequestError("HTTP_JSON_TOO_DEEP")
        if isinstance(item, dict):
            members += len(item)
            if members > limits["max_json_members"]:
                raise HttpRequestError("HTTP_JSON_TOO_COMPLEX")
            for nested in item.values():
                visit(nested, depth + 1)
        elif isinstance(item, list):
            members += len(item)
            if members > limits["max_json_members"]:
                raise HttpRequestError("HTTP_JSON_TOO_COMPLEX")
            for nested in item:
                visit(nested, depth + 1)

    visit(value, 1)


def _header(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.casefold() == name.casefold():
            return value
    return None


def _has_control(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)
