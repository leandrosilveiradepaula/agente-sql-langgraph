# SQL Security Gate

## Objetivo

`app/domain/sql_security.py` valida seguranca e autorizacao estrutural da
`current_sql` usando somente `QueryPlan` e `SqlStatementAnalysis`.

## Responsabilidade

O gate aprova apenas SQL de leitura com um statement, iniciando em `SELECT` ou
`WITH` seguido de `SELECT`. Ele rejeita comandos de escrita, DDL, comandos de
sessao, chamadas administrativas detectaveis, `SELECT INTO`, multiplos
statements, schemas nao autorizados, tabelas nao planejadas e referencias sem
schema ambiguas.

## Autorizacao

Schemas e tabelas autorizadas sao derivados de
`query_plan.planning_context.allowed_schemas` e
`query_plan.planning_context.required_tables`. CTEs nao sao tratadas como
tabelas fisicas. Subqueries sao analisadas por dentro para evitar que objetos
externos fiquem escondidos.

## Resultado

`SqlSecurityResult` retorna `approved`, `rejected` ou `error`, checks,
findings, objetos detectados, schemas, tabelas, statement count, statement type,
versao do gate, versao do analisador, fingerprint da SQL, duracao, erros e
warnings. A SQL completa nao e incluida.

## Roteamento

Quando aprovado, o grafo segue para `contract_gate` mantendo
`final_status = processing`. Quando rejeitado, encerra como `rejected`. Erros de
contrato interno ou excecoes inesperadas seguem para o finalizador de
infraestrutura.
