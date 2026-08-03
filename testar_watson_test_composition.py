from __future__ import annotations

import os

from app.adapters.testing.fake_http_transport import FakeHttpTransport
from app.adapters.testing.fake_secret_value_provider import FakeSecretValueProvider
from app.composition.watson_test import (
    DeploymentEnvironment,
    deployment_environment_from_text,
    build_watson_test_dependencies,
)
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.integrations.watson.flow_limits import default_watson_flow_limits
from app.integrations.watson.live_configuration import (
    create_live_watson_flow_configuration,
)


FLOW_ID = "00e0284a-d785-448b-aed3-95672dd4d189"


class BombSecretProvider(FakeSecretValueProvider):
    def get_secret(self, secret_name):
        raise AssertionError("composition root nao deve consultar secret")


class BombHttpTransport(FakeHttpTransport):
    def send(self, request):
        raise AssertionError("composition root nao deve chamar transporte")


def _config(*, enabled: bool = True):
    return create_live_watson_flow_configuration(
        api_base_url="https://example.invalid",
        flow_id=FLOW_ID,
        api_key_secret_name="IBM_CLOUD_API_KEY",
        enabled=enabled,
        limits=default_watson_flow_limits(),
    )


def _build(**overrides):
    kwargs = {
        "environment": DeploymentEnvironment.TEST,
        "live_configuration": _config(),
        "limits": default_watson_flow_limits(),
        "secret_provider": BombSecretProvider(secret=SensitiveSecret("test-api-key")),
        "http_transport": BombHttpTransport(),
    }
    kwargs.update(overrides)
    return build_watson_test_dependencies(**kwargs)


def main() -> None:
    assert deployment_environment_from_text("test") is DeploymentEnvironment.TEST
    for value in ("prod", "production", "prd", "live", "sandbox", "", object()):
        try:
            deployment_environment_from_text(value)
            raise AssertionError(value)
        except ValueError:
            pass

    assert _build(live_configuration=_config(enabled=False)).status == "disabled"
    assert _build(live_configuration=None).status == "invalid_configuration"
    assert _build(limits=None).status == "missing_dependency"
    assert _build(secret_provider=None).status == "missing_dependency"
    assert _build(http_transport=None).status == "missing_dependency"
    assert _build(environment="test").status == "invalid_environment"  # type: ignore[arg-type]

    before_env = dict(os.environ)
    result = _build()
    assert result.status == "success"
    assert result.dependencies is not None
    deps = result.dependencies
    assert type(deps.iam_token_provider).__name__ == "LiveIamTokenProvider"
    assert type(deps.flow_client).__name__ == "LiveWatsonFlowClient"
    assert type(deps.engine_preflight).__name__ == "WatsonFlowEnginePreflightAdapter"
    assert type(deps.sql_executor).__name__ == "WatsonFlowSqlExecutorAdapter"
    assert getattr(deps.secret_provider, "calls", 0) == 0
    assert getattr(deps.http_transport, "calls", 0) == 0
    assert dict(os.environ) == before_env
    text = repr(deps).casefold()
    assert "test-api-key" not in text
    assert "bearer" not in text
    assert "authorization" not in text
    assert "raw_output" not in text
    assert "sql_transport" not in text
    assert "graphstate" not in text
    assert repr(_build()) == repr(_build())

    from app.bootstrap import create_postgres_context_application_service

    assert create_postgres_context_application_service is not None
    print("testar_watson_test_composition.py: 20/20 OK")


if __name__ == "__main__":
    main()
