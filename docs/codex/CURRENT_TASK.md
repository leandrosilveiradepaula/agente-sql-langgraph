# CURRENT TASK — dre_custos CMV-only microetapa 8

## Decisão registrada

Em 2026-10-01 a AI Product Factory registrou decisão humana explícita de que `dre_custos` representa CMV-only neste contexto versionado.

- Gate: `59f6db12-8dfa-4ea0-8202-063a3dfa8ca7`
- Resolução: `approved`
- Benchmark de 63 perguntas: não executado
- Deploy/cutover: fora de escopo
- n8n: caminho oficial
- LangGraph: offline shadow

## Escopo

Versionar o binding offline:
- tabela: `demo_lakehouse.gold_plano_contas`
- coluna: `grupo_contabil`
- operador: `=`
- valor: `CMV`
- join: `gold_lancamentos_contabeis.nk_conta = gold_plano_contas.nk_conta`
- binding ref: `demo-dre-custos-v1`

`custo` e `custos` ficam cobertos apenas por este conceito versionado. `gasto/gastos`, `custo operacional` e `custo de vendas` não são promovidos implicitamente.

## Guardrails

- `automatic_apply=false`
- `activation.allowed=false`
- sem mudança Supabase/n8n/Watson
- sem SQL real
- sem benchmark
- sem expected SQL/golden answer
- `sql_filter_hint` e `nivel_1_bi` não viram contrato

## Validação

- `python scripts/check_all.py`
- `Offline validation`
- Contract Gate aprova CMV correto e rejeita filtro ausente/divergente
- `dre_despesas_operacionais` permanece fail-closed

## Estado

Implementação vinculada à issue #20. Esta microetapa não ativa runtime.
