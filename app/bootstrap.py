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
from app.asgi.asgi_limits import (
    validate_asgi_http_limit_compatibility,
)
from app.asgi.sql_agent_asgi_app import AsgiSqlAgentApplication
from app.application.sql_agent_service import (
    IdGenerator,
    SqlAgentApplicationService,
)
from app.application.internal_sql_agent_v1 import (
    ExecuteApprovedSqlShadowUseCase,
    GenerateSqlUseCase,
)
from app.http.internal_sql_agent_v1_handler import (
    InternalSqlAgentV1HttpHandler,
    create_internal_sql_agent_v1_http_handler,
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
from app.integrations.watson.configuration import WatsonFlowConfiguration
from app.integrations.watson.flow_limits import WatsonFlowLimits
from app.integrations.watson.flow_preflight_adapter import (
    WatsonFlowEnginePreflightAdapter,
)
from app.integrations.watson.flow_sql_executor import (
    WatsonFlowSqlExecutorAdapter,
)
from app.integrations.google_gemini.configuration import (
    GoogleGeminiConfiguration,
    load_google_gemini_configuration,
    load_google_gemini_repairer_configuration,
)
from app.integrations.google_gemini.client import GoogleGeminiClient
from app.integrations.google_gemini.sql_generator_adapter import (
    GoogleGeminiSqlGeneratorAdapter,
)
from app.integrations.google_gemini.sql_repairer_adapter import (
    GoogleGeminiSqlRepairerAdapter,
)
from app.integrations.watson.live_configuration import (
    LiveWatsonFlowConfiguration,
)
from app.integrations.watson.live_iam_token_provider import (
    LiveIamTokenProvider,
)
from app.integrations.watson.live_watson_flow_client import (
    LiveWatsonFlowClient,
)
from app.infrastructure.http.stdlib_http_transport import StdlibHttpTransport
from app.infrastructure.secrets.environment_secret_provider import (
    EnvironmentSecretProvider,
)
from app.ports.iam_token_provider import IamTokenProvider
from app.ports.http_transport import HttpTransport
from app.ports.secret_value_provider import SecretValueProvider
from app.ports.watson_flow_client import WatsonFlowClient


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


class LiveWatsonFlowDependencies:
    def __init__(
        self,
        *,
        iam_token_provider: IamTokenProvider,
        flow_client: WatsonFlowClient,
        engine_preflight: WatsonFlowEnginePreflightAdapter,
        sql_executor: WatsonFlowSqlExecutorAdapter,
    ) -> None:
        self.iam_token_provider = iam_token_provider
        self.flow_client = flow_client
        self.engine_preflight = engine_preflight
        self.sql_executor = sql_executor


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
        context_schema=config.context_schema,
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


def create_watson_flow_preflight_adapter(
    *,
    configuration: WatsonFlowConfiguration | None = None,
    limits: WatsonFlowLimits | None = None,
    iam_token_provider: IamTokenProvider | None = None,
    flow_client: WatsonFlowClient | None = None,
) -> WatsonFlowEnginePreflightAdapter:
    """
    Cria adapter Watson Flow de preflight somente com dependencias explicitas.
    """

    if configuration is None:
        raise RuntimeError("configuration deve ser injetada.")
    if limits is None:
        raise RuntimeError("limits deve ser injetado.")
    if iam_token_provider is None:
        raise RuntimeError("iam_token_provider deve ser injetado.")
    if flow_client is None:
        raise RuntimeError("flow_client deve ser injetado.")
    return WatsonFlowEnginePreflightAdapter(
        configuration=configuration,
        limits=limits,
        iam_token_provider=iam_token_provider,
        flow_client=flow_client,
    )


def create_watson_flow_sql_executor(
    *,
    configuration: WatsonFlowConfiguration | None = None,
    limits: WatsonFlowLimits | None = None,
    iam_token_provider: IamTokenProvider | None = None,
    flow_client: WatsonFlowClient | None = None,
) -> WatsonFlowSqlExecutorAdapter:
    """
    Cria executor Watson Flow somente com dependencias explicitas.
    """

    if configuration is None:
        raise RuntimeError("configuration deve ser injetada.")
    if limits is None:
        raise RuntimeError("limits deve ser injetado.")
    if iam_token_provider is None:
        raise RuntimeError("iam_token_provider deve ser injetado.")
    if flow_client is None:
        raise RuntimeError("flow_client deve ser injetado.")
    return WatsonFlowSqlExecutorAdapter(
        configuration=configuration,
        limits=limits,
        iam_token_provider=iam_token_provider,
        flow_client=flow_client,
    )


def create_live_watson_flow_dependencies(
    *,
    live_configuration: LiveWatsonFlowConfiguration | None = None,
    limits: WatsonFlowLimits | None = None,
    secret_provider: SecretValueProvider | None = None,
    http_transport: HttpTransport | None = None,
) -> LiveWatsonFlowDependencies:
    """
    Compoe dependencias live Watson somente quando explicitamente habilitadas.

    Nao acessa secret, rede, token, banco, servidor ou SQL durante a factory.
    """

    if live_configuration is None:
        raise RuntimeError("live_configuration deve ser injetada.")
    if not isinstance(live_configuration.enabled, bool):
        raise RuntimeError("enabled deve ser bool.")
    if live_configuration.enabled is not True:
        raise RuntimeError("watson live desabilitado.")
    if limits is None:
        raise RuntimeError("limits deve ser injetado.")
    if secret_provider is None:
        raise RuntimeError("secret_provider deve ser injetado.")
    if http_transport is None:
        raise RuntimeError("http_transport deve ser injetado.")

    iam = LiveIamTokenProvider(
        configuration=live_configuration.watson_configuration,
        api_key_secret_name=live_configuration.api_key_secret_name,
        secret_provider=secret_provider,
        http_transport=http_transport,
    )
    flow = LiveWatsonFlowClient(
        configuration=live_configuration.watson_configuration,
        http_transport=http_transport,
        limits=limits,
    )
    return LiveWatsonFlowDependencies(
        iam_token_provider=iam,
        flow_client=flow,
        engine_preflight=WatsonFlowEnginePreflightAdapter(
            configuration=live_configuration.watson_configuration,
            limits=limits,
            iam_token_provider=iam,
            flow_client=flow,
        ),
        sql_executor=WatsonFlowSqlExecutorAdapter(
            configuration=live_configuration.watson_configuration,
            limits=limits,
            iam_token_provider=iam,
            flow_client=flow,
        ),
    )


def create_stdlib_live_watson_flow_dependencies(
    *,
    live_configuration: LiveWatsonFlowConfiguration | None = None,
    limits: WatsonFlowLimits | None = None,
    secret_provider: SecretValueProvider | None = None,
) -> LiveWatsonFlowDependencies:
    """
    Compoe a variante stdlib. Construir o transporte nao abre rede.
    """

    if secret_provider is None:
        raise RuntimeError("secret_provider deve ser injetado.")
    return create_live_watson_flow_dependencies(
        live_configuration=live_configuration,
        limits=limits,
        secret_provider=secret_provider,
        http_transport=StdlibHttpTransport(),
    )


def create_google_gemini_sql_generator(
    environ: RuntimeEnvironment | None = None,
    *,
    configuration: GoogleGeminiConfiguration | None = None,
    secret_provider: SecretValueProvider | None = None,
    http_transport: HttpTransport | None = None,
) -> GoogleGeminiSqlGeneratorAdapter:
    """
    Cria o provider Gemini explicitamente, sem rede ou leitura de secret.
    """

    if configuration is None:
        configuration = load_google_gemini_configuration(environ)
    if secret_provider is None:
        secret_provider = EnvironmentSecretProvider()
    if http_transport is None:
        http_transport = StdlibHttpTransport()
    client = GoogleGeminiClient(
        configuration=configuration,
        secret_provider=secret_provider,
        http_transport=http_transport,
    )
    return GoogleGeminiSqlGeneratorAdapter(client=client)


def create_google_gemini_sql_repairer(
    environ: RuntimeEnvironment | None = None,
    *,
    configuration: GoogleGeminiConfiguration | None = None,
    secret_provider: SecretValueProvider | None = None,
    http_transport: HttpTransport | None = None,
) -> GoogleGeminiSqlRepairerAdapter:
    """
    Cria o repairer Gemini explicitamente, sem rede ou leitura de secret.
    """

    if configuration is None:
        configuration = load_google_gemini_repairer_configuration(environ)
    if secret_provider is None:
        secret_provider = EnvironmentSecretProvider()
    if http_transport is None:
        http_transport = StdlibHttpTransport()
    client = GoogleGeminiClient(
        configuration=configuration,
        secret_provider=secret_provider,
        http_transport=http_transport,
    )
    return GoogleGeminiSqlRepairerAdapter(client=client)


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


def create_internal_sql_agent_v1_entry_adapter(
    *,
    generate_use_case: GenerateSqlUseCase | None = None,
    execute_approved_shadow_use_case: (
        ExecuteApprovedSqlShadowUseCase | None
    ) = None,
    request_limits: Mapping[str, Any] | None = None,
    response_limits: Mapping[str, Any] | None = None,
) -> InternalSqlAgentV1HttpHandler:
    """
    Cria o handler HTTP interno v1 para shadow em duas etapas.

    Nao cria grafo, provider live, servidor, rede, banco, Watson ou Gemini.
    """

    if generate_use_case is None:
        raise RuntimeError("generate_use_case deve ser injetado.")
    if execute_approved_shadow_use_case is None:
        raise RuntimeError(
            "execute_approved_shadow_use_case deve ser injetado."
        )
    return create_internal_sql_agent_v1_http_handler(
        generate_use_case=generate_use_case,
        execute_approved_shadow_use_case=execute_approved_shadow_use_case,
        request_limits=request_limits,
        response_limits=response_limits,
    )


def create_asgi_application(
    *,
    http_handler: SqlAgentHttpHandler | None = None,
    asgi_limits: Mapping[str, Any] | None = None,
    http_request_limits: Mapping[str, Any] | None = None,
    http_response_limits: Mapping[str, Any] | None = None,
) -> AsgiSqlAgentApplication:
    """
    Cria a aplicacao ASGI framework-agnostic sobre um handler HTTP existente.

    Nao cria grafo, service, auth providers, servidor, socket, rede ou banco.
    """

    if http_handler is None:
        raise RuntimeError("http_handler deve ser injetado.")
    if asgi_limits is None:
        raise RuntimeError("asgi_limits deve ser injetado.")
    validate_asgi_http_limit_compatibility(
        asgi_limits=asgi_limits,
        http_request_limits=http_request_limits,
        http_response_limits=http_response_limits,
    )
    return AsgiSqlAgentApplication(
        http_handler=http_handler,
        asgi_limits=asgi_limits,
    )
