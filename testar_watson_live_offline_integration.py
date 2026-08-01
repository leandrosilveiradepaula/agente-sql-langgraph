from __future__ import annotations

from app.adapters.testing.fake_audit_sink import FakeAuditSink
from app.adapters.testing.fake_http_transport import FakeHttpTransport
from app.adapters.testing.fake_observability_sink import FakeObservabilitySink
from app.adapters.testing.fake_run_repository import FakeRunRepository
from app.adapters.testing.fake_secret_value_provider import FakeSecretValueProvider
from app.adapters.testing.fake_sql_repairer import FakeSqlRepairer
from app.bootstrap import create_live_watson_flow_dependencies
from app.graph.builder import create_graph
from app.infrastructure.http.http_contracts import (
    HttpTransportResponse,
    http_transport_failure,
    http_transport_success,
)
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.integrations.watson.flow_limits import default_watson_flow_limits
from app.integrations.watson.live_configuration import create_live_watson_flow_configuration
from testar_grafo_base import FakeSqlGenerator, SuccessContextRepository


FLOW_ID = "00e0284a-d785-448b-aed3-95672dd4d189"
IAM_BODY = b'{"access_token":"test-token","token_type":"Bearer","expires_in":3600}'


def _json(body: bytes, status: int = 200, headers=None):
    safe_headers = {"Content-Type": "application/json"}
    if headers:
        safe_headers.update(headers)
    return http_transport_success(
        HttpTransportResponse(status_code=status, headers=safe_headers, body=body)
    )


def _config():
    return create_live_watson_flow_configuration(
        api_base_url="https://example.invalid",
        flow_id=FLOW_ID,
        api_key_secret_name="IBM_CLOUD_API_KEY",
        enabled=True,
        connect_timeout_seconds=3,
        read_timeout_seconds=5,
        max_response_bytes=1000,
    )


def _state():
    return {
        "question": "Execute uma generic analysis de teste.",
        "user": {"id": "usuario-1", "email": "admin@local.com", "profile": "admin"},
        "options": {
            "use_cache": False,
            "max_repair_attempts": 1,
            "shadow_mode": False,
            "sql_execution_limits": {
                "timeout_seconds": 10,
                "max_rows": 5,
                "max_response_bytes": 4096,
                "max_cell_bytes": 128,
            },
        },
    }


def _invoke(sequence, secret_result=None):
    limits = default_watson_flow_limits()
    secret = FakeSecretValueProvider(
        secret=SensitiveSecret("test-api-key"),
        result=secret_result,
    )
    transport = FakeHttpTransport(sequence=list(sequence))
    deps = create_live_watson_flow_dependencies(
        live_configuration=_config(),
        limits=limits,
        secret_provider=secret,
        http_transport=transport,
    )
    graph = create_graph(
        SuccessContextRepository(),
        FakeSqlGenerator(),
        deps.engine_preflight,
        FakeSqlRepairer(responses=["SELECT value FROM schema_test.table_test"]),
        deps.sql_executor,
        FakeRunRepository(),
        FakeAuditSink(),
        FakeObservabilitySink(),
    )
    return graph.invoke(_state(), config={"recursion_limit": 30}), secret, transport


def main() -> None:
    success_rows = b'{"success":true,"data":[{"id":1}],"columns":["id"],"row_count":1}'
    result, secret, transport = _invoke([
        _json(IAM_BODY),
        _json(b'{"success":true,"data":[],"columns":[],"row_count":0}'),
        _json(IAM_BODY),
        _json(success_rows),
    ])
    assert result["application_response"]["status"] == "success"
    assert result["sql_execution_result"]["status"] == "success"
    assert secret.calls == 2
    assert transport.calls == 4
    assert transport.requests[1].operation_name == "watson_flow_preflight"
    assert transport.requests[3].operation_name == "watson_flow_execution"
    assert _invoke([_json(b"{}", status=401)])[0]["final_status"] == "infrastructure_error"
    assert _invoke([_json(IAM_BODY), http_transport_failure("timeout")])[0]["final_status"] == "infrastructure_error"
    assert _invoke([_json(IAM_BODY), _json(b"{}", status=429)])[0]["final_status"] == "infrastructure_error"
    assert _invoke([_json(IAM_BODY), _json(b"{")])[0]["final_status"] == "infrastructure_error"
    assert len(transport.requests) == 4
    assert all("test-token" not in repr(req) for req in transport.requests)
    serialized = repr(result).casefold()
    assert "test-token" not in serialized
    assert "raw_output" not in serialized
    assert "sql_transport" not in serialized
    print("testar_watson_live_offline_integration.py: 11/11 OK")


if __name__ == "__main__":
    main()
