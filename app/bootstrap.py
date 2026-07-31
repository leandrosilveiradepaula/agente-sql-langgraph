from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.adapters.engine_preflight import (
    CapabilityUnavailableEnginePreflight,
)
from app.adapters.postgres.context_repository import (
    PostgresContextRepository,
)
from app.config.engine_preflight_runtime import (
    EnginePreflightRuntimeConfig,
)
from app.config.postgres_context import (
    PostgresContextRuntimeConfig,
    load_postgres_context_runtime_config,
)
from app.graph.builder import create_graph
from app.ports.context_repository import ContextRepository
from app.ports.engine_preflight import EnginePreflight
from app.ports.audit_sink import AuditSink
from app.ports.observability_sink import ObservabilitySink
from app.ports.run_repository import RunRepository
from app.ports.sql_executor import SqlExecutor
from app.ports.sql_generator import SqlGenerator
from app.ports.sql_repairer import SqlRepairer


RuntimeEnvironment = Mapping[str, str]
ConfigLoader = Callable[
    [RuntimeEnvironment | None],
    PostgresContextRuntimeConfig,
]
RepositoryFactory = Callable[
    [PostgresContextRuntimeConfig],
    ContextRepository,
]
GraphFactory = Callable[
    [
        ContextRepository,
        SqlGenerator,
        EnginePreflight,
        SqlRepairer,
        SqlExecutor,
        RunRepository,
        AuditSink,
        ObservabilitySink,
    ],
    Any,
]


def create_postgres_context_repository(
    config: PostgresContextRuntimeConfig,
) -> PostgresContextRepository:
    """
    Cria o repositorio PostgreSQL a partir da configuracao validada.

    Nenhuma conexao e aberta durante esta etapa. A conexao ocorre
    somente quando o grafo executa load_active_context.
    """

    return PostgresContextRepository(
        dsn=config.dsn,
        semantic_agent_version=config.semantic_agent_version,
        connect_timeout_seconds=config.connect_timeout_seconds,
    )


def create_engine_preflight_from_runtime_config(
    config: EnginePreflightRuntimeConfig,
) -> EnginePreflight:
    """
    Cria provider diagnostico quando nao ha capability live comprovada.

    Esta factory nao cria adapter real, nao abre rede e nao executa SQL. Quando
    um provider seguro for validado, uma factory especifica devera substitui-la
    no composition root chamador.
    """

    return CapabilityUnavailableEnginePreflight(config=config)


def create_postgres_context_graph(
    environ: RuntimeEnvironment | None = None,
    *,
    sql_generator: SqlGenerator | None = None,
    engine_preflight: EnginePreflight | None = None,
    sql_repairer: SqlRepairer | None = None,
    sql_executor: SqlExecutor | None = None,
    run_repository: RunRepository | None = None,
    audit_sink: AuditSink | None = None,
    observability_sink: ObservabilitySink | None = None,
    config_loader: ConfigLoader = (
        load_postgres_context_runtime_config
    ),
    repository_factory: RepositoryFactory = (
        create_postgres_context_repository
    ),
    graph_factory: GraphFactory = create_graph,
) -> Any:
    """
    Composition root do grafo com contexto PostgreSQL.

    Fluxo de montagem:
    ambiente externo
    -> configuracao validada
    -> PostgresContextRepository
    -> create_graph(
       repository, sql_generator, engine_preflight, sql_repairer,
       sql_executor, run_repository, audit_sink, observability_sink
    )
    -> grafo compilado

    Esta fase nao define providers padrao. Os adapters devem ser
    injetados explicitamente pelo composition root chamador.
    """

    config = config_loader(environ)
    repository = repository_factory(config)

    if sql_generator is None:
        raise RuntimeError(
            "sql_generator deve ser injetado no composition root."
        )

    if engine_preflight is None:
        raise RuntimeError(
            "engine_preflight deve ser injetado no composition root."
        )

    if sql_repairer is None:
        raise RuntimeError(
            "sql_repairer deve ser injetado no composition root."
        )

    if sql_executor is None:
        raise RuntimeError(
            "sql_executor deve ser injetado no composition root."
        )

    if run_repository is None:
        raise RuntimeError(
            "run_repository deve ser injetado no composition root."
        )

    if audit_sink is None:
        raise RuntimeError(
            "audit_sink deve ser injetado no composition root."
        )

    if observability_sink is None:
        raise RuntimeError(
            "observability_sink deve ser injetado no composition root."
        )

    return graph_factory(
        repository,
        sql_generator,
        engine_preflight,
        sql_repairer,
        sql_executor,
        run_repository,
        audit_sink,
        observability_sink,
    )
