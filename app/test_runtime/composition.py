from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.application.internal_sql_agent_v1 import (
    ExecuteApprovedSqlShadowUseCase,
    GenerateSqlUseCase,
)
from app.application.internal_shadow_read_v1 import (
    GetShadowRunSafeViewUseCase,
    GetShadowRunVisualizationUseCase,
    ListAgentShadowRunsUseCase,
)
from app.adapters.postgres.context_repository import (
    PostgresContextRepository,
)
from app.asgi.asgi_limits import (
    default_asgi_adapter_limits,
    validate_asgi_http_limit_compatibility,
)
from app.asgi.sql_agent_asgi_app import AsgiSqlAgentApplication
from app.http.http_request import default_http_request_limits
from app.http.http_response import default_http_response_limits
from app.http.internal_sql_agent_v1_handler import (
    create_internal_sql_agent_v1_http_handler,
)
from app.http.internal_shadow_read_v1_handler import (
    create_internal_shadow_read_v1_http_handler,
)
from app.http.internal_service_auth_handler import (
    protect_internal_service_http_handler,
)
from app.http.internal_v1_router import create_internal_v1_http_router
from app.infrastructure.persistence.postgres_shadow_evidence_repository import (
    PostgresShadowEvidenceRepository,
)
from app.infrastructure.http.stdlib_http_transport import StdlibHttpTransport
from app.infrastructure.secrets.environment_secret_provider import (
    EnvironmentSecretProvider,
)
from app.composition.sql_generator_registry import (
    SqlGeneratorRegistration,
    SqlGeneratorRegistry,
)
from app.integrations.google_gemini.sql_generator_adapter import (
    GoogleGeminiSqlGeneratorAdapter,
)
from app.integrations.openai_compatible.client import OpenAiCompatibleClient
from app.integrations.openai_compatible.configuration import (
    load_openai_compatible_configuration,
)
from app.integrations.openai_compatible.sql_generator_adapter import (
    OpenAiCompatibleSqlGeneratorAdapter,
)
from app.integrations.google_gemini.sql_repairer_adapter import (
    GoogleGeminiSqlRepairerAdapter,
)
from app.integrations.google_gemini.client import GoogleGeminiClient
from app.integrations.google_gemini.configuration import (
    load_google_gemini_configuration,
    load_google_gemini_repairer_configuration,
)
from app.ports.context_repository import ContextRepository
from app.ports.sql_generator import SqlGenerator
from app.ports.sql_repairer import SqlRepairer
from app.security.internal_service_auth import InternalServiceAuthConfig
from app.test_runtime.asgi_app import ShadowTestAsgiApplication
from app.test_runtime.config import (
    ShadowTestRuntimeConfig,
    load_shadow_test_runtime_config,
)
from app.test_runtime.observability import (
    ObservedInternalHttpHandler,
    ObservedShadowEvidenceRepository,
)
from app.test_runtime.offline_adapters import (
    ShadowTestEnginePreflight,
    ShadowTestIds,
)


@dataclass(frozen=True, slots=True)
class ShadowTestRuntime:
    app: ShadowTestAsgiApplication
    config: ShadowTestRuntimeConfig
    raw_shadow_repository: Any
    shadow_repository: ObservedShadowEvidenceRepository
    context_repository: ContextRepository
    sql_generator: SqlGenerator
    engine_preflight: ShadowTestEnginePreflight
    sql_repairer: SqlRepairer


