# 28/10/2026 — G5 REAL RESTORE ISOLADO FALHOU; CAUSA AINDA NAO IDENTIFICADA

**Operador VPS executou o primeiro ensaio real autorizado** do arquivo criptografado SOURCE `nywxpvzhlpqjtcafpdfe` em PostgreSQL 17 isolado, após `--plan` PASS e confirmacao local. Retornou `G5_REHEARSAL_RESULT=BLOCKED`, `G5_REHEARSAL_ERROR=ISOLATED_RESTORE_SQL_FAILED`, `G5_RESTORE_TEST=NOT_VERIFIED`. O original descartava stderr do pg_restore: NAO e comprovado se faltou extensao, role, privilegio ou outro requisito. Nao afirmar restore nem aposentar SOURCE. Como a excecao foi devolvida apos `cleanup_container`, a remocao do container foi confirmada pelo script; caso contrario seria `ISOLATED_CLEANUP_UNVERIFIED`. Nenhum Supabase foi alterado. Backup cifrado original SHA PASS, senha/GPG PASS, TOC 811 entradas PASS.

**Correcao em andamento:** `scripts/operations/g5_restore_isolated_rehearsal.py` deve drenar stderr do pg_restore SOMENTE em memoria e expor apenas uma categoria sanitizada fixa (extensao, role, dependencia, permissao, conflito, recurso etc.). Mantem `G5_RESTORE_TEST=NOT_VERIFIED` e erro bloqueado; **nunca imprimir SQL, objeto, DSN, erro bruto, senha ou dados**. Ensaiar nos testes offline e CI antes de qualquer nova tentativa. Um ensaio diagnostico posterior continua em container isolado com confirmacao typed; nunca autorizar importar no DEMO/SOURCE, desativar n8n, alterar roles/DSN ou pular objetos para tornar testes verdes.

**Permanecem pendentes:** restauração integral real aprovada, cópia cifrada fora da VPS comprovada e custódia, inventario das dependencias SOURCE (n8n oficial com 9 bindings, Shadow persistence, Vercel), portabilidade, hardcodes n8n, paridade e cutover humano. `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. Evidencias e limites em `docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md`, issue #155.

---

# 28/10/2026 — G5: BACKUP REAL LEGIVEL, RESTAURACAO ISOLADA AINDA NAO EXECUTADA

**Ultima evidencia operador VPS:** `G5_ARCHIVE_DECRYPTION=PASS`, `G5_PG_RESTORE_TOC=PASS`, `G5_PG_RESTORE_TOC_ENTRIES=811`, `G5_DECRYPTED_ARCHIVE_BYTES=25905751`, `G5_RESTORE_TEST=NOT_PERFORMED` no arquivo criptografado SOURCE `nywxpvzhlpqjtcafpdfe` capturado e SHA-256 PASS. O teste confirmou a senha e leitura integral do catalogo, mas **NENHUMA SQL do arquivo foi restaurada em qualquer PostgreSQL**. PR #188 mergeada no GitHub, SHA `4f189574a92816d9693a4a3c4557eb0a60beb643`.

**Proxima entrega em codigo (sem executar restauracao):** `scripts/operations/g5_restore_isolated_rehearsal.py` usa Docker PostgreSQL 17 ja em cache, sem rede/portas, sem bind/volumes de host, rootfs read-only, tmpfs, menor privilegio e limite de recursos. `--plan` verifica apenas readiness. `--restore` exige **nova autorizacao explicita do operador** e confirmacao tipada, senha offline e destrucao verificada do container; falhar em qualquer extensao/grant/DDL interrompe e NUNCA declara restauro concluido. Ver `docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md`. O script nunca aponta para SOURCE/DEMO ou executa SQL financeira real fora da sandbox.

**Persistem como bloqueios:** copia segura do arquivo cifrado fora da VPS ainda nao atestada, recuperacao logica integral/roles/Auth/Storage/Edge ainda nao homologada, 9 referencias SOURCE no n8n oficial, Shadow LangGraph DSN SOURCE, Vercel databases nao atestados, tenant real sem membership e cutover/hardcodes ainda nao certificados. **Nao** realizar restore, mudanca n8n/Supabase/DSN/roles, SQL financeira em Shadow, cutover ou remocao SOURCE implicitamente. `OFFICIAL=n8n`, `SHADOW=LangGraph` e `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.

