from __future__ import annotations

from typing import TypedDict


class HttpResponseLimits(TypedDict):
    max_response_body_bytes: int
    max_header_count: int
    max_header_name_length: int
    max_header_value_length: int


class HttpResponseEnvelope(TypedDict):
    status_code: int
    headers: dict[str, str]
    body: bytes
