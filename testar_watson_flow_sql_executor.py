from __future__ import annotations

from app.adapters.testing.fake_iam_token_provider import FakeIamTokenProvider
from app.adapters.testing.fake_watson_flow_client import FakeWatsonFlowClient
from app.integrations.watson.configuration import (
    IBM_IAM_TOKEN_URL,
    WATSON_FLOW_CONTRACT_VERSION,
    WatsonFlowConfiguration,
)
from app.integrations.watson.flow_contracts import watson_flow_failure, watson_flow_success
from app.integrations.watson.flow_limits import default_watson_flow_limits
from app.integrations.watson.flow_sql_executor import WatsonFlowSqlExecutorAdapter
from app.integrations.watson.iam_contracts import (
    SensitiveBearerToken,
    iam_token_failure,
    iam_token_success,
)


FLOW_ID = "00e0284a-d785-448b-aed3-95672dd4d189"
SUCCESS = {
    "success": True,
    "data": [{"category": "A", "amount": 10}],
    "columns": ["category", "amount"],
    "row_count": 1,
    "execution_time_ms": 12,
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


def _request(sql: str = "SELECT category, amount FROM t"):
    return {
        "contract_version": "v1.0.0-controlled-sql-execution",
        "current_sql": sql,
        "sql_fingerprint": "sql-fp",
        "request_id": "req",
        "run_id": "run",
        "context_version": "ctx",
        "intent_name": "intent",
        "query_plan_fingerprint": "plan-fp",
        "preflight_fingerprint": "pre-fp",
        "limits": {
            "timeout_seconds": 5,
            "max_rows": 10,
            "max_response_bytes": 10000,
            "max_cell_bytes": 1000,
        },
        "attempt": 1,
        "execution_id": "exec",
        "dialect": None,
        "engine_hint": None,
        "request_fingerprint": "req-fp",
    }


def _adapter(flow_result=None, iam_result=None):
    iam = FakeIamTokenProvider(
        result=iam_result or iam_token_success(SensitiveBearerToken("tok-test"))
    )
    flow = FakeWatsonFlowClient(
        result=flow_result or watson_flow_success(SUCCESS, invocation_id="exec")
    )
    adapter = WatsonFlowSqlExecutorAdapter(
        configuration=_config(),
        limits=default_watson_flow_limits(),
        iam_token_provider=iam,
        flow_client=flow,
    )
    return adapter, iam, flow


def main() -> None:
    adapter, iam, flow = _adapter()
    result = adapter.execute(_request())
    assert result["status"] == "success"
    assert result["row_count"] == 1
    assert _adapter(flow_result=watson_flow_success({"success": True, "data": [], "columns": [], "row_count": 0}, invocation_id="exec"))[0].execute(_request())["row_count"] == 0
    assert _adapter(flow_result=watson_flow_success({**SUCCESS, "truncated": True}, invocation_id="exec"))[0].execute(_request())["truncated"] is True
    assert _adapter(flow_result=watson_flow_success({"success": False, "error": "failed"}, invocation_id="exec"))[0].execute(_request())["status"] == "rejected"
    assert _adapter(iam_result=iam_token_failure("unavailable"))[0].execute(_request())["failure_category"] == "provider_failed"
    assert _adapter(iam_result=iam_token_failure("timeout"))[0].execute(_request())["failure_category"] == "timeout"
    assert _adapter(iam_result=iam_token_failure("authentication_failed"))[0].execute(_request())["failure_category"] == "authentication_failed"
    assert _adapter(flow_result=watson_flow_failure("unavailable", invocation_id="exec"))[0].execute(_request())["failure_category"] == "provider_failed"
    assert _adapter(flow_result=watson_flow_failure("timeout", invocation_id="exec"))[0].execute(_request())["failure_category"] == "timeout"
    assert _adapter(flow_result=watson_flow_failure("rate_limited", invocation_id="exec"))[0].execute(_request())["failure_category"] == "provider_failed"
    assert _adapter(flow_result=watson_flow_failure("http_error", invocation_id="exec", http_status=500))[0].execute(_request())["failure_category"] == "provider_failed"
    assert _adapter(flow_result=watson_flow_failure("invalid_response", invocation_id="exec"))[0].execute(_request())["failure_category"] == "response_invalid"
    ambiguous = {"result": SUCCESS, "output": {"success": True, "data": [{"x": 1}], "columns": ["x"], "row_count": 1}}
    assert _adapter(flow_result=watson_flow_success(ambiguous, invocation_id="exec"))[0].execute(_request())["failure_category"] == "response_invalid"
    invalid = {"success": True, "data": [{"a": object()}], "columns": ["a"], "row_count": 1}
    assert _adapter(flow_result=watson_flow_success(invalid, invocation_id="exec"))[0].execute(_request())["failure_category"] == "response_invalid"
    assert iam.calls == 1
    assert flow.calls == 1
    assert flow.calls == 1
    assert flow.last_request["purpose"] == "execution"
    assert set(flow.last_request["payload"].keys()) == {"sql_query"}
    assert "limit" not in flow.last_request["payload"]
    original = _request("SELECT  a FROM t")
    before = original["current_sql"]
    adapter.execute(original)
    assert original["current_sql"] == before
    assert "sql_transport" not in repr(result).casefold()
    assert "tok-test" not in repr(result)
    assert "raw_output" not in repr(result)
    assert "error': 'failed" not in repr(
        _adapter(
            flow_result=watson_flow_success(
                {"success": False, "error": "failed"},
                invocation_id="exec",
            )
        )[0].execute(_request())
    )
    assert _adapter(iam_result=iam_token_failure("timeout"))[0].execute(_request())["status"] == "error"
    copy_result = adapter.execute(_request())
    copy_result["provider_name"] = "changed"
    assert adapter.execute(_request())["provider_name"] == "watson_flow_sql_executor"
    print("testar_watson_flow_sql_executor.py: 28/28 OK")


if __name__ == "__main__":
    main()
