from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.adapters.postgres.context_repository import (
    PostgresContextRepository,
)
from app.config.postgres_context import (
    PostgresContextRuntimeConfig,
    load_postgres_context_runtime_config,
)
from app.graph.builder import create_graph
from app.ports.context_repository import ContextRepository
from app.ports.engine_preflight import EnginePreflight
from app.ports.sql_generator import SqlGenerator


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
    [ContextRepository, SqlGenerator, EnginePreflight],
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


def create_postgres_context_graph(
    environ: RuntimeEnvironment | None = None,
    *,
    sql_generator: SqlGenerator | None = None,
    engine_preflight: EnginePreflight | None = None,
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
    -> create_graph(repository, sql_generator, engine_preflight)
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

    return graph_factory(repository, sql_generator, engine_preflight)
