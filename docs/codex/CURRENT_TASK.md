# CURRENT TASK — planned_filters microetapa 6

## Objetivo

Resolver de forma auditavel e ainda sem deploy a parte comprovavel do GAP `DEMO-PF-001`, reconciliando o delta `v8-planned-filters` com evidencia real obtida por leitura somente do ambiente DEMO e com o contrato generico de `planned_filters` ja validado.

A microetapa 5 esta concluida e mergeada. O artefato `semantic_context/demo_planned_filters_v8.delta.json` existe, mas manteve `filter_bindings` vazio por falta de evidencia fisica suficiente no repositorio.

Nesta microetapa, a evidencia faltante para o conceito de Receita foi coletada por inspeção somente leitura do projeto Supabase `Demo`. Nenhuma escrita, migration ou deploy foi executado.

## Evidencia confirmada por leitura somente

### Contexto semantico DEMO atual

Versao ativa observada: `demo-finance-v1`.

`semantic_context.ai_ducklake_entity_aliases` contem:
- `entity_type = dre_group`
- `user_term = Receita`
- `canonical_value = Receita`
- `target_table = gold_plano_contas`
- `target_column = grupo_contabil`
- `sql_filter_hint = grupo_contabil = 'Receita'`

`semantic_context.ai_ducklake_dre_mapping` contem para Receita:
- `dre_code = RECEITA`
- `nivel_1_bi = Receita`
- `category = revenue`
- `is_revenue = true`
- `sql_filter_hint = grupo_contabil = 'Receita'`

IMPORTANTE: `sql_filter_hint` continua sendo apenas evidencia TRANSITIONAL. Ele nao deve ser copiado como contrato final nem consumido pelo motor.

### Catalogo versionado DEMO

`semantic_context.ai_ducklake_table_catalog` confirma:
- `demo_lakehouse.gold_lancamentos_contabeis` como fonte principal de realizado;
- metrica `valor`;
- chave `nk_conta`;
- join versionado de `gold_lancamentos_contabeis.nk_conta` para `gold_plano_contas.nk_conta`;
- `demo_lakehouse.gold_plano_contas` como tabela de classificacao por grupo contabil.

### Schema fisico DEMO

Leitura de `information_schema.columns` confirmou:
- `demo_lakehouse.gold_lancamentos_contabeis.nk_conta` existe;
- `demo_lakehouse.gold_lancamentos_contabeis.valor` existe;
- `demo_lakehouse.gold_plano_contas.nk_conta` existe;
- `demo_lakehouse.gold_plano_contas.grupo_contabil` existe.

Leitura de dados confirmou que `gold_plano_contas.grupo_contabil` possui o valor exato `Receita`, e que existem lancamentos associados via `nk_conta`.

## Decisao semantica obrigatoria

Nao promover o conceito atual `dre_receita_operacional_liquida` como equivalente a `Receita`. A evidencia DEMO confirma o grupo `Receita`, mas nao comprova que ele represente "receita operacional liquida". Misturar esses conceitos seria um erro semantico.

Portanto:
- criar/ajustar um conceito canonico de filtro para Receita compatível com a evidencia real, por exemplo `dre_receita`;
- aliases devem representar somente termos semanticamente sustentados pela evidencia, como `receita` e `receitas`;
- nao usar `receita operacional liquida` como alias de `dre_receita` sem evidencia adicional;
- nao criar formula de ROL, lucro, margem ou composicao Receita - Deducoes nesta microetapa.

## Binding fisico permitido para Receita

A microetapa pode criar um `filter_binding` versionado para o conceito de Receita porque agora ha evidencia independente e convergente para todos os elementos necessarios.

O binding deve ser expresso no formato generico ja suportado pelo motor e deve representar, sem depender de `sql_filter_hint`:
- conceito semantico: Receita;
- tabela de classificacao: `demo_lakehouse.gold_plano_contas`;
- coluna: `grupo_contabil`;
- operador estrutural: `=`;
- valor: `Receita`;
- scope compativel com filtro de linha/WHERE;
- join path estruturado a partir da fonte de realizado `demo_lakehouse.gold_lancamentos_contabeis` via `nk_conta` para `demo_lakehouse.gold_plano_contas.nk_conta`.

Usar `binding_ref` estavel e versionado. O `planned_filter` deve continuar semantic-only e nunca carregar tabela/coluna/operador/valor/join_path.

## Conceitos ainda nao resolvidos

Nao inventar bindings para `dre_custos` ou `dre_despesas_operacionais` nesta microetapa.

Motivos:
- `category = cost` aparece associado a CMV, mas a palavra generica "custos" pode ter escopo semantico mais amplo; nao assumir equivalencia sem regra versionada explicita;
- `category = opex` cobre multiplos grupos (`Despesas Comerciais`, `Marketing`, `Logistica`, `Pessoal`, `Administrativas`, `Tecnologia`, `Outras Despesas Operacionais`), enquanto o contrato atual de filtro simples nao deve ser estendido ad hoc para satisfazer este caso.

