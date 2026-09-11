# CURRENT TASK — planned_filters microetapa 3

## Objetivo

Fazer o Contract Gate validar que toda obrigacao `planned_filter.required=true` realmente esta presente na SQL gerada, usando exclusivamente o `binding_ref` e o binding fisico estruturado/versionado correspondente do `planning_context`.

Esta microetapa fecha o caminho planner -> generator -> Contract Gate para filtros obrigatorios, sem alterar Security Gate, repair, execute, Supabase, n8n, Watson, migrations, contexto/dados DEMO ou deploy.

## Estado confirmado da main

A microetapa 2 ja esta mergeada. O `planning_context` agora transporta separadamente:
- `planned_filters`: obrigacoes semanticas, sem detalhes fisicos;
- `resolved_filter_bindings`: bindings fisicos correlacionados por `binding_ref`.

O Contract Gate atual valida tabelas, colunas, grouping, operacoes analiticas, joins, regras, limit e wildcards, mas ainda nao valida `planned_filters` contra os predicados da SQL.

O analisador SQL atual e conservador e nao expoe ainda uma estrutura dedicada de predicados WHERE. Se for indispensavel para uma verificacao correta, e permitido estender o analisador de forma estrutural, conservadora e generica.

## Premissas obrigatorias

- `planned_filter` continua semantic-only.
- O Contract Gate nao pode inferir filtro a partir de `normalized_question`.
- Nao usar `sql_filter_hint` como contrato final.
- Nao criar `if` para receita, custo, despesa, DRE, marca, conta, centro de custo, pergunta, benchmark ou qualquer conceito de negocio.
- Nao comparar por substring textual de SQL como mecanismo principal de verificacao.
- Nao usar benchmark/golden/SQL esperada/resposta esperada na validacao.
- O binding fisico continua separado e versionado.
- Falha de verificabilidade para filtro obrigatorio deve ser fail-closed; nunca aprovar por aproximacao.

## Escopo permitido

Alterar somente o necessario em:
- `app/domain/sql_contract.py`;
- `app/graph/nodes/contract_gate.py`, apenas se o contrato de resultado/estado exigir;
- `app/domain/sql_analysis.py`, apenas se indispensavel para representar predicados de filtro de forma estruturada/conservadora;
- tipos diretamente relacionados ao analisador/contrato, se existirem separados;
- testes sinteticos diretamente relacionados, preferencialmente `testar_sql_contract.py`, `testar_sql_analysis.py`, `testar_contract_gate.py` ou equivalentes ja existentes.

Nao alterar:
- planner/planning, salvo incompatibilidade estrutural comprovada e minima;
- SQL generator, salvo incompatibilidade estrutural comprovada e minima;
- Security Gate;
- repair;
- execute;
- provider adapters;
- Supabase;
- migrations;
- n8n;
- Watson;
- dados/contexto DEMO;
- deploy.

## Contrato de validacao esperado

Para cada `planned_filter` com `required=true`:

1. localizar exatamente um `resolved_filter_binding` pelo `binding_ref`;
2. validar coerencia estrutural entre obrigacao e binding (`filter_concept`, `scope`, `required` e demais campos estruturais aplicaveis);
3. verificar na SQL analisada a existencia de predicado semanticamente equivalente ao binding esperado;
4. resolver aliases/tabelas/colunas de forma estrutural, reutilizando o analisador existente sempre que possivel;
5. comparar operador e valor sem transformar literal de negocio em regra hardcoded;
6. registrar evidencia estruturada no resultado do Contract Gate.

O Contract Gate deve rejeitar quando o filtro obrigatorio estiver:
- ausente;
- em coluna/tabela diferente;
- com operador incompatível;
- com valor diferente;
- ambiguo;
- estruturalmente invalido;
- impossivel de verificar com seguranca.

## Semantica conservadora

- Identificadores SQL podem ser normalizados conforme as regras estruturais ja usadas pelo analisador.
- Literais devem preservar semantica; nao aplicar `casefold` a valores de negocio para forcar equivalencia.
- Predicado em `JOIN ... ON` ou `HAVING` nao deve satisfazer automaticamente uma obrigacao de escopo de linha/WHERE.
- Se um `scope` ou operador nao puder ser verificado com seguranca pelo analisador, o resultado deve ser fail-closed e explicito, nao uma aprovacao silenciosa.
- Nao rejeitar filtros extras nesta microetapa apenas por serem extras; o objetivo aqui e validar obrigacoes requeridas. Nao ampliar escopo para uma politica geral de filtros nao planejados.

## Resultado/evidence

Adicionar ao resultado do Contract Gate uma projecao estruturada de verificacao de filtros, por exemplo `filters`, contendo para cada obrigacao:
- `filter_ref`;
- `binding_ref`;
- `filter_concept`;
- `scope`;
- `status`: `satisfied | violated | unverifiable | not_applicable` conforme convencao existente;
- `reason`;
- detalhes estruturais seguros necessarios para auditoria, sem secrets e sem raw provider response.

Adicionar codigos de finding especificos e estruturais para os casos necessarios, por exemplo:
- required filter missing/violated;
- filter binding invalid/ambiguous;
- filter unverifiable.

Os nomes finais podem seguir o padrao existente `SQL_CONTRACT_*`, sem criar codigos ligados a negocio.

