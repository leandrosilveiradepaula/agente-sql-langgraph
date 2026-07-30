# AGENTS.md

## Arquitetura

O LangGraph local carrega um `ContextSnapshot` canonico, resolve uma unica
intencao, constroi um `QueryPlan` deterministico e gera SQL por um
`SqlGenerator` injetado. Depois, o Security Gate valida read-only e
autorizacao estrutural, e o Contract Gate valida aderencia ao `QueryPlan`.
O planner usa somente o snapshot versionado ja validado; geracao e gates
consomem somente o `QueryPlan` e a SQL corrente.

## Comandos principais

- `python -m compileall app`
- `python testar_intent_resolver.py`
- `python testar_classify_intent.py`
- `python testar_planner.py`
- `python testar_build_plan.py`
- `python testar_sql_generation.py`
- `python testar_sql_analysis.py`
- `python testar_sql_security.py`
- `python testar_security_gate.py`
- `python testar_sql_contract.py`
- `python testar_contract_gate.py`
- `python testar_generate_sql.py`
- `python testar_grafo_base.py`
- `python scripts/check_all.py`

## Restricoes

Nao modificar workflows n8n, nao tocar PROD e nao executar scripts live com
escrita. Gemini, Watson, Supabase e outros servicos externos nao fazem parte do
planner.

## Hardcodes

Nao colocar termos de negocio, nomes reais de clientes, fabricantes, tabelas,
colunas ou exemplos de benchmark em regras Python. Decisoes devem vir do
`ContextSnapshot` e, depois do planejamento, do `QueryPlan`. Gates nao releem
o snapshot completo, nao executam SQL e nao corrigem SQL automaticamente.

## Testes

A suite local deve usar dados genericos. Scripts live ficam separados e so
podem ser usados em leitura quando necessario. `scripts/check_all.py` e a
regressao consolidada esperada antes de commit.
