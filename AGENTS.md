# 28/10/2026 — G5 SOURCE BACKUP CRIPTOGRAFADO REAL CAPTURADO, RESTORE AINDA NAO VERIFICADO

**Evidencia VPS confirmada pelo operador:** G5 exportou PostgreSQL SOURCE `nywxpvzhlpqjtcafpdfe` com autorizacao read-only, `G5_ARCHIVE_RESULT=ENCRYPTED_CAPTURED`, `G5_ARCHIVE_INTEGRITY=ENCRYPTED_DIGEST_PASS`; manifesto em caminho root-only `/root/.local/share/agente-sql-langgraph/source-archives/source-nywxpvzhlpqjtcafpdfe-20261028T145054Z-1557baa82308af9b.dump.gpg.manifest.json`. **NAO declarar recuperacao provada:** `G5_ARCHIVE_RESTORE=NOT_VERIFIED`; senha armazenada pelo operador fora do chat. Nunca copiar arquivo cifrado para GitHub.

**Nova entrega proposta:** fluxo offline de inspecao com senha (decriptacao GPG em pipe anonimo e `pg_restore --list` somente em stdin, sem banco, gravacao de plaintext, DSN ou log de nomes). Objetivo e atestar senha de recuperacao e legibilidade do TOC; NAO equivale a restauracao integral. A prova de restore isolado precisa de autorizacao propria. Preservar copia cifrada fora da VPS, SHA-256, manifesto e senha sob custodia separada.

