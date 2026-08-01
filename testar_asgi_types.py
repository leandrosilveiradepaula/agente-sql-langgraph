from __future__ import annotations

from app.asgi.asgi_limits import (
    default_asgi_adapter_limits,
    validate_asgi_adapter_limits,
    validate_asgi_http_limit_compatibility,
)
from app.asgi.sql_agent_asgi_app import prepare_asgi_response_events
from app.http.http_request import default_http_request_limits
from app.http.http_response import default_http_response_limits


def _raises(func, *args, **kwargs) -> None:
    try:
        func(*args, **kwargs)
    except ValueError:
        return
    except Exception:
        return
    raise AssertionError("Era esperado erro.")


def test_limits_validos() -> None:
    limits = validate_asgi_adapter_limits(default_asgi_adapter_limits())
    assert limits["max_request_body_bytes"] == 65_536


def test_zero_negativo_excessivo() -> None:
    for value in [0, -1, 9_999_999]:
        _raises(
            validate_asgi_adapter_limits,
            {**default_asgi_adapter_limits(), "max_request_chunks": value},
        )
    _raises(
        validate_asgi_adapter_limits,
        {**default_asgi_adapter_limits(), "max_response_headers": 1},
    )


def test_compatibilidade_body_headers() -> None:
    asgi_limits = default_asgi_adapter_limits()
    validate_asgi_http_limit_compatibility(
        asgi_limits=asgi_limits,
        http_request_limits=default_http_request_limits(),
        http_response_limits=default_http_response_limits(),
    )
    _raises(
        validate_asgi_http_limit_compatibility,
        asgi_limits={**asgi_limits, "max_request_body_bytes": 70_000},
        http_request_limits=default_http_request_limits(),
    )
    _raises(
        validate_asgi_http_limit_compatibility,
        asgi_limits={**asgi_limits, "max_header_count": 33},
        http_request_limits=default_http_request_limits(),
    )


def test_defaults_independentes() -> None:
    first = default_asgi_adapter_limits()
    second = default_asgi_adapter_limits()
    first["max_request_chunks"] = 1
    assert second["max_request_chunks"] == 32


def test_status_e_headers_asgi() -> None:
    events = prepare_asgi_response_events(
        {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": b"{}",
        },
        limits=default_asgi_adapter_limits(),
    )
    assert events[0]["status"] == 200
    assert (b"content-type", b"application/json") in events[0]["headers"]


def test_status_invalido() -> None:
    _raises(
        prepare_asgi_response_events,
        {"status_code": 99, "headers": {}, "body": b"{}"},
        limits=default_asgi_adapter_limits(),
    )


def test_header_invalido() -> None:
    _raises(
        prepare_asgi_response_events,
        {"status_code": 200, "headers": {"Bad\nName": "x"}, "body": b"{}"},
        limits=default_asgi_adapter_limits(),
    )
    _raises(
        prepare_asgi_response_events,
        {"status_code": 200, "headers": {"X-Test": "bad\rvalue"}, "body": b"{}"},
        limits=default_asgi_adapter_limits(),
    )


def test_utf8_multibyte_limite() -> None:
    limits = {**default_asgi_adapter_limits(), "max_path_bytes": 7}
    from app.asgi.sql_agent_asgi_app import build_http_request_envelope
    import asyncio

    async def receive():
        return {"type": "http.request", "body": b"{}", "more_body": False}

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/ação",
        "query_string": b"",
        "headers": [],
    }
    envelope = asyncio.run(build_http_request_envelope(scope, receive, limits=limits))
    assert envelope["path"] == "/ação"
    scope["path"] = "/ações"
    try:
        asyncio.run(build_http_request_envelope(scope, receive, limits=limits))
    except Exception:
        pass
    else:
        raise AssertionError("Path acima do limite deveria falhar.")


def main() -> None:
    tests = [
        test_limits_validos,
        test_zero_negativo_excessivo,
        test_compatibilidade_body_headers,
        test_defaults_independentes,
        test_status_e_headers_asgi,
        test_status_invalido,
        test_header_invalido,
        test_utf8_multibyte_limite,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()
