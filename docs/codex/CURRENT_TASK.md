# CURRENT TASK — planned_filters microetapa 7

## Objetivo

Implementar suporte generico, offline e fail-closed a `filter_binding` multi-valor sem adicionar conhecimento de negocio ao motor.

Issue: #17

## Contrato autorizado

- operador estrutural `IN`;
- `value` deve ser uma lista nao vazia;
- todos os itens da lista devem ser literais simples suportados e do mesmo tipo:
  string, number ou boolean;
- planner e generator preservam a separacao entre obrigacao semantica e binding fisico;
- SQL analyzer reconhece somente `IN (...)` literal simples;
- Contract Gate deve comprovar tabela, coluna, operador e conjunto de valores esperado;
- ordem da lista nao deve alterar equivalencia;
- duplicatas devem ser rejeitadas no binding ou normalizadas de forma deterministica na SQL sem enfraquecer o contrato;
- subquery em `IN`, expressoes, funcoes e `OR` continuam fail-closed.

## Compatibilidade obrigatoria

Bindings escalares existentes com `=`, `<>`, `<`, `<=`, `>` e `>=` devem continuar funcionando sem alteracao semantica.

## Escopo permitido

- `app/domain/sql_analysis.py`;
- `app/domain/sql_contract.py`;
- `app/domain/sql_generation.py`;
- `app/domain/planner.py` e tipos de planning somente se necessario para contrato generico;
- testes offline afetados;
- documentacao da microetapa.

## Fora de escopo

- criar binding para `dre_despesas_operacionais`;
- decidir que `dre_custos` equivale a CMV;
- aplicar ou ativar `semantic_context/demo_planned_filters_v8.delta.json`;
- alterar Supabase, n8n, Watson, PROD, deploy ou cutover;
- executar SQL real;
- executar benchmark de 63 perguntas;
- usar golden answers, expected SQL ou `sql_filter_hint` como fonte de comportamento;
- criar qualquer `if` de DRE, Receita, CMV, custos, despesas ou cliente.

## Validacao obrigatoria

1. analyzer reconhece `col IN ('a','b')` como predicado verificavel;
2. analyzer rejeita `IN (SELECT ...)`, funcoes e expressoes;
3. binding `IN` exige lista nao vazia, homogenea e sem valores nulos;
4. Contract Gate aprova mesma colecao independentemente da ordem;
5. Contract Gate rejeita valor ausente, adicional, tipo divergente e operador divergente;
6. bindings escalares anteriores permanecem verdes;
7. `OR` permanece unverifiable/fail-closed;
8. generator recebe a colecao sem conhecimento especifico de negocio;
9. nenhum benchmark/golden/expected SQL entra no request;
10. `python scripts/check_all.py` deve permanecer offline e verde.

## Hardcode inventory

Toda mudanca deve ser classificada como STRUCTURAL. Nenhum hardcode FORBIDDEN pode entrar no motor.

## Publicacao

Commit e PR estao autorizados para esta microetapa. Merge pode ser realizado pelo ChatGPT/revisor quando CI e gates estiverem verdes, conforme a autorizacao permanente do usuario para merges no projeto.

## Deploy / ambientes externos

Nao autorizado. Esta microetapa termina em codigo/testes/documentacao offline.
