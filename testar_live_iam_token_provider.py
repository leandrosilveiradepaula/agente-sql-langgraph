from __future__ import annotations

from urllib.parse import parse_qs

from app.adapters.testing.fake_http_transport import FakeHttpTransport
from app.adapters.testing.fake_secret_value_provider import FakeSecretValueProvider
from app.infrastructure.http.http_contracts import (
    HttpTransportResponse,
    http_transport_failure,
    http_transport_success,
)
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.integrations.watson.configuration import IBM_IAM_TOKEN_URL, WATSON_FLOW_CONTRACT_VERSION, WatsonFlowConfiguration
from app.integrations.watson.live_iam_token_provider import LiveIamTokenProvider
from app.ports.secret_value_provider import SecretName


FLOW_ID = "00e0284a-d785-448b-aed3-95672dd4d189"


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


def _response(body=b'{"access_token":"test-token","token_type":"Bearer","expires_in":3600}', status=200, content_type="application/json"):
    return http_transport_success(HttpTransportResponse(status_code=status, headers={"Content-Type": content_type}, body=body))


def _provider(result=None, secret="test-api-key"):
    transport = FakeHttpTransport(result=result or _response())
    secret_provider = FakeSecretValueProvider(secret=SensitiveSecret(secret))
    provider = LiveIamTokenProvider(
        configuration=_config(),
        api_key_secret_name=SecretName("IBM_CLOUD_API_KEY"),
        secret_provider=secret_provider,
        http_transport=transport,
    )
    return provider, secret_provider, transport


def _request():
    return {"request_id": "req", "run_id": "run", "timeout_seconds": 5, "force_refresh": False}


def main() -> None:
    provider, secrets, transport = _provider()
    result = provider.get_token(_request())
    assert result["status"] == "success"
    assert secrets.calls == 1
    assert transport.calls == 1
    req = transport.last_request
    assert req.method == "POST"
    assert req.url == IBM_IAM_TOKEN_URL
    headers = {header.name: header for header in req.headers}
    assert headers["Content-Type"].public_value == "application/x-www-form-urlencoded"
    assert headers["Accept"].public_value == "application/json"
    assert headers["Accept-Encoding"].public_value == "identity"
    assert "Authorization" not in headers
    parsed = parse_qs(req.body.decode("ascii"))
    assert parsed["grant_type"] == ["urn:ibm:params:oauth:grant-type:apikey"]
    assert parsed["apikey"] == ["test-api-key"]
    special = _provider(secret="test key+:/")[0]
    assert special.get_token(_request())["status"] == "success"
    assert "test-api-key" not in repr(req)
    assert "test-api-key" not in repr(provider.get_token(_request()))
    for status in (400, 401, 403):
        assert _provider(_response(status=status))[0].get_token(_request())["status"] == "authentication_failed"
    assert _provider(_response(status=429))[0].get_token(_request())["status"] == "unavailable"
    assert _provider(_response(status=500))[0].get_token(_request())["status"] == "unavailable"
    assert _provider(http_transport_failure("timeout"))[0].get_token(_request())["status"] == "timeout"
    for failure in ("dns_failure", "tls_failure", "connection_failure"):
        assert _provider(http_transport_failure(failure))[0].get_token(_request())["status"] == "unavailable"
    assert _provider(_response(content_type=None))[0].get_token(_request())["status"] == "invalid_response"
    assert _provider(_response(content_type="text/plain"))[0].get_token(_request())["status"] == "invalid_response"
    assert _provider(_response(content_type="application/json; charset=latin-1"))[0].get_token(_request())["status"] == "invalid_response"
    assert _provider(_response(body=b"{"))[0].get_token(_request())["status"] == "invalid_response"
    assert _provider(_response(body=b'{"access_token":"a","access_token":"b"}'))[0].get_token(_request())["status"] == "invalid_response"
    assert _provider(_response(body=b'[]'))[0].get_token(_request())["status"] == "invalid_response"
    assert _provider(_response(body=b'{"token_type":"Bearer"}'))[0].get_token(_request())["status"] == "invalid_response"
    assert _provider(_response(body=b'{"access_token":1}'))[0].get_token(_request())["status"] == "invalid_response"
    assert _provider(_response(body=b'{"access_token":"test-token","token_type":"Basic"}'))[0].get_token(_request())["status"] == "invalid_response"
    assert _provider(_response(body=b'{"access_token":"test-token","expires_in":true}'))[0].get_token(_request())["status"] == "invalid_response"
    assert _provider(_response(body=b'{"access_token":"test-token","expires_in":-1}'))[0].get_token(_request())["status"] == "invalid_response"
    assert _provider(http_transport_failure("response_too_large"))[0].get_token(_request())["status"] == "invalid_response"
    assert "test-token" not in repr(result)
    provider, _, transport = _provider()
    provider.get_token(_request())
    assert transport.calls == 1
    print("testar_live_iam_token_provider.py: 32/32 OK")


if __name__ == "__main__":
    main()
