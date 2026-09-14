# CURRENT TASK — planned_filters microetapa 6 encerrada

## Estado final

A microetapa 6 de `planned_filters` esta concluida, publicada e mergeada na
`main`.

- PR: `#12`
- Merge commit em `main`: `ff800c8bd3fae462e10dabf52c8e09e0816f730c`
- CI pos-merge: `Offline validation` verde
- Deploy: nao autorizado e nao executado
- Supabase: nao alterado
- n8n: nao alterado
- Delta v8: nao aplicado

## Resultado entregue

O fluxo offline de `planned_filters` ficou completo para a parte comprovada da
microetapa:

- planner detecta obrigacoes semanticas em `planned_filters`;
- planner resolve `resolved_filter_bindings` separadamente por `binding_ref`;
- generator recebe obrigacao semantica e binding fisico como estruturas
  separadas;
- Contract Gate valida filtros obrigatorios;
- Contract Gate comprova `filter_binding.join_path` de forma estrutural;
- `join_path` valida tabela, coluna e operador de cada passo;
- aliases SQL sao resolvidos;
- comparacoes invertidas sao aceitas;
- comparacoes de `JOIN ... ON` distintos permanecem isoladas;
- ausencia de `join_path` ou `[]` preserva compatibilidade;
- ausencia de `planned_filters` preserva compatibilidade.

Nenhuma regra especifica de Receita, DRE, DEMO, tabela, coluna, pergunta,
benchmark ou cliente foi adicionada ao motor.

## Contexto DEMO v8

`semantic_context/demo_planned_filters_v8.delta.json` permanece como proposta
declarativa, offline e auditavel.

- `automatic_apply`: `false`
- `activation.allowed`: `false`
- contexto ativo DEMO nao foi alterado por esta tarefa;
- nenhuma migration foi executada;
- nenhuma escrita externa foi executada;
- nenhum deploy ou cutover foi autorizado.

O conceito `dre_receita` possui binding fisico evidenciado por manifesto
read-only:

- `binding_ref`: `demo-dre-receita-v1`
- tabela alvo: `demo_lakehouse.gold_plano_contas`
- coluna alvo: `grupo_contabil`
- operador: `=`
- valor: `Receita`
- `join_path`: de `demo_lakehouse.gold_lancamentos_contabeis.nk_conta` para
  `demo_lakehouse.gold_plano_contas.nk_conta`

`Receita` nao foi promovida a "receita operacional liquida". Lucro, margem,
ROL e conceitos derivados continuam sem modelagem ou evidencia suficiente.

## Gaps ainda bloqueados

`dre_custos` permanece `BLOCKING_FAIL_CLOSED`.

Motivo: a evidencia TRANSITIONAL associada a CMV/cost nao prova o escopo
semantico da palavra generica "custos" nem fornece binding fisico completo.

`dre_despesas_operacionais` permanece `BLOCKING_FAIL_CLOSED`.

Motivo: o conceito cobre multiplos grupos e o contrato atual de filtro simples
nao deve ser estendido ad hoc para satisfazer esse caso.

## Dividas TRANSITIONAL

- `sql_filter_hint` permanece somente como inventario/evidencia historica; seu
  uso como contrato de binding continua proibido.
- `nivel_1_bi` permanece somente como evidencia historica; seu uso como
  inferencia automatica de coluna alvo continua proibido.
- `dre_custos` e `dre_despesas_operacionais` ainda dependem de decisao
  versionada e evidencia adicional antes de qualquer binding.

## Proxima decisao pendente

Nao ha microetapa tecnica nova autorizada neste arquivo.

A proxima decisao deve escolher explicitamente entre:

A. microetapa de evidencia/versionamento para `dre_custos`;

B. desenho generico de suporte a filtros multi-grupo para
`dre_despesas_operacionais`.

Ambas permanecem sem ativacao, deploy, Supabase ou cutover ate decisao
explicita.

## Principios preservados

- codigo conhece processo;
- contexto versionado contem conhecimento de negocio;
- sem `if` de Receita, custo ou opex no motor;
- benchmark, golden answer e expected SQL nao influenciam geracao;
- n8n continua estrategico e oficial;
- LangGraph permanece shadow/offline;
- nao ha cutover implicito.

## Fora de escopo ate nova autorizacao

- aplicar delta v8;
- alterar Supabase;
- executar migrations;
- alterar n8n;
- fazer deploy;
- ativar runtime DEMO;
- iniciar microetapa 7;
- criar binding para custos, despesas operacionais, lucro, margem ou ROL por
  suposicao.
