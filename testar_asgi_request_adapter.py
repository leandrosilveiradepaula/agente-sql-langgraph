from __future__ import annotations

import asyncio
from copy import deepcopy

from app.asgi.asgi_limits import default_asgi_adapter_limits
from app.asgi.sql_agent_asgi_app import build_http_request_envelope


def _scope(**overrides):
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/v1/sql-agent/query",
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"authorization", b"Bearer token"),
        ],
        "scheme": "http",
        "client": ("127.0.0.1", 1234),
        "server": ("example.invalid", 80),
    }
    scope.update(overrides)
    return scope


class Receive:
    def __init__(self, messages):
        self.messages = list(messages)
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        return deepcopy(self.messages.pop(0))


def _build(scope=None, messages=None, limits=None):
    receive = Receive(messages or [{"type": "http.request", "body": b"{}", "more_body": False}])
    result = asyncio.run(
        build_http_request_envelope(
            _scope() if scope is None else scope,
            receive,
            limits=limits or default_asgi_adapter_limits(),
        )
    )
    return result, receive


def _raises(scope=None, messages=None, limits=None) -> None:
    try:
        _build(scope=scope, messages=messages, limits=limits)
    except Exception:
        return
    raise AssertionError("Era esperado erro ASGI.")


def test_scope_http_valido() -> None:
    envelope, _receive = _build()
    assert envelope["method"] == "POST"
    assert envelope["path"] == "/v1/sql-agent/query"


def test_scope_invalidos() -> None:
    _raises(scope=[])
    _raises(scope={"method": "POST"})
    _raises(scope=_scope(type="unknown"))


def test_method_invalidos() -> None:
    _raises(scope=_scope(method=None))
    _raises(scope=_scope(method=""))
    _raises(scope=_scope(method="   "))
    _raises(scope=_scope(method="PO\nST"))


def test_path_invalidos() -> None:
    _raises(scope=_scope(path=None))
    _raises(scope=_scope(path="/bad\x00path"))
    _raises(scope=_scope(path="/" + "x" * 600))


def test_query_string() -> None:
    envelope, _receive = _build(scope=_scope(query_string=b"a=1"))
    assert envelope["path"] == "/v1/sql-agent/query"
    assert envelope["query_string"] == "a=1"
    _raises(scope=_scope(query_string=b"x" * 3000))
    _raises(scope=_scope(query_string="bad"))


def test_headers_validos_e_duplicados() -> None:
    envelope, _receive = _build(
        scope=_scope(
            headers=[
                (b"content-type", b"application/json"),
                (b"authorization", b"Bearer one"),
                (b"authorization", b"Bearer two"),
            ]
        )
    )
    values = [value for name, value in envelope["headers"].items() if name == "authorization"]
    assert values == ["Bearer one", "Bearer two"]


def test_headers_invalidos() -> None:
    _raises(scope=_scope(headers=[(b"Content-Type", b"application/json")]))
    _raises(scope=_scope(headers=[(b"bad\n", b"x")]))
    _raises(scope=_scope(headers=[(b"x-test", b"bad\r")]))
    _raises(scope=_scope(headers=[(b"x-test", b"bad\n")]))
    _raises(scope=_scope(headers=[(b"x", b"y")] * 40))
    _raises(scope=_scope(headers=[(b"x" * 80, b"y")]))


def test_body_chunks() -> None:
    envelope, _receive = _build(
        messages=[
            {"type": "http.request", "body": b"{", "more_body": True},
            {"type": "http.request", "body": b"}", "more_body": False},
        ]
    )
    assert envelope["body"] == b"{}"


def test_body_limites() -> None:
    limits = {**default_asgi_adapter_limits(), "max_request_body_bytes": 2}
    _build(messages=[{"type": "http.request", "body": b"ab", "more_body": False}], limits=limits)
    _raises(messages=[{"type": "http.request", "body": b"abc", "more_body": False}], limits=limits)


def test_chunk_limites() -> None:
    limits = {**default_asgi_adapter_limits(), "max_request_chunks": 2}
    _build(
        messages=[
            {"type": "http.request", "body": b"", "more_body": True},
            {"type": "http.request", "body": b"", "more_body": False},
        ],
        limits=limits,
    )
    _raises(
        messages=[
            {"type": "http.request", "body": b"", "more_body": True},
            {"type": "http.request", "body": b"", "more_body": True},
            {"type": "http.request", "body": b"", "more_body": False},
        ],
        limits=limits,
    )


def test_eventos_invalidos_e_disconnect() -> None:
    _raises(messages=[{"type": "http.request", "body": "x", "more_body": False}])
    _raises(messages=[{"type": "http.request", "body": b"x", "more_body": "no"}])
    _raises(messages=[{"type": "weird"}])
    _raises(messages=[{"type": "http.disconnect"}])
    _raises(
        messages=[
            {"type": "http.request", "body": b"x", "more_body": True},
            {"type": "http.disconnect"},
        ]
    )


def test_nao_chama_receive_apos_final_e_nao_muta() -> None:
    scope = _scope()
    original_scope = deepcopy(scope)
    messages = [{"type": "http.request", "body": b"{}", "more_body": False}]
    original_messages = deepcopy(messages)
    _envelope, receive = _build(scope=scope, messages=messages)
    assert receive.calls == 1
    assert scope == original_scope
    assert messages == original_messages


def main() -> None:
    tests = [
        test_scope_http_valido,
        test_scope_invalidos,
        test_method_invalidos,
        test_path_invalidos,
        test_query_string,
        test_headers_validos_e_duplicados,
        test_headers_invalidos,
        test_body_chunks,
        test_body_limites,
        test_chunk_limites,
        test_eventos_invalidos_e_disconnect,
        test_nao_chama_receive_apos_final_e_nao_muta,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()
