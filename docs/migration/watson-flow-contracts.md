# Watson Flow integration contracts

Baseline funcional: `TEST - Agente SQL Financeiro DuckLake - v2.2.31 (7).json`,
com apoio do `discovery.txt`. Esta fase reproduz contratos offline do n8n mais
recente e nao implementa transporte live.

## Cadeias externas documentadas

IAM:

- `POST https://iam.cloud.ibm.com/identity/token`
- headers: `Content-Type: application/x-www-form-urlencoded` e
  `Accept: application/json`
- body: `grant_type=urn:ibm:params:oauth:grant-type:apikey` e
  `apikey=<configuracao segura>`
- retorno necessario: `access_token`

Flow:

- `POST /v1/orchestrate/flows/{flow_id}/run`
- headers futuros: `Authorization: Bearer <access_token>`,
  `Content-Type: application/json` e `Accept: application/json`
- flow de teste documentado: `00e0284a-d785-448b-aed3-95672dd4d189`
- nome de discovery: `Agentic_workflow_1_5887h4`
- payload atual: `{"sql_query": "<SQL preparada para transporte>"}`

Nao enviar `limit`, `max_rows`, pergunta, usuario, GraphState, contexto, plano,
token no body ou headers arbitrarios por request.

## SQL original vs transporte

`approved_sql` e a SQL aprovada pelo pipeline e preservada pelos contratos
existentes. `sql_transport` e uma copia compactada para o limite Watson de
10.000 caracteres, criada apenas no adapter. A compactacao remove comentarios
externos e reduz whitespace fora de strings/identificadores por maquina de
estados. Ela preserva aspas simples, aspas duplas, escapes duplicados,
operadores e separacao segura entre tokens. Nao trunca, nao repara, nao adiciona
`LIMIT`, nao troca schema e nao persiste a copia de transporte.

## Ports e adapters

Foram criadas as portas `IamTokenProvider` e `WatsonFlowClient`. O dominio e o
grafo continuam conhecendo somente `EnginePreflight` e `SqlExecutor`.

Adapters:

- `WatsonFlowEnginePreflightAdapter`
- `WatsonFlowSqlExecutorAdapter`

Ambos recebem `WatsonFlowConfiguration`, `WatsonFlowLimits`,
`IamTokenProvider` e `WatsonFlowClient` explicitamente. Nao ha fake default,
client live, leitura de env, secret provider, rede, socket ou servidor.

## Normalizacao fail-closed

O normalizador aceita envelopes historicos diretos, `result`, `output`,
`result.output`, `output.result` e `data` somente como envelope. `success` deve
ser bool real. Strings, inteiros, ausencia de success, envelopes conflitantes,
linhas malformadas, colunas divergentes, profundidade excessiva, ciclos,
NaN/Infinity e resposta grande sao rejeitados. Raw output e descartado apos a
normalizacao e nao entra em GraphState, RunRecord, audit, observability ou
ApplicationResponse.

## Diferencas deliberadas em relacao ao n8n

- nao presumir `success=true`;
- nao transportar `raw_result`;
- nao usar token em JSON intermediario;
- nao colocar API key em node state;
- nao repetir configuracao em preflight/execution;
- nao fazer retry dentro do adapter;
- nao usar Wait;
- nao expor erro bruto do provider;
- nao enviar `limit`;
- nao substituir SQL original pela SQL compactada.

## Testes

A suite offline cobre configuracao, IAM token contract, Watson Flow client
contract, compactacao SQL, normalizador, adapters de preflight/execution,
integracao com grafo real e bootstrap explicito. Todos usam fakes injetados,
sem rede, sem SQL, sem Watson, sem IBM Cloud e sem servidor. A proxima fase live
deve adicionar apenas transporte real por dependency injection e manter os
contratos desta fase.
