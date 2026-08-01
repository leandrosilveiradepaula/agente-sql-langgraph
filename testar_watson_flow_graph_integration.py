from __future__ import annotations

from app.adapters.testing.fake_audit_sink import FakeAuditSink
from app.adapters.testing.fake_iam_token_provider import FakeIamTokenProvider
from app.adapters.testing.fake_observability_sink import FakeObservabilitySink
from app.adapters.testing.fake_run_repository import FakeRunRepository
from app.adapters.testing.fake_sql_repairer import FakeSqlRepairer
from app.adapters.testing.fake_watson_flow_client import FakeWatsonFlowClient
from app.graph.builder import create_graph
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
from app.integrations.watson.flow_sql_executor import (
    WatsonFlowSqlExecutorAdapter,
)
from app.integrations.watson.iam_contracts import (
    SensitiveBearerToken,
    iam_token_success,
)
from testar_grafo_base import (
    FakeSqlGenerator,
    SuccessContextRepository,
)


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


def _state(max_repair_attempts: int = 1):
    return {
        "question": "Execute uma generic analysis de teste.",
        "user": {
            "id": "usuario-1",
            "email": "admin@local.com",
            "profile": "admin",
        },
        "options": {
            "use_cache": False,
            "max_repair_attempts": max_repair_attempts,
            "shadow_mode": False,
            "sql_execution_limits": {
                "timeout_seconds": 10,
                "max_rows": 5,
                "max_response_bytes": 4096,
                "max_cell_bytes": 128,
            },
        },
    }


def _graph(flow_sequence):
    limits = default_watson_flow_limits()
    iam = FakeIamTokenProvider(
        result=iam_token_success(SensitiveBearerToken("tok-test"))
    )
    flow = FakeWatsonFlowClient(sequence=flow_sequence)
    preflight = WatsonFlowEnginePreflightAdapter(
        configuration=_config(),
        limits=limits,
        iam_token_provider=iam,
        flow_client=flow,
    )
    executor = WatsonFlowSqlExecutorAdapter(
        configuration=_config(),
        limits=limits,
        iam_token_provider=iam,
        flow_client=flow,
    )
    graph = create_graph(
        SuccessContextRepository(),
        FakeSqlGenerator(),
        preflight,
        FakeSqlRepairer(responses=["SELECT value FROM schema_test.table_test"]),
        executor,
        FakeRunRepository(),
        FakeAuditSink(),
        FakeObservabilitySink(),
    )
    return graph, iam, flow


def _invoke(flow_sequence, max_repair_attempts: int = 1):
    graph, iam, flow = _graph(flow_sequence)
    result = graph.invoke(
        _state(max_repair_attempts=max_repair_attempts),
        config={"recursion_limit": 30},
    )
    return result, iam, flow


def main() -> None:
    success_rows = {
        "success": True,
        "data": [{"id": 1}],
        "columns": ["id"],
        "row_count": 1,
    }
    result, iam, flow = _invoke(
        [
            watson_flow_success({"success": True, "data": [], "columns": [], "row_count": 0}, invocation_id="pre"),
            watson_flow_success(success_rows, invocation_id="exec"),
        ]
    )
    assert result["final_status"] == "approved"
    assert result["sql_execution_result"]["status"] == "success"
    assert result["normalized_result"]["status"] == "success"
    assert result["serialized_result"]["status"] == "success"
    assert result["application_response"]["status"] == "success"
    assert iam.calls == 2
    assert flow.calls == 2
    assert [req["purpose"] for req in flow.requests] == ["preflight", "execution"]
    assert all(set(req["payload"].keys()) == {"sql_query"} for req in flow.requests)

    repair_result, repair_iam, repair_flow = _invoke(
        [
            watson_flow_success(
                {
                    "success": False,
                    "error_code": "column_not_found",
                    "failure_category": "column_not_found",
                },
                invocation_id="pre-1",
            ),
            watson_flow_success({"success": True, "data": [], "columns": [], "row_count": 0}, invocation_id="pre-2"),
            watson_flow_success({"success": True, "data": [{"value": 1}], "columns": ["value"], "row_count": 1}, invocation_id="exec"),
        ]
    )
    assert repair_result["final_status"] == "approved"
    assert repair_result["repair_attempts"] == 1
    assert repair_iam.calls == 3
    assert repair_flow.calls == 3

    infra_result, infra_iam, infra_flow = _invoke(
        [watson_flow_failure("timeout", invocation_id="pre-timeout")]
    )
    assert infra_result["final_status"] == "infrastructure_error"
    assert infra_result.get("sql_execution_result") is None
    assert infra_iam.calls == 1
    assert infra_flow.calls == 1

    failure_result, _, failure_flow = _invoke(
        [
            watson_flow_success({"success": True, "data": [], "columns": [], "row_count": 0}, invocation_id="pre"),
            watson_flow_success({"success": False, "error": "generic failure"}, invocation_id="exec"),
        ]
    )
    assert failure_result["final_status"] == "rejected"
    assert failure_result["sql_execution_result"]["status"] == "rejected"
    assert failure_flow.calls == 2

    invalid_result, _, invalid_flow = _invoke(
        [
            watson_flow_success({"success": True, "data": [], "columns": [], "row_count": 0}, invocation_id="pre"),
            watson_flow_success({"success": "true"}, invocation_id="exec"),
        ]
    )
    assert invalid_result["final_status"] == "rejected"
    assert invalid_result["sql_execution_result"]["failure_category"] == "response_invalid"
    assert invalid_flow.calls == 2

    serialized = repr(result).casefold()
    assert "tok-test" not in serialized
    assert "sql_transport" not in serialized
    assert "raw_output" not in serialized
    assert "graphstate" not in repr(result["application_response"]).casefold()
    assert result["run_record"]["status"] == "built"
    assert result["run_record"]["outcome"] == "success"
    assert result["persistence_result"]["status"] == "persisted"
    assert result["audit_result"]["status"] == "written"
    assert result["observability_result"]["status"] == "emitted"
    print("testar_watson_flow_graph_integration.py: 21/21 OK")


if __name__ == "__main__":
    main()
