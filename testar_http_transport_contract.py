from __future__ import annotations

from app.infrastructure.http.http_contracts import (
    HttpHeader,
    HttpTransportRequest,
    HttpTransportResponse,
    http_transport_failure,
    http_transport_success,
)
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.infrastructure.contracts import InfrastructureContractError


def _raises(fn, exc=Exception) -> None:
    try:
        fn()
    except exc:
        return
    raise AssertionError("Era esperada falha.")


def _request(**overrides):
    values = {
        "method": "POST",
        "url": "https://example.invalid/path",
        "headers": (HttpHeader("Accept", public_value="application/json"),),
        "body": b"{}",
        "connect_timeout_seconds": 1,
        "read_timeout_seconds": 2,
        "max_response_bytes": 10,
        "operation_name": "op",
    }
    values.update(overrides)
    return HttpTransportRequest(**values)


def main() -> None:
    assert _request().method == "POST"
    _raises(lambda: _request(method="GET"), InfrastructureContractError)
    _raises(lambda: _request(url="not-url"), InfrastructureContractError)
    _raises(lambda: _request(url="http://example.invalid/path"), InfrastructureContractError)
    _raises(lambda: _request(url="https://u:p@example.invalid/path"), InfrastructureContractError)
    _raises(lambda: _request(url="https://example.invalid/path?q=1"), InfrastructureContractError)
    assert _request(url="https://example.invalid/path?q=1", allow_query=True).allow_query is True
    _raises(lambda: _request(url="https://example.invalid/path#f"), InfrastructureContractError)
    assert repr(HttpHeader("Accept", public_value="application/json"))
    sensitive = HttpHeader("Authorization", sensitive_value=SensitiveSecret("Bearer test-token"))
    assert "test-token" not in repr(sensitive)
    _raises(lambda: HttpHeader("X-Test", public_value="a\nb"), InfrastructureContractError)
    _raises(lambda: _request(headers=(sensitive, sensitive)), InfrastructureContractError)
    cl = HttpHeader("Content-Length", public_value="1")
    _raises(lambda: _request(headers=(cl, cl)), InfrastructureContractError)
    assert _request(body=b"abc").body == b"abc"
    _raises(lambda: _request(body="abc"), InfrastructureContractError)
    _raises(lambda: _request(connect_timeout_seconds=0), InfrastructureContractError)
    _raises(lambda: _request(read_timeout_seconds=True), InfrastructureContractError)
    _raises(lambda: _request(max_response_bytes=0), InfrastructureContractError)
    response = HttpTransportResponse(status_code=200, headers={"Content-Type": "application/json", "Set-Cookie": "x"}, body=b"{}")
    assert response.headers == {"content-type": "application/json"}
    assert http_transport_success(response).status == "success"
    for status in ("timeout", "dns_failure", "tls_failure", "connection_failure", "response_too_large", "invalid_response", "unexpected_error"):
        assert http_transport_failure(status).status == status
    assert "Bearer" not in repr(http_transport_failure("unexpected_error", diagnostics={"authorization": "Bearer test-token"}))
    print("testar_http_transport_contract.py: 26/26 OK")


if __name__ == "__main__":
    main()
