# CURRENT TASK — planned_filters microetapa 5

## Objetivo

Preparar, somente no repositorio e sem aplicar em ambiente externo, o delta de contexto semantico versionado necessario para o ambiente DEMO usar `planned_filters` de forma real, partindo do motor ja validado nas microetapas 1-4.

A microetapa 4 esta concluida e mergeada. O motor ja prova offline o caminho:

`contexto semantico -> evidence -> planner -> planned_filters/resolved_filter_bindings -> generator -> Contract Gate`.

O proximo risco nao e mais de motor; e de contexto. O runtime DEMO precisa ter conceitos e bindings versionados compativeis com esse contrato. Esta tarefa deve preparar esse contexto sem executar SQL em Supabase, sem alterar DEMO real e sem deploy.

## Regra de ouro

Migrar conhecimento para contexto/configuracao versionada, nao para Python/TypeScript.

Nenhuma regra de negocio desta microetapa pode virar `if`, constante, threshold, tabela/coluna ou SQL especial no motor.

## Premissas obrigatorias

- Nao criar pergunta -> SQL.
- Nao criar resposta pronta.
- Nao usar benchmark/golden/expected SQL como fonte de comportamento.
- `business_question_examples` continuam apenas sinais auxiliares.
- `planned_filter` permanece semantic-only.
- detalhes fisicos ficam somente em `filter_binding` versionado.
- `sql_filter_hint` pode ser lido apenas como evidencia TRANSITIONAL para inventario/migracao; nunca como contrato final do motor.
- nenhuma informacao fisica deve ser inventada se nao houver evidencia versionada suficiente.
- se um binding nao puder ser derivado com seguranca, registrar GAP/fail-closed em vez de criar valor por suposicao.
- conhecimento de negocio DEMO e permitido somente em artefato de contexto/configuracao versionada, nunca no codigo do motor.

## Fonte de verdade permitida

Usar apenas artefatos ja existentes no repositorio e documentacao versionada disponivel nele para inferir o delta.

Nao consultar nem modificar Supabase, n8n, Watson, PROD, credenciais ou qualquer ambiente externo nesta microetapa.

Se os artefatos do repositorio nao contiverem informacao suficiente para um binding fisico seguro, produzir explicitamente uma lacuna a ser confirmada antes de qualquer futura aplicacao.

## Entrega esperada

Criar um pacote declarativo e auditavel de contexto DEMO, preferencialmente em arquivo novo dedicado, contendo:

1. versao de contexto alvo proposta, sem substituir silenciosamente a versao atual;
2. entidades `filter_concept` necessarias para categorias/conceitos financeiros ja existentes no contexto DEMO documentado;
3. entidades `filter_binding` somente quando tabela, coluna, operador, valor, scope e join_path puderem ser sustentados por evidencia versionada;
4. provenance/source para cada item;
5. inventario de itens TRANSITIONAL reaproveitados apenas como pista de migracao;
6. lista de gaps nao resolvidos;
7. procedimento de validacao offline do pacote contra normalizer/validator/planner/generator/Contract Gate;
8. rollback conceitual: trocar `SEMANTIC_AGENT_VERSION` de volta para a versao anterior, sem apagar dados.

O artefato pode ser JSON, YAML, SQL declarativo nao aplicado ou formato equivalente ja coerente com o repositorio. Nao criar script que se conecte automaticamente a banco.

## Escopo permitido

- novos artefatos declarativos de contexto/configuracao DEMO;
- documentacao de migracao/validacao;
- fixtures e testes offline que carreguem esse artefato;
- ajustes minimos e estruturais no loader/validator apenas se houver incompatibilidade generica comprovada.

Nao alterar comportamento de planner, generator ou Contract Gate para acomodar um caso de negocio.

## Escopo proibido

- executar migrations;
- conectar Supabase;
- alterar n8n;
- alterar Watson;
- alterar PROD;
- deploy/cutover;
- mudar `real_sql_execution`;
- alterar credenciais/permissoes;
- modificar benchmark para fazer teste passar;
- codificar Receita, Custo, Despesa, DRE, conta, marca, centro de custo, unidade ou qualquer outra regra de negocio no motor.

## Validacao offline obrigatoria

O pacote deve ser validado sem rede e sem banco externo.

Cobrir no minimo:

1. normalizacao e validacao do snapshot/fixture;
2. `filter_concept` resolve para `planned_filter` sem detalhes fisicos;
3. `binding_ref` resolve para `resolved_filter_binding` separado;
4. generator recebe obrigacao e binding separados;
5. SQL sintetica equivalente ao binding passa Contract Gate;
6. SQL sem filtro obrigatorio falha;
7. binding ausente/ambiguo/invalido permanece fail-closed;
8. duas formulacoes semanticamente equivalentes chegam ao mesmo conceito quando configuradas assim;
9. nenhum benchmark/golden/expected SQL entra no request;
10. nenhum `sql_filter_hint` e consumido como contrato final;
11. nenhum hardcode FORBIDDEN novo no motor;
12. regressao das microetapas 1-4 permanece verde.

Executar:
- `python -m compileall app`;
- testes de contexto afetados;
- `python testar_planner.py`;
- `python testar_sql_generation.py`;
- `python testar_sql_contract.py`;
- `python testar_contract_gate.py`;
- `python testar_planned_filters_e2e.py`;
- novos testes do pacote DEMO, se criados;
- `git diff --check`;
- `python scripts/check_hardcodes.py`;
- `PYTHONDONTWRITEBYTECODE=1 python scripts/check_all.py`.

Se `check_all.py` parar apenas no bloqueio Windows preexistente por ausencia de `SystemRoot`/`cmd.exe`, reportar sem alterar esse teste. Merge continua dependendo do `Offline validation` no GitHub Actions no HEAD remoto.

## Hardcode inventory

Classificar tudo encontrado/adicionado como:
- STRUCTURAL;
- TRANSITIONAL;
- FORBIDDEN.

Nesta microetapa, conhecimento financeiro especifico pode existir somente no artefato de contexto/configuracao versionada. Nenhum FORBIDDEN pode ser introduzido no codigo do motor.

## Anti-overfitting

Responder explicitamente antes de concluir:
"Isso melhora a capacidade geral ou apenas faz um caso especifico passar?"

A entrega deve demonstrar que o mecanismo continua generico e que a mudanca e de contexto, nao de logica especial por pergunta.

## Publicacao

Ao concluir:
- tente publicar branch/PR;
- se o workspace nao puder publicar, inclua NA MESMA EXECUCAO o unified diff completo de todos os arquivos alterados;
- reporte `base_sha`, `local_commit_sha`, `publication_status`, `remote_branch`, `remote_head_sha`, `pr_number`, `publication_blocker`;
- nao peca ao usuario para copiar patch, SHA, log ou comando.

## Commit sugerido

`feat: prepare versioned demo filter context`

## Merge

Codex nao faz merge. O ChatGPT/revisor tecnico pode revisar e mergear conforme `docs/codex/MERGE_POLICY.md` se todos os gates passarem.

## Deploy / ambientes externos

Nao autorizado.

Esta microetapa termina com artefato versionado e testes na `main`, sem aplicar nada em Supabase, n8n, Watson, DEMO real, PROD ou qualquer ambiente externo.
