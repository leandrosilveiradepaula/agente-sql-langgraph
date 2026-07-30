# SQL Analysis Contract

## Objetivo

`app/domain/sql_analysis.py` fornece uma analise SQL conservadora para fases
locais posteriores a geracao. O analisador nao executa SQL, nao acessa banco,
nao chama providers e nao tenta ser parser SQL completo.

## Escopo

O analisador cobre uma unica instrucao `SELECT` ou `WITH`, incluindo CTEs,
subqueries, `JOIN`, `UNION`, aliases, funcoes, `GROUP BY`, `ORDER BY`,
`HAVING`, `LIMIT`, strings, identificadores entre aspas e comentarios.

## Politica Conservadora

Strings e identificadores entre aspas sao tokenizados sem transformar palavras
internas em comandos. Comentarios sao descartados da analise logica e contados
sem expor seu conteudo. Ponto e virgula dentro de string nao separa statement.
Ponto e virgula entre comandos separa statements e gera erro.

Quando a estrutura nao pode ser classificada com seguranca, como parenteses nao
balanceados ou tokens desconhecidos, a analise falha. Os gates devem rejeitar ou
tratar como erro estruturado, nunca aprovar silenciosamente.

## Saida

`SqlStatementAnalysis` inclui fingerprint da SQL, tipo do statement, contagem
de statements, objetos, schemas, tabelas, aliases, CTEs, colunas, joins,
funcoes, flags de `LIMIT`, `SELECT *`, `table.*`, `SELECT INTO`, comentarios,
versao do analisador, erros e warnings. A SQL completa nao e armazenada.

## Limites

O analisador e intencionalmente parcial. Ele identifica estruturas necessarias
para Security e Contract Gate, mas nao substitui engine preflight, otimizador,
parser completo do banco ou validacao de permissao real.