def create_shadow_test_runtime(
    environ: Mapping[str, str] | None = None,
    *,
    shadow_repository_override: Any | None = None,
    connect_override: Any | None = None,
    context_connect_override: Any | None = None,
    context_repository_override: ContextRepository | None = None,
    sql_generator_override: SqlGenerator | None = None,
    sql_repairer_override: SqlRepairer | None = None,
    http_transport_override: Any | None = None,
    secret_provider_override: Any | None = None,
    logger: Any | None = None,
) -> ShadowTestRuntime:
    config = load_shadow_test_runtime_config(environ)
    raw_repository = shadow_repository_override or _postgres_shadow_repository(
        config=config,
        connect_override=connect_override,
    )
    observed_repository = ObservedShadowEvidenceRepository(raw_repository)
    context_repository = (
        context_repository_override
        or _postgres_context_repository(
            config=config,
            connect_override=context_connect_override,
        )
    )
    http_transport = http_transport_override or StdlibHttpTransport()
    secret_provider = secret_provider_override or EnvironmentSecretProvider(
        environ=environ,
    )
    sql_generator = sql_generator_override or _gemini_sql_generator(
        environ=environ,
        http_transport=http_transport,
        secret_provider=secret_provider,
    )
    sql_generator_registry = _sql_generator_registry(
        environ=environ,
        default_generator=sql_generator,
        http_transport=http_transport,
        secret_provider=secret_provider,
    )
    engine_preflight = ShadowTestEnginePreflight()
    sql_repairer = sql_repairer_override or _gemini_sql_repairer(
        environ=environ,
        http_transport=http_transport,
        secret_provider=secret_provider,
    )
    ids = ShadowTestIds()
    request_limits = default_http_request_limits()
    response_limits = default_http_response_limits()
    sql_handler = create_internal_sql_agent_v1_http_handler(
        generate_use_case=GenerateSqlUseCase(
            context_repository=context_repository,
            sql_generator=sql_generator,
            sql_generator_resolver=sql_generator_registry,
            engine_preflight=engine_preflight,
            sql_repairer=sql_repairer,
            id_generator=ids,
            shadow_repository=observed_repository,
            langgraph_version=config.langgraph_version,
            langgraph_commit=config.langgraph_commit,
        ),
        execute_approved_shadow_use_case=ExecuteApprovedSqlShadowUseCase(
            engine_preflight=engine_preflight,
            sql_repairer=sql_repairer,
            id_generator=ids,
            shadow_repository=observed_repository,
            langgraph_version=config.langgraph_version,
            langgraph_commit=config.langgraph_commit,
        ),
        request_limits=request_limits,
        response_limits=response_limits,
    )
    shadow_read_handler = create_internal_shadow_read_v1_http_handler(
        get_shadow_run_use_case=GetShadowRunSafeViewUseCase(
            repository=observed_repository,
        ),
        list_agent_shadow_runs_use_case=ListAgentShadowRunsUseCase(
            repository=observed_repository,
        ),
        get_shadow_run_visualization_use_case=GetShadowRunVisualizationUseCase(
            repository=observed_repository,
        ),
        response_limits=response_limits,
    )
    handler = create_internal_v1_http_router(
        sql_handler=sql_handler,
        shadow_read_handler=shadow_read_handler,
    )
    observed_handler = ObservedInternalHttpHandler(
        inner=handler,
        repository=observed_repository,
        logger=logger,
    )
    protected_handler = protect_internal_service_http_handler(
        inner=observed_handler,
        auth_config=InternalServiceAuthConfig(expected_token=config.s2s_token),
    )
    asgi_limits = default_asgi_adapter_limits()
    validate_asgi_http_limit_compatibility(
        asgi_limits=asgi_limits,
        http_request_limits=request_limits,
        http_response_limits=response_limits,
    )
    internal_app = AsgiSqlAgentApplication(
        http_handler=protected_handler,  # type: ignore[arg-type]
        asgi_limits=asgi_limits,
    )
    return ShadowTestRuntime(
        app=ShadowTestAsgiApplication(internal_app=internal_app, config=config),
        config=config,
        raw_shadow_repository=raw_repository,
        shadow_repository=observed_repository,
        context_repository=context_repository,
        sql_generator=sql_generator,
        engine_preflight=engine_preflight,
        sql_repairer=sql_repairer,
    )


