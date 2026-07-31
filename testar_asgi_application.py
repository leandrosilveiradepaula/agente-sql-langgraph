from __future__ import annotations

import asyncio
import json
from copy import deepcopy

from app.asgi.asgi_limits import default_asgi_adapter_limits
from app.asgi.sql_agent_asgi_app import AsgiSqlAgentApplication


_DEFAULT = object()


class FakeHandler:
    def __init__(self, response=_DEFAULT, exception=None) -> None:
        self.response = _response() if response is _DEFAULT else response
        self.exception = exception
        self.calls = 0
        self.requests = []

    def handle(self, request):
        self.calls += 1
        self.requests.append(deepcopy(request))
        if self.exception is not None:
            raise self.exception
        return deepcopy(self.response)


class Receive:
    def __init__(self, messages):
        self.messages = list(messages)

    async def __call__(self):
        return deepcopy(self.messages.pop(0))


class Send:
    def __init__(self, fail_on=None) -> None:
        self.events = []
        self.fail_on = fail_on

    async def __call__(self, event):
        if event["type"] == self.fail_on:
            raise RuntimeError("send failed with sensitive value")
        self.events.append(deepcopy(event))


def _response(status=200, body=b'{"ok":true}'):
    return {
        "status_code": status,
        "headers": {"Content-Type": "application/json"},
        "body": body,
    }


def _scope(**overrides):
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/sql-agent/query",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
    }
    scope.update(overrides)
    return scope


def _run(handler=None, scope=None, messages=None, send=None, limits=None):
    selected_handler = handler or FakeHandler()
    selected_send = send or Send()
    app = AsgiSqlAgentApplication(
        http_handler=selected_handler,
        asgi_limits=limits or default_asgi_adapter_limits(),
    )
    asyncio.run(
        app(
            _scope() if scope is None else scope,
            Receive(messages or [{"type": "http.request", "body": b"{}", "more_body": False}]),
            selected_send,
        )
    )
    return selected_handler, selected_send


def _body(send):
    return json.loads(send.events[1]["body"].decode("utf-8"))


def test_request_valida_chama_handler_uma_vez() -> None:
    handler, send = _run()
    assert handler.calls == 1
    assert len(send.events) == 2


def test_handler_nao_chamado_em_scope_body_disconnect() -> None:
    for scope, messages in [
        ({"type": "http"}, None),
        (None, [{"type": "http.request", "body": b"x" * 70_000, "more_body": False}]),
        (None, [{"type": "http.disconnect"}]),
    ]:
        handler, send = _run(scope=scope, messages=messages)
        assert handler.calls == 0
        if messages == [{"type": "http.disconnect"}]:
            assert send.events == []


def test_handler_exception_e_resultado_invalido_fail_closed() -> None:
    for handler in [
        FakeHandler(exception=RuntimeError("raw provider token")),
        FakeHandler(response=None),
        FakeHandler(response="bad"),
        FakeHandler(response={"status_code": 700, "headers": {}, "body": b"x"}),
    ]:
        _handler, send = _run(handler=handler)
        assert send.events[0]["status"] == 500
        assert "raw provider token" not in repr(_body(send)).casefold()
        assert handler.calls == 1


def test_sem_retry_e_um_start() -> None:
    handler, send = _run()
    assert handler.calls == 1
    assert [event["type"] for event in send.events].count("http.response.start") == 1


def test_send_failures() -> None:
    try:
        _run(send=Send(fail_on="http.response.start"))
    except RuntimeError:
        pass
    else:
        raise AssertionError("Falha no response.start deveria propagar.")
    send = Send(fail_on="http.response.body")
    _run(send=send)
    assert [event["type"] for event in send.events] == ["http.response.start"]


def test_cancelled_error_preservado() -> None:
    class CancelHandler(FakeHandler):
        def handle(self, request):
            del request
            raise asyncio.CancelledError()

    try:
        _run(handler=CancelHandler())
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("CancelledError nao deve virar 500.")


def test_websocket_nao_chama_handler() -> None:
    handler, send = _run(scope={"type": "websocket"})
    assert handler.calls == 0
    assert send.events == [{"type": "websocket.close", "code": 1003}]


def test_lifespan_startup_shutdown_e_invalido() -> None:
    async def run(messages):
        send = Send()
        app = AsgiSqlAgentApplication(
            http_handler=FakeHandler(),
            asgi_limits=default_asgi_adapter_limits(),
        )
        await app({"type": "lifespan"}, Receive(messages), send)
        return send.events

    events = asyncio.run(
        run(
            [
                {"type": "lifespan.startup"},
                {"type": "lifespan.shutdown"},
            ]
        )
    )
    assert events == [
        {"type": "lifespan.startup.complete"},
        {"type": "lifespan.shutdown.complete"},
    ]
    assert asyncio.run(run([{"type": "weird"}]))[0]["type"] == "lifespan.startup.failed"


def test_chamadas_independentes_e_concorrencia() -> None:
    handler = FakeHandler()
    app = AsgiSqlAgentApplication(
        http_handler=handler,
        asgi_limits=default_asgi_adapter_limits(),
    )

    async def one(body):
        send = Send()
        await app(
            _scope(),
            Receive([{"type": "http.request", "body": body, "more_body": False}]),
            send,
        )
        return send.events

    async def run_both():
        return await asyncio.gather(one(b"one"), one(b"two"))

    first, second = asyncio.run(run_both())
    assert first[1]["body"] == b'{"ok":true}'
    assert second[1]["body"] == b'{"ok":true}'
    assert handler.calls == 2
    assert handler.requests[0]["body"] in {b"one", b"two"}
    assert handler.requests[1]["body"] in {b"one", b"two"}


def main() -> None:
    tests = [
        test_request_valida_chama_handler_uma_vez,
        test_handler_nao_chamado_em_scope_body_disconnect,
        test_handler_exception_e_resultado_invalido_fail_closed,
        test_sem_retry_e_um_start,
        test_send_failures,
        test_cancelled_error_preservado,
        test_websocket_nao_chama_handler,
        test_lifespan_startup_shutdown_e_invalido,
        test_chamadas_independentes_e_concorrencia,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()