**Bloqueios SOURCE ainda reais:** nove referencias PostgreSQL legadas no n8n oficial, persistencia Shadow LangGraph apontando SOURCE, Vercel DATABASE_URL dos dois Produtos ainda sem destino confirmado, identidade tenant/membership real indisponivel, hardcodes legados nao externalizados, paridade financeira/cutover nao atestados. NAO alterar n8n, DEMO, SOURCE, roles, credenciais, DSNs, Vercel, producao ou SQL financeira em Shadow por causa do backup. `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. Ver docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md e issue #155.

---

# 28/10/2026 — G5: PRIMEIRA CAPTURA AUTORIZADA FALHOU, SOURCE AINDA ATIVA

Operador autorizou exportacao SOMENTE LEITURA de SOURCE `nywxpvzhlpqjtcafpdfe` para backup privado com senha. Na VPS, `--capture` retornou `G5_ARCHIVE_RESULT=BLOCKED`, `G5_ARCHIVE_ERROR=ENCRYPTED_DUMP_FAILED`, `G5_ARCHIVE_RESTORE=NOT_VERIFIED`; nenhum backup completo foi comprovado. O stderr estava descartado e o codigo antigo misturava falha pg_dump e GPG, portanto a causa real NAO e conhecida. A sessao SSH encerrou depois do erro; nao afirmar que banco caiu. Consulta independente de metadados confirmou PostgreSQL SOURCE 17.6 respondendo.

**Proxima acao atual:** homologar correcao G5 que classifica stderr apenas em codigos sanitizados e verifica digest criptografado dentro de `--capture`. Apos PR/CI/merge humano, repetir uma captura de forma simples (sem pipe/tee/subshell), informar senha e DSN somente na VPS, nunca no chat. Essa exportacao esta AUTORIZADA; qualquer restore/import DEMO, mudanca de DSN/n8n/roles, cutover e exclusao SOURCE NAO esta. Prova de restauracao isolada e custodia externa do arquivo/senha permanecem obrigatorias. `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` nao muda.

---

# 28/10/2026 — G5 PREPARACAO DO ARQUIVO E IDENTIDADE (PR #185, SEM MERGE)

**Operador confirmou na VPS:** workflow oficial armazenado 68 nos, uma credencial SOURCE em 9 referencias e uma DEMO em 2; os 2 bindings G1 sao DEMO. Shadow n8n 7 nos sem credenciais Postgres diretas; LangGraph ainda grava evidencias SOURCE e le contexto DEMO. SQL real Shadow desativada. Dois Produtos Vercel DATABASE_URL continuam sem destino atestado. O banco SOURCE nao pode ser apagado.

**Entrega proposta:** [PR #185](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/pull/185) cria ferramenta de arquivo **criptografado e read-only** com captura interativa especificamente autorizada (nenhuma captura realizada), testes de recibo SHA-256 e gate de login Shadow que requer organizacao UUID ativa + membership ativa do Produto. DEMO tem zero organizacoes/memberships: P3 continua bloqueado ate autorizacao/cadastro real.

**NUNCA** confundir backup logico com restauro provado, nem autorizar restore no DEMO. Nao executar SQL financeira, alterar n8n, DSNs, banco, roles ou Vercel sem aprovacao independente; nao ativar cutover nem apagar SOURCE implicitamente. Manter OFFICIAL=n8n, SHADOW=LangGraph e LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. O merge desta PR nao autoriza executar --capture.

---

# ATUALIZACAO OPERACIONAL 28/10/2026 — G5 APOSENTADORIA DO SUPABASE ANTIGO (PR #183)

**Decisao mais recente do operador:** objetivo imediato e consolidar a operacao
do Agente Financeiro, preservar o historico necessario e poder eliminar a
origem Supabase `nywxpvzhlpqjtcafpdfe`. Manter destino DEMO
`cenhadslwxgykqtuobgc`. O projeto nao esta pronto para exclusao.
**Nao confundir a migracao P3 de 200 evidencias com a consolidacao do banco.**

Auditoria 28/10: 200/200 evidencias Shadow com checksum identico, mas existem
47 tabelas public na origem vs 10 no DEMO, 238 vs 42 runs Produto, 10 vs 1
usuario, e contextos diferentes (11 versoes legadas em public vs 10 versoes
DEMO em semantic_context). Nao misturar conhecimentos, benchmarks, SQL ou
DRE de clientes diferentes. Dois Produtos Vercel Production READY possuem
DATABASE_URL protegido cujo destino real nao foi certificado. O n8n oficial
usa credenciais proprias e o ultimo PUT publicado teve drift nao reconciliado.
Shadow tem DSNs separados para persistencia e contexto.

**Entrega ativa:** PR [#183](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/pull/183)
unifica inventario, verificacao offline e auditoria local da VPS/n8n sem
exibir segredos. A auditoria viva so conta depois de executada na VPS:
nao substituir evidencia por CI verde. Procedimento e bloqueios:
[docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md](docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md).

**Proibido por efeito desta etapa:** deletar/desativar qualquer Supabase,
executar SQL financeira, modificar n8n, Vercel, DSN, credenciais, roles,
deploy, cutover ou ativar flags. Offical continua n8n+Gemini, Shadow continua
n8n+LangGraph+Gemini, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.
Merge e delete de banco permanecem gates humanos independentes.

---

# ATUALIZAÇÃO OPERACIONAL 27/10/2026 — P3/G1 pós-PUT, não repetir API nem rollout

**Status real comprovado pela VPS:** P1/P2 já foram comprovados nas fases
anteriores. No G1, o operador autorizou e executou uma recuperação após
preflight PASS: role `finance_g1_readonly` tem login SELECT-only validado,
credencial PostgreSQL n8n foi criada, snapshot privado foi persistido e
PUT do workflow oficial foi **tentado**. O verificador pós-PUT retornou
`ERROR=drift na versao publicada fora dos bindings`; portanto **não há
prova da equivalência do workflow nem confirmação final dos dois vínculos**.
O PUT pode ter efetivamente atualizado o workflow, portanto não presumir
que ele esteja intacto. Última `main` antes da auditoria:
`0b251c0e0a98ff46666506c8793a29ac03100c04` (PR #178).

**Auditoria pós-rotacão independente no Supabase DEMO:** role existente,
atributos seguros, read-only e timeouts confirmados; 8 relações financeiras
SELECT autorizadas, nenhuma leitura fora da lista, nenhum CREATE/TEMP.
Nenhuma consulta financeira de negócio foi executada nessa auditoria.

**Bloqueio prioritário atual:** PR
[#179](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/pull/179)
introduz `scripts/operations/g1_post_put_audit_readonly.py` e testes.
Após merge humano e CI PASS, rodar **uma vez na VPS** o auditor CLI local
**sem pedir API key ou DSN**. Ele lê snapshot privado e versão n8n 2.4.8
armazenada via CLI, sem HTTP, SQL, escrita ou logs sensíveis. Responder
com os status G1_*; somente `G1_AUDIT_RESULT=STRICT_PASS` equivale à
verificação de persistência e equivalência do workflow, não à paridade
financeira. Ver `docs/runbooks/g1-readonly-single-step-operator.md`.

**PROIBIDO até a reconciliação:** repetir `--apply` ou `--recover`,
fazer `--rollback` ou `--verify` às cegas, executar webhook financeiro,
benchmark/SQL financeira real, alterar credenciais, schema ou produção
implicitamente. Preservar snapshot, role e credencial existente.
`OFFICIAL=n8n`, `SHADOW=LangGraph`,
`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. Cutover permanece humano e
dependente de paridade e portabilidade.

