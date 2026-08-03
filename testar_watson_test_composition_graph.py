from __future__ import annotations

from app.adapters.testing.fake_audit_sink import FakeAuditSink
from app.adapters.testing.fake_http_transport import FakeHttpTransport
from app.adapters.testing.fake_observability_sink import FakeObservabilitySink
from app.adapters.testing.fake_run_repository import FakeRunRepository
from app.adapters.testing.fake_secret_value_provider import FakeSecretValueProvider
from app.adapters.testing.fake_sql_repairer import FakeSqlRepairer
from app.composition.watson_test import (
    DeploymentEnvironment,
    build_watson_test_dependencies,
)
from app.graph.builder import create_graph
from app.infrastructure.http.http_contracts import (
    HttpTransportResponse,
    http_transport_failure,
    http_transport_success,
)
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.integrations.watson.flow_limits import default_watson_flow_limits
from app.integrations.watson.live_configuration import (
    create_live_watson_flow_configuration,
)
from testar_grafo_base import FakeSqlGenerator, SuccessContextRepository


FLOW_ID = "00e0284a-d785-448b-aed3-95672dd4d189"
IAM = b'{"access_token":"test-token","token_type":"Bearer","expires_in":3600}'
PREFLIGHT_OK = b'{"success":true,"data":[],"columns":[],"row_count":0}'
EXECUTION_OK = b'{"success":true,"data":[{"id":1}],"columns":["id"],"row_count":1}'


def _json(body: bytes, status: int = 200, headers=None):
    safe_headers = {"Content-Type": "application/json"}
    if headers:
        safe_headers.update(headers)
    return http_transport_success(
        HttpTransportResponse(
            status_code=status,
            headers=safe_headers,
            body=body,
            duration_ms=1,
        )
    )


def _state(max_repair_attempts: int = 1):
    return {
        "question": "Execute uma generic analysis de teste.",
        "user": {"id": "usuario-1", "email": "admin@local.com", "profile": "admin"},
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


def _invoke(sequence, *, repairer=None):
    limits = default_watson_flow_limits()
    secret = FakeSecretValueProvider(secret=SensitiveSecret("test-api-key"))
    transport = FakeHttpTransport(sequence=list(sequence))
    composition = build_watson_test_dependencies(
        environment=DeploymentEnvironment.TEST,
        live_configuration=create_live_watson_flow_configuration(
            api_base_url="https://example.invalid",
            flow_id=FLOW_ID,
            api_key_secret_name="IBM_CLOUD_API_KEY",
            enabled=True,
            limits=limits,
        ),
        limits=limits,
        secret_provider=secret,
        http_transport=transport,
    )
    assert composition.status == "success"
    assert composition.dependencies is not None
    repairer = repairer or FakeSqlRepairer(responses=["SELECT value FROM schema_test.table_test"])
    graph = create_graph(
        SuccessContextRepository(),
        FakeSqlGenerator(),
        composition.dependencies.engine_preflight,
        repairer,
        composition.dependencies.sql_executor,
        FakeRunRepository(),
        FakeAuditSink(),
        FakeObservabilitySink(),
    )
    result = graph.invoke(_state(), config={"recursion_limit": 30})
    return result, secret, transport, repairer


def main() -> None:
    result, secret, transport, repairer = _invoke([
        _json(IAM),
        _json(PREFLIGHT_OK),
        _json(IAM),
        _json(EXECUTION_OK),
    ])
    assert result["application_response"]["status"] == "success"
    assert result["sql_execution_result"]["status"] == "success"
    assert secret.calls == 2
    assert transport.calls == 4
    assert repairer.calls == 0
    operations = [request.operation_name for request in transport.requests]
    assert operations == [
        "watson_iam_token",
        "watson_flow_preflight",
        "watson_iam_token",
        "watson_flow_execution",
    ]
    flow_requests = [request for request in transport.requests if request.operation_name.startswith("watson_flow")]
    assert [request.operation_name for request in flow_requests] == [
        "watson_flow_preflight",
        "watson_flow_execution",
    ]
    assert all(b'"sql_query"' in request.body for request in flow_requests)
    assert all(b'"limit"' not in request.body for request in flow_requests)
    assert all(b"adapter_contract_probe" not in request.body for request in flow_requests)
    serialized = repr(result).casefold()
    public = repr(result["application_response"]).casefold()
    assert "test-token" not in serialized
    assert "raw_output" not in serialized
    assert "sql_transport" not in serialized
    assert "test-token" not in public
    assert "raw_output" not in public
    assert result["persistence_result"]["status"] == "persisted"
    assert result["audit_result"]["status"] == "written"
    assert result["observability_result"]["status"] == "emitted"

    preflight_failure, pre_secret, pre_transport, pre_repair = _invoke([
        _json(IAM),
        _json(b'{"success":false,"error_code":"not_repairable","failure_category":"provider_failed"}'),
    ])
    assert preflight_failure["final_status"] == "rejected"
    assert pre_secret.calls == 1
    assert pre_transport.calls == 2
    assert pre_repair.calls == 0

    iam_failure, iam_secret, iam_transport, iam_repair = _invoke([
        _json(b"{}", status=401),
    ])
    assert iam_failure["final_status"] == "infrastructure_error"
    assert iam_secret.calls == 1
    assert iam_transport.calls == 1
    assert iam_repair.calls == 0

    exec_rate, _, exec_transport, exec_repair = _invoke([
        _json(IAM),
        _json(PREFLIGHT_OK),
        _json(IAM),
        _json(b"{}", status=429),
    ])
    assert exec_rate["final_status"] == "infrastructure_error"
    assert exec_transport.calls == 4
    assert exec_repair.calls == 0

    timeout_result, _, timeout_transport, timeout_repair = _invoke([
        _json(IAM),
        http_transport_failure("timeout"),
    ])
    assert timeout_result["final_status"] == "infrastructure_error"
    assert timeout_transport.calls == 2
    assert timeout_repair.calls == 0

    invalid_result, _, invalid_transport, invalid_repair = _invoke([
        _json(IAM),
        _json(b"{"),
    ])
    assert invalid_result["final_status"] == "infrastructure_error"
    assert invalid_transport.calls == 2
    assert invalid_repair.calls == 0
    print("testar_watson_test_composition_graph.py: 27/27 OK")


if __name__ == "__main__":
    main()
