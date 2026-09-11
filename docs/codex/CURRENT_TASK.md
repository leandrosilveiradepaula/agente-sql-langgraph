# CURRENT TASK — planned_filters microetapa 4

## Objetivo

Fechar a prontidao end-to-end offline de `planned_filters`, conectando o contexto semantico versionado ao planner, generator e Contract Gate com testes sinteticos de fluxo completo, sem deploy e sem alterar ambientes externos.

A microetapa 3 ja esta mergeada. Hoje o motor ja possui:
- deteccao de `filter_concept` a partir de evidencia semantica;
- resolucao de `filter_binding` versionado em `entities`;
- `planned_filters` semantic-only;
- `resolved_filter_bindings` fisicos separados;
- geracao SQL instruida por bindings estruturados;
- Contract Gate que valida os filtros obrigatorios na SQL de forma fail-closed.

O proximo risco e integracao: garantir que um snapshot semantico versionado com `filter_concept` + `filter_binding` percorra o caminho completo sem atalhos textuais ou conhecimento de negocio no codigo.

## Premissas obrigatorias

- Nao criar pergunta -> SQL.
- Nao criar if por termo de negocio.
- Nao usar benchmark/golden/expected SQL como entrada do fluxo.
- Nao usar `sql_filter_hint` como contrato final.
- `planned_filter` continua sem campos fisicos.
- detalhes fisicos permanecem apenas no binding estruturado/versionado.
- conhecimento de negocio deve permanecer no contexto/configuracao, nunca no motor.
- ausencia/ambiguidade/inconsistencia de binding obrigatorio deve continuar fail-closed.
- manter arquitetura hibrida n8n + LangGraph; esta tarefa e somente semantica/agentic do LangGraph.

## Escopo permitido

Alterar somente o necessario para:
1. tornar explicito no contrato/tipos do contexto que `filter_concept` e `filter_binding` sao entidades semanticas suportadas, se isso ainda nao estiver representado adequadamente;
2. validar/normalizar estruturalmente `filter_binding` no carregamento ou no ponto canonico mais adequado, sem introduzir regras de negocio;
3. adicionar fixtures/contextos sinteticos versionados contendo conceitos e bindings genericos;
4. adicionar teste end-to-end offline do caminho:
   contexto semantico -> intent/evidence -> planner -> planned_filters/resolved_filter_bindings -> SQL generation request -> SQL gerada sintetica/provider fake -> Contract Gate;
5. provar comportamento fail-closed quando o contexto tem conceito sem binding, binding ambiguo/invalido ou binding divergente;
6. provar que perguntas semanticamente equivalentes e nao identicas produzem a mesma obrigacao estrutural quando a evidencia semantica configurada assim determina.

Arquivos candidatos, somente se necessarios:
- `app/domain/context.py`;
- loader/normalizador de contexto existente;
- testes de contexto/planner/generator/contract;
- um novo teste de integracao offline sintetico, se for a opcao mais limpa.

Nao alterar:
- n8n;
- Supabase;
- Watson;
- PROD;
- credenciais/permissoes;
- execute real;
- repair;
- Security Gate;
- adapters externos;
- dados/contexto DEMO real;
- migrations aplicadas a ambiente;
- deploy/cutover.

## Contrato sintetico esperado

Usar apenas nomes genericos, por exemplo conceitos como `category_alpha`/`category_beta` e tabelas/colunas sinteticas. Nenhum nome de cliente, DRE real, conta, marca, centro de custo ou SQL historica.

O teste de integracao deve demonstrar no minimo:

1. uma pergunta sintetica contendo termo configurado como alias de `filter_concept` gera exatamente um `planned_filter` semantic-only;
2. o `binding_ref` resolve exatamente um `resolved_filter_binding` separado;
3. o request do generator recebe a obrigacao semantica e o binding fisico separado;
4. a SQL sintetica correta passa no Contract Gate;
5. a mesma SQL sem o filtro obrigatorio falha no Contract Gate;
6. conceito conhecido sem binding falha fechado antes de inventar filtro;
7. dois bindings para o mesmo conceito sao ambiguos e falham fechado;
8. binding incompleto/invalido nao e aceito;
9. duas formulacoes semanticamente equivalentes, nao iguais literalmente, chegam ao mesmo conceito/obrigacao por configuracao/evidencia semantica;
10. `planned_filters=[]` continua retrocompativel;
11. nenhum benchmark/golden/expected SQL participa da geracao/validacao;
12. nenhum `sql_filter_hint` participa como contrato final;
13. nenhum hardcode FORBIDDEN novo.

## Generalizacao

Antes de aceitar qualquer mudanca, responder:
"Isso melhora a capacidade geral ou apenas faz um caso especifico passar?"

O teste deve provar generalizacao com pelo menos uma reformulacao semantica nao identica ao exemplo principal.

## Hardcode inventory

Classificar todo hardcode novo/encontrado no escopo como:
- STRUCTURAL;
- TRANSITIONAL;
- FORBIDDEN.

Nenhum FORBIDDEN pode ser introduzido.

## Validacao obrigatoria

Executar no working tree real:
- `python -m compileall app`;
- testes de contexto/loader se alterados;
- `python testar_planner.py`;
- `python testar_sql_generation.py`;
- `python testar_sql_contract.py`;
- `python testar_contract_gate.py`;
- novo teste de integracao offline, se criado;
- demais testes diretamente impactados;
- `git diff --check`;
- `PYTHONDONTWRITEBYTECODE=1 python scripts/check_all.py`.

Se `scripts/check_all.py` parar exclusivamente no teste Windows preexistente por ausencia de `SystemRoot`/`cmd.exe`, reportar exatamente. Merge somente depois do workflow GitHub Actions `Offline validation` passar no HEAD remoto do PR.

## Publicacao

Ao concluir:
- tente publicar branch/PR;
- se o workspace nao puder publicar, inclua NA MESMA EXECUCAO o unified diff completo de todos os arquivos alterados para permitir materializacao pelo GitHub Connector;
- reporte `base_sha`, `local_commit_sha`, `publication_status`, `remote_branch`, `remote_head_sha`, `pr_number`, `publication_blocker`;
- nao peca ao usuario para copiar patch, SHA, log ou comando.

## Commit

Mensagem sugerida:
`test: prove planned filters end to end`

## Merge

Codex nao faz merge. O ChatGPT/revisor tecnico decide e pode executar merge conforme `docs/codex/MERGE_POLICY.md` quando todos os gates estiverem satisfeitos.

## Deploy / ambientes externos

Nao autorizado. Esta microetapa termina com codigo/testes prontos na `main`, sem aplicar nada em Supabase, n8n, Watson, DEMO real, PROD ou qualquer ambiente externo.
