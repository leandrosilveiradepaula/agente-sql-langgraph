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
    ShadowTestContextRepository,
    ShadowTestEnginePreflight,
    ShadowTestIds,
    ShadowTestSqlGenerator,
    ShadowTestSqlRepairer,
)


@dataclass(frozen=True, slots=True)
class ShadowTestRuntime:
    app: ShadowTestAsgiApplication
    config: ShadowTestRuntimeConfig
    raw_shadow_repository: Any
    shadow_repository: ObservedShadowEvidenceRepository
    sql_generator: ShadowTestSqlGenerator
    engine_preflight: ShadowTestEnginePreflight
    sql_repairer: ShadowTestSqlRepairer


def create_shadow_test_runtime(
    environ: Mapping[str, str] | None = None,
    *,
    shadow_repository_override: Any | None = None,
    connect_override: Any | None = None,
    logger: Any | None = None,
) -> ShadowTestRuntime:
    config = load_shadow_test_runtime_config(environ)
    raw_repository = shadow_repository_override or _postgres_shadow_repository(
        config=config,
        connect_override=connect_override,
    )
    observed_repository = ObservedShadowEvidenceRepository(raw_repository)
    sql_generator = ShadowTestSqlGenerator()
    engine_preflight = ShadowTestEnginePreflight()
    sql_repairer = ShadowTestSqlRepairer()
    ids = ShadowTestIds()
    request_limits = default_http_request_limits()
    response_limits = default_http_response_limits()
    sql_handler = create_internal_sql_agent_v1_http_handler(
        generate_use_case=GenerateSqlUseCase(
            context_repository=ShadowTestContextRepository(),
            sql_generator=sql_generator,
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
        sql_generator=sql_generator,
        engine_preflight=engine_preflight,
        sql_repairer=sql_repairer,
    )


def create_shadow_test_asgi_app(
    environ: Mapping[str, str] | None = None,
    *,
    shadow_repository_override: Any | None = None,
    connect_override: Any | None = None,
    logger: Any | None = None,
) -> ShadowTestAsgiApplication:
    return create_shadow_test_runtime(
        environ,
        shadow_repository_override=shadow_repository_override,
        connect_override=connect_override,
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
