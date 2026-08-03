from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from app.application.sql_agent_service import IdGenerator, SqlAgentApplicationService
from app.bootstrap import (
    CompiledGraphRuntime,
    create_application_service,
    create_live_watson_flow_dependencies,
    create_postgres_context_graph,
)
from app.graph.builder import create_graph
from app.integrations.watson.flow_limits import WatsonFlowLimits
from app.integrations.watson.flow_preflight_adapter import (
    WatsonFlowEnginePreflightAdapter,
)
from app.integrations.watson.flow_sql_executor import WatsonFlowSqlExecutorAdapter
from app.integrations.watson.live_configuration import LiveWatsonFlowConfiguration
from app.integrations.watson.live_iam_token_provider import LiveIamTokenProvider
from app.integrations.watson.live_watson_flow_client import LiveWatsonFlowClient
from app.ports.audit_sink import AuditSink
from app.ports.context_repository import ContextRepository
from app.ports.graph_runtime import GraphRuntime
from app.ports.http_transport import HttpTransport
from app.ports.iam_token_provider import IamTokenProvider
from app.ports.observability_sink import ObservabilitySink
from app.ports.run_repository import RunRepository
from app.ports.secret_value_provider import SecretValueProvider
from app.ports.sql_generator import SqlGenerator
from app.ports.sql_repairer import SqlRepairer
from app.ports.watson_flow_client import WatsonFlowClient


class DeploymentEnvironment(Enum):
    TEST = "test"


CompositionStatus = Literal[
    "success",
    "disabled",
    "invalid_configuration",
    "invalid_environment",
    "missing_dependency",
    "unexpected_error",
]


@dataclass(frozen=True, slots=True)
class WatsonTestDependencies:
    live_configuration: LiveWatsonFlowConfiguration
    limits: WatsonFlowLimits
    secret_provider: SecretValueProvider
    http_transport: HttpTransport
    iam_token_provider: IamTokenProvider
    flow_client: WatsonFlowClient
    engine_preflight: WatsonFlowEnginePreflightAdapter
    sql_executor: WatsonFlowSqlExecutorAdapter

    def __repr__(self) -> str:
        return (
            "WatsonTestDependencies("
            "environment='test', "
            f"configuration={type(self.live_configuration).__name__}, "
            f"limits={type(self.limits).__name__}, "
            f"secret_provider={type(self.secret_provider).__name__}, "
            f"http_transport={type(self.http_transport).__name__}, "
            f"iam_token_provider={type(self.iam_token_provider).__name__}, "
            f"flow_client={type(self.flow_client).__name__}, "
            f"engine_preflight={type(self.engine_preflight).__name__}, "
            f"sql_executor={type(self.sql_executor).__name__})"
        )


@dataclass(frozen=True, slots=True)
class WatsonTestCompositionResult:
    status: CompositionStatus
    dependencies: WatsonTestDependencies | None = None
    error_code: str | None = None
    message: str | None = None


def deployment_environment_from_text(value: object) -> DeploymentEnvironment:
    if value == DeploymentEnvironment.TEST:
        return DeploymentEnvironment.TEST
    if not isinstance(value, str):
        raise ValueError("deployment_environment invalido.")
    text = value.strip().casefold()
    if text == "test":
        return DeploymentEnvironment.TEST
    if text in {"prod", "production", "prd", "live"}:
        raise ValueError("deployment_environment proibido.")
    raise ValueError("deployment_environment desconhecido.")


def build_watson_test_dependencies(
    *,
    environment: DeploymentEnvironment,
    live_configuration: LiveWatsonFlowConfiguration | None,
    limits: WatsonFlowLimits | None,
    secret_provider: SecretValueProvider | None,
    http_transport: HttpTransport | None,
) -> WatsonTestCompositionResult:
    try:
        if environment is not DeploymentEnvironment.TEST:
            return _result("invalid_environment", "WATSON_TEST_ENVIRONMENT_INVALID")
        if live_configuration is None:
            return _result("invalid_configuration", "WATSON_TEST_CONFIGURATION_MISSING")
        if live_configuration.enabled is not True:
            return _result("disabled", "WATSON_TEST_CONFIGURATION_DISABLED")
        if limits is None:
            return _result("missing_dependency", "WATSON_TEST_LIMITS_MISSING")
        if secret_provider is None:
            return _result("missing_dependency", "WATSON_TEST_SECRET_PROVIDER_MISSING")
        if http_transport is None:
            return _result("missing_dependency", "WATSON_TEST_HTTP_TRANSPORT_MISSING")
        deps = create_live_watson_flow_dependencies(
            live_configuration=live_configuration,
            limits=limits,
            secret_provider=secret_provider,
            http_transport=http_transport,
        )
        if not isinstance(deps.iam_token_provider, LiveIamTokenProvider):
            return _result("unexpected_error", "WATSON_TEST_IAM_PROVIDER_INVALID")
        if not isinstance(deps.flow_client, LiveWatsonFlowClient):
            return _result("unexpected_error", "WATSON_TEST_FLOW_CLIENT_INVALID")
        return WatsonTestCompositionResult(
            status="success",
            dependencies=WatsonTestDependencies(
                live_configuration=live_configuration,
                limits=limits,
                secret_provider=secret_provider,
                http_transport=http_transport,
                iam_token_provider=deps.iam_token_provider,
                flow_client=deps.flow_client,
                engine_preflight=deps.engine_preflight,
                sql_executor=deps.sql_executor,
            ),
        )
    except Exception:
        return _result("unexpected_error", "WATSON_TEST_COMPOSITION_FAILED")


def build_watson_test_graph_runtime(
    *,
    base_dependencies: dict[str, Any],
    watson_dependencies: WatsonTestDependencies,
) -> GraphRuntime:
    graph = create_postgres_context_graph(
        None,
        sql_generator=_required(base_dependencies, "sql_generator"),
        engine_preflight=watson_dependencies.engine_preflight,
        sql_repairer=_required(base_dependencies, "sql_repairer"),
        sql_executor=watson_dependencies.sql_executor,
        run_repository=_required(base_dependencies, "run_repository"),
        audit_sink=_required(base_dependencies, "audit_sink"),
        observability_sink=_required(base_dependencies, "observability_sink"),
        config_loader=lambda _env: _required(base_dependencies, "runtime_config"),
        repository_factory=lambda _config: _required(base_dependencies, "context_repository"),
        graph_factory=base_dependencies.get("graph_factory", create_graph),
    )
    return CompiledGraphRuntime(graph)


def build_watson_test_application_service(
    *,
    base_dependencies: dict[str, Any],
    watson_dependencies: WatsonTestDependencies,
    id_generator: IdGenerator,
    limits: dict[str, Any] | None = None,
) -> SqlAgentApplicationService:
    runtime = build_watson_test_graph_runtime(
        base_dependencies=base_dependencies,
        watson_dependencies=watson_dependencies,
    )
    return create_application_service(
        runtime=runtime,
        id_generator=id_generator,
        limits=limits,
    )


def _required(values: dict[str, Any], name: str) -> Any:
    value = values.get(name)
    if value is None:
        raise RuntimeError(f"{name} deve ser injetado.")
    return value


def _result(status: CompositionStatus, code: str) -> WatsonTestCompositionResult:
    return WatsonTestCompositionResult(
        status=status,
        error_code=code,
        message="Composition root Watson TEST falhou de forma sanitizada.",
    )
