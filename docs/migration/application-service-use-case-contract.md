# Application Service Use Case Contract

## Objetivo

Esta fase cria a fachada interna unica para executar o grafo local:

`ApplicationRequest -> SqlAgentApplicationService.execute(...) -> ApplicationResponse`

Chamadores futuros nao precisam conhecer `GraphState`, LangGraph, adapters,
fingerprints, `final_status` ou a localizacao de `application_response` no
estado final.

## Escopo

Incluido:

- contratos tipados de request;
- validacao estrutural da request;
- construcao do estado inicial minimo;
- porta minima `GraphRuntime`;
- fake local configuravel;
- service/use case sincrono;
- factory explicita de bootstrap;
- respostas fail-closed para input invalido e falha de runtime.

Fora de escopo:

- endpoint HTTP;
- autenticacao/autorizacao real;
- adapter live;
- banco real;
- rede;
- SQL real;
- streaming;
- retry automatico;
- scheduler.

## ApplicationRequest

A request contem somente entrada publica necessaria:

- `question`;
- `request_id` opcional;
- `run_id` opcional;
- `user` minimo;
- `options` ja suportadas pelo grafo;
- `correlation_id` e `client_request_id` opcionais;
- `metadata` publica e escalar.

Nao aceita `GraphState`, `ContextSnapshot`, `QueryPlan`, SQL, credenciais,
headers integrais, callbacks, sinks, adapters ou prompts.

## User

`ApplicationRequestUser` aceita apenas:

- `id`;
- `email`;
- `profile`;
- `organization_id`.

O service nao autentica nem autoriza. A futura camada de entrada devera
autenticar, autorizar e entao preencher esse contexto minimo.

## Options

O service mapeia apenas opcoes ja conhecidas pelo grafo:

- `use_cache`;
- `max_repair_attempts`;
- `shadow_mode`;
- `sql_execution_limits`;
- `result_normalization_limits`;
- `run_finalization_limits`;
- `application_response_limits`;
- `execution_attempt`;
- `timeout_seconds`.

Campos desconhecidos sao rejeitados. O chamador nao consegue desativar Security
Gate, Contract Gate ou Preflight, nao injeta provider e nao forca execucao.

## IDs

`request_id` e `run_id` sao preservados quando validos. Quando ausentes, sao
gerados por `IdGenerator` injetado. O service nao usa timestamp, estado global
ou `uuid.uuid4()` diretamente. IDs iguais sao rejeitados.

`correlation_id` e `client_request_id` sao validados somente como contexto
publico; nao controlam idempotencia e nao sao labels de metricas nesta fase.

## Limites

`ApplicationServiceLimits` define limites positivos para pergunta, IDs, user e
metadata. UTF-8 e contabilizado em bytes para `question`. Nao ha truncamento
silencioso.

Metadata aceita somente valores escalares seguros: `str`, `int`, `bool` ou
`None`.

## Initial State

`build_initial_graph_state(...)` cria somente:

- `question`;
- `request_id`;
- `run_id`;
- `user`;
- `options`.

O service nao inicializa gates, plano, SQL, execucao, finalizacao ou resposta.
Essa responsabilidade continua no grafo, a partir de `receive_question`.

## GraphRuntime

`GraphRuntime.invoke(initial_state)` recebe e retorna mappings. A porta nao
conhece `ApplicationRequest` e nao conhece SQL, adapters ou sinks.

`CompiledGraphRuntime` encapsula um grafo compilado que exponha `invoke`.

## SqlAgentApplicationService

O service:

- valida a request;
- resolve IDs;
- monta estado inicial minimo;
- invoca o runtime uma unica vez;
- valida o estado final;
- exige `ApplicationResponse` valida;
- retorna copia independente da resposta.

Ele nunca retorna `GraphState`, nao faz retry, nao chama sinks/adapters, nao
conhece provider SQL e nao interpreta sucesso a partir de campos parciais.

## Request Invalida

Request invalida retorna `ApplicationResponse` minima com:

- `status=rejected`;
- `original_outcome=rejected`;
- `data=None`;
- `finalization.status=incomplete`;
- codigo canonico da request.

O runtime nao e invocado.

## Runtime Failure

Excecoes ou resultados invalidos retornam `ApplicationResponse` minima com:

- `status=infrastructure_error`;
- `data=None`;
- `APPLICATION_SERVICE_RUNTIME_FAILED` ou
  `APPLICATION_SERVICE_INVALID_GRAPH_RESULT`;
- `request_id` e `run_id` preservados quando disponiveis.

Mensagens brutas de exception, stack traces, pergunta integral, SQL, payload e
GraphState nao atravessam.

## Timeout

`timeout_seconds` e validado como contrato de entrada, mas nao ha timeout falso.
Como o runtime sincrono atual nao oferece cancelamento cooperativo confiavel no
Windows, o service nao abandona threads, nao usa signal e nao declara
cancelamento real. A futura camada de runtime pode implementar esse suporte.

## Determinismo E Imutabilidade

O comportamento e deterministico dado o runtime e o `IdGenerator` injetados.
Request, user, options, estado inicial, estado final e resposta retornada sao
copiados nas fronteiras para evitar mutacao acidental.

## Seguranca

O service nao loga payload, pergunta integral, SQL ou estado final. Respostas
minimas nao incluem credenciais, tokens, DSN, headers, provider messages,
stack trace, `RunRecord`, `SerializedQueryResult` ou `GraphState`.

## Bootstrap

`create_application_service(...)` exige `runtime` ou `graph` e `id_generator`.
Nao ha singleton, fake default ou leitura de env no dominio.

`create_postgres_context_application_service(...)` monta o grafo com as mesmas
dependencias explicitas ja obrigatorias e o encapsula no service.

## Proximos Passos

- criar uma camada HTTP futura que traduza entrada externa para
  `ApplicationRequest`;
- manter endpoints futuros chamando somente o application service;
- implementar timeout cooperativo apenas se o runtime oferecer suporte seguro.
