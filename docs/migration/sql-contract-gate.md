# SQL Contract Gate

## Objetivo

`app/domain/sql_contract.py` valida aderencia da `current_sql` ao `QueryPlan`.
Ele nao valida seguranca basica, nao executa SQL, nao repara SQL e nao relê
`ContextSnapshot`.

## Entrada

O gate usa exclusivamente `query_plan.selected_pattern`,
`query_plan.planning_context`, `query_plan.sql_pattern_metadata`,
`query_plan.selection_diagnostic`, versoes/fingerprint do plano, `current_sql`
e `SqlStatementAnalysis`.

## Tabelas e Colunas

Toda tabela referenciada deve estar no plano, e toda tabela requerida deve
aparecer na SQL quando verificavel. Colunas qualificadas por alias ou tabela
sao resolvidas contra o catalogo projetado. Colunas nao qualificadas so passam
quando sao unicas entre as tabelas planejadas. Colunas inexistentes, aliases
invalidos e ambiguidades sao rejeitados.

## Joins

Joins sao comparados com `planning_context.authorized_joins` quando o formato e
interpretavel. Joins divergentes sao rejeitados. Joins com regra opaca no plano
sao registrados como `unverifiable` e nao viram aprovacao falsa.

## Regras

Regras estruturadas podem declarar `required_sql_fragments`,
`forbidden_sql_fragments`, `required_filters`, `forbidden_filters`,
`required_groupings`, `forbidden_keywords`, `limit_policy`, `required_tables`,
`required_columns`, `required_joins`, `select_star_policy` ou
`wildcard_policy`. Regras opacas sao registradas como `unverifiable` e geram
warning diagnostico.

## LIMIT e SELECT *

`LIMIT` segue apenas politica declarada em regra projetada: `allow`, `forbid`
ou `require`. Sem politica, o gate nao inventa proibicao global.

`SELECT *` e `table.*` usam politica projetada quando existir. Sem politica
explicita, o comportamento documentado e `warn`: aprova com diagnostico, sem
silenciar o uso de wildcard.

## Resultado e Roteamento

`SqlContractResult` retorna status, checks, findings, verificacoes de tabelas,
colunas, joins e regras, regras nao verificaveis, versoes do planner/contexto,
fingerprint da SQL, duracao, erros e warnings. A SQL completa nao e incluida.

Quando aprovado, o grafo encerra esta fase com `final_status = processing` e
`current_stage = contract_gate`, preservando espaco para engine preflight em
fase futura. Rejeicoes encerram como `rejected`; erros internos seguem para o
finalizador de infraestrutura.
