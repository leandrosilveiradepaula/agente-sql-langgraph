# Controlled SQL Execution Contract

## Objetivo

Esta fase adiciona a infraestrutura local para execucao controlada de SQL ja
aprovada, sem adapter live e sem executar SQL real durante testes ou bootstrap.
O grafo passa a suportar `engine_preflight approved -> execute_sql -> END`
somente quando um `SqlExecutor` e explicitamente injetado.

## Pre-condicoes

`execute_sql` so pode construir a request quando todas as condicoes sao
verdadeiras:

- `current_sql` existe e e read-only (`SELECT` ou `WITH` cujo corpo e
  `SELECT`);
- Security Gate esta `approved`;
- Contract Gate esta `approved`;
- Engine Preflight esta `approved`;
- `preflight.executed=False`;
- `preflight.rows_returned=0`;
- `preflight.statement_planned=True`;
- fingerprints dos gates e do preflight batem com `current_sql`;
- limites de execucao foram informados explicitamente em
  `options.sql_execution_limits`.

Capability unavailable, erro de infraestrutura e preflight rejected nao
autorizam execucao.

## Request

`SqlExecutionRequest` e autocontida e minima. Ela contem `current_sql`,
`sql_fingerprint`, `request_id`, `run_id`, `context_version`, `intent_name`,
`query_plan_fingerprint`, `preflight_fingerprint`, `limits`, `attempt`,
`execution_id`, `dialect`, `engine_hint` e `request_fingerprint`.

A request nao contem `GraphState`, `ContextSnapshot`, `QueryPlan` integral,
credenciais, DSN, objetos n8n, prompt, catalogo de intencoes ou logs externos.

## Result

`SqlExecutionResult` registra status, colunas, linhas, contagens, truncamento,
bytes, duracao, provider sanitizado, fingerprints, diagnosticos, warnings,
`executed`, `statement_type`, codigo de erro, categoria de falha e metricas.

Erros nao carregam SQL integral, stack trace, tokens, DSN, headers ou payloads
externos.

## Limites

Os limites obrigatorios sao `timeout_seconds`, `max_rows`,
`max_response_bytes` e `max_cell_bytes`. Todos devem ser inteiros positivos e
fornecidos explicitamente por configuracao/opcoes tipadas. Nao ha default
silencioso para execucao.

Tetos defensivos locais:

- `timeout_seconds <= 300`;
- `max_rows <= 10000`;
- `max_response_bytes <= 10485760`;
- `max_cell_bytes <= 1048576`.

## Politica De Truncamento

A politica desta fase e fail-closed: linhas acima de `max_rows`, payload acima
de `max_response_bytes` ou celula acima de `max_cell_bytes` rejeitam o
resultado. O contrato preserva `truncated` para providers futuros, mas esta
fase nao trunca silenciosamente e nao adiciona `LIMIT` a SQL.

Quando `bytes_received` e informado pelo provider, ele deve coincidir com o
tamanho deterministico calculado localmente sobre colunas e linhas
preservadas. Valores ausentes sao calculados localmente; valores negativos ou
divergentes rejeitam a resposta.

## Fingerprints

`sql_fingerprint` usa a SQL atual com `strip` apenas para fingerprint, sem
alterar a SQL enviada ao executor. `request_fingerprint`,
`query_plan_fingerprint` e `preflight_fingerprint` usam JSON estavel com chaves
ordenadas. O fingerprint da request ignora o proprio campo
`request_fingerprint`.

## Roteamento

- `engine_preflight approved` com `executed=False`, `rows_returned=0` e
  `statement_planned=True` -> `execute_sql`;
- `engine_preflight rejected repairable` -> `repair_sql`;
- `engine_preflight rejected not repairable` -> END rejected;
- `engine_preflight infrastructure_error` -> `finalize_infrastructure_error`;
- `execute_sql success` -> END approved;
- `execute_sql rejected` -> END rejected;
- `execute_sql infrastructure_error` -> `finalize_infrastructure_error`.

Nao ha ciclo de execucao e nenhuma falha de execucao dispara reparo.

## Tratamento De Erros

Falhas de pre-condicao viram `rejected`, exceto erros inesperados internos que
viram `infrastructure_error`. Timeout, autenticacao, falha de provider e erro
inesperado do executor sao classificados como infraestrutura.

## Sanitizacao

Mensagens, warnings, provider name e provider version passam pela mesma
sanitizacao usada no preflight. A SQL atual e texto proibido para diagnosticos
de erro. Padroes de token, DSN, senha, host e authorization sao removidos.

## Fake

`FakeSqlExecutor` permite configurar resposta, excecoes, colunas, linhas,
contagem, bytes, truncamento, duracao e metadados do provider. Ele captura as
requests, conta chamadas e afirma que nao recebeu GraphState, ContextSnapshot,
QueryPlan integral, catalogos, DSN, senha ou token. O fake nao executa nem
interpreta SQL.

## Ausencia De Adapter Live

Nao existe adapter Watson, DuckLake, PostgreSQL ou n8n nesta fase. O bootstrap
exige `sql_executor` explicitamente e nao cria fallback. A implementacao futura
depende de contrato live comprovado do Watson/engine, inclusive confirmacao de
preflight seguro antes de permitir execucao real.

## Riscos Restantes

- O contrato live do provider ainda precisa ser obtido.
- A politica fail-closed pode rejeitar respostas grandes que um produto final
  talvez queira paginar.
- Tipos de coluna sao metadados livres do provider e devem ser validados no
  adapter real.
- Timeout e cancelamento real dependem da capacidade do provider futuro.
