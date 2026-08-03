from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
from app.integrations.watson.live_configuration import create_live_watson_flow_configuration
from app.ports.secret_value_provider import secret_lookup_failure
from testar_grafo_base import FakeSqlGenerator, SuccessContextRepository


FLOW_ID = "00e0284a-d785-448b-aed3-95672dd4d189"
IAM_OK = b'{"access_token":"fake-token-for-rehearsal","token_type":"Bearer","expires_in":3600}'
PREFLIGHT_OK = b'{"success":true,"data":[],"columns":[],"row_count":0}'
EXECUTION_OK = b'{"success":true,"data":[{"id":1}],"columns":["id"],"row_count":1}'
SQL = "SELECT 1 AS adapter_contract_probe"
FORBIDDEN_OUTPUT = (
    "fake-token-for-rehearsal",
    "fake-api-key-for-rehearsal",
    "adapter_contract_probe",
    "sql_transport",
    "raw_output",
)


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    kind: str
    result: object
    evidence: str = ""


def _json(
    body: bytes,
    *,
    status: int = 200,
    content_type: str = "application/json",
    headers: dict[str, str] | None = None,
):
    response_headers = {"Content-Type": content_type}
    response_headers.update(headers or {})
    return http_transport_success(
        HttpTransportResponse(
            status_code=status,
            headers=response_headers,
            body=body,
            duration_ms=1,
        )
    )


def _composition(*, secret=None, sequence=None):
    limits = default_watson_flow_limits()
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
        secret_provider=secret
        or FakeSecretValueProvider(secret=SensitiveSecret("fake-api-key-for-rehearsal")),
        http_transport=FakeHttpTransport(sequence=list(sequence or [])),
    )
    assert composition.status == "success"
    assert composition.dependencies is not None
    return composition.dependencies


def _preflight(sequence, *, secret=None):
    deps = _composition(secret=secret, sequence=sequence)
    return deps.engine_preflight.preflight(
        {
            "sql": SQL,
            "timeout_ms": 1000,
            "request_fingerprint": "preflight-rehearsal",
            "query_plan_fingerprint": "plan-rehearsal",
        }
    )


def _execution(sequence, *, secret=None):
    deps = _composition(secret=secret, sequence=sequence)
    return deps.sql_executor.execute(
        {
            "contract_version": "v1.0.0-controlled-sql-execution",
            "current_sql": SQL,
            "sql_fingerprint": "sql-rehearsal",
            "request_id": "request-rehearsal",
            "run_id": "run-rehearsal",
            "context_version": "context-rehearsal",
            "intent_name": "intent-rehearsal",
            "query_plan_fingerprint": "plan-rehearsal",
            "preflight_fingerprint": "preflight-rehearsal",
            "limits": {
                "timeout_seconds": 1,
                "max_rows": 5,
                "max_response_bytes": 4096,
                "max_cell_bytes": 128,
            },
            "attempt": 1,
            "execution_id": "execution-rehearsal",
            "dialect": None,
            "engine_hint": None,
            "request_fingerprint": "execution-rehearsal",
        }
    )


def _graph(sequence):
    deps = _composition(sequence=sequence)
    repairer = FakeSqlRepairer(responses=["SELECT value FROM schema_test.table_test"])
    graph = create_graph(
        SuccessContextRepository(),
        FakeSqlGenerator(),
        deps.engine_preflight,
        repairer,
        deps.sql_executor,
        FakeRunRepository(),
        FakeAuditSink(),
        FakeObservabilitySink(),
    )
    result = graph.invoke(
        {
            "question": "Execute uma generic analysis de teste.",
            "user": {"id": "usuario-1", "email": "admin@local.com", "profile": "admin"},
            "options": {
                "use_cache": False,
                "max_repair_attempts": 1,
                "shadow_mode": False,
                "sql_execution_limits": {
                    "timeout_seconds": 1,
                    "max_rows": 5,
                    "max_response_bytes": 4096,
                    "max_cell_bytes": 128,
                },
            },
        },
        config={"recursion_limit": 30},
    )
    return result, repairer


