# Engine Preflight Contract

## Objetivo

`app/domain/engine_preflight.py` define o contrato da fase que valida se a
`current_sql` aprovada por Security Gate e Contract Gate pode ser analisada e
planejada por um motor de dados. A fase nao executa a consulta de negocio, nao
retorna linhas e nao mede desempenho real.

## Limites

O preflight nao substitui Security Gate nem Contract Gate. Ele nao reescreve
SQL, nao adiciona `LIMIT`, nao corrige alias, nao chama o gerador novamente e
nao implementa loop de reparo. `EXPLAIN ANALYZE` e proibido. Qualquer adapter
real deve usar apenas validacao sem execucao, preferencialmente `EXPLAIN` sem
`ANALYZE`, com timeout e modo leitura.

## Porta

`app/ports/engine_preflight.py` expõe `EnginePreflight.preflight(request)`.
A porta recebe somente `EnginePreflightRequest`; nao recebe `GraphState`,
`ContextSnapshot`, credenciais, objetos n8n ou detalhes de UI. O bootstrap
exige injecao explicita. Nao existe fake global ou provider padrao oculto.

## Request

`EnginePreflightRequest` contem SQL corrente, fingerprint da SQL,
`context_version`, `context_fingerprint`, `intent_name`, schemas autorizados,
tabelas planejadas, `dialect` ou `engine_hint` quando presentes no `QueryPlan`,
timeout logico, tentativa e capacidades solicitadas. O `QueryPlan` completo,
regras de negocio e `ContextSnapshot` completo nao sao enviados ao adapter.

O fingerprint da request e estavel e calculado sobre uma copia deterministica
do payload, sem mutar entradas.

## Result

`EnginePreflightResult` contem status, approved, repairable,
failure_category, findings, errors, warnings, provider, versao do contrato,
fingerprints, contexto, duracao, tentativa, capacidades usadas,
`statement_planned`, `executed = false` e `rows_returned = 0`.

O resultado nao inclui a SQL completa e deve provar que a consulta nao foi
executada.

## Categorias

Categorias reparaveis de SQL incluem `syntax_error`, `schema_not_found`,
`table_not_found`, `column_not_found`, `ambiguous_column`,
`function_not_found`, `invalid_grouping`, `invalid_ordering`,
`type_mismatch`, `invalid_cast`, `invalid_join`, `invalid_cte`,
`invalid_subquery`, `dialect_error`, `planning_error` e
`unknown_sql_error`.

Categorias de infraestrutura incluem `provider_unavailable`,
`authentication_failed`, `timeout`, `connection_failed`, `protocol_error` e
`adapter_error`.

## Sanitizacao

Mensagens, hints e identificadores vindos do provider sao sanitizados para
remover DSN, senha, token, segredo, usuario e chaves. O dominio preserva
codigo do provider, SQLSTATE, posicao, linha, coluna, objeto relacionado e hint
somente quando fornecidos de forma estruturada e segura.

## Adapters

A branch cria apenas a porta e `app/adapters/testing/fake_engine_preflight.py`
para testes locais. Adapter real ficou pendente porque o repositorio possui
somente adapter PostgreSQL de contexto e scripts live separados; nao ha porta
segura existente para planejamento sem execucao.

A fase posterior adicionou configuracao e diagnostico de capability em
`docs/migration/live-engine-preflight-adapter.md`. Enquanto nao houver
capacidade comprovada do motor final, o provider diagnostico falha fechado com
`ENGINE_PREFLIGHT_CAPABILITY_UNAVAILABLE` e nao deve ser apresentado como
adapter live real.

Caso um adapter PostgreSQL de preflight seja criado no futuro, ele deve ficar
fora de `scripts/check_all.py`, nao executar `EXPLAIN ANALYZE`, nao persistir
nada, nao exigir credenciais na suite local e nao ser executado automaticamente.

## Roteamento

Fluxo final:

`START -> receive_question -> load_context -> classify_intent -> build_plan ->
generate_sql -> security_gate -> contract_gate -> engine_preflight -> END`.

`contract_gate` aprovado com `processing` chama `engine_preflight`.
`contract_gate` rejeitado encerra. `engine_preflight` aprovado encerra com
`final_status = processing`; rejeicoes SQL encerram como `rejected`; falhas de
infraestrutura seguem para `finalize_infrastructure_error`.

## Proxima Fase

A fase prepara `repairable`, categoria, posicao, objeto relacionado, hint
sanitizado e tentativa para um futuro repair loop. O loop de reparo,
persistencia de historico, execucao da consulta e retorno de dados permanecem
fora deste contrato.
