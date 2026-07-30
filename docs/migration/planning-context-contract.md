# Planning Context Contract

## Objetivo

Esta fase adiciona planejamento deterministico e orientado pelo
`ContextSnapshot` versionado. O fluxo passa a construir um `QueryPlan`
autocontido depois da resolucao de intencao.

## Limites da fase

O planner nao gera SQL final, nao chama LLM, nao usa embeddings, nao acessa
PostgreSQL novamente e nao chama servicos externos. O campo legado
`sql_pattern` e preservado apenas como metadado de compatibilidade.

## Tipos

Os contratos ficam em `app/domain/planning.py`:

- `SelectedPattern`: copia canonica do query pattern escolhido.
- `PatternSelectionDiagnostic`: candidatos avaliados, metricas e razao.
- `PlanningContextProjection`: recorte do contexto necessario para as fases
  seguintes.
- `QueryPlan`: plano autocontido com versao do planner, versao/fingerprint do
  contexto, intencao, padrao selecionado, projecao e diagnostico.
- `PlanningBuildResult`: resultado estruturado de sucesso, rejeicao ou erro de
  contrato.

## Selecao do query_pattern

O resolvedor puro em `app/domain/planner.py` recebe intencao aplicada, pergunta
normalizada e os `query_patterns` do contexto. Para padroes da mesma intencao,
ele aplica a ordem abaixo:

1. exemplo igual apos normalizacao;
2. maior similaridade lexical deterministica;
3. maior cobertura de tokens do exemplo;
4. menor prioridade numerica configurada;
5. `pattern_name` como desempate estavel quando existe evidencia semantica.

Prioridade ausente e tratada como prioridade infinita. Numero menor representa
maior prioridade.

## Ambiguidades

Quando multiplos padroes ficam indistinguiveis sem evidencia semantica
suficiente e sem prioridade diferenciadora, o planner rejeita com
`PLANNING_PATTERN_AMBIGUOUS`. A decisao nao e arbitraria nem silenciosa.

## Regras

A projecao inclui regras listadas em `selected_pattern.required_rules` e regras
cujo `applies_to_intents` contem a intencao selecionada. Duplicatas sao
removidas e a ordem e deterministica por prioridade e nome.

## Tabelas

A projecao inclui somente tabelas exigidas por `required_tables` e existentes em
`table_catalog`. Referencias qualificadas usam `schema_name.table_name`;
referencias sem schema so sao aceitas quando nao ambiguas.

## Colunas

O planner preserva metadados do catalogo sem inventar colunas. `columns`
detalhadas continuam separadas de `key_columns`, `metric_columns` e
`date_columns`.

## Joins

`join_rules` das tabelas selecionadas sao preservadas. Quando o formato permite
identificar tabelas referenciadas, apenas joins entre tabelas selecionadas sao
mantidos. Quando o formato ainda e opaco, o payload original e preservado com
diagnostico.

## Entidades

Entidades operacionais sao projetadas quando referenciam a intencao, tabelas ou
colunas selecionadas. Entidades `intent_definition` sao excluidas porque ja
pertencem ao mecanismo de resolucao de intencao.

## DRE

Mapeamentos DRE so entram quando ha evidencia explicita em `sql_filter_hint`
apontando para a intencao, tabela ou coluna selecionada. Sem evidencia segura, a
lista fica vazia e o diagnostico registra `no_explicit_context_evidence`.

## Erros

Codigos estaveis:

- `PLANNING_INTENT_MISSING`
- `PLANNING_PATTERN_NOT_FOUND`
- `PLANNING_PATTERN_AMBIGUOUS`
- `PLANNING_REQUIRED_RULE_NOT_FOUND`
- `PLANNING_REQUIRED_TABLE_NOT_FOUND`
- `PLANNING_CONTEXT_INVALID`
- `PLANNING_UNEXPECTED_ERROR`

Rejeicoes semanticas terminam como `rejected`. Erros de contrato ou falhas
inesperadas seguem para `finalize_infrastructure_error`.

## Roteamento

Fluxo final:

`START -> receive_question -> load_context -> classify_intent -> build_plan -> END`

Depois de `classify_intent`, `processing` com intencao aplicada vai para
`build_plan`, `rejected` encerra e `infrastructure_error` segue ao finalizador.
Depois de `build_plan`, `processing` com `query_plan` encerra, `rejected`
encerra e `infrastructure_error` segue ao finalizador.

## Determinismo e imutabilidade

Todas as funcoes do planner sao puras, usam copias defensivas e ordenacao
estavel. O `ContextSnapshot` original nao e mutado.

## Compatibilidade

O campo `sql_pattern` permanece como `sql_pattern_metadata` no `QueryPlan`, mas
nao e contrato de SQL pronto para execucao.

## Proxima fase

A geracao SQL devera consumir o `QueryPlan` e sua `PlanningContextProjection`
sem reler o snapshot completo e sem inferir tabelas, colunas, joins ou regras
fora do contrato projetado.
