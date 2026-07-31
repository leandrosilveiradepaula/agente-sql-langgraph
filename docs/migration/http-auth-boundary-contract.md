# HTTP Auth Boundary Contract

## Objetivo

Adicionar uma fronteira provider-agnostic de autenticacao e autorizacao para
`POST /v1/sql-agent/query`, antes do `SqlAgentApplicationService`.

Fluxo:

`HTTP request -> transporte -> Authorization Bearer -> Authenticator -> AuthenticatedPrincipal -> Authorizer -> ApplicationRequest -> ApplicationResponse`

## Escopo

Esta fase cria contratos, portas, fakes, extracao segura de Bearer, integracao
no handler, status publicos e testes. Nao implementa IBM IAM, OAuth/OIDC,
JWKS, JWT live, sessao, cookie, banco de usuarios, provider real, servidor ou
framework HTTP.

## Mudanca Incompativel

O campo `user` no body publico agora e proibido. Se presente, a request retorna
`HTTP_IDENTITY_FIELD_FORBIDDEN` com status `400`. A identidade confiavel vem
somente do `AuthenticatedPrincipal`.

Mapeamento para `ApplicationRequest.user`:

- `subject_id` -> `id`
- `email` -> `email`
- `profile` -> `profile`
- `organization_id` -> `organization_id`

Roles, scopes, claims e token nao atravessam para `ApplicationRequest`.

## Authorization Bearer

`Authorization: Bearer <credential>` e obrigatorio. Header ausente, scheme
invalido, credencial vazia, ambiguidades, controle, whitespace ambiguo e
limites excedidos falham fechados. O valor bruto nao aparece em erro,
diagnostico, resposta, metadata, repr ou fingerprint publico.

## Authenticator

Porta minima:

`authenticate(BearerCredential, AuthenticationContext) -> AuthenticationResult`

O contexto contem apenas metodo e rota canonica nesta fase. Nao contem body,
question, headers completos, SQL, `GraphState` ou `ApplicationRequest`.

Estados:

- `authenticated`
- `invalid_credentials`
- `unavailable`
- `error`

Credencial invalida retorna `401`; indisponibilidade retorna `503`; erro
inesperado retorna `500`, sempre sem chamar o service.

## AuthenticatedPrincipal

Principal contem apenas atributos seguros: `subject_id`, `email`, `profile`,
`organization_id`, roles, scopes, attributes allowlisted, metodo e issuer nao
sensiveis. Nao contem token, claims brutas, headers, cookie, segredo, senha ou
provider response.

Roles, scopes e attributes sao copias independentes e imutaveis.

## Authorizer

Porta minima:

`authorize(AuthenticatedPrincipal, AuthorizationRequest) -> AuthorizationDecision`

`AuthorizationRequest` usa action `sql_agent.query.execute` e resource
`sql_agent.query`. Nao contem token, question, SQL, body, `GraphState` ou data
da `ApplicationResponse`.

Estados:

- `allowed`
- `denied`
- `unavailable`
- `error`

`denied` retorna `403`; indisponibilidade retorna `503`; erro inesperado
retorna `500`. Nenhuma falha de autorizacao chama o service.

## WWW-Authenticate

Respostas `401` incluem somente `WWW-Authenticate: Bearer`. `403` nao inclui
esse header. Nenhum detalhe de token, issuer, tenant, provider ou stack trace e
exposto.

## Limites

`AuthSecurityLimits` valida tamanhos em bytes UTF-8 para Authorization,
credencial, principal, roles, scopes, attributes e diagnostics. Todos os
limites devem ser positivos e abaixo de tetos defensivos. Nao ha truncamento
silencioso.

## Fail-Closed

Header ausente/invalido, credencial invalida, principal invalido, exception,
deny ou indisponibilidade impedem `SqlAgentApplicationService`. Nao existe
retry, usuario anonimo, allow-all default, policy global ou leitura de env no
dominio.

## Bootstrap

`create_http_entry_adapter` exige explicitamente:

- `application_service`
- `authenticator`
- `authorizer`
- `auth_limits`
- `request_limits`
- `response_limits`

Nao cria fake, singleton, provider live, servidor, rede ou banco.

## Logs E Seguranca

Esta fase nao adiciona logger. Authorization, credencial, principal, roles,
scopes, body, question, SQL e decisions completas nao devem ser logados.

## Testes

Cobertura local:

- `testar_auth_types.py`
- `testar_auth_header.py`
- `testar_http_auth_boundary.py`
- `testar_http_auth_integration.py`
- regressao HTTP e bootstrap em `scripts/check_all.py`

Todos usam fakes e dados genericos, sem rede, servidor, socket, SQL,
PostgreSQL, Watson, n8n, PROD ou provider real.

## Proximos Passos

Um provider real futuro deve implementar as portas `Authenticator` e
`Authorizer` existentes, mantendo fail-closed e sem alterar o contrato publico
HTTP.
