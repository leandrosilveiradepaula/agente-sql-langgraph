# CURRENT TASK — dre_custos CMV-only microetapa 8

## Decisão humana

A AI Product Factory registrou em 2026-10-01 uma decisão humana explícita aprovando:

`dre_custos = CMV-only` neste contexto versionado.

- Gate: `59f6db12-8dfa-4ea0-8202-063a3dfa8ca7`
- Resolução: `approved`
- Benchmark de 63 perguntas: não executado
- Deploy/cutover: não autorizado
- n8n: continua caminho oficial
- LangGraph: continua offline shadow

## Escopo desta microetapa

Versionar o binding offline de `dre_custos` usando somente a evidência read-only já existente:

- target: `demo_lakehouse.gold_plano_contas.grupo_contabil`
- operador: `=`
- valor: `CMV`
- join: `gold_lancamentos_contabeis.nk_conta = gold_plano_contas.nk_conta`
- binding ref: `demo-dre-custos-v1`

A decisão promove `custo` e `custos` somente dentro do conceito `dre_custos` versionado. Não promove `gasto/gastos`, `custo operacional` nem `custo de vendas`.

## Guardrails

- `automatic_apply=false`
- `activation.allowed=false`
- sem alteração Supabase
- sem alteração n8n
- sem Watson real
- sem execução SQL real
- sem benchmark
- sem hardcode de pergunta/expected SQL/golden answer
- `sql_filter_hint` e `nivel_1_bi` continuam apenas evidência transitória, nunca contrato

## Validação requerida

- `python scripts/check_all.py`
- `Offline validation`
- Contract Gate deve aprovar CMV correto e rejeitar filtro ausente/divergente
- `dre_despesas_operacionais` deve continuar fail-closed

## Estado

Implementação em PR da issue #20. Nenhuma ativação é autorizada por esta microetapa.
