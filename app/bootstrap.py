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
    [ContextRepository],
    Any,
]


def create_postgres_context_repository(
    config: PostgresContextRuntimeConfig,
) -> PostgresContextRepository:
    """
    Cria o repositório PostgreSQL a partir da configuração validada.

    Nenhuma conexão é aberta durante esta etapa. A conexão ocorre
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
    -> configuração validada
    -> PostgresContextRepository
    -> create_graph(repository)
    -> grafo compilado

    O parâmetro environ permite testes determinísticos sem alterar
    os.environ. As factories são injetáveis somente para testes e
    outros composition roots controlados.
    """

    config = config_loader(environ)
    repository = repository_factory(config)

    return graph_factory(repository)