def create_shadow_test_asgi_app(
    environ: Mapping[str, str] | None = None,
    *,
    shadow_repository_override: Any | None = None,
    connect_override: Any | None = None,
    context_connect_override: Any | None = None,
    context_repository_override: ContextRepository | None = None,
    sql_generator_override: SqlGenerator | None = None,
    sql_repairer_override: SqlRepairer | None = None,
    http_transport_override: Any | None = None,
    secret_provider_override: Any | None = None,
    logger: Any | None = None,
) -> ShadowTestAsgiApplication:
    return create_shadow_test_runtime(
        environ,
        shadow_repository_override=shadow_repository_override,
        connect_override=connect_override,
        context_connect_override=context_connect_override,
        context_repository_override=context_repository_override,
        sql_generator_override=sql_generator_override,
        sql_repairer_override=sql_repairer_override,
        http_transport_override=http_transport_override,
        secret_provider_override=secret_provider_override,
        logger=logger,
    ).app


def _postgres_shadow_repository(
    *,
    config: ShadowTestRuntimeConfig,
    connect_override: Any | None,
) -> PostgresShadowEvidenceRepository:
    if connect_override is None:
        return PostgresShadowEvidenceRepository(dsn=config.shadow_database_dsn)
    return PostgresShadowEvidenceRepository(
        dsn=config.shadow_database_dsn,
        connect=connect_override,
    )


def _postgres_context_repository(
    *,
    config: ShadowTestRuntimeConfig,
    connect_override: Any | None,
) -> PostgresContextRepository:
    kwargs: dict[str, Any] = {}
    if connect_override is not None:
        kwargs["connect"] = connect_override
    return PostgresContextRepository(
        dsn=config.context_postgres_dsn,
        semantic_agent_version=config.semantic_agent_version,
        context_schema=config.context_schema,
        connect_timeout_seconds=config.context_connect_timeout_seconds,
        **kwargs,
    )


def _sql_generator_registry(
    *,
    environ: Mapping[str, str] | None,
    default_generator: SqlGenerator,
    http_transport: Any,
    secret_provider: Any,
) -> SqlGeneratorRegistry:
    gemini_configuration = load_google_gemini_configuration(environ)
    source = {} if environ is None else environ
    gemini_config_version = str(
        source.get(
            "GEMINI_SQL_GENERATOR_CONFIG_VERSION",
            "gemini-shadow-v1",
        )
    ).strip()

    registrations = [
        SqlGeneratorRegistration(
            provider_key="google_gemini",
            model_key=gemini_configuration.model_id,
            config_version=gemini_config_version,
            generator=default_generator,
        )
    ]

    compatible = load_openai_compatible_configuration(environ)
    if compatible is not None:
        client = OpenAiCompatibleClient(
            configuration=compatible,
            secret_provider=secret_provider,
            http_transport=http_transport,
        )
        registrations.append(
            SqlGeneratorRegistration(
                provider_key=compatible.provider_key,
                model_key=compatible.model_id,
                config_version=compatible.config_version,
                generator=OpenAiCompatibleSqlGeneratorAdapter(
                    client=client,
                    configuration=compatible,
                ),
            )
        )

    return SqlGeneratorRegistry(registrations)


def _gemini_sql_generator(
    *,
    environ: Mapping[str, str] | None,
    http_transport: Any,
    secret_provider: Any,
) -> GoogleGeminiSqlGeneratorAdapter:
    client = GoogleGeminiClient(
        configuration=load_google_gemini_configuration(environ),
        secret_provider=secret_provider,
        http_transport=http_transport,
    )
    return GoogleGeminiSqlGeneratorAdapter(client=client)


def _gemini_sql_repairer(
    *,
    environ: Mapping[str, str] | None,
    http_transport: Any,
    secret_provider: Any,
) -> GoogleGeminiSqlRepairerAdapter:
    client = GoogleGeminiClient(
        configuration=load_google_gemini_repairer_configuration(environ),
        secret_provider=secret_provider,
        http_transport=http_transport,
    )
    return GoogleGeminiSqlRepairerAdapter(client=client)
