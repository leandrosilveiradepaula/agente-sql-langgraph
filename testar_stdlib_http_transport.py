from __future__ import annotations

import socket
import ssl

from app.infrastructure.http.http_contracts import HttpHeader, HttpTransportRequest
from app.infrastructure.http.stdlib_http_transport import StdlibHttpTransport
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.infrastructure.contracts import InfrastructureContractError


class FakeSock:
    def __init__(self) -> None:
        self.timeouts: list[int] = []

    def settimeout(self, value):
        self.timeouts.append(value)


class FakeResponse:
    def __init__(self, *, status=200, headers=None, chunks=None) -> None:
        self.status = status
        self._headers = headers or [("Content-Type", "application/json")]
        self._chunks = list(chunks or [b"{}"])

    def getheaders(self):
        return list(self._headers)

    def getheader(self, name):
        for key, value in self._headers:
            if key.casefold() == name.casefold():
                return value
        return None

    def read(self, size):
        del size
        if self._chunks:
            return self._chunks.pop(0)
        return b""


class FakeConnection:
    instances = []
    response = FakeResponse()
    exception = None
    request_exception = None

    def __init__(self, host, port=None, timeout=None, context=None):
        if FakeConnection.exception is not None:
            raise FakeConnection.exception
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.sock = FakeSock()
        self.requests = []
        self.closed = False
        FakeConnection.instances.append(self)

    def request(self, method, path, body=None, headers=None):
        if FakeConnection.request_exception is not None:
            raise FakeConnection.request_exception
        self.requests.append((method, path, body, dict(headers or {})))

    def getresponse(self):
        return FakeConnection.response

    def close(self):
        self.closed = True


def _reset(response=None, exc=None, request_exc=None):
    FakeConnection.instances = []
    FakeConnection.response = response or FakeResponse()
    FakeConnection.exception = exc
    FakeConnection.request_exception = request_exc


def _request(**overrides):
    values = {
        "method": "POST",
        "url": "https://example.invalid:9443/path",
        "headers": (HttpHeader("Authorization", sensitive_value=SensitiveSecret("Bearer test-token")),),
        "body": b"abc",
        "connect_timeout_seconds": 3,
        "read_timeout_seconds": 4,
        "max_response_bytes": 3,
        "operation_name": "op",
    }
    values.update(overrides)
    return HttpTransportRequest(**values)


def _send(response=None, exc=None, request_exc=None, request=None):
    _reset(response, exc, request_exc)
    transport = StdlibHttpTransport(connection_factory=FakeConnection)
    return transport.send(request or _request())


def main() -> None:
    result = _send()
    conn = FakeConnection.instances[-1]
    assert conn.host == "example.invalid" and conn.port == 9443
    assert conn.context.verify_mode == ssl.CERT_REQUIRED and conn.context.check_hostname is True
    try:
        StdlibHttpTransport(ssl_context=type("Bad", (), {"check_hostname": False, "verify_mode": ssl.CERT_REQUIRED})())
    except ValueError:
        pass
    else:
        raise AssertionError("TLS permissivo deveria falhar.")
    try:
        _request(url="http://example.invalid/path")
    except InfrastructureContractError:
        pass
    assert conn.requests[0][0] == "POST"
    assert conn.requests[0][1] == "/path"
    assert "test-token" not in repr(_request())
    assert conn.requests[0][3]["Content-Length"] == "3"
    assert conn.requests[0][3]["Connection"] == "close"
    assert conn.requests[0][3]["Accept-Encoding"] == "identity"
    assert result.status == "success" and result.response.body == b"{}"
    assert _send(FakeResponse(chunks=[b"{", b"}"])).response.body == b"{}"
    assert _send(FakeResponse(headers=[("Content-Type", "application/json"), ("Content-Length", "3")], chunks=[b"abc"])).status == "success"
    assert _send(FakeResponse(chunks=[b"abcd"])).status == "response_too_large"
    assert _send(FakeResponse(headers=[("Content-Type", "application/json"), ("Content-Length", "4")])).status == "response_too_large"
    assert _send(FakeResponse(headers=[("Content-Type", "application/json"), ("Content-Length", "x")])).status == "invalid_response"
    assert _send(FakeResponse(headers=[("Content-Type", "application/json"), ("Content-Length", "1"), ("Content-Length", "2")])).status == "invalid_response"
    assert _send(FakeResponse(headers=[("Content-Type", "application/json"), ("Content-Length", "3")], chunks=[b"ab"])).status == "invalid_response"
    assert _send(FakeResponse(headers=[("Content-Type", "application/json"), ("Content-Encoding", "identity")])).status == "success"
    assert _send(FakeResponse(headers=[("Content-Type", "application/json"), ("Content-Encoding", "gzip")])).status == "invalid_response"
    assert _send(FakeResponse(headers=[("Content-Type", "application/json"), ("Content-Encoding", "identity"), ("Content-Encoding", "gzip")])).status == "invalid_response"
    assert _send(exc=socket.timeout()).status == "timeout"
    assert _send(exc=socket.gaierror()).status == "dns_failure"
    assert _send(exc=ssl.SSLError()).status == "tls_failure"
    assert _send(exc=ConnectionError()).status == "connection_failure"
    assert _send(exc=ValueError()).status == "unexpected_error"
    assert FakeConnection.instances == []
    _send()
    assert FakeConnection.instances[-1].closed is True
    _send(request_exc=ConnectionError())
    assert FakeConnection.instances[-1].closed is True
    _send()
    assert len(FakeConnection.instances) == 1
    assert _send().status == "success"
    print("testar_stdlib_http_transport.py: 32/32 OK")


if __name__ == "__main__":
    main()
