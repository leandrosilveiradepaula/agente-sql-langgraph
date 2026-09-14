# Delta de contexto DEMO para `planned_filters` v8

## Estado e fronteira

`semantic_context/demo_planned_filters_v8.delta.json` e uma proposta declarativa,
offline e auditavel. Ela parte de `v7-planned-metrics`, propoe
`v8-planned-filters` e nao substitui nem aplica automaticamente a versao atual.
Esta microetapa nao conecta banco, nao executa SQL e nao altera DEMO ou PROD.

Os aliases sao conhecimento de contexto. Cada `filter_concept` e semantic-only:
ele identifica o conceito percebido, mas nao carrega tabela, coluna, operador,
valor, escopo, caminho de join ou `binding_ref`. Esses campos pertencem
exclusivamente a um `filter_binding` fisico, versionado e completo.

## Decisao semantica de Receita

A evidencia DEMO sustenta o conceito canonico `dre_receita`, com aliases somente
`receita` e `receitas`. Ela nao comprova que o grupo `Receita` seja equivalente a
"receita operacional liquida"; portanto esse termo nao e alias do conceito e
nenhuma formula de ROL, lucro, margem ou composicao foi criada.

O manifesto read-only
`semantic_context/evidence/demo_revenue_filter_binding_v1.json` registra a
convergencia entre catalogo versionado, schema fisico e valor observado. Com essa
evidencia, `demo-dre-receita-v1` liga separadamente `dre_receita` a
`demo_lakehouse.gold_plano_contas.grupo_contabil = 'Receita'`, no escopo de linha,
e declara o join desde `demo_lakehouse.gold_lancamentos_contabeis` por `nk_conta`.
O `planned_filter` continua sendo apenas a obrigacao semantica; o binding fisico e
resolvido por `binding_ref` e nao deriva de `sql_filter_hint`.

## Evidencia e GAPs remanescentes

`DEMO-PF-001` fica resolvido somente para Receita. `DEMO-PF-002` mantem
`dre_custos` em **BLOCKING_FAIL_CLOSED**, pois a evidencia de CMV nao prova o
escopo da palavra generica "custos". `DEMO-PF-003` mantem
`dre_despesas_operacionais` em **BLOCKING_FAIL_CLOSED**, pois o conceito cobre
multiplos grupos e o contrato simples atual nao deve ser estendido ad hoc.

`sql_filter_hint` e `nivel_1_bi` permanecem **TRANSITIONAL**, apenas no inventario
de migracao. Nenhum deles e contrato final. Como ainda existem GAPs bloqueantes,
a ativacao integral do pacote permanece desabilitada.

## Validacao offline

1. Validar sintaxe JSON, contrato, provenance read-only e ausencia de aplicacao
   automatica.
2. Confirmar `dre_receita` e seus dois aliases exatos, sem equivalencia silenciosa
   com receita operacional liquida.
3. Confirmar a separacao entre conceito semantic-only e o binding fisico completo
   `demo-dre-receita-v1`.
4. Confirmar join estruturado por `nk_conta` e que campos TRANSITIONAL nao entram
   no binding.
5. Confirmar custos e opex sem binding e fail-closed.
6. Executar as regressoes de planner, generator e Contract Gate, que validam o
   contrato generico com dados sinteticos, sem criar comportamento DEMO no motor.

Comandos locais relevantes:

```text
python -m json.tool semantic_context/demo_planned_filters_v8.delta.json
python -m json.tool semantic_context/evidence/demo_revenue_filter_binding_v1.json
python testar_demo_planned_filters_context.py
python testar_context_normalizer.py
python testar_context_validator.py
python testar_planner.py
python testar_sql_generation.py
python testar_sql_contract.py
python testar_contract_gate.py
python testar_planned_filters_e2e.py
python scripts/check_hardcodes.py
python scripts/check_all.py
```

## Rollback conceitual

Se uma ativacao futura for formalmente autorizada e precisar ser revertida,
restaurar `SEMANTIC_AGENT_VERSION` para `v7-planned-metrics`. O rollback nao
remove dados e nao autoriza deploy ou alteracao de ambiente nesta microetapa.

## Inventario de hardcodes

- **STRUCTURAL:** formato e versionamento do delta, provenance, GAPs, rollback e o
  binding DEMO integral sustentado por evidencia read-only no contexto versionado.
- **TRANSITIONAL:** `sql_filter_hint` e `nivel_1_bi`, somente como evidencia
  historica para inventario e nunca como contrato de binding.
- **FORBIDDEN:** nenhum no motor; nao ha pergunta para SQL, benchmark/golden,
  branch especial de Receita, equivalencia com ROL ou binding especulativo de
  custos/opex.

## Anti-overfitting

Isso melhora a capacidade geral ou apenas faz um caso especifico passar?
Melhora a capacidade geral: o motor permanece generico e Receita funciona porque
o contexto versionado fornece, separadamente, uma obrigacao semantica e um binding
fisico auditavel. Nenhum comportamento do motor foi alterado para uma frase ou
conceito financeiro especifico.