---

# ESTADO OPERACIONAL REAL — 26/10/2026: P1/P2 PASS, P3 G1 BLOQUEADO EM VIEW DO POSTGRESQL

**Foco exclusivo: fechar P3, não repetir geração Gemini.** P1 comprovou
n8n candidato → LangGraph → Gemini com SQL válida; P2 comprovou a
correlação autenticada Produto → n8n candidato → LangGraph e evidência da
mesma tentativa: `agent_run_id=41d54ee0-b730-41ec-ba69-836d862b1780`,
`run_id=lg-shadow-test-run-3`,
`shadow_record_id=shadow-07d311c493efb7383fe0f5e0fc133997`.
`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` permanece.

**G1/P3 evidência real na VPS, `main@3a30e42`:** compensação
`PUBLIC TEMPORARY` do Supabase financeiro DEMO foi aplicada, preservou
privilégios existentes (35 roles, 32 compensadas) e foi confirmada com
`P3_ACL_VERIFY=PASS`. `g1_readonly_rollout.py --dry-run` passou:
`G1_N8N_BINDINGS=PREFLIGHT:0eee554daf77`,
`G1_ROLE=NOT_APPLIED`, `G1_ROLLBACK=READY`.
Um `--apply` autorizado parou dentro da transação ao detectar
`ERROR=role pode modificar uma relacao`. Diagnóstico catalogal real
read-only confirmou: **um único objeto PUBLIC DML, exclusivamente a view
de sistema `pg_catalog.pg_settings` com `PUBLIC UPDATE`; zero relações
com DML PUBLIC em schemas financeiros, public, net e demais; role G1
não existe, snapshot G1 não existe.** Nenhuma credencial n8n foi criada,
nenhum rebind ocorreu nessa tentativa; não executar SQL financeira.