## Analise SQL

Se o analisador precisar ser estendido, preferir uma representacao estruturada de predicados, por exemplo com:
- clause/scope;
- coluna e qualifier;
- tabela resolvida quando possivel;
- operador normalizado;
- literal/valor estruturado;
- posicao/escopo suficiente para resolucao conservadora.

Nao implementar parser SQL generico completo nesta microetapa. Suportar somente formas que possam ser verificadas com seguranca e rejeitar como `unverifiable` as demais.

## Testes obrigatorios

Usar somente nomes sinteticos/genericos.

Cobrir no minimo:

1. required filter valido em WHERE -> `satisfied` e gate aprovado;
2. required filter ausente -> gate rejeitado;
3. coluna errada -> rejeitado;
4. tabela/alias errado -> rejeitado;
5. operador errado -> rejeitado;
6. valor literal errado -> rejeitado;
7. binding ausente -> fail-closed;
8. binding duplicado/ambiguo -> fail-closed;
9. binding incompleto/invalido -> fail-closed;
10. `planned_filters=[]` preserva comportamento anterior;
11. dois filtros obrigatorios corretos, em ordem diferente na SQL -> aprovados deterministicamente;
12. um de dois filtros obrigatorios ausente -> rejeitado;
13. alias SQL valido resolve corretamente target table/column;
14. predicado equivalente em JOIN/HAVING nao satisfaz filtro de escopo WHERE/row;
15. forma de predicado nao suportada -> `unverifiable` e rejeicao para required=true;
16. string literal deve ser comparada preservando valor, sem casefold arbitrario;
17. nenhum `sql_filter_hint` e usado como fonte final;
18. nenhum benchmark/golden/expected SQL participa da verificacao;
19. regressao das validacoes existentes de tabelas, colunas, grouping, operacoes, joins, rules, limit e wildcards permanece verde;
20. Contract Gate node continua preservando evidence e failure_stage corretamente.

Se o analisador suportar naturalmente operadores como `=`, `IN`, comparadores, `IS NULL`, `BETWEEN` etc., testar os que forem efetivamente implementados. Nao ampliar suporte somente para fazer um caso especifico passar.

## Anti-overfitting

Antes de aceitar qualquer mudanca, responder:

"Isso melhora a capacidade geral ou apenas faz um caso especifico passar?"

Nenhum teste deve usar pergunta conhecida, SQL real de cliente, nome real de tabela/coluna de negocio, DRE real ou benchmark como fonte de comportamento.

## Hardcode inventory

Classificar todo hardcode novo/encontrado no escopo como:
- `STRUCTURAL`;
- `TRANSITIONAL`;
- `FORBIDDEN`.

Nenhum `FORBIDDEN` pode ser introduzido.

Operadores SQL e nomes de campos do contrato sao estruturais. Valores, tabelas, colunas, categorias e regras de negocio nao sao.

## Validacao obrigatoria

Executar no working tree real:
- `python -m compileall app`;
- testes do analisador SQL se alterado;
- testes do SQL Contract;
- testes do Contract Gate;
- `python testar_sql_generation.py` para regressao do contrato anterior;
- demais testes diretamente impactados;
- `git diff --check`;
- `PYTHONDONTWRITEBYTECODE=1 python scripts/check_all.py`.

Se `scripts/check_all.py` nao puder concluir no ambiente Linux exclusivamente por teste Windows preexistente, reportar exatamente o bloqueio e nao modificar o teste para contornar. O merge somente podera ocorrer depois do workflow GitHub Actions `Offline validation on Windows` passar no HEAD remoto do PR.

## Publicacao obrigatoria

O usuario nao deve transportar patch, SHA, log, screenshot ou codigo.

Ao concluir:
- configure `origin` se estiver ausente;
- tente publicar a branch remota e abrir/atualizar PR;
- reporte `local_commit_sha`, `publication_status`, `remote_branch`, `remote_head_sha`, `pr_number`, `publication_blocker`;
- se o workspace nao tiver autenticacao/rede para push, reporte o bloqueio objetivamente. Nao peça ao usuario para copiar patch ou executar comandos.

## Entrega esperada

Reportar:
- arquivos alterados;
- diff resumido;
- modelo de evidence de filtros no Contract Gate;
- estrategia de analise/resolucao de predicados;
- comportamento fail-closed;
- resultado de cada teste;
- hardcode inventory;
- riscos/restantes nao cobertos;
- `git status`;
- dados completos de publicacao remota.

## Commit

Commit autorizado apos testes locais obrigatorios diretamente impactados passarem e regressao disponivel ser executada/reportada.

Mensagem sugerida:

`feat: validate planned filters in contract gate`

## Merge

Codex nao deve executar merge.

O merge e decisao delegada ao ChatGPT/revisor tecnico conforme `docs/codex/MERGE_POLICY.md`. Se PR remoto, diff, hardcodes, testes, Windows CI, conflitos e escopo estiverem aprovados, o ChatGPT pode executar o merge sem nova confirmacao do usuario.

## Deploy / ambientes externos

Nao autorizado.

Nao alterar Supabase, n8n, Watson, migrations, dados/contexto DEMO, PROD, credenciais, permissoes ou qualquer ambiente externo.