---

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

# STATUS EXECUTIVO / PRIORIDADE IMEDIATA — 26/10/2026

**Única entrega ativa: P1 = prova real de geração no caminho n8n candidato → LangGraph → Gemini, sem execução SQL financeira.** O passo seguinte é P2 (correlação Produto autenticado); a execução financeira read-only/role G1 é P3. [Plano operacional e regra anti-desvio](docs/operations/DELIVERY-FOCUS.md); [roadmap #155](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/issues/155).

**Fatos confirmados:** GitHub `main@e7ccff858506097e02c3e5d89ecb0016a9180664`, PR #172 mergeada; auditoria real na VPS sob `HEAD=e7ccff8`: `G1_PUBLIC_TEMPORARY=TRUE`, `G1_PUBLIC_CREATE=FALSE`, `G1_TARGET_ROLE_EXISTS=FALSE`, `G1_AUDIT_RESULT=REVIEW_REQUIRED`; nenhum banco alterado pela auditoria. Produto Demo Vercel último deployment Production consultado em `READY` no commit `7d784ec14568599049f039532805905036c52705` (PR #31). **Não foi feita nova verificação n8n/LangGraph vivo nesta atualização**; a condição publicada/healthy permanece último relato, a confirmar antes do teste.

**O que ainda NÃO foi provado:** geração real com Gemini via n8n candidato e LangGraph; execução completa Produto→n8n→LangGraph com `agent_run_id/run_id/shadow_record_id`; paridade financeira ou multicliente real. `G1_CORRELATED_EXECUTION=NOT_TESTED`. Shadow Production segue desabilitado segundo último diagnóstico autenticado; nenhuma nova leitura autenticada do valor da flag nesta atualização.

**Decisão de foco:** não usar `/api/generate-sql` da Demo para o teste P1, pois o fluxo oficial gera **e pode executar** SQL. O problema de `PUBLIC TEMPORARY` não será ignorado nem resolvido por revogação global sem aprovação: é bloqueador para rollout read-only e execução P3, **não para P1 em modo generate-only isolado**. Antes de P1 com Gemini real, confirmar ambiente e obter autorização de custo/chamada; `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` permanece obrigatório. Não realizar benchmark 63, SQL financeira, deploy, migração ou alteração de permissões por efeito deste documento.

**Próximo bloco:** pré-verificar candidato n8n e runtime LangGraph TEST, confirmar rota de geração isolada e evidência, e executar **uma** pergunta inédita via Gemini quando autorizada; registrar o erro real encontrado e corrigi-lo até obter SQL validada e evidência correlacionada. Arquivos/ensaios offline não fecham P1/G1.

> As seções datadas abaixo são **histórico**, não substituem esta prioridade. Não reabrir etapas concluídas sem evidência nova.

---

## Gate G1 — preflight real no Supabase DEMO: PUBLIC TEMPORARY bloqueia criação (25/10/2026)

- **Evidência real fornecida pelo operador** em `main@76b9e70`: VPS PostgreSQL com `psycopg[binary]==3.3.4` e CA oficial Supabase Root 2021 válida; `--dry-run` (sem escrita) passou `G1_ROLE=NOT_APPLIED`, `G1_N8N_BINDINGS=PREFLIGHT:0eee554daf77`, `G1_ROLLBACK=READY`.
- Auditoria SQL catalogal **read-only** do projeto financeiro confirmou `G1_PUBLIC_TEMPORARY=TRUE`, `G1_PUBLIC_DATABASE_CREATE=FALSE`, `G1_PUBLIC_ACL_CHECK=PASS`. Qualquer nova role herdará `TEMPORARY` por `PUBLIC`. `NOINHERIT` ou `REVOKE ... FROM` apenas da role não resolve.
- **Correção candidata desta PR:** `--dry-run`/ `--apply` verificam ACL efetiva `PUBLIC` no database antes de `CREATE ROLE`; falham fechado caso `TEMPORARY` ou `CREATE` esteja ativo. Testes offline simulam ACLs, bloqueio de criação, inexistência de POST n8n e fluxo positivo preservado.
- **Não autorizado:** `REVOKE TEMPORARY ON DATABASE postgres FROM PUBLIC` ou qualquer alteração global de grants, permissões n8n ou migração. Depende de inventário de impacto, plano de rollback e decisão explícita. Nenhuma alteração de banco/n8n/Shadow executada por esta PR. `OFFICIAL=n8n`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`, `G1_CORRELATED_EXECUTION=NOT_TESTED`.
- **Evidência e detalhes:** `docs/runbooks/g1-readonly-single-step-operator.md`; acompanhamento operacional [#155](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/issues/155). Não confundir PASS de TLS/preflight antigo com homologação G1.

---

## Gate G2 — inventário integral de encaminhamento (2026-10-23, snapshot do operador)

- Inventário sanitizado de **68 nós** do JSON fornecido pelo operador em 20/10: `docs/audits/n8n-official-68-node-externalization-ledger.md`.
- Grafo estático do arquivo: **60 nós alcançáveis**, **8 inalcançáveis**; os oito não comprovam comportamento ativo. Triagem por responsabilidade com candidatos FORBIDDEN, TRANSITIONAL e STRUCTURAL; não é auditoria de cada expressão nem reconciliação com `--published`.
- Principal direção: externalizar métricas, aliases, filtros, schema, prompt, planos e relatórios em contexto versionado; **não** transportar os hardcodes do cleaner para LangGraph. Cache/credenciais/tenant e pré-aprovação exigem gates próprios.
- **Candidata nesta branch:** o adapter PostgreSQL agora aceita mapeamento configurável de nomes das tabelas semânticas e DRE opcional via `CONTEXT_CATALOG_TABLES_JSON`, preservando o default antigo. Testes offline exercitam dois contextos físicos distintos e validação contra injeções. **Ainda não há implantação nem comprovação de paridade multicliente em bancos reais.** Enforcements de RBAC/tenant não foram implementados neste loader; continuam pendentes.
- Workflow oficial e versões/credenciais runtime não foram alterados por este inventário. G1/G2 e paridade financeira continuam pendentes.

---

## Gate G1 — evidência operacional observada em 2026-10-21 (UTC)

- Na VPS, o operador confirmou n8n **2.4.8**, um contêiner detectado,
  CLI `n8n import:workflow` disponível e
  `LANGGRAPH_SHADOW_INTERNAL_BASE_URL` **ausente** no ambiente do n8n.
  O teste foi read-only; não identifica importação ou ativação do candidato.
- Último Shadow TEST operacionalmente validado pelo operador: imagem e
  runtime `136da3419a18ec79bf67b5d42fcb7b3acdce16ba`,
  `SEMANTIC_AGENT_VERSION=demo-finance-v9`, Gemini configurado,
  execução SQL real desativada e conectividade n8n→Shadow confirmada.
  A inspeção local posterior mostrou checkout VPS também nesse commit.
- O GitHub `main` avançou para `d4f6718e0cb333fdadc0dfa94060cb629cc4fbe8`
  pela PR #143 (transporte opcional de `llm_selection`). **Esse commit
  não foi confirmado como implantado na VPS**; apenas o candidato n8n
  versionado mudou. Não há motivo para trocar o runtime sem evidência.
- A Demo `demo/grupo-horizonte` recebeu a PR #17 no commit
  `687447c8314d6706d9853fc595a262316afeb3ca`, com deploy Vercel
  READY. As variáveis `LANGGRAPH_SHADOW_TRANSPORT`,
  `LANGGRAPH_SHADOW_N8N_WEBHOOK_URL` e
  `N8N_SHADOW_WEBHOOK_TOKEN` ainda não constavam no inventário de
  configuração da Demo; nenhuma ativação foi comprovada.
- Gate G1 continua **pendente**: workflow paralelo de sete nós não
  comprovadamente importado/ativo, sem correlação real Produto→n8n→
  LangGraph e sem prova de paridade financeira. n8n + Gemini **oficial**
  permanece intocado.
- Para n8n 2.x, o template candidato usa `$env` nas URLs internas, cuja
  disponibilidade pode estar bloqueada por padrão. O renderizador
  `scripts/n8n/render_parallel_shadow_workflow.py` prepara um arquivo
  privado/inativo com destino interno autorizado **sem alterar a proteção
  global de ambiente n8n**. A preparação é offline e não autoriza a
  importação, credenciais, ativação ou qualquer chamada paga.
- Importação/publicação do workflow, credenciais, configuração Vercel,
  uso real de LLM e execução SQL read-only continuam exigindo suas
  autorizações separadas. Não considerar G1/G2/G3 concluídos pelo CI.

---

## Rastreabilidade de provedor/modelo na comparação Shadow — candidato

A nova comparação expõe apenas identificadores sanitizados de
`sql_generation_result` (e reparo quando presente), retirados da
evidência persistida/fingerprint-validada. O Produto pode confrontar
esses identificadores com `llm_provider` e `llm_model` do run
oficial, sem passar resultado oficial ao gerador, criar aliases
hardcoded ou gastar LLM. Isso **não** prova Gemini paritário quando
a configuração do runtime não foi verificada. Integração real G1/G3
permanece pendente; `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.

---

## Comparador pós-geração proposto — 2026-10-20

Implementação candidada: `POST /v1/internal/sql-agent/compare-shadow-sql`,
atrás da autenticação interna S2S atual. Compara SQL **oficial já gerada**
com a SQL LangGraph previamente persistida, usando o mesmo `agent_run_id`,
`shadow_record_id`, pergunta e identidade de principal/tenant autorizados.
Diferenças estruturais de tabelas, joins, filtros, projeções,
agregações e ordenação são reportadas sem retornar a SQL, nomes
físicos ou literais. A comparação não chama gerador, LLM nem executor.
`normalized_sql_match` **não** significa paridade financeira.
A falta de tenant identificado impede alegar isolamento completo.
Integração no Produto e paridade financeira seguem pendentes.

---

# PROJECT-STATUS.md

## Estado operativo reconciliado em 2026-10-19

> Atualiza o **objetivo** e os **próximos gates**, sem reescrever evidências
> históricas de 2026-10-07 abaixo. Fontes normativas:
> `AGENTS.md`, `CHATGPT-PROJECT-INSTRUCTIONS.md`,
> `ORCHESTRATION-STRATEGY.md` e
> `docs/architecture/PORTABILITY-AND-CUTOVER-CONTRACT.md`.
> Estado operacional precisa ser reconfirmado no GitHub/VPS em cada sessão.

**Objetivo de entrega fechado pelo operador:** (1) n8n+Gemini oficial e
n8n+LangGraph+Gemini Shadow até paridade funcional e portabilidade;
(2) substituir o **mecanismo inteligente** antigo do n8n, mantendo n8n como
orquestrador e Gemini como LLM, somente com gate humano/rollback;
(3) comparar Gemini vs SQL-InfoDive na mesma arquitetura homologada.

**Restrição principal:** não transportar hardcodes financeiros dos nós n8n
para LangGraph; inventariar `STRUCTURAL/TRANSITIONAL/FORBIDDEN` nos fluxos
reais e externalizar conhecimento cliente-específico em contexto
versionado. Demonstrar portabilidade com pelo menos dois clientes/datasets
materialmente diferentes sem mudança no motor.

### Evidência de código e testes observada

- `main` observada nesta atualização: commit
  `b1d6800623faef7e6d62735c38a9a64ef795aeec`
  (PR #132 mergeada; não implica Shadow v18 ativada).
- Comparação v16 × v17 enviada pelo operador: **125/146** na v17 vs
  **118/146** na v16, sem regressões entre contextos no motor da v17.
  Houve **deriva entre versões do motor** em conjuntos anteriores;
  nenhum desses números comprova geração SQL/resultado financeiro.
- Candidata `demo-finance-v18` existe como overlay virtual e código
  mergeado; **a comparação read-only de 182 casos com v17 não foi
  comprovada nesta atualização**. Exigir saída real da VPS antes de
  declarar aprovação. Não ativar contexto automaticamente.
- A linha oficial n8n + Gemini serve de baseline posterior; a
  equivalência real entre os dois **fluxos completos** ainda requer
  evidência integrada e resultados SQL/read-only autorizados.
- `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` continua obrigatório para o
  Shadow atual. Nenhum cutover autorizado.

### Evidência adicional para G2 — inventário n8n exportado (2026-10-19/20)

Uma exportação **histórica** do workflow n8n está versionada no produto
`leandrosilveiradepaula/Agente-Financeiro`, arquivo
`workflows/n8n/agente-sql-financeiro-ducklake/Agente SQL Financeiro DuckLake - v2.2.31-stable-preflight-retry.json`
(blob `5c385ee2718f73e74d24c59fa6afbeed3c3570fd`, último commit
`d8897b347ca4fe8a79aa8ffc14e80b4ecd28143a` em 2026-07-20).

O inventário preliminar `docs/audits/n8n-legacy-workflow-v2.2.31-inventory.md`
indexa 75 nós e documenta **13** nós com hardcodes FORBIDDEN
comprovados no legado: classificação/aliases, prompt SQL, planner, gates
semânticos de DRE, schema e filtros fixos, e relatórios financeiros. O
script `scripts/audit_n8n_workflow_export_readonly.py` permite comparar
exportações locais sem reproduzir SQL, prompts ou credenciais. A revisão
estendida confirmou sete outros nós hardcoded no mesmo snapshot histórico,
incluindo reescrita automática de SQL no cleaner, tabelas fixas em gate e
inferência duplicada de métricas/dimensões. O comparador agora acompanha
deriva de topologia e configuração runtime além dos parâmetros. Nenhum dado
desse legado deve ser transplantado para código LangGraph.

**Importante:** não foi acessado/alterado o workflow ativo na VPS, e a
exportação arquivada não prova paridade nem que este é o fluxo oficial atual.
G2 continua aberto até reconciliar com exportação ativa e externalizar as
regras; G1 e G3–G6 permanecem abertos.

### Próxima evidência operacional preparada — published n8n

Script de coleta manual: `scripts/audit_n8n_published_workflow_readonly.sh`.
Seleciona **somente a versão publicada** usando `n8n export:workflow --published`
via Docker local, exige ID e contêiner autorizado, guarda o JSON bruto em
arquivos temporários privados, valida unicidade/identidade, entrega somente
fingerprints e contagens, e remove o bruto antes de imprimir resultados.
`scripts/audit_n8n_workflow_export_readonly.py` foi ajustado para aceitar
exportação singleton e mascarar **todos** os nomes de nós, inclusive segredos
não óbvios. Os testes sintéticos permanecem no CI offline.

Procedimento e cautelas: `docs/audits/n8n-published-workflow-readonly-runbook.md`.
**Este PR não executa o script na VPS, não verifica workflow vivo e não
habilita SQL real.** G1 e G2 continuam com evidência pendente.

Verificação cross-repo no produto `leandrosilveiradepaula/Agente-Financeiro`
atual na investigação: `app/api/generate-sql/route.ts` usa n8n como
caminho oficial e dispara LangGraph após a resposta via `after()` somente
quando `LANGGRAPH_SHADOW_ENABLED=true`. `lib/langgraph-shadow-read-client.ts`
e a UI mostram metadados Shadow, mas **não demonstram equivalência de
SQL/resultados**; `lib/n8n-endpoint.ts` ainda possui URL fallback fixa
para uma instância, um risco de configuração/portabilidade que deve ser
tratado **após confirmação de ambiente**, sem quebrar produção por inferência.

### Observação de deployment do Produto (Vercel, apenas leitura)

Inspeção da Vercel no escopo de equipe autorizado retornou dois projetos
distintos, não confundíveis: `agente-financeiro` e
`agente-financeiro-demo`. O deployment de produção READY mais recente
listado para o primeiro usa `leandrosilveiradepaula/Agente-Financeiro`
commit `d2f01a836cf3c12a478011f07a8e06a0065ae086`. O segundo
retornou deployment READY do branch `demo/grupo-horizonte`, commit
`364a7a2d54508043cc03c6027badb8f702dcafdd`.

Ambos registram a chave de configuração `LANGGRAPH_SHADOW_ENABLED`
nos ambientes de projeto observados; a Vercel **não revelou o valor
efetivo dessa chave em deployment** (variável sensível). Portanto,
`LANGGRAPH_SHADOW_ENABLED` **não pode ser declarado ligado/desligado**
a partir desses resultados, nem é possível atestar o alcance do webhook
n8n ou a efetiva presença de `agent_run_id` correlacionado.

A fase G1 exige conferir o deployment/tenant **correto** do Produto e
um par de evidências n8n/Shadow produzido por fluxo real e autorizado.
Esses acessos foram estritamente de leitura; não houve alteração de
Vercel, n8n, SQL, LLM ou variáveis de ambiente.

### Estado dos gates finais

| Gate | Situação verificável nesta atualização |
|---|---|
| G1 — dispatch e evidence oficial/Shadow end-to-end | Prova isolada documentada, paridade operacional completa **não comprovada** |
| G2 — inventário n8n + eliminação FORBIDDEN + 2 contextos | **Parcial:** 75 nós de exportação histórica indexados; 13 FORBIDDEN comprovados no arquivo; VPS ativa e 2 contextos pendentes |
| G3 — Gemini equivalência semântica/SQL/números | **Pendente:** avaliações semânticas não validam respostas financeiras |
| G4 — segurança, execução autorizada, approvals/rollback | **Não homologado para cutover** |
| G5 — substituição controlada do caminho inteligente n8n | **Não autorizada / não realizada** |
| G6 — Gemini × SQL-InfoDive | **Fase posterior, não iniciada como comparação de qualidade** |

### Próximos passos por valor de conclusão

1. Reconciliar o estado atual do GitHub e a comparação v17 × v18
   read-only, sem promover versão por percentual de testes.
2. Inspecionar **workflows e prompts do n8n realmente usados**;
   inventariar hardcodes com classificação, fonte, destino versionado,
   prova de comportamento e critério de aposentadoria.
3. Validar o fluxo real de SQL Gemini do LangGraph com evidências e
   segurança, depois comparar com o fluxo n8n+Gemini na mesma pergunta.
4. Propor, para autorização humana, teste read-only isolado de
   equivalência numérica e critérios formais de aceitação; preservar
   execução real desabilitada no Shadow até decisão separada.
5. Construir prova multicliente, canário e rollback antes do cutover.
6. Comparar provedores apenas após homologar o fluxo final com Gemini.

**Sem alterar a arquitetura por inferência:** a LLM privada pode estar
hospedada em nuvem; isso não significa reintroduzir o adapter Watson/IBM IAM
ou trocar modelo na Fase 1.

---

## Snapshot histórico — 2026-10-07

Date: 2026-10-07

Branch: `main`

HEAD before PR #36: `8160b35da14329f9c6bb369d8812d0881730e0ba`

## Current State

LangGraph has not replaced n8n.

The governed architecture remains hybrid:

```text
Product / Next.js
+ n8n as official operational orchestration
+ LangGraph as semantic/reasoning core in shadow
```

Responsibilities remain separated:

- Product: interface, authentication, authorization, policies, history and observability.
- n8n: webhooks, integrations, deterministic orchestration and operational execution.
- LangGraph: semantic interpretation, intent resolution, context selection, planning, SQL generation/validation, repair proposal and evidence.

No implicit cutover is authorized.

## Operational Authority

Current authority is:

- OFFICIAL = n8n;
- SHADOW = LangGraph;
- real_sql_execution = false for LangGraph shadow.

LangGraph shadow must not alter the official answer and must not execute repaired or modified SQL silently.

Generate SQL, repair proposal and execute-approved remain separate lifecycle stages.

## LLM Status

Gemini remains the comparison provider used by the current benchmark baseline for both OFFICIAL and SHADOW so semantic architecture can be isolated from local-model quality.

Connectivity to the Infodive local provider has been validated separately:

- provider: `infodive_local`;
- model: `sql-infodive`;
- transport: OpenWebUI/Ollama over VPN.

This validates connectivity only. It does not claim semantic parity.

## Benchmark Baseline

The latest measured 63-question benchmark remains the pre-v9/v10 baseline:

- OFFICIAL: 59/63 approved = 93.65%;
- SHADOW technical success: 8/63;
- SHADOW rejected: 55/63.

Primary baseline rejection groups:

- 21 `INTENT_RESOLUTION_MINIMUM_SCORE_NOT_REACHED`;
- 18 `INTENT_RESOLUTION_AMBIGUOUS`;
- 10 `SQL_CONTRACT_JOIN_VIOLATED`;
- 3 `SQL_SECURITY_UNAUTHORIZED_TABLE`;
- 2 `INTERNAL_GENERATE_QUESTION_REQUIRED`;
- 1 `SQL_CONTRACT_AMBIGUOUS_COLUMN`.

This baseline must not be used as generation context or question-to-SQL lookup.

No claim is made yet that v9/v10 improved these counts because the 63-question regression has not been rerun after the new semantic context work.

## Recent Structural Changes

Merged changes include:

- provider failure reasons sanitized for observability;
- multiline/tab/CRLF question contract handling;
- safe intent-resolution and QueryPlan metadata;
- semantic intent coverage inventory;
- safe Security/Contract Gate diagnostics;
- planner join filtering now rejects join rules that reference unselected tables;
- `PLANNER_VERSION = v1.3.0-selected-table-join-filtering`.

The planner join correction is a confirmed structural bug fix. Correlation with historical unauthorized-table failures still requires post-change evidence.

## Semantic Context Versions

### v8 planned-filters

`semantic_context/demo_planned_filters_v8.delta.json` remains declarative and unapplied.

- `automatic_apply=false`;
- `activation.allowed=false`;
- Receita has a versioned binding;
- Custos is explicitly scoped as `CMV_ONLY`, backed by versioned evidence and an approved human decision;
- OPEX / `dre_despesas_operacionais` remains `BLOCKING_FAIL_CLOSED`.

The v8 delta is not the active runtime context.

### v9 period coverage

Migration merged:

`scripts/migrations/010_prepare_semantic_period_coverage_context_v9.sql`

Purpose:

- extend `metric_total_by_period` to explicit years, months, quarters and semesters;
- keep existing resolver scores and thresholds;
- remain context-driven rather than Python hardcode.

The migration is merged in source control but this status does not claim it has been applied to PostgreSQL or activated in Shadow.

### v10 curated intents

Migration merged:

`scripts/migrations/011_prepare_semantic_curated_intents_context_v10.sql`

Purpose:

- derive from v9;
- persist the 9 curated specialized `intent_definition` records from `semantic_context/intent_catalog_curado_v1.json`;
- preserve `metric_total_by_period`;
- remove dependence on a local in-memory overlay for those definitions.

The 9 curated definitions have no physical `target_table`, `target_column` or `sql_filter_hint` contract in the definition itself.

The migration is merged in source control but this status does not claim it has been applied to PostgreSQL or activated in Shadow.

## Intent Catalog Coverage

The curated catalog currently contains 9 specialized intent definitions:

- `resultado_por_marca`;
- `opex_por_marca`;
- `opex_por_centro_custo`;
- `orcado_vs_realizado`;
- `estouro_orcamento`;
- `dre_mensal`;
- `comparativo_marcas`;
- `impacto_setor_marca`;
- `responsavel_centro_custo`.

The generic semantic evolution also contains `metric_total_by_period`.

The live validator now inventories query-pattern intents versus intent-catalog definitions and reports missing coverage rather than silently treating examples as lookup.

## Security and Least Privilege

Shadow governance remains:

- `langgraph_shadow`: only required evidence persistence privileges; no DELETE;
- `langgraph_context_reader`: SELECT-only on authorized semantic context tables; no benchmark access and no writes.

No privilege expansion is authorized by v9/v10.

## Observability

Preserve and correlate:

- `agent_run_id`;
- LangGraph `run_id`;
- `shadow_record_id`;
- fingerprints;
- semantic/context versions;
- provider/model;
- token usage when available;
- status/gates/timeline;
- correlation metadata;
- sanitized provider failure reason;
- intent-resolution diagnostic;
- QueryPlan diagnostic;
- Security/Contract Gate structural diagnostic.

Do not persist or expose secrets, DSNs, authorization headers, cookies, API keys or unnecessary raw provider responses.

## Closed Decisions

- n8n remains strategic and is not being replaced.
- deterministic/operational work stays in n8n.
- semantic/agentic reasoning belongs in LangGraph.
- Product remains authority for UI, authn/authz, policies and history.
- benchmark fields are evaluation-only and must not reach generation prompts.
- business question examples are semantic signals only, never lookup.
- business knowledge belongs in versioned context/configuration, not new Python/TypeScript hardcode.
- repaired SQL loses approval and requires reapproval.
- Shadow remains non-executing until explicit promotion decision.

## Current Risks

- v9/v10 are merged in source control but still require controlled PostgreSQL application and read-only live validation before Shadow can select v10.
- The live catalog validator needed adaptation because v10 persists the curated definitions instead of relying only on overlay; PR #36 addresses this.
- OPEX planned-filter semantics remain fail-closed pending evidence-backed multi-group binding.
- Technical success still does not prove semantic correctness.
- Historical JOIN/security failures must be remeasured after the planner correction and new gate diagnostics.
- Local `sql-infodive` connectivity is validated, but semantic quality remains a separate test phase.

## Next Stage

Proceed in this order:

1. merge and validate PR #36;
2. apply v9 then v10 migrations to the semantic context store without changing OFFICIAL n8n;
3. run the live read-only catalog/context validator against v10;
4. switch only the LangGraph Shadow semantic context version to v10;
5. run a small set of new, semantically varied questions to verify generalization and evidence;
6. only then rerun the 63-question regression for measurement;
7. compare rejection distribution and semantic quality against the recorded baseline;
8. keep `real_sql_execution=false` until a separate explicit promotion decision.

No cutover is claimed.

## Architecture Decision — Watson / IBM Cloud Removal

As of 2026-10-07, Watson and IBM Cloud are removed from the target architecture. The supported direction is Product + n8n + LangGraph with configurable LLM providers. Generic Generate, Repair, Preflight and Execute-Approved contracts remain, but no Watson-specific adapter, IBM IAM dependency, probe, test or runbook is part of the runtime target.

## Gate G1 — prepared read-only binding verification (2026-10-21)

- Operator reported the three n8n credentials configured on the newly imported
  seven-node candidate `LwUsMRWi34D2ARWu1YzgV`. Browser read confirms
  seven node labels and a **Publish** button, not credential attachment or
  successful authentication. The 68-node official workflow was not changed.
- Added a fail-closed draft-export binding audit for the exact candidate ID.
  It checks inactive state, node/code/topology drift, two distinct credential
  boundaries and private Docker endpoint without printing credential IDs,
  names, secrets or node code. Synthetic offline negative tests cover
  missing/misbound credentials and unsafe changes.
- **Operational evidence pending:** the audit has not run on the VPS;
  n8n credential *values* and S2S authorization are not validated. No
  workflow publication, HTTP 202, persisted correlation, real SQL, LLM call,
  numeric parity or cutover is implied by this code change.
