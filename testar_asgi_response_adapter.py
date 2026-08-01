from __future__ import annotations

from copy import deepcopy

from app.asgi.asgi_limits import default_asgi_adapter_limits
from app.asgi.sql_agent_asgi_app import prepare_asgi_response_events


def _response(status=200, headers=None, body=b'{"ok":true}'):
    return {
        "status_code": status,
        "headers": headers
        if headers is not None
        else {
            "Content-Type": "application/json; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
        },
        "body": body,
    }


def _events(response=None, limits=None):
    return prepare_asgi_response_events(
        response or _response(),
        limits=limits or default_asgi_adapter_limits(),
    )


def _raises(response=None, limits=None) -> None:
    try:
        _events(response=response, limits=limits)
    except Exception:
        return
    raise AssertionError("Era esperado erro.")


def test_response_status_validos() -> None:
    for status in [200, 401, 403, 503]:
        events = _events(_response(status=status))
        assert events[0]["status"] == status


def test_www_authenticate_preservado() -> None:
    events = _events(_response(status=401, headers={"WWW-Authenticate": "Bearer"}))
    assert (b"www-authenticate", b"Bearer") in events[0]["headers"]
    events_403 = _events(_response(status=403, headers={"Content-Type": "application/json"}))
    assert all(name != b"www-authenticate" for name, _value in events_403[0]["headers"])


def test_headers_e_body_preservados() -> None:
    body = b'{"response_fingerprint":"abc"}'
    events = _events(_response(body=body))
    assert (b"x-content-type-options", b"nosniff") in events[0]["headers"]
    assert events[1]["body"] == body
    assert events[1]["more_body"] is False


def test_um_start_e_um_body() -> None:
    events = _events()
    assert events[0]["type"] == "http.response.start"
    assert events[1]["type"] == "http.response.body"


def test_response_invalidas() -> None:
    _raises(_response(status=99))
    _raises(_response(status=True))
    _raises({"status_code": 200, "headers": {}, "body": "bad"})
    _raises(_response(headers={"Bad\nName": "x"}))
    _raises(_response(headers={"X-Test": "bad\r"}))
    _raises(_response(headers={"X-Test": "valor-€"}))
    _raises(
        _response(headers={f"X-{index}": "v" for index in range(40)}),
        limits={**default_asgi_adapter_limits(), "max_response_headers": 10},
    )


def test_content_length() -> None:
    events = _events(_response(body=b"abc"))
    assert (b"content-length", b"3") in events[0]["headers"]
    events = _events(_response(headers={"Content-Length": "3"}, body=b"abc"))
    assert (b"content-length", b"3") in events[0]["headers"]
    _raises(_response(headers={"Content-Length": "2"}, body=b"abc"))


def test_sem_server_date_e_independencia() -> None:
    response = _response()
    original = deepcopy(response)
    events = _events(response)
    headers = dict(events[0]["headers"])
    assert b"server" not in headers
    assert b"date" not in headers
    response["body"] = b"changed"
    assert events[1]["body"] == original["body"]
    assert original != response


def main() -> None:
    tests = [
        test_response_status_validos,
        test_www_authenticate_preservado,
        test_headers_e_body_preservados,
        test_um_start_e_um_body,
        test_response_invalidas,
        test_content_length,
        test_sem_server_date_e_independencia,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()
