from __future__ import annotations

from app.adapters.testing.fake_iam_token_provider import FakeIamTokenProvider
from app.adapters.testing.fake_watson_flow_client import FakeWatsonFlowClient
from app.integrations.watson.configuration import (
    IBM_IAM_TOKEN_URL,
    WATSON_FLOW_CONTRACT_VERSION,
    WatsonFlowConfiguration,
)
from app.integrations.watson.flow_contracts import (
    watson_flow_failure,
    watson_flow_success,
)
from app.integrations.watson.flow_limits import default_watson_flow_limits
from app.integrations.watson.flow_preflight_adapter import (
    WatsonFlowEnginePreflightAdapter,
)
from app.integrations.watson.iam_contracts import (
    SensitiveBearerToken,
    iam_token_failure,
    iam_token_success,
)


FLOW_ID = "00e0284a-d785-448b-aed3-95672dd4d189"
SUCCESS = {"success": True, "data": [], "columns": [], "row_count": 0}
SQL_ERROR = {
    "success": False,
    "error_code": "column_not_found",
    "failure_category": "column_not_found",
}


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


def _request(sql: str = "SELECT a FROM t"):
    return {
        "sql": sql,
        "request_fingerprint": "req-fp",
        "query_plan_fingerprint": "plan-fp",
        "timeout_ms": 5000,
    }


def _adapter(flow_result=None, iam_result=None):
    iam = FakeIamTokenProvider(
        result=iam_result or iam_token_success(SensitiveBearerToken("tok-test"))
    )
    flow = FakeWatsonFlowClient(
        result=flow_result or watson_flow_success(SUCCESS, invocation_id="inv")
    )
    adapter = WatsonFlowEnginePreflightAdapter(
        configuration=_config(),
        limits=default_watson_flow_limits(),
        iam_token_provider=iam,
        flow_client=flow,
    )
    return adapter, iam, flow


def main() -> None:
    adapter, iam, flow = _adapter()
    result = adapter.preflight(_request())
    assert result["status"] == "approved"
    assert result["statement_planned"] is True

    adapter, _, _ = _adapter(watson_flow_success(SQL_ERROR, invocation_id="inv"))
    result = adapter.preflight(_request())
    assert result["status"] == "rejected"
    assert result["repairable"] is True

    adapter, _, _ = _adapter(watson_flow_success({"success": False}, invocation_id="inv"))
    assert adapter.preflight(_request())["repairable"] is False
    assert _adapter(iam_result=iam_token_failure("unavailable"))[0].preflight(_request())["failure_category"] == "provider_unavailable"
    assert _adapter(iam_result=iam_token_failure("timeout"))[0].preflight(_request())["failure_category"] == "timeout"
    assert _adapter(iam_result=iam_token_failure("authentication_failed"))[0].preflight(_request())["failure_category"] == "authentication_failed"
    assert _adapter(flow_result=watson_flow_failure("unavailable", invocation_id="inv"))[0].preflight(_request())["failure_category"] == "provider_unavailable"
    assert _adapter(flow_result=watson_flow_failure("timeout", invocation_id="inv"))[0].preflight(_request())["failure_category"] == "timeout"
    assert _adapter(flow_result=watson_flow_failure("rate_limited", invocation_id="inv"))[0].preflight(_request())["failure_category"] == "provider_unavailable"
    assert _adapter(flow_result=watson_flow_failure("invalid_response", invocation_id="inv"))[0].preflight(_request())["failure_category"] == "protocol_error"
    ambiguous = {"result": SUCCESS, "output": {"success": True, "data": [{"a": 1}], "columns": ["a"], "row_count": 1}}
    assert _adapter(flow_result=watson_flow_success(ambiguous, invocation_id="inv"))[0].preflight(_request())["status"] == "error"
    large = {"success": True, "data": [{"a": "x" * 2_000_000}], "columns": ["a"], "row_count": 1}
    assert _adapter(flow_result=watson_flow_success(large, invocation_id="inv"))[0].preflight(_request())["status"] == "error"
    assert iam.calls == 1
    assert flow.calls == 1
    assert flow.calls == 1
    assert set(flow.last_request["payload"].keys()) == {"sql_query"}
    assert "limit" not in flow.last_request["payload"]
    assert flow.last_request["purpose"] == "preflight"
    original = _request("SELECT  a FROM t")
    before = original["sql"]
    adapter.preflight(original)
    assert original["sql"] == before
    assert "sql_transport" not in repr(result).casefold()
    assert "tok-test" not in repr(result)
    assert "raw_output" not in repr(result)
    assert _adapter(iam_result=iam_token_failure("timeout"))[0].preflight(_request()).get("repairable") is False
    copy_result = adapter.preflight(_request())
    copy_result["provider_name"] = "changed"
    assert adapter.preflight(_request())["provider_name"] == "watson_flow_preflight"
    print("testar_watson_flow_preflight_adapter.py: 24/24 OK")


if __name__ == "__main__":
    main()
