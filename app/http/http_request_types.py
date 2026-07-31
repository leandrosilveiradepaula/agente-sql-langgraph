from __future__ import annotations

from typing import Literal, TypedDict


HTTP_CONTRACT_VERSION = "v1.0.0-http-entry-adapter"

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
HttpContentType = Literal["application/json"]
HttpErrorCode = Literal[
    "HTTP_BODY_INVALID_UTF8",
    "HTTP_BODY_REQUIRED",
    "HTTP_BODY_TOO_LARGE",
    "HTTP_CHARSET_UNSUPPORTED",
    "HTTP_CONTENT_LENGTH_INVALID",
    "HTTP_CONTENT_TYPE_REQUIRED",
    "HTTP_JSON_DUPLICATE_KEY",
    "HTTP_JSON_INVALID",
    "HTTP_JSON_ROOT_INVALID",
    "HTTP_JSON_TOO_COMPLEX",
    "HTTP_JSON_TOO_DEEP",
    "HTTP_METHOD_NOT_ALLOWED",
    "HTTP_NOT_ACCEPTABLE",
    "HTTP_RESPONSE_TOO_LARGE",
    "HTTP_ROUTE_NOT_FOUND",
    "HTTP_UNSUPPORTED_MEDIA_TYPE",
    "HTTP_ADAPTER_UNEXPECTED_ERROR",
]


class HttpHeader(TypedDict):
    name: str
    value: str


class HttpDiagnostic(TypedDict, total=False):
    code: HttpErrorCode | str
    message: str
    field: str


class HttpRequestLimits(TypedDict):
    max_request_body_bytes: int
    max_json_depth: int
    max_json_members: int
    max_json_integer_digits: int
    max_header_count: int
    max_header_name_length: int
    max_header_value_length: int


class HttpRequestEnvelope(TypedDict):
    method: str
    path: str
    headers: dict[str, str]
    body: bytes