def scenarios() -> list[Scenario]:
    return [
        Scenario("IAM missing secret", "preflight_error", _preflight([], secret=FakeSecretValueProvider())),
        Scenario("IAM invalid secret", "preflight_error", _preflight([], secret=FakeSecretValueProvider(result=secret_lookup_failure("invalid")))),
        Scenario("IAM 401", "preflight_error", _preflight([_json(b"{}", status=401)])),
        Scenario("IAM 429", "preflight_error", _preflight([_json(b"{}", status=429)])),
        Scenario("IAM 500", "preflight_error", _preflight([_json(b"{}", status=500)])),
        Scenario("IAM timeout", "preflight_error", _preflight([http_transport_failure("timeout")])),
        Scenario("IAM DNS failure", "preflight_error", _preflight([http_transport_failure("dns_failure")])),
        Scenario("IAM TLS failure", "preflight_error", _preflight([http_transport_failure("tls_failure")])),
        Scenario("Flow 401", "preflight_error", _preflight([_json(IAM_OK), _json(b"{}", status=401)])),
        Scenario("Flow 403", "preflight_error", _preflight([_json(IAM_OK), _json(b"{}", status=403)])),
        Scenario(
            "Flow 429 Retry-After valid",
            "preflight_error",
            _preflight([_json(IAM_OK), _json(b"{}", status=429, headers={"Retry-After": "1"})]),
            "retry_after_valid",
        ),
        Scenario(
            "Flow 429 Retry-After invalid",
            "preflight_error",
            _preflight([_json(IAM_OK), _json(b"{}", status=429, headers={"Retry-After": "invalid"})]),
            "retry_after_invalid",
        ),
        Scenario("Flow 500", "preflight_error", _preflight([_json(IAM_OK), _json(b"{}", status=500)])),
        Scenario("Flow timeout", "preflight_error", _preflight([_json(IAM_OK), http_transport_failure("timeout")])),
        Scenario("Flow DNS failure", "preflight_error", _preflight([_json(IAM_OK), http_transport_failure("dns_failure")])),
        Scenario("Flow TLS failure", "preflight_error", _preflight([_json(IAM_OK), http_transport_failure("tls_failure")])),
        Scenario("content-type invalid", "preflight_error", _preflight([_json(IAM_OK), _json(PREFLIGHT_OK, content_type="text/plain")])),
        Scenario("charset invalid", "preflight_error", _preflight([_json(IAM_OK), _json(PREFLIGHT_OK, content_type="application/json; charset=utf-16")])),
        Scenario("JSON invalid", "preflight_error", _preflight([_json(IAM_OK), _json(b"{")])),
        Scenario("duplicate keys", "preflight_error", _preflight([_json(IAM_OK), _json(b'{"success":true,"success":false}')])),
        Scenario("root list", "preflight_error", _preflight([_json(IAM_OK), _json(b"[]")])),
        Scenario("body above limit", "preflight_error", _preflight([_json(IAM_OK), http_transport_failure("response_too_large")])),
        Scenario("envelope unknown", "preflight_error", _preflight([_json(IAM_OK), _json(b'{"unknown":true}')])),
        Scenario("success missing", "preflight_error", _preflight([_json(IAM_OK), _json(b'{"data":[]}')])),
        Scenario("success non-bool", "preflight_error", _preflight([_json(IAM_OK), _json(b'{"success":"yes"}')])),
        Scenario("rows invalid", "execution_error", _execution([_json(IAM_OK), _json(b'{"success":true,"data":"bad","columns":["id"],"row_count":1}')])),
        Scenario("columns invalid", "execution_error", _execution([_json(IAM_OK), _json(b'{"success":true,"data":[{"id":1}],"columns":"id","row_count":1}')])),
        Scenario("row_count conflict", "execution_error", _execution([_json(IAM_OK), _json(b'{"success":true,"data":[{"id":1}],"columns":["id"],"row_count":2}')])),
        Scenario("query_id invalid", "execution_error", _execution([_json(IAM_OK), _json(b'{"success":true,"data":[{"id":1}],"columns":["id"],"row_count":1,"query_id":{}}')])),
        Scenario("execution failure no repair", "graph_no_repair", _graph([_json(IAM_OK), _json(PREFLIGHT_OK), _json(IAM_OK), _json(b"{}", status=500)])),
        Scenario("preflight failure blocks execution", "graph_no_repair", _graph([_json(IAM_OK), _json(b'{"success":false,"failure_category":"provider_failed"}')])),
        Scenario("rate limit no retry", "graph_no_repair", _graph([_json(IAM_OK), _json(b"{}", status=429)])),
        Scenario("timeout no retry", "graph_no_repair", _graph([_json(IAM_OK), http_transport_failure("timeout")])),
        Scenario("no raw output crosses", "no_leak", _execution([_json(IAM_OK), _json(EXECUTION_OK)])),
        Scenario("no token crosses", "no_leak", _preflight([_json(IAM_OK), _json(PREFLIGHT_OK)])),
        Scenario("no compact transport crosses", "no_leak", _execution([_json(IAM_OK), _json(EXECUTION_OK)])),
    ]


def _passed(scenario: Scenario) -> bool:
    result = scenario.result
    if scenario.name == "Flow 429 Retry-After valid" and scenario.evidence != "retry_after_valid":
        return False
    if scenario.name == "Flow 429 Retry-After invalid" and scenario.evidence != "retry_after_invalid":
        return False
    if scenario.kind == "preflight_error":
        return isinstance(result, dict) and result.get("status") != "approved"
    if scenario.kind == "execution_error":
        return isinstance(result, dict) and result.get("status") != "success"
    if scenario.kind == "graph_no_repair":
        graph_result, repairer = result  # type: ignore[misc]
        return repairer.calls == 0 and graph_result.get("application_response", {}).get("status") != "success"
    if scenario.kind == "no_leak":
        return not any(marker in repr(result) for marker in FORBIDDEN_OUTPUT)
    return False


def main() -> int:
    items = scenarios()
    failures = [item.name for item in items if not _passed(item)]
    summary = "\n".join(f"{item.name}: {'OK' if item.name not in failures else 'FAIL'}" for item in items)
    if any(marker in summary for marker in FORBIDDEN_OUTPUT):
        print("FAILURE_REHEARSAL_FAILED: unsafe_output")
        return 1
    print(summary)
    print(f"SCENARIOS={len(items)}")
    if failures:
        print("FAILURE_REHEARSAL_FAILED")
        for name in failures:
            print(f"- {name}")
        return 1
    print("FAILURE_REHEARSAL_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
