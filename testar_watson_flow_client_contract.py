from __future__ import annotations

from app.integrations.watson.flow_contracts import (
    watson_flow_failure,
    watson_flow_run_request,
    watson_flow_success,
)
from app.integrations.watson.flow_limits import WatsonFlowContractError, default_watson_flow_limits
from app.integrations.watson.iam_contracts import SensitiveBearerToken


FLOW_ID = "00e0284a-d785-448b-aed3-95672dd4d189"
TOKEN = SensitiveBearerToken("tok-test")
LIMITS = default_watson_flow_limits()


def _request(**overrides):
    values = {
        "flow_id": FLOW_ID,
        "bearer_token": TOKEN,
        "payload": {"sql_query": "SELECT 1"},
        "request_id": "req",
        "run_id": "run",
        "invocation_id": "inv",
        "timeout_seconds": 5,
        "purpose": "preflight",
        "limits": LIMITS,
    }
    values.update(overrides)
    return watson_flow_run_request(**values)


def _raises(fn) -> None:
    try:
        fn()
    except WatsonFlowContractError:
        return
    raise AssertionError("Era esperada falha.")


def main() -> None:
    assert _request(purpose="preflight")["purpose"] == "preflight"
    assert _request(purpose="execution")["purpose"] == "execution"
    _raises(lambda: _request(purpose="other"))
    assert _request()["flow_id"] == FLOW_ID
    assert repr(_request()["bearer_token"]) == "SensitiveBearerToken(<redacted>)"
    assert _request()["payload"] == {"sql_query": "SELECT 1"}
    _raises(lambda: _request(timeout_seconds=0))
    assert watson_flow_success({"success": True}, invocation_id="inv")["status"] == "success"
    assert watson_flow_failure("http_error", invocation_id="inv", http_status=500)["status"] == "http_error"
    assert watson_flow_failure("unavailable", invocation_id="inv")["status"] == "unavailable"
    assert watson_flow_failure("timeout", invocation_id="inv")["status"] == "timeout"
    assert watson_flow_failure("authentication_failed", invocation_id="inv")["status"] == "authentication_failed"
    assert watson_flow_failure("rate_limited", invocation_id="inv")["status"] == "rate_limited"
    assert watson_flow_failure("invalid_response", invocation_id="inv")["status"] == "invalid_response"
    assert watson_flow_failure("unexpected_error", invocation_id="inv")["status"] == "unexpected_error"
    assert watson_flow_failure("rate_limited", invocation_id="inv", retry_after_seconds=1)["retry_after_seconds"] == 1
    _raises(lambda: watson_flow_failure("rate_limited", invocation_id="inv", retry_after_seconds=-1))
    assert "raw_output" in watson_flow_success({"success": True}, invocation_id="inv")
    assert "tok-test" not in repr(_request())
    req = _request()
    original = {"sql_query": "SELECT 1"}
    req2 = _request(payload=original)
    original["sql_query"] = "changed"
    assert req2["payload"]["sql_query"] == "SELECT 1"
    print("testar_watson_flow_client_contract.py: 20/20 OK")


if __name__ == "__main__":
    main()
