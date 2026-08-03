# Watson Flow Live Adapters

## Objetivo

Esta fase adiciona infraestrutura live isolada para IBM IAM e Watson Flow sem
ativacao automatica. O dominio, grafo, politicas de preflight, repair e
execucao continuam usando apenas portas ja existentes.

## Arquitetura

`WatsonFlowEnginePreflightAdapter` e `WatsonFlowSqlExecutorAdapter` continuam
dependendo somente de `IamTokenProvider` e `WatsonFlowClient`. As
implementacoes live ficam abaixo dessas portas:

`LiveIamTokenProvider` / `LiveWatsonFlowClient` -> `HttpTransport` ->
`StdlibHttpTransport`.

Secrets entram por `SecretValueProvider`; API key nao entra em contrato de
dominio.

## Secrets

`SensitiveSecret` e imutavel, redige `repr`/`str`, nao e dataclass e so revela
o valor por `reveal_for_transport()`. `EnvironmentSecretProvider` le somente a
variavel solicitada, sem cache, fallback, `.env` ou copia do ambiente inteiro.

## HTTP

`HttpTransportRequest` contem metodo, URL, headers seguros, body bytes,
timeouts, limite de resposta e metadados tecnicos. `HttpHeader` separa valor
publico de sensivel; `Authorization` e materializado apenas no transporte.

`StdlibHttpTransport` usa `http.client`, `ssl.create_default_context()` e
HTTPS. TLS verifica certificado e hostname. Nao ha proxy, redirect, pool,
retry, cookie jar, gzip ou logging. `Content-Length` e calculado pelo
transporte; `Connection: close` e `Accept-Encoding: identity` sao enviados.

Resposta e lida em chunks, com limite antes de acumular. `Content-Length`
invalido, acima do limite ou divergente falha fechado. `gzip`, `br`,
`deflate` e outros encodings sao rejeitados nesta fase.

## IAM

IAM chama:

`POST https://iam.cloud.ibm.com/identity/token`

Headers: `Content-Type: application/x-www-form-urlencoded`, `Accept:
application/json`, `Accept-Encoding: identity`.

Body deterministico:

`grant_type=urn%3Aibm%3Aparams%3Aoauth%3Agrant-type%3Aapikey&apikey=<secret externo>`

Status 400/401/403 viram `authentication_failed`; 408 vira `timeout`; 429 e
5xx viram `unavailable`; JSON malformado vira `invalid_response`.

## Watson Flow

Flow chama:

`{api_base_url}/v1/orchestrate/flows/{flow_id}/run`

Payload JSON contem somente `sql_query`. Nao envia `limit`, `max_rows`,
`params`, pergunta, usuario, IDs, contexto, plano, API key ou `flow_id` no
body. Status 2xx tenta sucesso, 401/403 viram authentication, 408 timeout, 429
rate limited, 5xx unavailable e demais 4xx http error.

JSON usa UTF-8 estrito, rejeita charset incompativel, chaves duplicadas,
`NaN`/`Infinity` e root nao objeto. `raw_output` fica apenas na fronteira
imediata e continua redigido em `repr`.

## Bootstrap

`create_live_watson_flow_dependencies(...)` exige `enabled=True`,
configuracao, limits, secret provider e transporte. A factory nao acessa
secret, token, rede, banco ou SQL. `create_stdlib_live_watson_flow_dependencies`
apenas construi o transporte stdlib e tambem permanece sem rede.

## Composition Root TEST

`app/composition/watson_test.py` adiciona uma composition root explicita para
o ambiente TEST. Ela aceita somente `DeploymentEnvironment.TEST`, rejeita
strings livres e aliases de producao como `prod`, `production`, `prd` e
`live`, exige `enabled=True`, limits, `SecretValueProvider` e `HttpTransport`
injetados.

A composition root constroi `LiveIamTokenProvider`, `LiveWatsonFlowClient`,
`WatsonFlowEnginePreflightAdapter` e `WatsonFlowSqlExecutorAdapter` sem
consultar env, secret, rede, socket, banco, servidor ou SQL. O container
`WatsonTestDependencies` guarda apenas objetos de dependencia e possui `repr`
sanitizado; nao armazena API key, token, Authorization, SQL, `sql_transport`,
raw output ou `GraphState`.

Factories auxiliares permitem compor `GraphRuntime` e
`SqlAgentApplicationService` substituindo somente as portas de preflight e
executor pelos adapters Watson, preservando os demais componentes genericos.

## Script Manual

`scripts/manual_watson_flow_probe.py` e dry-run por padrao. O dry-run valida
SQL, compactacao, payload e configuracao nao sensivel quando fornecida, mas nao
exige `IBM_CLOUD_API_KEY`, nao cria `EnvironmentSecretProvider`, nao cria
transporte live, nao consulta secret e nao acessa rede. Sem URL/flow ID, o
dry-run SQL-only continua aprovado e apenas sinaliza que a configuracao live
esta incompleta.

Live exige `--execute-live`, `--confirm-test-environment`, SQL valida, URL e
flow ID validos e secret disponivel via `SecretValueProvider`. A ordem e:
argumentos, flags, arquivo regular, tamanho, UTF-8, SQL nao vazia,
compactacao, payload, configuracao nao sensivel, confirmacao TEST, composicao
live, lookup do secret, IAM e Flow.

O script mostra hash/tamanho da SQL, plano sanitizado opcional com
`--print-plan-json`, nao imprime SQL completa, token, API key, Authorization,
body IAM, body Flow bruto ou rows por default. `--purpose preflight` executa
somente preflight; `--purpose execution` executa somente execution.

Variaveis lidas apenas em `main()`:

- `WATSON_API_BASE_URL`
- `WATSON_FLOW_ID`
- `IBM_CLOUD_API_KEY`
- `WATSON_IAM_TOKEN_URL` opcional
- `WATSON_CONNECT_TIMEOUT_SECONDS` opcional
- `WATSON_READ_TIMEOUT_SECONDS` opcional

## LIMITACOES DELIBERADAS

- sem retry;
- sem cache de token;
- sem refresh antecipado;
- sem proxy;
- sem redirect;
- sem gzip;
- sem async;
- sem pool;
- sem ADK;
- sem SDK IBM;
- sem health check externo;
- sem execucao automatica.

## Riscos Conhecidos

Timeouts de conexao e leitura usam a semantica disponivel em `http.client`;
quando o socket esta disponivel, o timeout de leitura e aplicado no socket. A
fase live real ainda precisa de validacao manual em ambiente controlado.
