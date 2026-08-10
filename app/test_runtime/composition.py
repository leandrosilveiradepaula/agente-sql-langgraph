from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.application.internal_sql_agent_v1 import (
    ExecuteApprovedSqlShadowUseCase,
    GenerateSqlUseCase,
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
from app.infrastructure.persistence.postgres_shadow_evidence_repository import (
    PostgresShadowEvidenceRepository,
)
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
    handler = create_internal_sql_agent_v1_http_handler(
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
    observed_handler = ObservedInternalHttpHandler(
        inner=handler,
        repository=observed_repository,
        logger=logger,
    )
    asgi_limits = default_asgi_adapter_limits()
    validate_asgi_http_limit_compatibility(
        asgi_limits=asgi_limits,
        http_request_limits=request_limits,
        http_response_limits=response_limits,
    )
    internal_app = AsgiSqlAgentApplication(
        http_handler=observed_handler,  # type: ignore[arg-type]
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
