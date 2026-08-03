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
    http_transport_success,
)
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.integrations.watson.flow_limits import default_watson_flow_limits
from app.integrations.watson.live_configuration import (
    create_live_watson_flow_configuration,
)
from testar_grafo_base import FakeSqlGenerator, SuccessContextRepository


FLOW_ID = "00e0284a-d785-448b-aed3-95672dd4d189"


def _json(body: bytes) -> object:
    return http_transport_success(
        HttpTransportResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=body,
            duration_ms=1,
        )
    )


def _state() -> dict[str, object]:
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


def main() -> int:
    limits = default_watson_flow_limits()
    secret_provider = FakeSecretValueProvider(secret=SensitiveSecret("test-api-key"))
    transport = FakeHttpTransport(
        sequence=[
            _json(b'{"access_token":"test-token","token_type":"Bearer","expires_in":3600}'),
            _json(b'{"success":true,"data":[],"columns":[],"row_count":0}'),
            _json(b'{"access_token":"test-token","token_type":"Bearer","expires_in":3600}'),
            _json(b'{"success":true,"data":[{"id":1}],"columns":["id"],"row_count":1}'),
        ]
    )
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
        secret_provider=secret_provider,
        http_transport=transport,
    )
    if composition.status != "success" or composition.dependencies is None:
        print("offline_status=failure")
        return 1
    graph = create_graph(
        SuccessContextRepository(),
        FakeSqlGenerator(),
        composition.dependencies.engine_preflight,
        FakeSqlRepairer(responses=["SELECT value FROM schema_test.table_test"]),
        composition.dependencies.sql_executor,
        FakeRunRepository(),
        FakeAuditSink(),
        FakeObservabilitySink(),
    )
    result = graph.invoke(_state(), config={"recursion_limit": 30})
    ok = (
        result.get("application_response", {}).get("status") == "success"
        and secret_provider.calls == 2
        and transport.calls == 4
        and [request.operation_name for request in transport.requests]
        == [
            "watson_iam_token",
            "watson_flow_preflight",
            "watson_iam_token",
            "watson_flow_execution",
        ]
    )
    print("offline_status=success" if ok else "offline_status=failure")
    print(f"secret_calls={secret_provider.calls}")
    print(f"http_calls={transport.calls}")
    print("network=false")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
