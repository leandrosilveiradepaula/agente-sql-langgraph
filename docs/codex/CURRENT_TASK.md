# CURRENT TASK — planned_filters microetapa 2

## Objetivo

Conectar o contrato de `planned_filters` ja incorporado ao planner ao contrato de geracao SQL, de forma generica, versionada e fail-closed.

Esta microetapa deve fazer o generator receber obrigacoes de filtro estruturadas e os bindings fisicos correspondentes, sem implementar ainda validacao no Contract Gate e sem alterar Supabase, n8n ou deploy.

## Premissas obrigatorias

- `planned_filter` continua sendo somente obrigacao semantica.
- Detalhes fisicos de filtro nao podem ser copiados para `planned_filter`.
- Detalhes fisicos devem permanecer em binding estruturado/versionado separado.
- O generator nao pode inferir tabela/coluna/operador/valor a partir do texto da pergunta.
- Nao usar `sql_filter_hint` como contrato final.
- Nao criar `if` para receita, custo, despesa, DRE, marca, conta, centro de custo, pergunta, benchmark ou qualquer termo de negocio.
- Benchmark/golden/SQL esperada nunca entram no request/prompt do generator.

## Escopo permitido

Alterar somente o necessario em:
- `app/domain/planning.py`, se for indispensavel para projetar bindings fisicos separados do `planned_filter`;
- `app/domain/planner.py`, se for indispensavel para projetar exclusivamente os bindings referenciados por `planned_filters`;
- `app/domain/sql_generation.py`;
- `app/graph/nodes/generate_sql.py`, somente se o contrato atual exigir;
- testes sinteticos diretamente relacionados (`testar_sql_generation.py`, `testar_generate_sql.py` e, se necessario, testes do planner).

Nao alterar:
- Contract Gate / `app/domain/sql_contract.py` / `app/graph/nodes/contract_gate.py`;
- Security Gate;
- repair;
- execute;
- adapters de provider, salvo necessidade estritamente estrutural comprovada;
- Supabase;
- migrations;
- n8n;
- Watson;
- deploy;
- dados/contexto DEMO.

## Contrato esperado

O `SqlGenerationContext` deve passar a carregar separadamente:

1. `planned_filters`
   - obrigacoes semanticas vindas do planner;
   - campos como `filter_ref`, `filter_concept`, `binding_ref`, `required`, `scope`, `detection_source`, `mapping_source`, `matched_user_term`, `provenance`;
   - sem `target_table`, `target_column`, `operator`, `value`, `join_path`.

2. bindings fisicos resolvidos, preferencialmente em campo separado como `filter_bindings`
   - somente bindings efetivamente referenciados por `planned_filters`;
   - `binding_ref`;
   - `target_table`;
   - `target_column`;
   - `operator`;
   - `value`;
   - `join_path`;
   - demais metadados estruturais necessarios.

Se o `planning_context` atual nao transportar esses detalhes de forma segura, adicionar uma projecao fisica separada (por exemplo `resolved_filter_bindings`) sem poluir `planned_filter`.

## Resolucao e seguranca

Fluxo esperado:

semantic evidence
-> filter_concept
-> filter_binding estruturado/versionado
-> planned_filter (obrigacao semantica)
-> binding fisico correspondente no generation context
-> generator instrucao estruturada de WHERE

Regras:

- cada `planned_filter.required=true` deve possuir exatamente um binding fisico correspondente por `binding_ref`;
- binding ausente, incompleto ou ambiguo deve causar falha fechada na construcao da requisicao de geracao, antes de chamar provider;
- nao inventar filtro quando nao houver binding;
- `planned_filters=[]` deve manter o comportamento anterior;
- multiplos filtros devem ser ordenados deterministicamente;
- o generator deve ser instruido a aplicar todas as obrigacoes `required=true` usando apenas os bindings correspondentes;
- nao deduzir filtros adicionais a partir de `normalized_question`;
- nenhum benchmark field pode ser propagado.

## Testes obrigatorios

Usar apenas fixtures/contexto sintetico, sem nomes reais de cliente ou negocio.

Cobrir no minimo:

1. um `planned_filter` + binding valido aparece corretamente no `SqlGenerationRequest`;
2. `planned_filter` continua sem campos fisicos;
3. binding fisico correspondente aparece separadamente e somente por `binding_ref` referenciado;
4. `planned_filters=[]` preserva compatibilidade do request anterior;
5. `planned_filter.required=true` sem binding correspondente -> rejeicao/falha fechada antes do provider;
6. binding ambiguo para o mesmo `binding_ref` -> rejeicao/falha fechada;
7. binding incompleto/invalido -> rejeicao/falha fechada;
8. dois filtros -> ordem deterministica independente da ordem de entrada;
9. `sql_filter_hint` nao e usado como fonte final do contrato;
10. nenhum detalhe de benchmark/golden entra no generation context/instructions;
11. instrucao ao generator deixa explicito que filtros obrigatorios devem ser aplicados e que nao pode inferir filtros extras do texto.

## Anti-overfitting

Antes de aceitar qualquer alteracao, validar:

"Isso melhora a capacidade geral ou apenas faz um caso especifico passar?"

Nao usar perguntas conhecidas, frases especificas ou regras de negocio nos testes de producao.

## Hardcode inventory

Classificar todo hardcode novo/encontrado no escopo como:
- `STRUCTURAL`
- `TRANSITIONAL`
- `FORBIDDEN`

Nenhum `FORBIDDEN` pode ser introduzido.

## Validacao obrigatoria

Executar no working tree real:
- `python -m compileall app`
- `python testar_planner.py` se planner/planning forem alterados
- `python testar_sql_generation.py`
- `python testar_generate_sql.py`
- demais testes diretamente impactados
- `git diff --check`
- `PYTHONDONTWRITEBYTECODE=1 python scripts/check_all.py`

Se `scripts/check_all.py` nao puder concluir no ambiente Linux exclusivamente por teste Windows preexistente, reportar exatamente o ponto de bloqueio; nao modificar o teste Windows para contornar. O PR so podera ser mergeado depois do workflow GitHub Actions `Offline validation on Windows` passar.

## Entrega esperada

Reportar:
- arquivos alterados;
- diff resumido;
- modelo final de `planned_filters` no generation context;
- modelo do binding fisico separado;
- algoritmo de correlacao por `binding_ref`;
- resultado de cada teste executado;
- hardcode inventory;
- riscos restantes;
- `git status`;
- commit SHA local;
- PR preparado para publicacao/atualizacao.

## Commit

Commit autorizado apos os testes locais obrigatorios diretamente impactados passarem e a regressao disponivel ser executada/reportada.

Mensagem sugerida:

`feat: pass planned filters to sql generation`

## Merge

Nao autorizado automaticamente. O merge sera feito somente apos revisao do diff e sucesso do workflow Windows no GitHub.

## Deploy / ambientes externos

Nao autorizado.

Nao alterar Supabase, n8n, Watson, migrations, dados DEMO ou qualquer ambiente externo.
