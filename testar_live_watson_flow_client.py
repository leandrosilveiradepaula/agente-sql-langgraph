from __future__ import annotations

import json

from app.adapters.testing.fake_http_transport import FakeHttpTransport
from app.infrastructure.http.http_contracts import HttpTransportResponse, http_transport_failure, http_transport_success
from app.integrations.watson.configuration import IBM_IAM_TOKEN_URL, WATSON_FLOW_CONTRACT_VERSION, WatsonFlowConfiguration
from app.integrations.watson.flow_contracts import watson_flow_run_request
from app.integrations.watson.flow_limits import default_watson_flow_limits
from app.integrations.watson.iam_contracts import SensitiveBearerToken
from app.integrations.watson.live_watson_flow_client import LiveWatsonFlowClient


FLOW_ID = "00e0284a-d785-448b-aed3-95672dd4d189"
LIMITS = default_watson_flow_limits()


def _config():
    return WatsonFlowConfiguration(
        api_base_url="https://example.invalid",
        flow_id=FLOW_ID,
        iam_token_url=IBM_IAM_TOKEN_URL,
        contract_version=WATSON_FLOW_CONTRACT_VERSION,
        connect_timeout_seconds=3,
        request_timeout_seconds=5,
        max_response_bytes=1000,
    )


def _response(body=b'{"success":true,"data":[],"columns":[],"row_count":0}', status=200, content_type="application/json", headers=None):
    safe_headers = {"Content-Type": content_type} if content_type is not None else {}
    if headers:
        safe_headers.update(headers)
    return http_transport_success(HttpTransportResponse(status_code=status, headers=safe_headers, body=body))


def _client(result=None):
    transport = FakeHttpTransport(result=result or _response())
    client = LiveWatsonFlowClient(configuration=_config(), http_transport=transport, limits=LIMITS)
    return client, transport


def _request(purpose="preflight", payload=None):
    return watson_flow_run_request(
        flow_id=FLOW_ID,
        bearer_token=SensitiveBearerToken("test-token"),
        payload=payload or {"sql_query": "SELECT 1"},
        request_id="req",
        run_id="run",
        invocation_id="inv",
        timeout_seconds=5,
        purpose=purpose,
        limits=LIMITS,
    )


def main() -> None:
    client, transport = _client()
    result = client.run_flow(_request())
    assert result["status"] == "success"
    assert transport.calls == 1
    req = transport.last_request
    assert req.url == f"https://example.invalid/v1/orchestrate/flows/{FLOW_ID}/run"
    assert "/v1/orchestrate/flows/" in req.url and req.url.endswith("/run")
    client.run_flow(_request("preflight"))
    assert transport.last_request.operation_name == "watson_flow_preflight"
    client, transport = _client()
    client.run_flow(_request("execution"))
    assert transport.last_request.operation_name == "watson_flow_execution"
    payload = json.loads(transport.last_request.body.decode("utf-8"))
    assert set(payload.keys()) == {"sql_query"}
    assert "limit" not in payload and "max_rows" not in payload
    assert "test-token" not in repr(transport.last_request)
    headers = {header.name: header for header in transport.last_request.headers}
    assert "test-token" not in repr(headers["Authorization"])
    assert headers["Content-Type"].public_value == "application/json"
    assert headers["Accept"].public_value == "application/json"
    assert headers["Accept-Encoding"].public_value == "identity"
    assert "Content-Length" not in headers
    for code, status in ((400, "http_error"), (401, "authentication_failed"), (403, "authentication_failed"), (404, "unavailable"), (408, "timeout"), (413, "http_error"), (429, "rate_limited"), (500, "unavailable")):
        assert _client(_response(status=code))[0].run_flow(_request())["status"] == status
    assert _client(_response(status=429, headers={"Retry-After": "3"}))[0].run_flow(_request())["retry_after_seconds"] == 3
    assert "retry_after_seconds" in _client(_response(status=429, headers={"Retry-After": "bad"}))[0].run_flow(_request())
    for failure, status in (("timeout", "timeout"), ("dns_failure", "unavailable"), ("tls_failure", "unavailable"), ("connection_failure", "unavailable")):
        assert _client(http_transport_failure(failure))[0].run_flow(_request())["status"] == status
    assert _client(_response(content_type=None))[0].run_flow(_request())["status"] == "invalid_response"
    assert _client(_response(content_type="text/plain"))[0].run_flow(_request())["status"] == "invalid_response"
    assert _client(_response(content_type="application/json; charset=latin-1"))[0].run_flow(_request())["status"] == "invalid_response"
    assert _client(_response(body=b"{"))[0].run_flow(_request())["status"] == "invalid_response"
    assert _client(_response(body=b'{"success":true,"success":false}'))[0].run_flow(_request())["status"] == "invalid_response"
    assert _client(_response(body=b"[]"))[0].run_flow(_request())["status"] == "invalid_response"
    too_large_limits = default_watson_flow_limits()
    huge_payload = {"sql_query": "x" * (too_large_limits.max_payload_bytes + 1)}
    assert _client()[0].run_flow(_request(payload=huge_payload))["status"] == "invalid_response"
    assert "raw-provider-body" not in repr(_client(_response(body=b'{"success":true,"data":"raw-provider-body"}'))[0].run_flow(_request()))
    assert "SELECT 1" not in repr(_client(http_transport_failure("unexpected_error"))[0].run_flow(_request()))
    client, transport = _client()
    client.run_flow(_request())
    assert transport.calls == 1
    print("testar_live_watson_flow_client.py: 36/36 OK")


if __name__ == "__main__":
    main()
