from __future__ import annotations

from app.adapters.testing.fake_http_transport import FakeHttpTransport
from app.adapters.testing.fake_secret_value_provider import FakeSecretValueProvider
from app.bootstrap import (
    create_live_watson_flow_dependencies,
    create_postgres_context_graph,
    create_stdlib_live_watson_flow_dependencies,
)
from app.infrastructure.http.http_contracts import HttpTransportResponse, http_transport_success
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.integrations.watson.flow_limits import default_watson_flow_limits
from app.integrations.watson.live_configuration import create_live_watson_flow_configuration
from testar_postgres_context_graph_bootstrap import (
    FAKE_ENVIRONMENT,
    FakeAuditSink,
    FakeEnginePreflight,
    FakeObservabilitySink,
    FakeRunRepository,
    FakeSqlExecutor,
    FakeSqlGenerator,
    FakeSqlRepairer,
)


FLOW_ID = "00e0284a-d785-448b-aed3-95672dd4d189"


def _config(enabled=True):
    return create_live_watson_flow_configuration(
        api_base_url="https://example.invalid",
        flow_id=FLOW_ID,
        api_key_secret_name="IBM_CLOUD_API_KEY",
        enabled=enabled,
        connect_timeout_seconds=3,
        read_timeout_seconds=5,
        max_response_bytes=1000,
    )


def _deps(enabled=True):
    secret = FakeSecretValueProvider(secret=SensitiveSecret("test-api-key"))
    transport = FakeHttpTransport(
        result=http_transport_success(
            HttpTransportResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                body=b"{}",
            )
        )
    )
    deps = create_live_watson_flow_dependencies(
        live_configuration=_config(enabled),
        limits=default_watson_flow_limits(),
        secret_provider=secret,
        http_transport=transport,
    )
    return deps, secret, transport


def _raises(fn) -> None:
    try:
        fn()
    except Exception:
        return
    raise AssertionError("Era esperada falha.")


def main() -> None:
    secret = FakeSecretValueProvider(secret=SensitiveSecret("test-api-key"))
    transport = FakeHttpTransport(result=http_transport_success(HttpTransportResponse(status_code=200, headers={}, body=b"{}")))
    _raises(lambda: create_live_watson_flow_dependencies(live_configuration=_config(False), limits=default_watson_flow_limits(), secret_provider=secret, http_transport=transport))
    _raises(lambda: _config(enabled="true"))
    _raises(lambda: create_live_watson_flow_dependencies(live_configuration=_config(), limits=default_watson_flow_limits(), secret_provider=secret))
    _raises(lambda: create_live_watson_flow_dependencies(limits=default_watson_flow_limits(), secret_provider=secret, http_transport=transport))
    _raises(lambda: create_live_watson_flow_dependencies(live_configuration=_config(), secret_provider=secret, http_transport=transport))
    _raises(lambda: create_live_watson_flow_dependencies(live_configuration=_config(), limits=default_watson_flow_limits(), http_transport=transport))
    _raises(lambda: create_live_watson_flow_dependencies(live_configuration=_config(), limits=default_watson_flow_limits(), secret_provider=secret))
    deps, secret, transport = _deps()
    assert deps.iam_token_provider.__class__.__name__ == "LiveIamTokenProvider"
    assert deps.flow_client.__class__.__name__ == "LiveWatsonFlowClient"
    assert deps.engine_preflight.__class__.__name__ == "WatsonFlowEnginePreflightAdapter"
    assert deps.sql_executor.__class__.__name__ == "WatsonFlowSqlExecutorAdapter"
    assert secret.calls == 0
    assert transport.calls == 0
    assert create_stdlib_live_watson_flow_dependencies(live_configuration=_config(), limits=default_watson_flow_limits(), secret_provider=secret).flow_client.__class__.__name__ == "LiveWatsonFlowClient"
    graph = create_postgres_context_graph(
        FAKE_ENVIRONMENT,
        sql_generator=FakeSqlGenerator(),
        engine_preflight=FakeEnginePreflight(),
        sql_repairer=FakeSqlRepairer(),
        sql_executor=FakeSqlExecutor(),
        run_repository=FakeRunRepository(),
        audit_sink=FakeAuditSink(),
        observability_sink=FakeObservabilitySink(),
    )
    assert callable(getattr(graph, "invoke", None))
    assert "live" not in globals()
    assert "Fake" not in deps.iam_token_provider.__class__.__name__
    print("testar_watson_live_bootstrap.py: 15/15 OK")


if __name__ == "__main__":
    main()
