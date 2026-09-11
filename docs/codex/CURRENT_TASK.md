# CURRENT TASK — planned_filters microetapa 1

## Objetivo

Implementar somente a primeira microetapa de `planned_filters` no planner, mantendo a arquitetura atual e sem tocar generator, Contract Gate, Supabase, n8n ou deploy.

## Escopo permitido

Alterar apenas o necessario em:
- `app/domain/planning.py`
- `app/domain/planner.py`
- testes sintéticos relacionados ao planner

Nao alterar generator, Contract Gate, adapters, Supabase, migrations, n8n ou qualquer ambiente externo.

## Contrato esperado

`planned_filter` representa somente a obrigacao semantica e deve referenciar `binding_ref`.

Preferir os campos:
- `filter_ref`
- `filter_concept`
- `binding_ref`
- `required`
- `scope`
- `detection_source`
- `mapping_source`
- `matched_user_term`
- `provenance`

Os detalhes fisicos permanecem exclusivamente no binding estruturado:
- `target_table`
- `target_column`
- `operator`
- `value`
- `join_path`

`planned_filter` nao deve carregar esses detalhes fisicos.

## Resolucao esperada

Fluxo geral:

semantic evidence
-> canonical concept
-> structured/versioned filter binding
-> planned_filter obligation

A resolucao deve ser generica e orientada por contexto. Nao usar `if` por termo, pergunta, categoria ou benchmark.

Nao usar `sql_filter_hint` como contrato final de `planned_filter`. Pode permanecer como legado/transitional, mas o novo caminho deve usar binding estruturado.

Quando houver categoria/conceito conhecido sem binding resolvivel, falhar fechado:
- registrar unresolved em diagnostico;
- nao inventar filtro;
- nao inventar tabela/coluna/operador/valor.

Duas categorias na mesma pergunta devem produzir comportamento deterministico e nao depender da ordem da evidencia.

`planned_filters=[]` deve preservar compatibilidade atual.

## Testes obrigatorios

1. categoria sintetica A -> `planned_filter` correto;
2. sinonimo de A -> mesmo `filter_concept`;
3. categoria sintetica B -> `planned_filter` distinto sem mudanca de codigo;
4. termo generico `valor total` -> nenhum filtro DRE;
5. categoria conhecida sem binding -> unresolved, sem filtro inventado;
6. duas categorias na mesma pergunta -> comportamento deterministico;
7. `planned_filters` vazio mantem compatibilidade atual.

Todos os testes devem usar apenas fixtures/contexto sintetico. Nao usar nomes reais de cliente, DRE, marcas, contas, centros de custo, tabelas de negocio reais, perguntas de benchmark, SQL esperada ou golden answer.

## Hardcode inventory

Classificar qualquer hardcode encontrado ou introduzido como:
- `STRUCTURAL`
- `TRANSITIONAL`
- `FORBIDDEN`

Nenhum `FORBIDDEN` pode ser introduzido em codigo de producao.

## Validacao obrigatoria

Executar no working tree real:
- `python -m compileall app`
- `python testar_planner.py`
- `python testar_build_plan.py`
- novos testes de `planned_filters`
- demais testes de planner diretamente impactados, se houver
- `python scripts/check_all.py`

Nao afirmar sucesso de teste sem ter executado o comando correspondente.

## Entrega esperada

Ao concluir, reportar:
- arquivos alterados;
- diff resumido;
- modelo final de `planned_filter`;
- algoritmo de resolucao;
- resultados de todos os testes executados;
- hardcode inventory;
- riscos restantes;
- `git status`;
- commit SHA, se houver commit.

## Commit

Commit autorizado apos todos os testes obrigatorios e `scripts/check_all.py` passarem.

Mensagem sugerida:

`feat: add planned filter planning contract`

## Deploy

Nao autorizado.

## Supabase / n8n / ambientes externos

Nao alterar.
