from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.asgi.asgi_types import AsgiAdapterLimits
from app.http.http_request_types import HttpRequestLimits
from app.http.http_response_types import HttpResponseLimits


def default_asgi_adapter_limits() -> AsgiAdapterLimits:
    return {
        "max_request_body_bytes": 65_536,
        "max_request_chunks": 32,
        "max_header_count": 32,
        "max_header_name_bytes": 64,
        "max_header_value_bytes": 2_048,
        "max_path_bytes": 512,
        "max_query_string_bytes": 2_048,
        "max_method_bytes": 16,
        "max_scheme_bytes": 16,
        "max_client_host_bytes": 255,
        "max_server_host_bytes": 255,
        "max_response_headers": 16,
        "max_response_header_name_bytes": 64,
        "max_response_header_value_bytes": 256,
    }


def validate_asgi_adapter_limits(
    limits: Mapping[str, Any],
) -> AsgiAdapterLimits:
    defaults = default_asgi_adapter_limits()
    maximums = {
        "max_request_body_bytes": 1_000_000,
        "max_request_chunks": 1_000,
        "max_header_count": 100,
        "max_header_name_bytes": 256,
        "max_header_value_bytes": 8_192,
        "max_path_bytes": 4_096,
        "max_query_string_bytes": 8_192,
        "max_method_bytes": 64,
        "max_scheme_bytes": 32,
        "max_client_host_bytes": 512,
        "max_server_host_bytes": 512,
        "max_response_headers": 100,
        "max_response_header_name_bytes": 256,
        "max_response_header_value_bytes": 8_192,
    }
    output: dict[str, int] = {}
    for key, maximum in maximums.items():
        value = limits.get(key, defaults[key])
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Limite ASGI invalido.")
        if value <= 0 or value > maximum:
            raise ValueError("Limite ASGI fora da faixa.")
        output[key] = value
    return output  # type: ignore[return-value]


def validate_asgi_http_limit_compatibility(
    *,
    asgi_limits: Mapping[str, Any],
    http_request_limits: Mapping[str, Any] | None = None,
    http_response_limits: Mapping[str, Any] | None = None,
) -> None:
    safe_asgi = validate_asgi_adapter_limits(asgi_limits)
    if http_request_limits is not None:
        _require_at_most(
            safe_asgi["max_request_body_bytes"],
            http_request_limits["max_request_body_bytes"],
            "body",
        )
        _require_at_most(
            safe_asgi["max_header_count"],
            http_request_limits["max_header_count"],
            "headers",
        )
        _require_at_most(
            safe_asgi["max_header_name_bytes"],
            http_request_limits["max_header_name_length"],
            "header_name",
        )
    if http_response_limits is not None:
        _require_at_most(
            safe_asgi["max_response_headers"],
            http_response_limits["max_header_count"],
            "response_headers",
        )
        _require_at_most(
            safe_asgi["max_response_header_name_bytes"],
            http_response_limits["max_header_name_length"],
            "response_header_name",
        )


def _require_at_most(value: int, maximum: int, field: str) -> None:
    if value > maximum:
        raise ValueError(f"Limite ASGI incompativel: {field}.")
