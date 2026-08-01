# ASGI entry adapter contract

## Objetivo

Esta fase adiciona uma aplicacao ASGI 3 minima para expor o
`SqlAgentHttpHandler` existente. O adapter e apenas uma fronteira de protocolo:
traduz `scope`, `receive` e `send` para `HttpRequestEnvelope` e
`HttpResponseEnvelope`.

Nao ha FastAPI, Starlette, Uvicorn, Hypercorn, servidor, socket, rede,
provider de identidade, banco, SQL, Watson, n8n ou PROD.

## Fluxo

`scope/receive/send -> AsgiSqlAgentApplication -> HttpRequestEnvelope ->
SqlAgentHttpHandler.handle -> HttpResponseEnvelope -> http.response.start +
http.response.body`

O adapter ASGI nao conhece `GraphState`, `GraphRuntime`, LangGraph,
`ApplicationRequest`, `Authenticator`, `Authorizer`, `SqlGenerator`,
`SqlExecutor`, repositories ou sinks. O handler HTTP continua responsavel por
rota, metodo, `Content-Type`, `Accept`, `Content-Length`, JSON, autenticacao,
autorizacao, chamada do service e mapeamento de dominio.

## Limits

`AsgiAdapterLimits` valida, em bytes, body, chunks, headers, path, query
string, method, scheme, client/server e response headers. Todos os limites sao
positivos, possuem teto defensavel e sao validados na construcao. Nao ha
defaults mutaveis compartilhados nem truncamento silencioso.

O bootstrap pode validar compatibilidade com `HttpRequestLimits` e
`HttpResponseLimits`; o limite ASGI de body e headers deve ser igual ou mais
restritivo que o limite HTTP correspondente.

## Scope HTTP

Somente `scope["type"] == "http"` e processado como HTTP. O adapter valida
estrutura minima, `asgi.version` quando presente, `http_version`, method, path,
query string, scheme, client/server opcionais e headers. `raw_path`,
`extensions`, `state`, client e server nao sao usados para identidade,
autorizacao ou regra de negocio.

`scope["path"]` e usado como rota logica. A query string e preservada em campo
separado do envelope, nao e interpretada e nao e usada para token ou pergunta.

## Headers

Headers ASGI entram como pares de bytes. O adapter valida nomes lowercase ASCII,
valores bytes, limites e ausencia de CR, LF, NUL e controles proibidos.
Duplicatas sao preservadas em `HeaderPairs`, inclusive `Authorization`, para que
o handler rejeite ambiguidades. `Content-Length` duplicado conflitante falha
fechado no adapter. O adapter nao interpreta `Authorization`, nao redige token e
nao registra headers.

## Body

O adapter le apenas eventos `http.request` e `http.disconnect`. Body ausente em
evento request equivale a `b""`; body nao-bytes, `more_body` nao-bool, evento
inesperado, excesso de chunks e excesso incremental de bytes falham fechados.
Depois de `more_body=False`, `receive` nao e chamado novamente. O adapter nao
decodifica JSON, nao interpreta conteudo e nao loga body.

`http.disconnect` interrompe a chamada: o handler nao e chamado, nao ha retry e
nenhuma resposta HTTP e enviada.

## Erros

Falhas antes do handler produzem uma `ApplicationResponse` minima publica
quando for seguro enviar HTTP. Os codigos incluem `ASGI_SCOPE_INVALID`,
`ASGI_METHOD_INVALID`, `ASGI_PATH_INVALID`, `ASGI_QUERY_STRING_INVALID`,
`ASGI_HEADERS_INVALID`, `ASGI_HEADERS_TOO_LARGE`, `ASGI_BODY_TOO_LARGE`,
`ASGI_BODY_TOO_MANY_CHUNKS`, `ASGI_RECEIVE_EVENT_INVALID`,
`ASGI_HANDLER_RESULT_INVALID`, `ASGI_SEND_FAILED` e
`ASGI_ADAPTER_UNEXPECTED_ERROR`.

Erros nunca incluem scope, headers, Authorization, token, cookie, query string,
body, question, SQL, GraphState, principal, roles/scopes, provider message,
stack trace, path local ou repr arbitrario.

## Response

Uma resposta valida gera exatamente um `http.response.start` e um
`http.response.body`. O adapter valida status 100..599, headers e body bytes.
Ele preserva `Content-Type`, headers de seguranca e body JSON ja produzido pelo
handler, sem resserializar `ApplicationResponse` e sem recalcular fingerprint.

Politica de `Content-Length`: o adapter adiciona `Content-Length` exato quando
ausente. Se o `HttpResponseEnvelope` trouxer `Content-Length`, o valor deve ser
unico, decimal e igual ao tamanho real do body; divergencia falha fechada. O
adapter nao adiciona `Server`, `Date`, CORS ou status line textual.

## Falha Ao Enviar

Antes de `response.start`, ainda e possivel enviar resposta minima. Depois de
`response.start`, o adapter nao tenta uma segunda resposta. Nao ha retry e o
handler nao e chamado novamente. A falha de envio e sanitizada; quando o
servidor ASGI nao permite recuperacao, a falha propaga sem dados sensiveis.

## Lifespan E WebSocket

Lifespan e stateless: `lifespan.startup` retorna
`lifespan.startup.complete`, e `lifespan.shutdown` retorna
`lifespan.shutdown.complete`. Nao ha health check, recurso externo, conexao,
thread ou background task.

WebSocket nao e suportado: o adapter envia `websocket.close` com codigo
generico e nao chama handler, auth, service ou grafo.

## Concorrencia E Cancelamento

A aplicacao e reutilizavel e stateless por request. Body, headers,
`response_started` e eventos sao variaveis locais por invocacao. Scope e eventos
de entrada nao sao mutados; eventos enviados sao copias independentes.

`asyncio.CancelledError` nao vira sucesso nem resposta 500 enganosa: o
cancelamento e preservado.

## Bootstrap

`create_asgi_application(http_handler, asgi_limits, ...)` exige handler e
limites explicitamente. A factory nao cria grafo, service, authenticator,
authorizer, fakes, singleton, env, servidor, socket, rede ou banco.

## Testes

Os testes ASGI usam harness em memoria: nenhum TestClient, socket, servidor,
rede, SQL, PostgreSQL, Watson, n8n, PROD ou provider live.

Proximos passos ficam fora desta fase: escolher servidor ASGI, composicao de
provider real de identidade e deploy controlado.
