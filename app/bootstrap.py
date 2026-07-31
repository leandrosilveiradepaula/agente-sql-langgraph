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
from app.application.sql_agent_service import (
    IdGenerator,
    SqlAgentApplicationService,
)
from app.http.sql_agent_http_handler import (
    SqlAgentHttpHandler,
    create_sql_agent_http_handler,
)
from app.ports.graph_runtime import GraphRuntime
from app.ports.authenticator import Authenticator
from app.ports.authorizer import Authorizer
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


class CompiledGraphRuntime:
    """
    Adapter minimo para expor um grafo compilado pela porta GraphRuntime.
    """

    def __init__(self, graph: Any) -> None:
        if graph is None or not callable(getattr(graph, "invoke", None)):
            raise RuntimeError("graph deve expor invoke.")
        self._graph = graph

    def invoke(
        self,
        initial_state: Mapping[str, object],
    ) -> Mapping[str, object]:
        result = self._graph.invoke(dict(initial_state))
        if not isinstance(result, Mapping):
            raise RuntimeError("graph retornou estado invalido.")
        return result


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


def create_application_service(
    *,
    runtime: GraphRuntime | None = None,
    graph: Any | None = None,
    id_generator: IdGenerator | None = None,
    limits: Mapping[str, Any] | None = None,
) -> SqlAgentApplicationService:
    """
    Cria a fachada interna de aplicacao a partir de runtime explicito.

    Nenhum fake, singleton, adapter live, rede ou banco e criado aqui.
    """

    if runtime is None:
        if graph is None:
            raise RuntimeError(
                "runtime ou graph deve ser injetado explicitamente."
            )
        runtime = CompiledGraphRuntime(graph)
    if id_generator is None:
        raise RuntimeError(
            "id_generator deve ser injetado explicitamente."
        )
    return SqlAgentApplicationService(
        runtime=runtime,
        id_generator=id_generator,
        limits=limits,
    )


def create_postgres_context_application_service(
    environ: RuntimeEnvironment | None = None,
    *,
    id_generator: IdGenerator | None = None,
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
    limits: Mapping[str, Any] | None = None,
) -> SqlAgentApplicationService:
    """
    Composition root de alto nivel: constroi grafo e encapsula no service.

    As dependencias do grafo continuam explicitamente obrigatorias.
    """

    graph = create_postgres_context_graph(
        environ,
        sql_generator=sql_generator,
        engine_preflight=engine_preflight,
        sql_repairer=sql_repairer,
        sql_executor=sql_executor,
        run_repository=run_repository,
        audit_sink=audit_sink,
        observability_sink=observability_sink,
        config_loader=config_loader,
        repository_factory=repository_factory,
        graph_factory=graph_factory,
    )
    return create_application_service(
        graph=graph,
        id_generator=id_generator,
        limits=limits,
    )


def create_http_entry_adapter(
    *,
    application_service: SqlAgentApplicationService | None = None,
    authenticator: Authenticator | None = None,
    authorizer: Authorizer | None = None,
    auth_limits: Mapping[str, Any] | None = None,
    request_limits: Mapping[str, Any] | None = None,
    response_limits: Mapping[str, Any] | None = None,
) -> SqlAgentHttpHandler:
    """
    Cria o handler HTTP framework-agnostic.

    Nao cria grafo, adapters, fakes, servidor, rede ou banco.
    """

    if application_service is None:
        raise RuntimeError(
            "application_service deve ser injetado explicitamente."
        )
    if authenticator is None:
        raise RuntimeError("authenticator deve ser injetado.")
    if authorizer is None:
        raise RuntimeError("authorizer deve ser injetado.")
    if auth_limits is None:
        raise RuntimeError("auth_limits deve ser injetado.")
    if request_limits is None:
        raise RuntimeError("request_limits deve ser injetado.")
    if response_limits is None:
        raise RuntimeError("response_limits deve ser injetado.")
    return create_sql_agent_http_handler(
        application_service=application_service,
        authenticator=authenticator,
        authorizer=authorizer,
        auth_limits=auth_limits,
        request_limits=request_limits,
        response_limits=response_limits,
    )
