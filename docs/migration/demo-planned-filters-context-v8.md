# Delta de contexto DEMO para `planned_filters` v8

## Estado e fronteira

`semantic_context/demo_planned_filters_v8.delta.json` e uma proposta declarativa,
offline e auditavel. Ela parte de `v7-planned-metrics`, propoe
`v8-planned-filters` e nao substitui nem aplica automaticamente a versao atual.
Esta microetapa nao conecta banco, nao executa SQL e nao altera DEMO ou PROD.

Os aliases sao conhecimento de contexto. Cada `filter_concept` e semantic-only:
ele identifica o conceito percebido, mas nao carrega tabela, coluna, operador,
valor, escopo ou caminho de join. Esses campos pertencem exclusivamente a um
`filter_binding` fisico, versionado e completo.

## Evidencia e GAP

As migrations versionadas existentes documentam categorias e aliases, mas nao
fornecem evidencia suficiente, conjunta e inequívoca para todos os campos de um
binding fisico. Por isso, `filter_bindings` permanece vazio. `sql_filter_hint` e
o metadado historico `nivel_1_bi` ficam classificados como **TRANSITIONAL** e
servem apenas ao inventario de migracao; nenhum deles e contrato final.

`DEMO-PF-001` e **BLOCKING_FAIL_CLOSED**. Enquanto ele estiver aberto, os
conceitos deste pacote nao podem ser ativados nem produzir `planned_filters` no
runtime. Uma aplicacao futura exige evidencia versionada e auditavel de tabela,
coluna, operador, valor, escopo e `join_path`, sem inferencia por SQL historica.

## Validacao offline

1. Validar sintaxe JSON e o contrato do pacote.
2. Confirmar que origem e alvo sao versoes distintas e que `automatic_apply` e
   falso.
3. Confirmar aliases semantic-only, provenance e ausencia de campos fisicos.
4. Confirmar `filter_bindings` vazio e o GAP bloqueante.
5. Executar os testes de normalizer, validator, planner, generator e Contract
   Gate. Os testes sinteticos das microetapas anteriores continuam demonstrando
   o fluxo completo quando um binding valido e injetado.
6. Nao usar benchmark, golden answer, expected SQL ou `sql_filter_hint` como
   entrada do generator.

Comandos locais relevantes:

```text
python -m json.tool semantic_context/demo_planned_filters_v8.delta.json
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

- **STRUCTURAL:** formato do delta, versoes, provenance, GAP, validacao e rollback.
- **TRANSITIONAL:** `sql_filter_hint` e `nivel_1_bi`, somente como evidencia
  historica para inventario.
- **FORBIDDEN:** nenhum no motor; termos financeiros permanecem no contexto
  declarativo, e nenhum binding incompleto foi promovido.

## Anti-overfitting

Isso melhora a capacidade geral ou apenas faz um caso especifico passar?
Melhora a preparacao geral do contexto: o motor permanece generico, sem
pergunta para SQL, condicional por frase, benchmark, golden answer ou SQL
especial. O pacote explicita a mesma fronteira semantic-only/fisica para todos
os conceitos e falha fechado quando a evidencia nao basta.
