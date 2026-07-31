# Result Normalization and Serialization Contract

## Objetivo

Esta fase adiciona uma camada deterministica entre `execute_sql` e o fim do
grafo. O resultado bruto validado pelo executor controlado e transformado em
um contrato normalizado e depois em um payload JSON-safe, autocontido e
independente de provider.

Fluxo:

```text
engine_preflight approved -> execute_sql -> normalize_result -> serialize_result -> END
```

## Escopo

Incluido:

- `NormalizedQueryResult` com colunas, linhas, tipos, metricas, diagnosticos e
  lineage.
- `SerializedQueryResult` com payload canonico JSON-safe e fingerprint
  deterministico.
- Nos puros `normalize_result` e `serialize_result`.

Fora do escopo:

- persistencia;
- API HTTP;
- integracao Next.js;
- adapters live;
- Watson, n8n, PROD ou banco real;
- execucao SQL real;
- graficos, resumo por IA, cache, download ou paginacao live.

## Contratos

`SqlExecutionResult` precisa estar em `status=success`, `executed=True`, sem
truncamento, com `request_fingerprint`, `response_fingerprint` e
`sql_fingerprint` presentes. Resultados `not_run`, `rejected`,
`infrastructure_error`, inconsistentes ou sem fingerprints sao rejeitados.

O normalizador nao altera `SqlExecutionResult` nem o `GraphState`. O
serializador nao altera `NormalizedQueryResult` nem o `GraphState`.

## Lineage

O lineage preserva identificadores e fingerprints minimos:

- `request_id`, `run_id`, `context_version`, `intent_name`;
- `sql_fingerprint`, `query_plan_fingerprint`, `preflight_fingerprint`;
- `execution_request_fingerprint`, `execution_response_fingerprint`;
- provider de execucao sanitizado, versao e duracao;
- fingerprints normalizado e serializado;
- contagem de linhas/colunas, bytes estimados, truncamento e versoes de
  contrato.

Nao inclui SQL integral, `QueryPlan` completo, `ContextSnapshot`, credenciais
ou dados de negocio em diagnosticos.

## Tipos

Tipos suportados:

- null;
- boolean;
- integer;
- decimal;
- float;
- string;
- date;
- datetime;
- time;
- binary;
- json;
- uuid.

Tipos desconhecidos sao rejeitados. Nao ha fallback `str(value)`.

## Decimal

`Decimal` nunca vira float. O valor e preservado como texto reversivel, por
exemplo:

```json
{"type":"decimal","value":"123.4500"}
```

## Float Especial

Floats comuns permanecem numericos. `NaN`, `Infinity`, `-Infinity` e `-0.0`
sao representados explicitamente, sem gerar JSON invalido.

## Datas

Datas e horas usam ISO 8601. Timezone existente e preservado; timezone ausente
permanece identificado como ausente. Nenhuma conversao de fuso, locale ou
inferencia de data e feita.

## Binary

Bytes e bytearray sao serializados em base64. O normalizador nao tenta
decodificar bytes como texto e nao inclui conteudo binario em diagnosticos.

## JSON

`dict`, `list` e `tuple` sao normalizados recursivamente. Chaves de objetos
precisam ser texto. Ciclos, profundidade excessiva, colecoes excessivas e
objetos arbitrarios sao rejeitados.

## Canonicalizacao

Canonicalizacao usa JSON UTF-8, chaves ordenadas, separadores estaveis e
`allow_nan=False`. Fingerprints nao dependem de endereco de memoria, `repr`,
locale, timezone local, timestamp corrente ou ordem arbitraria de dict.

## Limites

A normalizacao possui limites defensivos tipados:

- `max_rows`;
- `max_columns`;
- `max_total_cells`;
- `max_nesting_depth`;
- `max_collection_items`;
- `max_serialized_bytes`;
- `max_diagnostic_entries`.

Quando presentes em `options.result_normalization_limits`, sao usados
explicitamente. No grafo local, podem ser derivados dos limites de execucao
para manter compatibilidade com chamadas existentes, sem ampliar linhas ou
bytes alem da execucao.

## Seguranca

Nao ha mascaramento de dados nesta fase. O contrato tambem nao registra payload
completo em erros, nao inclui celulas em warnings e nao carrega linhas em
`AgentError.details`. Diagnosticos usam apenas ordinal de linha/coluna, tipo,
tamanho, fingerprint e codigo.

## Roteamento

- `execute_sql success -> normalize_result`;
- `execute_sql rejected -> END`;
- `execute_sql infrastructure_error -> finalize_infrastructure_error`;
- `normalize_result success -> serialize_result`;
- `normalize_result rejected -> END`;
- `normalize_result infrastructure_error -> finalize_infrastructure_error`;
- `serialize_result success -> END`;
- `serialize_result rejected -> END`;
- `serialize_result infrastructure_error -> finalize_infrastructure_error`.

Nao ha ciclo, nova execucao, reparo depois de execucao, nem retorno ao executor.

## Proximos Passos

Fases futuras podem persistir, auditar ou expor `SerializedQueryResult`, desde
que mantenham o contrato JSON-safe, nao reinterpretam valores e nao executem
SQL fora do executor controlado.
