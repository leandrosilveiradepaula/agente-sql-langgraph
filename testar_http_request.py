from __future__ import annotations

from copy import deepcopy

from app.http.http_request import (
    HttpRequestError,
    default_http_request_limits,
    parse_http_request_json,
    validate_method_route_and_headers,
)


def _request(**overrides):
    request = {
        "method": "POST",
        "path": "/v1/sql-agent/query",
        "headers": {"Content-Type": "application/json"},
        "body": b'{"question":"ok"}',
    }
    request.update(overrides)
    return request


def _raises(code, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except HttpRequestError as error:
        assert error.code == code
    else:
        raise AssertionError(f"Era esperado {code}.")


def _parse(request, limits=None):
    return parse_http_request_json(
        request,
        limits=limits or default_http_request_limits(),
    )


def _validate(request, limits=None):
    return validate_method_route_and_headers(
        request,
        limits=limits or default_http_request_limits(),
    )


def test_post_valido_content_type_e_accept() -> None:
    _validate(_request(headers={"Content-Type": "application/json"}))
    _validate(_request(headers={"Content-Type": "application/json; charset=utf-8"}))
    _validate(_request(headers={"Content-Type": "application/json", "Accept": "application/json"}))
    _validate(_request(headers={"Content-Type": "application/json", "Accept": "*/*"}))
    _validate(_request(headers={"Content-Type": "application/json", "Accept": "text/html, application/json"}))
    _validate(_request(headers={"Content-Type": "application/json"}))
    assert _parse(_request()) == {"question": "ok"}


def test_metodo_rota_content_type_e_accept_invalidos() -> None:
    _raises("HTTP_METHOD_NOT_ALLOWED", _validate, _request(method="GET"))
    _raises("HTTP_ROUTE_NOT_FOUND", _validate, _request(path="/missing"))
    _raises("HTTP_CONTENT_TYPE_REQUIRED", _validate, _request(headers={}))
    _raises("HTTP_UNSUPPORTED_MEDIA_TYPE", _validate, _request(headers={"Content-Type": "text/plain"}))
    _raises("HTTP_CHARSET_UNSUPPORTED", _validate, _request(headers={"Content-Type": "application/json; charset=latin1"}))
    _raises("HTTP_NOT_ACCEPTABLE", _validate, _request(headers={"Content-Type": "application/json", "Accept": "text/html"}))
    _raises("HTTP_NOT_ACCEPTABLE", _validate, _request(headers={"Content-Type": "application/json", "Accept": "application/json;q=0"}))
    _validate(_request(headers={"Content-Type": "application/json", "Authorization": "Bearer opaque"}))
    _raises("HTTP_JSON_INVALID", _validate, _request(headers={"Content-Type": "application/json", "Cookie": "secret"}))


def test_body_vazio_limite_utf8_e_json_invalido() -> None:
    _raises("HTTP_BODY_REQUIRED", _parse, _request(body=b""))
    _raises(
        "HTTP_BODY_TOO_LARGE",
        _parse,
        _request(body=b'{"question":"toolong"}'),
        {**default_http_request_limits(), "max_request_body_bytes": 4},
    )
    _raises("HTTP_BODY_INVALID_UTF8", _parse, _request(body=b"\xff"))
    _raises("HTTP_JSON_INVALID", _parse, _request(body=b"{"))
    _raises("HTTP_JSON_INVALID", _parse, _request(body=b'{"a":1} garbage'))


def test_json_raiz_constantes_duplicadas_e_complexidade() -> None:
    for body in [b"[]", b'"x"', b"null"]:
        _raises("HTTP_JSON_ROOT_INVALID", _parse, _request(body=body))
    _raises("HTTP_JSON_DUPLICATE_KEY", _parse, _request(body=b'{"a":1,"a":2}'))
    _raises("HTTP_JSON_INVALID", _parse, _request(body=b'{"a":NaN}'))
    _raises("HTTP_JSON_INVALID", _parse, _request(body=b'{"a":Infinity}'))
    _raises(
        "HTTP_JSON_TOO_DEEP",
        _parse,
        _request(body=b'{"a":{"b":{"c":1}}}'),
        {**default_http_request_limits(), "max_json_depth": 2},
    )
    _raises(
        "HTTP_JSON_TOO_COMPLEX",
        _parse,
        _request(body=b'{"a":1,"b":2,"c":3}'),
        {**default_http_request_limits(), "max_json_members": 2},
    )
    _raises(
        "HTTP_JSON_TOO_COMPLEX",
        _parse,
        _request(body=b'{"a":12345}'),
        {**default_http_request_limits(), "max_json_integer_digits": 2},
    )


def test_content_length_e_tamanho_real() -> None:
    _raises("HTTP_CONTENT_LENGTH_INVALID", _parse, _request(headers={"Content-Type": "application/json", "Content-Length": "abc"}))
    _raises("HTTP_CONTENT_LENGTH_INVALID", _parse, _request(headers={"Content-Type": "application/json", "Content-Length": "-1"}))
    _raises("HTTP_CONTENT_LENGTH_INVALID", _parse, _request(headers={"Content-Type": "application/json", "Content-Length": "1,2"}))
    _raises("HTTP_CONTENT_LENGTH_INVALID", _parse, _request(headers={"Content-Type": "application/json", "Content-Length": "1"}))
    _raises(
        "HTTP_BODY_TOO_LARGE",
        _parse,
        _request(headers={"Content-Type": "application/json", "Content-Length": "999"}),
        {**default_http_request_limits(), "max_request_body_bytes": 10},
    )
    _raises(
        "HTTP_BODY_TOO_LARGE",
        _parse,
        _request(headers={"Content-Type": "application/json", "Content-Length": "1"}, body=b'{"question":"abc"}'),
        {**default_http_request_limits(), "max_request_body_bytes": 4},
    )


def test_envelope_nao_mutado() -> None:
    request = _request()
    original = deepcopy(request)
    assert _parse(request) == {"question": "ok"}
    assert request == original


def main() -> None:
    tests = [
        test_post_valido_content_type_e_accept,
        test_metodo_rota_content_type_e_accept_invalidos,
        test_body_vazio_limite_utf8_e_json_invalido,
        test_json_raiz_constantes_duplicadas_e_complexidade,
        test_content_length_e_tamanho_real,
        test_envelope_nao_mutado,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()