Atualizar o inventario de GAPs para refletir que Receita possui evidencia suficiente e que os demais conceitos continuam fail-closed. Pode preservar `DEMO-PF-001` com escopo refinado ou criar GAPs derivados, desde que a rastreabilidade fique explicita.

## Regra de ouro

Migrar conhecimento para contexto/configuracao versionada, nao para Python/TypeScript.

Nenhuma regra de Receita, DRE, tabela, coluna ou valor pode virar `if`, constante de negocio, threshold ou excecao no motor.

## Escopo permitido

- atualizar `semantic_context/demo_planned_filters_v8.delta.json`;
- atualizar documentacao da migracao/contexto;
- adicionar um manifesto de evidencia versionado no repositorio, se util;
- ajustar testes offline especificos do artefato DEMO;
- ajustes estruturais minimos de loader/validator somente se uma incompatibilidade generica real do contrato for comprovada.

## Escopo proibido

- qualquer escrita no Supabase;
- executar migration;
- alterar n8n;
- alterar Watson;
- alterar PROD;
- deploy/cutover;
- mudar `real_sql_execution`;
- alterar credenciais/permissoes;
- usar benchmark/golden/expected SQL como fonte de comportamento;
- criar pergunta -> SQL;
- criar SQL especial para Receita;
- adicionar `if receita`, `if custo`, `if despesa` ou equivalente no motor;
- promover `sql_filter_hint` a contrato final;
- resolver custos/opex por suposicao.

## Validacao offline obrigatoria

Cobrir no minimo:
1. conceito Receita resolve semanticamente para `planned_filter` com `binding_ref` e sem detalhes fisicos;
2. `binding_ref` resolve separadamente para um unico `resolved_filter_binding` completo;
3. generator recebe obrigacao semantica e binding fisico separados;
4. SQL sintetica estruturalmente equivalente ao binding passa Contract Gate;
5. SQL sem filtro Receita falha Contract Gate;
6. coluna, operador ou valor divergente falham;
7. join/path incoerente ou binding incompleto falham fechado;
8. duas formulacoes semanticamente equivalentes de Receita chegam ao mesmo conceito quando configuradas;
9. termos nao sustentados, como `receita operacional liquida`, nao devem ser silenciosamente tratados como Receita apenas para fazer teste passar;
10. conceitos de custos/opex permanecem sem binding e fail-closed;
11. nenhum `sql_filter_hint` e consumido como contrato final;
12. nenhum benchmark/golden/expected SQL entra no request;
13. nenhum hardcode FORBIDDEN entra no motor;
14. regressao das microetapas 1-5 permanece verde.

Executar os testes afetados, `python scripts/check_hardcodes.py`, `git diff --check` e `PYTHONDONTWRITEBYTECODE=1 python scripts/check_all.py`.

Se o `check_all.py` parar apenas no bloqueio Windows preexistente por ausencia de `SystemRoot`/`cmd.exe`, reportar sem alterar esse teste. Merge continua dependendo do `Offline validation` do GitHub Actions no HEAD remoto.

## Hardcode inventory

Classificar tudo encontrado/adicionado como STRUCTURAL, TRANSITIONAL ou FORBIDDEN.

Conhecimento financeiro DEMO e permitido apenas no artefato de contexto/evidence versionado e em testes especificos desse artefato. Nenhum FORBIDDEN pode entrar no motor.

## Anti-overfitting

Responder explicitamente:
"Isso melhora a capacidade geral ou apenas faz um caso especifico passar?"

A resposta aceitavel deve demonstrar que o motor continua generico e que Receita funciona porque o contexto versionado fornece uma obrigacao e um binding, nao porque existe logica especial para a palavra.

## Publicacao

Ao concluir:
- tente publicar branch/PR;
- se o workspace nao puder publicar, inclua NA MESMA EXECUCAO o unified diff completo de todos os arquivos alterados em comentario visivel da Issue;
- nao use `make_pr` como unico destino do patch se nao houver PR remoto;
- reporte `base_sha`, `local_commit_sha`, `publication_status`, `remote_branch`, `remote_head_sha`, `pr_number`, arquivos, testes, hardcode inventory e gaps;
- nao peca ao usuario para transportar comandos, patches, SHAs ou logs.

## Commit sugerido

`feat: add evidence-backed demo revenue filter binding`

## Merge

Codex nao faz merge. O ChatGPT/revisor tecnico pode revisar e mergear conforme `docs/codex/MERGE_POLICY.md` se todos os gates passarem.

## Deploy / ambientes externos

Nao autorizado.

Esta microetapa termina com contexto e binding de Receita preparados e testados na `main`, mas sem aplicar o delta ao Supabase e sem alterar o runtime DEMO.