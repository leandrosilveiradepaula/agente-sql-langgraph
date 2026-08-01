from __future__ import annotations

from app.infrastructure.http.http_contracts import (
    HttpHeader,
    HttpTransportRequest,
    HttpTransportResponse,
    http_transport_failure,
    http_transport_success,
)
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.integrations.watson.flow_limits import WatsonFlowContractError


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
    _raises(lambda: _request(method="GET"), WatsonFlowContractError)
    _raises(lambda: _request(url="not-url"), WatsonFlowContractError)
    _raises(lambda: _request(url="http://example.invalid/path"), WatsonFlowContractError)
    _raises(lambda: _request(url="https://u:p@example.invalid/path"), WatsonFlowContractError)
    _raises(lambda: _request(url="https://example.invalid/path?q=1"), WatsonFlowContractError)
    assert _request(url="https://example.invalid/path?q=1", allow_query=True).allow_query is True
    _raises(lambda: _request(url="https://example.invalid/path#f"), WatsonFlowContractError)
    assert repr(HttpHeader("Accept", public_value="application/json"))
    sensitive = HttpHeader("Authorization", sensitive_value=SensitiveSecret("Bearer test-token"))
    assert "test-token" not in repr(sensitive)
    _raises(lambda: HttpHeader("X-Test", public_value="a\nb"), WatsonFlowContractError)
    _raises(lambda: _request(headers=(sensitive, sensitive)), WatsonFlowContractError)
    cl = HttpHeader("Content-Length", public_value="1")
    _raises(lambda: _request(headers=(cl, cl)), WatsonFlowContractError)
    assert _request(body=b"abc").body == b"abc"
    _raises(lambda: _request(body="abc"), WatsonFlowContractError)
    _raises(lambda: _request(connect_timeout_seconds=0), WatsonFlowContractError)
    _raises(lambda: _request(read_timeout_seconds=True), WatsonFlowContractError)
    _raises(lambda: _request(max_response_bytes=0), WatsonFlowContractError)
    response = HttpTransportResponse(status_code=200, headers={"Content-Type": "application/json", "Set-Cookie": "x"}, body=b"{}")
    assert response.headers == {"content-type": "application/json"}
    assert http_transport_success(response).status == "success"
    for status in ("timeout", "dns_failure", "tls_failure", "connection_failure", "response_too_large", "invalid_response", "unexpected_error"):
        assert http_transport_failure(status).status == status
    assert "Bearer" not in repr(http_transport_failure("unexpected_error", diagnostics={"authorization": "Bearer test-token"}))
    print("testar_http_transport_contract.py: 26/26 OK")


if __name__ == "__main__":
    main()
