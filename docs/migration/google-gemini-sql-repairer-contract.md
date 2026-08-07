# Google Gemini SQL Repairer Contract

## Objetivo

Esta fase adiciona um provider real para a porta `SqlRepairer` do LangGraph,
usando Google Gemini API por REST direto e sem SDK. A capacidade criada e
somente de reparo textual de SQL depois de `Engine Preflight` reparavel; ela
nao substitui n8n, nao executa SQL, nao cria benchmark e nao altera Watson,
PostgreSQL, DuckLake ou PROD.

O n8n permanece baseline oficial. Nao ha evidencia local suficiente para
reproduzir um reparo n8n especifico, portanto nenhum prompt monolitico, regra
oculta, cleaner, alias-fix, chave, payload bruto ou comportamento nao
documentado do n8n e copiado para o codigo.

## Porta

O adapter implementa a porta existente:

```python
repair(
    request: SqlRepairRequest,
) -> SqlRepairProviderResult
```

`SqlRepairRequest` permanece inalterado. O adapter nao recebe `GraphState`,
`ContextSnapshot`, usuario, headers, PostgreSQL, Watson, n8n, DuckLake ou PROD.
O campo `failure` continua unico e estruturado.

## Request

O payload enviado ao modelo e derivado somente de `SqlRepairRequest`:

- SQL atual com falha;
- tentativa atual e limite;
- `repair_context`;
- `failure` estruturado e ja sanitizado;
- `previous_attempts`;
- `instructions`;
- `output_constraints`.

Nao sao concatenados stack trace, erro bruto adicional, body de banco/provider,
headers, token, API key, DSN ou segredo.

## Provider Result

Em sucesso, o retorno padrao e:

```python
{
    "provider_name": "google_gemini",
    "output_text": "<texto retornado pelo modelo>",
    "duration_ms": 0,
}
```

`raw_response` e omitido. O `output_text` e preservado como texto retornado pelo
client, sem limpeza de Markdown, alias-fix, regex rewrite ou alteracao
semantica.

## Configuracao

Defaults aprovados:

- `api_base_url = https://generativelanguage.googleapis.com`
- `model_id = gemini-2.5-flash`
- `temperature = 0`
- `top_p = 0.1`
- `top_k = 1`
- `max_output_tokens = 8192`
- `response_mime_type = text/plain`
- `thinking_budget = 0`

O repairer usa variavel propria nao sensivel:

```text
GEMINI_SQL_REPAIRER_MODEL
```

O generator continua podendo usar `GEMINI_SQL_GENERATOR_MODEL`. Os dois podem
ter `model_id` diferentes. A configuracao nao contem chave de API.

## Segredo

O segredo e identificado somente por:

```text
GEMINI_API_KEY
```

O valor e lido apenas em runtime via `SecretValueProvider`. Imports,
configuracao, factories e bootstrap nao consultam nem materializam a chave.

## HTTP

O client usa `GoogleGeminiClient.generate_content(...)` com `HttpTransport`,
`HttpTransportRequest`, `HttpHeader` e `SensitiveSecret`. A chave e enviada
como header sensivel `x-goog-api-key`, nunca em query string.

O client faz exatamente uma tentativa por chamada. Nao ha retry, cache ou
backoff.

## Payload

O payload Gemini usa:

- `contents[0].role = user`;
- `contents[0].parts[0].text` com prompt de reparo e JSON deterministico do
  `SqlRepairRequest`;
- `generationConfig` com parametros aprovados.

O prompt instrui o modelo a corrigir a SQL existente, preservar intencao,
filtros, metricas, agrupamentos e escopo semantico, corrigir somente a falha
informada, respeitar `repair_context`, `instructions`,
`output_constraints` e `previous_attempts`, e retornar exatamente uma SQL de
leitura como texto puro.

## Boundaries

O adapter nao:

- executa SQL;
- chama Security Gate;
- chama Contract Gate;
- chama Engine Preflight;
- valida SQL reparada;
- limpa Markdown;
- aplica cleaner ou alias-fix;
- reescreve SQL por regex;
- decide numero de tentativas;
- atualiza `GraphState`;
- faz retry, cache ou backoff;
- retorna `raw_response`.

## Validacao Externa Ao Adapter

A validacao da SQL reparada continua no dominio:

`validate_sql_repair_response(...)`

Essa validacao rejeita vazio, Markdown, explicacao, multiplos statements,
DDL/DML, SQL nao iniciada por `SELECT` ou `WITH`, SQL identica a atual e SQL ja
repetida em `previous_attempts`.

Depois de aceita estruturalmente, a SQL volta para:

```text
Security Gate -> Contract Gate -> Engine Preflight
```

## Fluxo

```text
preflight reparavel
-> repair_sql
-> Google Gemini SqlRepairer
-> validacao de dominio
-> Security Gate
-> Contract Gate
-> Engine Preflight
```

Falhas de provider, secret, transporte, HTTP, JSON invalido ou envelope
invalido viram erro sanitizado de provider. Falhas estruturais da SQL reparada
viram rejeicao pelo dominio/grafo, nao pelo adapter.

## Fora Do Escopo

Esta fase nao altera n8n, Watson, PostgreSQL, PROD, workflows, requirements,
arquivos de lock ou benchmarks. Qualquer prova live futura deve ser manual,
separada da suite offline, com confirmacao explicita, sem imprimir segredo,
headers, body integral, URL com chave, raw response ou SQL sensivel.
