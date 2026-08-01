# HTTP Entry Adapter Contract

## Objetivo

Implementar uma fronteira HTTP fina e segura:

`HTTP request -> ApplicationRequest -> SqlAgentApplicationService -> ApplicationResponse -> HTTP response`

O adapter nao conhece LangGraph, `GraphState`, SQL, providers, banco ou sinks.

## Decisao De Framework

O repositorio nao possui `pyproject.toml` e `requirements.txt` contem apenas
LangGraph e Psycopg. Portanto, esta fase nao adiciona FastAPI, Starlette ou
Flask. Foi criado um handler framework-agnostic testavel sem servidor, socket
ou dependencia nova.

## Rota E Metodo

Operacao unica:

- `POST /v1/sql-agent/query`

Outros metodos retornam `405` com `Allow: POST`. Rotas inexistentes retornam
`404`. Nao ha aliases, health check, debug ou endpoint administrativo.

## Request HTTP

O body deve ser JSON UTF-8 com objeto raiz e campos destinados ao
`ApplicationRequest`. O handler valida apenas transporte e parsing; as regras
de `ApplicationRequest` continuam no application service.

## Content-Type E UTF-8

Aceito:

- `application/json`
- `application/json; charset=utf-8`

Sem sniffing. Charset diferente, body nao UTF-8 e Content-Type ausente ou
invalido sao rejeitados.

## Parser JSON

Usa `json.loads` defensivo com:

- `object_pairs_hook` para rejeitar chaves duplicadas;
- `parse_constant` para rejeitar `NaN` e `Infinity`;
- limite de profundidade;
- limite de membros;
- limite de digitos em inteiros;
- rejeicao de raiz nao objeto.

O body nunca aparece em mensagens de erro.

## Limites

`HttpRequestLimits`:

- `max_request_body_bytes`;
- `max_json_depth`;
- `max_json_members`;
- `max_json_integer_digits`;
- limites de headers.

`HttpResponseLimits`:

- `max_response_body_bytes`;
- limites de headers.

Tamanhos sao medidos em bytes UTF-8. Resposta acima do limite nao e truncada:
o adapter retorna resposta minima fail-closed com `HTTP_RESPONSE_TOO_LARGE`.

## Status HTTP

Mapeamento estavel por campo estruturado:

- `success` -> `200`;
- `rejected` -> `422`;
- `infrastructure_error` -> `503`;
- request HTTP invalida -> `400`, `404`, `405`, `406`, `413` ou `415`;
- falha inesperada do adapter -> `500`.

## Response HTTP

O body contem somente `ApplicationResponse`, sem envelope adicional. A
serializacao usa JSON UTF-8 com `allow_nan=False`; nao recalcula fingerprint,
nao transforma dados, nao duplica payload e nao armazena JSON canonico.

## Headers

Sempre:

- `Content-Type: application/json; charset=utf-8`;
- `X-Content-Type-Options: nosniff`;
- `Cache-Control: no-store`;
- `Pragma: no-cache`;
- `Referrer-Policy: no-referrer`.

Quando seguros e disponiveis:

- `X-Request-ID`;
- `X-Run-ID`;
- `X-Response-ID`.

Fingerprints nao sao expostos em headers.

## CORS E Autenticacao

CORS fica desabilitado por padrao; o adapter nao emite
`Access-Control-Allow-Origin: *`. A rota agora exige
`Authorization: Bearer <credential>`, processado por `Authenticator` e
`Authorizer` explicitamente injetados no handler. Authorization nao e copiado,
logado ou retornado. Nao ha provider real, sessao, cookie ou JWT live nesta
fase.

## Identidade HTTP

O campo `user` no body publico e proibido e retorna
`HTTP_IDENTITY_FIELD_FORBIDDEN`. A identidade usada em `ApplicationRequest`
deriva somente do `AuthenticatedPrincipal`: `subject_id`, `email`, `profile` e
`organization_id`. Roles, scopes, claims e token nao atravessam.

## Dependency Injection

`SqlAgentHttpHandler` recebe explicitamente:

- `SqlAgentApplicationService`;
- `Authenticator`;
- `Authorizer`;
- `AuthSecurityLimits`;
- `HttpRequestLimits`;
- `HttpResponseLimits`.

Nao cria grafo, adapters, fakes, singleton, servidor, rede ou banco.

## Adapter ASGI

Existe agora uma fronteira ASGI 3 minima sobre este handler. Ela traduz
`scope/receive/send` para `HttpRequestEnvelope`, chama
`SqlAgentHttpHandler.handle` exatamente uma vez por request valida e converte
`HttpResponseEnvelope` para eventos ASGI.

O nucleo HTTP continua framework-agnostic. Servidor ASGI, framework, socket,
rede, deploy e provider real nao fazem parte desta fase.

## Separacao

- HTTP: metodo, rota, headers, body, JSON, status e serializacao.
- Application service: `ApplicationRequest`, IDs, runtime e validacao de
  `ApplicationResponse`.
- Grafo: pipeline e regras.

## Erros

Erros de transporte retornam `ApplicationResponse` minima e publica. Nao expoem
body, fragmento JSON, headers, exception, stack trace, SQL, `GraphState`,
payload ou credenciais.

## Proximos Passos

Uma camada de servidor ASGI pode ser adicionada depois como composition root
externo, sem mudar este contrato e sem iniciar servidor em testes locais.