**Correção atual:** tratar *somente* o `UPDATE` intrínseco concedido por
`PUBLIC` à view de configuração `pg_catalog.pg_settings`, cujo efeito
é `SET` da própria sessão em PostgreSQL, preservando a rejeição de
todo DML em outras relações/schemas e de privilégios adicionais,
inclusive nessa view. Ver [runbook G1](docs/runbooks/g1-readonly-single-step-operator.md)
e [roadmap vivo #155](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/issues/155).
Homologar com PostgreSQL descartável antes de PR/merge; depois reconfirmar
o preflight e o rollout G1 autorizado com snapshots/rollback. Não realizar
cutover, consultas financeiras reais, migrações ou modelo SQL-InfoDive sem
as respectivas autorizações.

---

# FOCO IMEDIATO — decisão operacional de 26/10/2026 (leia primeiro)

**Meta única até prova real:** fazer **n8n candidato → LangGraph → Gemini** receber uma pergunta inédita, **gerar SQL dinâmica**, passar pelos gates e persistir evidências correlacionadas, **sem executar SQL financeira**. Este é o marco P1, não a conclusão de G1 ou da paridade. Ver [plano de entrega e critérios objetivos](docs/operations/DELIVERY-FOCUS.md).

**Ordem obrigatória de demonstração:** P1 geração real isolada em TEST → P2 integração com Produto autenticado/Shadow correlacionado → P3 execução read-only com menor privilégio e paridade → requisitos multicliente/hardcodes, cutover humano e comparação de modelos na ordem contratada.

- **Não confundir os bloqueios:** `PUBLIC TEMPORARY=true` impede o rollout da role read-only e execução financeira dependente dela, mas **não deve desviar a entrega P1 generate-only**. **Não** revogar grants globais, reduzir gates, usar a rota oficial Demo que também executa SQL ou alterar produção para obter P1.
- **Autorização humana permanece:** chamada Gemini paga, ativação/execução em ambiente real, Vercel/n8n oficial, banco/permissões, SQL real, migrations, merge e cutover exigem seus próprios gates. `OFFICIAL=n8n+Gemini`; `SHADOW=n8n+LangGraph+Gemini`; `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.
- **Anti-loop:** não abrir PRs/mudar hardcodes/refazer infraestrutura apenas para produzir novos diagnósticos. Trabalhar sobre o primeiro bloqueio concreto da prova ativa e demonstrar a correção; manter benchmark só para avaliação posterior.
- **Continuidade:** verificar GitHub/CI/runtime reais e ler o plano acima + status/roadmap antes de iniciar. Registrar ao fim de cada bloco qual P1/P2/P3 foi realmente comprovado, artefatos/SHA e a única próxima prova.

O contrato de portabilidade/cutover e as instruções abaixo **continuam integrais**, sem exceções.

---

# Operação permanente — objetivo final (decisão de 2026-10-19)

> **Leitura obrigatória antes de qualquer tarefa neste repositório.** Este bloco
> registra a intenção atual do operador e prevalece sobre instruções históricas
> abaixo sobre microetapas, Watson, provedores ou manutenção indefinida do
> caminho de geração antiga. Consulte a versão integral em
> [`docs/architecture/PORTABILITY-AND-CUTOVER-CONTRACT.md`](docs/architecture/PORTABILITY-AND-CUTOVER-CONTRACT.md).
> Texto pronto para as instruções do projeto no ChatGPT:
> [`CHATGPT-PROJECT-INSTRUCTIONS.md`](CHATGPT-PROJECT-INSTRUCTIONS.md).

## Missão e entrega final

- **Não substituir n8n:** ele permanece a plataforma de orquestração,
  webhooks, integrações, automação determinística e coordenação da execução.
- **Substituir, após homologação, a inteligência SQL antiga do n8n:**
  atual `n8n + Gemini` → futuro oficial `n8n + LangGraph + Gemini`.
  O novo mecanismo deve assumir intenção, contexto, planejamento, geração
  dinâmica, validação de SQL, repair proposto e governança.
- **Ordem fixa:** (1) equivalência Shadow usando Gemini em ambos os
  caminhos; (2) cutover humano seguro, desabilitando a geração inteligente
  antiga e preservando n8n; (3) comparação Gemini vs **SQL-InfoDive** com
  mesma arquitetura/contexto.
- **Zero hardcode de negócio no motor:** migrar comportamento, não replicar
  regras de nós n8n para Python/TypeScript. Auditar os nós reais, inventariar
  `STRUCTURAL` / `TRANSITIONAL` / `FORBIDDEN`, externalizar regras de
  cliente (catálogo, métricas, dimensões, joins, DRE quando existir,
  filtros, aliases, intenções, SQL patterns estruturais) em contexto
  versionado e auditável; nenhum `FORBIDDEN` no código novo.
- **Portabilidade não negociável:** alterar cliente/esquema deve exigir
  configuração, contexto, dialeto/conector autorizado e homologação,
  **nunca** um `if cliente`, SQL por pergunta, threshold casuístico
  ou alteração do núcleo. Não inferir regras contábeis ausentes.
  Comprovar com pelo menos dois contextos materialmente diferentes.
- **Shadow atual:** `OFFICIAL=n8n`, `SHADOW=LangGraph`,
  `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. Sem cutover, real SQL,
  mudança n8n/PROD/banco ou privilégios implícitos. Paridade numérica
  exige autorização separada de execução read-only isolada.
- **Benchmark é avaliação posterior:** SQL/respostas atuais do n8n são
  referência para confronto, jamais dados de geração ou prompt; não
  ajustar motor para perguntas de teste. Testar generalização, segurança,
  correspondência financeira e regressões entre commits.
- **Gates humanos:** aprovação/reaprovação de SQL, merge, permissões,
  migrations, cutover, credenciais/custo e produção. Sem auto-merge.
  Trabalhar autonomamente no restante, em blocos substantivos.
- **Continuidade sem memória improvisada:** verificar HEAD, PR, CI,
  evidências e contexto ativo reais; diferenciar confirmação de hipótese.
  Retomar pelos arquivos `AGENTS.md`, `CHATGPT-PROJECT-INSTRUCTIONS.md`,
  `ORCHESTRATION-STRATEGY.md`, `PROJECT-STATUS.md` e contrato acima.

**Nota de precedência:** `docs/codex/CURRENT_TASK.md` descreve uma
microetapa específica e pode ficar historicamente desatualizado. Não usar
seu conteúdo para sobrescrever uma tarefa explicitamente determinada agora
pelo operador nem para autorizar deploy/cutover/SQL real. Referências antigas
a Watson são contratos históricos e não metas para o runtime novo.

---

# AGENTS.md

## Arquitetura

O LangGraph local carrega um `ContextSnapshot` canonico, resolve uma unica
intencao, constroi um `QueryPlan` deterministico e gera SQL por um
`SqlGenerator` injetado. Depois, o Security Gate valida read-only e
autorizacao estrutural, e o Contract Gate valida aderencia ao `QueryPlan`.
O Engine Preflight valida planejamento do motor por porta injetada, sem
executar a consulta de negocio.
Quando aprovado, a execucao controlada usa somente `current_sql` e uma
`SqlExecutionRequest` minima enviada a um `SqlExecutor` explicitamente
injetado.
Depois da execucao aprovada, o resultado e apenas normalizado e serializado:
nao interpretar, arredondar, inferir moeda, percentual ou data. `Decimal` nao
vira float; erros nao carregam celulas; serializacao deve ser JSON-safe,
deterministica e sem logs do payload completo.
Preflight live so pode ser habilitado com capability comprovada do motor real;
execucao normal, `LIMIT 0` e `EXPLAIN ANALYZE` nunca podem ser usados como
preflight.
Se o preflight rejeitar uma SQL com erro reparavel, o grafo pode chamar um
SqlRepairer injetado e reenviar a SQL reparada para Security Gate, Contract
Gate e Engine Preflight.
O planner usa somente o snapshot versionado ja validado; geracao e gates
consomem somente o `QueryPlan` e a SQL corrente.
Toda saida terminal do grafo passa por finalizacao local: `RunRecord`,
persistencia obrigatoria, auditoria obrigatoria e observabilidade best-effort.
Depois da finalizacao, toda execucao terminal deve produzir uma
`ApplicationResponse` publica, deterministica e segura. Mensagens publicas sao
canonicas; erros brutos de provider nao atravessam. `data` so existe em
success finalizado com persistencia e auditoria aprovadas. Falha de
persistencia/auditoria e fail-closed; observabilidade degradada preserva o
outcome original. Nao duplicar payload, e JSON canonico deve ser produzido
somente sob demanda.
Toda execucao externa futura deve passar pelo application service. Endpoints
nao invocam o grafo diretamente. O service sempre retorna `ApplicationResponse`,
request invalida nao chama o grafo, exception de runtime e fail-closed, e
`GraphState` nunca e retornado.

## Principios permanentes do Agente Financeiro

- A arquitetura e hibrida: n8n permanece responsavel por orquestracao operacional,
  webhooks, integracoes e etapas deterministicas; LangGraph fica com semantica,
  classificacao, selecao de contexto, planejamento, geracao/validacao de SQL,
  repair como proposta e evidence/governanca. Nao migrar tarefas para LangGraph
  apenas porque ele existe.
- Nunca implementar pergunta -> SQL, frase -> resposta ou benchmark -> comportamento.
  Perguntas, SQLs historicas e golden answers servem apenas para avaliacao e
  documentacao, nunca para geracao.
- Migrar comportamento, nao hardcode. Classificar conhecimento encontrado como:
  `STRUCTURAL` (motor/plataforma), `TRANSITIONAL` (divida herdada) ou `FORBIDDEN`
  (regra de negocio, tabela/coluna cliente-especifica, DRE, marca, conta, centro
  de custo, alias, intencao especifica, excecao, SQL pronta, pergunta/resposta ou
  threshold de caso). Nenhum `FORBIDDEN` entra em codigo novo.
- O codigo conhece o PROCESSO; conhecimento de negocio deve vir de contexto/configuracao
  versionada e auditavel. Preferir fontes como regras, aliases, mappings, patterns
  e catalogo semantico versionados.
- `business_question_examples` sao apenas sinais semanticos auxiliares; nunca lookup.
- Campos de benchmark (`tabelas_obrigatorias`, `filtros_obrigatorios`,
  `deve_conter_sql`, `nao_deve_conter_sql`, `criterio_semantico`, SQL esperada,
  resposta esperada, golden answer) nunca podem chegar ao generator/prompt.
- Antes de aceitar uma mudanca, validar se ela melhora capacidade geral ou apenas
  um caso. Nunca reduzir threshold, criar `if` por frase ou SQL especial para benchmark.
- `SEMANTIC_AGENT_VERSION` deve permitir trocar regras, aliases, mappings, patterns
  e catalogo preferencialmente sem alterar Python/TypeScript.
- Durante shadow: OFFICIAL = n8n, SHADOW = LangGraph, `real_sql_execution=false` e
  nenhum cutover implicito.
- Generate, Repair e Execute sao etapas distintas. SQL alterada perde aprovacao,
  exige `requires_reapproval=true` e nunca e executada silenciosamente.
- Preservar observabilidade e correlation metadata; nunca expor secrets, DSN,
  Authorization, cookies, API keys ou raw provider responses desnecessarias.
- Nunca afirmar que arquivo, codigo, SQL, log ou configuracao foi revisado sem
  realmente acessar o conteudo.
- Testar generalizacao com perguntas novas e equivalentes semanticamente, nao apenas
  benchmark conhecido.

## Protocolo Codex

O Codex deve tratar este repositorio como fonte de verdade operacional.
Antes de qualquer implementacao, ler este `AGENTS.md` e
`docs/codex/CURRENT_TASK.md` quando existir.

Para cada tarefa:
1. confirmar HEAD/branch e working tree antes de editar;
2. respeitar estritamente o escopo de `CURRENT_TASK.md`;
3. nao alterar arquivos ou subsistemas fora do escopo sem necessidade comprovada;
4. executar os testes novos e a regressao relevante indicada;
5. executar `python scripts/check_all.py` antes de commit quando a tarefa exigir
   regressao consolidada;
6. produzir inventario de hardcodes `STRUCTURAL / TRANSITIONAL / FORBIDDEN`;
7. nunca introduzir `FORBIDDEN` em codigo de producao;
8. registrar no resultado: arquivos alterados, diff resumido, testes, riscos e
   `git status`;
9. somente fazer commit quando `CURRENT_TASK.md` autorizar explicitamente;
10. nunca fazer deploy, alterar Supabase, n8n, PROD ou servico externo sem autorizacao
    explicita na tarefa corrente.

### Protocolo de publicacao remota

A tarefa nao e considerada entregue apenas porque existe um commit no workspace do
Codex. O estado remoto do GitHub e a fonte de verdade para entrega.

Ao finalizar uma tarefa que autoriza commit/PR, o Codex deve reportar explicitamente:
- `local_commit_sha`;
- `publication_status`: `published` ou `not_published`;
- `remote_branch`, quando publicada;
- `remote_head_sha`, quando publicada;
- `pr_number`, quando houver PR;
- `publication_blocker`, quando `not_published`.

Regras de publicacao:
1. nunca escrever "PR criado", "PR atualizado", "publicado" ou equivalente sem
   confirmar que o commit esta visivel no GitHub remoto;
2. commit existente apenas no workspace deve ser reportado como `not_published`;
3. quando a tarefa tiver sido iniciada a partir de issue/PR do GitHub, preservar a
   mesma linha de trabalho para correcoes subsequentes; nao criar nova tarefa apenas
   para transportar um commit local;
4. quando houver PR remoto, toda correcao deve terminar no mesmo PR, salvo instrucao
   explicita em contrario;
5. se o ambiente nao tiver `git remote`, credencial ou capacidade de publicar, nao
   tentar contornar com segredo, token, provider externo ou configuracao ad hoc;
   registrar `publication_blocker` e preservar o patch/commit no workspace;
6. nunca pedir ao usuario que transporte codigo, SHA, logs ou screenshots entre
   ChatGPT, Codex e GitHub;
7. a verificacao de entrega sera feita pelo ChatGPT diretamente no GitHub por
   comentarios completos, branch/HEAD, commits, diff e checks; screenshots nao sao
   parte do protocolo de verificacao;
8. merge e deploy permanecem proibidos sem autorizacao explicita do usuario.

`docs/codex/CURRENT_TASK.md` e o control plane da tarefa corrente. Ele nao deve
conter secrets nem golden answers de benchmark. Ao concluir uma tarefa, nao inventar
a proxima: aguardar que a tarefa corrente seja atualizada.

## Comandos principais

- `python -m compileall app`
- `python testar_intent_resolver.py`
- `python testar_classify_intent.py`
- `python testar_planner.py`
- `python testar_build_plan.py`
- `python testar_sql_generation.py`
- `python testar_sql_execution.py`
- `python testar_engine_preflight.py`
- `python testar_sql_repair.py`
- `python testar_sql_analysis.py`
- `python testar_sql_security.py`
- `python testar_security_gate.py`
- `python testar_sql_contract.py`
- `python testar_contract_gate.py`
- `python testar_engine_preflight_node.py`
- `python testar_execute_sql.py`
- `python testar_repair_sql.py`
- `python testar_generate_sql.py`
- `python testar_run_record.py`
- `python testar_application_response.py`
- `python testar_build_application_response.py`
- `python testar_grafo_base.py`
- `python scripts/check_all.py`

## Restricoes

Nao modificar workflows n8n, nao tocar PROD e nao executar scripts live com
escrita. Gemini, Watson, Supabase e outros servicos externos nao fazem parte do
planner.

## Hardcodes

Nao colocar termos de negocio, nomes reais de clientes, fabricantes, tabelas,
colunas ou exemplos de benchmark em regras Python. Decisoes devem vir do
`ContextSnapshot` e, depois do planejamento, do `QueryPlan`. Gates nao releem
o snapshot completo, nao executam SQL e nao corrigem SQL automaticamente.
Preflight tambem nao rele o snapshot completo, nao chama o gerador novamente,
nao executa SQL, nao usa `EXPLAIN ANALYZE` e deve sanitizar erros. O loop de
reparo so inicia depois de preflight reparavel, nao recarrega contexto, nao
reexecuta geracao inicial, respeita limite obrigatorio e registra historico
sem SQL integral. SQL reparada volta aos gates antes de novo preflight.
Provider live e sempre explicitamente injetado; nao ha provider global, fake
como fallback de producao ou credenciais versionadas. Na ausencia de capability
segura comprovada, use apenas diagnostico fail-closed.
Execucao SQL controlada tambem exige executor explicitamente injetado, nao
recebe GraphState nem ContextSnapshot, nao altera SQL e nao pode ser alcancada
sem Security Gate, Contract Gate e Engine Preflight aprovados.
ApplicationResponse nao cria endpoint nesta fase, nao executa SQL, nao chama
sinks, nao expoe SQL integral, pergunta integral, QueryPlan, ContextSnapshot,
GraphState, prompts, headers, tokens, DSN, RunRecord integral ou eventos
integrais.
Application service tambem nao cria endpoint HTTP, nao loga pergunta, SQL ou
payload, nao chama adapters/sinks diretamente e nao implementa retry automatico.
HTTP entry adapter chama `Authenticator` e `Authorizer` explicitamente
injetados antes de `SqlAgentApplicationService`; endpoints nunca invocam o
grafo diretamente. Identidade HTTP nunca vem do body: `user` em JSON publico
e proibido, e `ApplicationRequest.user` deriva somente do principal
autenticado. Authorization, credenciais, principal, roles e scopes nunca devem
ser logados ou retornados. Auth falha fechada, deny por padrao, sem usuario
anonimo, sem role de negocio hardcoded e sem provider real nos testes. O
adapter nao inicia servidor em `check_all.py` e nenhum endpoint expoe
`GraphState`.
ASGI adapter traduz somente protocolo para o `SqlAgentHttpHandler`: nao chama
grafo, application service, authenticator ou authorizer diretamente. Nao
armazenar scope, body, headers, eventos ou tokens em estado global; nao logar
eventos, headers ou body; nao iniciar servidor em `check_all.py`; nao adicionar
Uvicorn/Hypercorn nesta fase. `http.disconnect` nao chama o handler. Depois de
`http.response.start`, nao enviar segunda resposta.
Watson Flow nesta fase existe apenas como contratos offline e adapters
explicitamente injetados. O payload Watson contem somente `sql_query`; nunca
enviar `limit` sem mudanca formal de contrato. `approved_sql` e
`sql_transport` sao conceitos diferentes: compactar apenas uma copia de
transporte, sem truncar, sem persistir e sem substituir a SQL original. Token
IAM e value object sensivel e nao pode ser serializado, logado ou retornado.
Raw output do Flow nao atravessa a fronteira do adapter. Cada adapter faz uma
tentativa; retry deve ser decorator ou orquestracao explicita. Falhas de IAM,
provider, timeout, rate limit, autenticacao, resposta invalida ou ambigua nunca
acionam repair. `check_all.py` nunca acessa rede, socket, Watson ou IBM Cloud.
O dry-run do probe Watson nao exige secret, nao acessa `SecretValueProvider`,
nao cria adapters live e nao acessa rede. Somente live mode pode consultar API
key, sempre depois de validar arquivo SQL, compactacao, payload, configuracao
nao sensivel e confirmacao TEST. A composition root Watson TEST aceita somente
`DeploymentEnvironment.TEST`, rejeita PROD/production/prd/live, nao infere TEST
pela URL e nao altera o bootstrap padrao offline. Operacao Windows deve
documentar comandos CMD quando o usuario pedir fluxo operacional; nunca usar
`setx` para secrets. Probe live continua manual, sem retry automatico.

## Testes

A suite local deve usar dados genericos. Scripts live ficam separados e so
podem ser usados em leitura quando necessario. `scripts/check_all.py` e a
regressao consolidada esperada antes de commit.
Testes locais de preflight usam fake injetado e nao acessam motor real.
Persistencia e auditoria devem ser idempotentes, falhar fechadas e nunca
registrar SQL integral ou valores em auditoria/telemetria. Observabilidade pode
degradar sem apagar resultado persistido, mas nao usa IDs de alta cardinalidade
como labels. Fakes de persistencia, auditoria e observabilidade nunca sao
defaults e nenhum adapter live entra no `check_all.py`.
Testes locais de reparo usam fake injetado, sem rede, sem banco e sem
execucao de SQL.
Testes locais de execucao usam fake injetado e nao executam SQL real.
Script live de preflight fica fora de `scripts/check_all.py` e nao deve ser
executado automaticamente.
Testes de auth usam fakes injetados, sem token real, rede, servidor, socket ou
provider live.
Testes ASGI usam harness em memoria, sem TestClient que abra socket, sem rede,
sem servidor e sem framework externo.
Testes Watson Flow usam FakeIamTokenProvider e FakeWatsonFlowClient injetados,
sem token real, sem API key, sem rede, sem servidor, sem SQL e sem provider
live.
Adapters Watson live nunca sao defaults. Nenhum import ou factory pode acessar
secret, IAM, Watson, rede, socket, servidor ou PostgreSQL. API key vem somente
de `SecretValueProvider` e nunca entra em request de dominio; `Authorization`
sempre e header sensivel materializado apenas no transporte. `check_all.py`
permanece offline. O script manual Watson exige confirmacao explicita para
rede, nao imprime body IAM/Flow, token, API key ou Authorization, nao segue
redirect, nao aceita TLS inseguro, nao usa proxy env e nao implementa retry
interno.
Testes de composition root Watson TEST usam FakeSecretValueProvider e
FakeHttpTransport. A composition root pode construir objetos live, mas isso
nao pode consultar secret, IAM, Watson, env, rede, socket, servidor,
PostgreSQL ou executar SQL. O runner offline pode simular IAM e Flow com fakes
e pode entrar no `check_all.py`; probe live nunca entra no `check_all.py`.
CI e `check_all.py` sao offline. `scripts/check_clean_room.py` e executado
separadamente para evitar recursao; quando ele chama `check_all.py`, o ambiente
clean-room desabilita `pip check`. O network guard e obrigatorio para testes
criticos e deve bloquear rede real apenas no subprocesso protegido. O launcher
CMD nao armazena secrets, nao usa `setx`, nao faz retry, nao limpa variaveis da
sessao CMD pai quando usa `setlocal` e deve recomendar a limpeza manual
`set "IBM_CLOUD_API_KEY="`. O launcher prefere
`.venv\Scripts\python.exe`; se a venv nao existir, pode usar um `python.exe`
valido no PATH, como no CI com `actions/setup-python`. Ele nunca cria venv,
nunca instala dependencias, nunca chama pip e falha antes de qualquer operacao
quando nao ha Python valido. Em maquina operacional, recomenda-se usar a
`.venv`; usar PATH nao implica isolamento de dependencias. Probe live e sempre
uma tentativa unica, fora do CI, sem cache, retry, backoff ou probe automatico.
Failure rehearsal usa somente fakes. Workspace hygiene e dependency checker sao
obrigatorios e operam offline, sem apagar arquivos e sem consultar PyPI.
