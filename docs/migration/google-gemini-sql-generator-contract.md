# Google Gemini SQL Generator Contract

## Objetivo

Esta fase adiciona um provider real para a porta `SqlGenerator` do LangGraph,
usando Google Gemini API por REST direto e sem SDK. A capacidade criada e
somente de geracao SQL; ela nao substitui n8n, nao cria shadow mode e nao
altera Watson, PostgreSQL, DuckLake ou PROD.

O n8n permanece baseline oficial. O LangGraph podera rodar futuramente em
paralelo, em modo de teste/shadow, somente depois de validacao propria.

## Provider

- Provider: Google Gemini API.
- Modelo aprovado: `gemini-2.5-flash`.
- Operacao: `generateContent`.
- Transporte: HTTP REST direto.
- SDKs externos: nenhum.

A decisao vem do workflow n8n atual, mas nenhum segredo, payload bruto ou
prompt monolitico do n8n e copiado para o codigo.

## Entrada

O adapter implementa a porta existente:

```python
generate(
    request: SqlGenerationRequest,
) -> SqlGenerationProviderResult
```

`SqlGenerationRequest` contem somente:

- `contract_version`
- `generation_context`
- `instructions`
- `output_constraints`

O adapter nao recebe `GraphState`, `ContextSnapshot`, usuario, headers,
PostgreSQL, Watson, n8n, DuckLake ou PROD.

## Saida

Em sucesso, o retorno padrao e:

```python
{
    "provider_name": "google_gemini",
    "output_text": "<texto retornado pelo modelo>",
    "duration_ms": 0,
}
```

`raw_response` e omitido por padrao. A validacao estrutural de SQL continua no
dominio existente em `app/domain/sql_generation.py`.

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

Timeouts e tamanho de resposta possuem limites defensivos. A configuracao nao
contem chave de API.

## Segredo

O segredo e identificado somente por:

```text
GEMINI_API_KEY
```

O valor do segredo nao pode aparecer em codigo, teste, fixture, log,
documentacao, erro publico, resultado, commit ou saida de terminal.

O segredo e lido apenas em runtime por `SecretValueProvider`. Imports,
configuracao, factories e bootstrap nao consultam o ambiente nem materializam a
chave.

## HTTP

O client usa o transporte injetavel existente:

- `HttpTransport`
- `HttpTransportRequest`
- `HttpHeader`
- `SensitiveSecret`

A chave e enviada como header sensivel `x-goog-api-key`, evitando URL com chave
em query string. A URL usada para `generateContent` nao deve aparecer em
diagnosticos junto com segredo.

O client faz exatamente uma tentativa por chamada. Nao ha retry, cache ou
backoff.

## Payload

O payload enviado ao Gemini contem:

- `contents[0].role = user`
- `contents[0].parts[0].text` com representacao deterministica do
  `SqlGenerationRequest`
- `generationConfig` com os parametros aprovados

Nao ha `safetySettings` copiado do n8n.

O texto do prompt pede uma unica SQL de leitura, texto puro, iniciando por
`SELECT` ou `WITH`, sem Markdown, comentarios, JSON ou explicacoes. Regras de
negocio, tabelas, joins, filtros, aliases e DRE entram somente via
`SqlGenerationRequest`.

## Resposta

O client extrai texto de:

```text
candidates[*].content.parts[*].text
```

Regras:

- considerar somente parts textuais;
- concatenar textos em ordem;
- ignorar parts nao textuais;
- remover apenas espacos externos globais;
- nao limpar Markdown;
- nao corrigir SQL;
- nao remover comentarios;
- deixar a validacao para o dominio existente.

Falhas de secret, transporte, HTTP, JSON invalido ou envelope invalido viram
erro sanitizado de provider.

## Fora Do Adapter

O adapter nao:

- implementa `SqlRepairer`;
- executa SQL;
- executa gates;
- executa preflight;
- adiciona `LIMIT`;
- corrige SQL;
- cria catalogo paralelo;
- implementa regras financeiras;
- altera n8n;
- altera Watson live;
- acessa PostgreSQL;
- acessa PROD;
- cria benchmark.

## Testes Offline

A fase exige testes com `FakeHttpTransport` e `FakeSecretValueProvider`, sem
rede e sem chave real. Os testes devem cobrir configuracao, payload
deterministico, erros HTTP, erros de secret, extracao de resposta, ausencia de
vazamento de chave e integracao com a validacao existente.

## Prova Live Futura

Qualquer prova live futura deve ser manual, separada da suite offline, com
confirmacao explicita, uma unica tentativa, sem retry, sem imprimir segredo,
headers, body integral, URL com chave, raw response ou SQL sensivel.
