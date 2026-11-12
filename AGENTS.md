## DECISÃO DO OPERADOR — CONTINUIDADE AUTÔNOMA E SÓ RESULTADO FINAL (11/11/2026 23:56 UTC)

**Não interromper uma execução substancial com mensagens de progresso, desculpas ou pedido de `prossiga`.** O operador quer **somente o resultado final**, depois de completar todo o trabalho técnico seguro executável naquele turno. Não alegar trabalho em segundo plano, prometer entrega futura ou fazer alterações sujeitas a gate humano; continuar autonomamente com GitHub e VPS até haver uma entrega funcional ou bloqueio externo incontornável. Se houver pausa técnica, resolver sem enviar relatório intermediário. Consultar o código e evidências reais a cada retomada.

**Entrega funcional desta execução:** implementado o mecanismo universal *multi-source fact stream → `UNION ALL` → aggregate* encontrado estruturalmente no nó n8n 22, com contexto versionado por tenant, granularidade, sinais, filtros, dimensões, SQL dinâmica e contrato SQL que **não aceita** semântica de união alterada. **Dois contextos sintéticos diferentes passaram** no LangGraph HTTP real em contêiner sem rede com adaptador estrutural injetado; nenhum LLM, DB financeira ou benchmark foi chamado. A documentação de mecanismo/evidências está em `docs/architecture/GENERIC-MULTISOURCE-METRIC-COMPOSITION.md`; `testar_metric_source_composition_e2e.py` (15) + `testar_canonical_composition_shadow_e2e.py` (3) e regressões aprovados. Evidência privada SHA `7d072603f211ad1fde940d809c366246bfa3c2cfdfda77a7b328ea89e6dc2db6`.

**Estado honesto:** capacidade **estrutural demonstrada somente em cenários sintéticos**; a migração financeira real permanece `IMPLEMENTED_UNPROVEN`/`NOT_PROVEN` porque o pacote G5 original da versão oficial contém 77 registros cifrados sem aprovação contábil. Não usar a DEMO como substituto, não inventar signo, fórmula, join ou coluna, não declarar paridade com n8n+Gemini. Sem deploy/migration/merge, n8n oficial não alterado, SQL real Shadow false. Expandir para outros comportamentos com a mesma abordagem, sem hardcode. O código do renderer está isolado, **não** substituiu o provider Gemini em produção.

---

## 11/11/2026 — FONTE DEMO NÃO É A SEMÂNTICA DO LEGADO (VERIFICAÇÃO REAL)

**Sem perguntar ao operador nem executar SQL financeira**, foram verificadas as duas fontes Supabase já conectadas. O projeto SOURCE original do Agente Financeiro está `INACTIVE` e sua API de esquema retorna indisponível. A DEMO está `ACTIVE_HEALTHY` e, além das 13 tabelas do schema `public` anteriormente examinadas, **possui as cinco coleções `ai_ducklake_*` no schema `semantic_context`** (regra, aliases, DRE, catálogo e padrões históricos). Na DEMO, SELECT agregado **somente de hashes de versão e contagens** sobre as quatro coleções de conhecimento — sem tocar as linhas de `sql_patterns` ou consultar valores financeiros — confirmou **10 versões**, totalizando 110 regras, 605 aliases, 130 DRE e 80 registros de catálogo. Os 10 hashes foram comparados ao manifesto G5 original na VPS: **0/10 versões comuns às 11 versões do G5**. A versão selecionada pelo workflow oficial permanece **somente no G5** (`7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485`).

**Consequência obrigatória:** jamais copiar a semântica da DEMO para substituir a fonte antiga ou declarar paridade só porque os nomes das cinco tabelas coincidem. O workflow n8n usa duas identidades de credencial PG: grupo G1 (nó 5 e outros de contexto/cache), grupo G2 (nós 66/67 preflight/executor); IDs separados **não provam** bancos nem autorizações iguais. As definições contábeis dos 77 registros da versão oficial permanecem cifradas e **não homologadas**; requerem custódia GPG legítima, que não deve ser contornada nem exigida ao operador como tarefa de rotina. Continuar engenharia reversa dos JS e mecanismos genéricos com as fontes disponíveis. SQL financeira real, alterações de banco, ativação de contexto, cutover e merges continuam bloqueados pelos gates humanos.

**Correção de CI:** no commit `86733408284d728caf91bc3735a24d6d6ab22de5`, o teste GPG trata Windows de forma *fail-closed* sem enfraquecer Linux POSIX. A suíte local (7 testes G5 + 16 de versão + 10 de crosswalk) passou; CI do HEAD deve ser reconfirmado. Acesso à VPS já está concedido: **não pedir comandos SSH ao usuário**.

---

## 11/11/2026 — ACESSO À VPS JÁ AUTORIZADO: NÃO TRANSFERIR OPERAÇÃO AO USUÁRIO

**Decisão explícita do operador:** o ChatGPT já dispõe do conector Agente Financeiro VPS e deve executar autonomamente nele as leituras, análises, inspeções, testes e verificações permitidas. **Não pedir ao operador para copiar/colar comandos SSH ou reiterar “autorize usar VPS”.** Tratar somente gates realmente indelegáveis (segredo de criptografia indisponível, aprovação contábil, alteração de privilégios/DB, execução financeira SQL, produção, merge e cutover) como bloqueios distintos. Acesso administrativo à VPS **não fornece automaticamente a senha GPG**; jamais procurá-la em locais não autorizados, contornar a criptografia ou solicitar envio de segredos pelo chat.

**Apuração do próprio agente:** fonte Supabase original do Agente Financeiro está `INACTIVE` e a API de schema respondeu indisponível; DEMO está ativa, mas as coleções G5 não foram encontradas entre as tabelas do schema `public` consultado. No acervo privado G5 examinado na VPS há 11 pacotes cifrados, índices/lineages/hints e evidências sanitizadas; **não foi verificado texto contábil legível**. Não tratar metadados de versões nem coincidências de nomes como mapeamento aprovado. Continuar reversão dos 68 nós e melhorias genéricas com ferramentas existentes, sem questionamento repetitivo.

**Falha real CI #233 identificada:** runner Windows `Full offline checks` rejeitou criação privada porque o teste tentava atestar `0700/0600` em sistema de arquivos sem semântica POSIX. Correção em `86733408284d728caf91bc3735a24d6d6ab22de5`: o utilitário G5 recusa persistência em Windows, o teste exige recusa segura, Linux mantém restrições. Testes locais 7 G5 + 16 reconciliação + 10 crosswalk PASS; revalidar CI do HEAD efetivo. Sem prova financeira nem SQL real.

---

## 11/11/2026 — M1 verificado: versão oficial única + fronteira de avaliação no loader

Foi verificado na VPS que os **cinco SELECTs de contexto do nó 5** fixam a mesma versão semântica, SHA-256 7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485. **Um único pacote do manifesto G5**, índice 10/11, tem exatamente esse hash: **77 registros** (18 regras, 40 aliases, 11 mapeamentos DRE, 8 registros de catálogo) e 48 hints. Na versão correta, **3 dos 8 bindings de tabelas do nó 22** têm match textual, todos AMBIGUOUS_TABLE_NAME; análise agregada entre versões indicava 4/8 e não pode servir de mapeamento contábil. Relatório privado SHA-256 e376d3a3555d67467b57ece1949af4d26e1ca622f54487fc922c7d921521fbea. Nenhum conteúdo contábil cifrado foi aberto ou aprovado.

No modo canônico (não no legado), app/domain/canonical_source_boundary.py bloqueia SQL pronta, exemplos de perguntas, notas livres e padrões sem proveniência estrutural aprovada, mesmo com flag historical_evaluation_sql_excluded=true: **correção efetiva**, não declaração. Testes de isolamento/negativas com dois clientes sintéticos passaram, sem LLM, SQL financeira, mudança n8n ou cutover. O bloqueio GPG real continua: próxima etapa é desbloquear **somente a versão selecionada** no terminal local e revisar seus 77 registros sob custódia. Ver docs/operations/G5-ACTIVE-VERSION-LOCAL-REVIEW.md. Isso não é prova financeira ou produto concluído.

---

# 2026-11-11 21:36 UTC — ORDEM VINCULANTE: PROVAR A MIGRAÇÃO FINANCEIRA REAL

**Missão única:** migrar a inteligência do Agente Financeiro EXISTENTE, estudando juntos o workflow n8n publicado (**68 nós, 78 conexões**) e as **11 versões semânticas do banco/backup G5**, para Produto + n8n (preservado) + LangGraph + Gemini. Não criar outro agente, não confundir com Factory/CRM, não copiar código/SQL/regras casuísticas ou hardcodes financeiros do n8n para Python/TypeScript.

**Próxima entrega, antes de mais infraestrutura/benchmark/documentação:** selecionar uma capacidade financeira **real** do legado e demonstrar rastreavelmente **nó/branch do n8n + regra/registro/versão G5 + significado financeiro validado → contexto semântico versionado por tenant → pergunta inédita → interpretação/plano LangGraph → SQL dinâmica generate-only e gates**. Depois expandir até cobrir os comportamentos necessários, preservando logs, cache, relatórios, aprovações e outros efeitos na camada correta. Sem vínculo contábil aprovado não afirmar migração.

**Zero hardcode e multicliente:** motor conhece processo, catálogo aprovado/versionado conhece o negócio. Sem nomes de clientes, tabelas, colunas, DRE obrigatória, métricas, aliases, joins, sinais, filtros ou fórmulas no código novo; clientes podem ter estruturas distintas e exigir adaptadores de dialeto. Significado contábil não comprovado gera falha segura/pendência humana. Testar pelo menos dois contextos materialmente diferentes e perguntas inéditas.

**Métrica de progresso por capacidade:** `NOT_MIGRATED`, `IMPLEMENTED_UNPROVEN` ou `PROVEN`, com SHA/PR, fonte, versão/fingerprint, teste, resultado e riscos. CI verde, número de documentos, 68 nós enumerados, mocks ou benchmark alto **não** provam migração. A estimativa de 12–20 semanas anterior foi **retirada**: não inventar novos prazos ou percentuais sem medição real.

**Benchmark e SQL histórica:** 63 perguntas oficiais e 106 padrões SQL históricos são **somente para avaliação cega posterior** n8n+Gemini versus n8n+LangGraph+Gemini, nunca exemplos, prompt, input do planner, SQL esperada ou resposta a copiar. Correção de divergência deve ser genérica, não por benchmark.

**Gates:** `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. `Generate`, `Repair` e `Execute Approved` separados; SQL reparada exige `requires_reapproval=true`. SQL financeira read-only para comparação numérica requer autorização separada em isolamento; merge, migração, alteração de DB/n8n/produção/permissões, custos e cutover são humanos. Gemini × SQL-InfoDive somente após cutover homologado.

**Retomada e execução:** verificar GitHub HEAD/PRs #230/#231/#233, CI, runtime VPS e fontes reais; trabalhar em blocos substantivos sem pedir `prossiga` a cada microtarefa. Não reauditar continuamente o que já foi provado. Relatar apenas capacidades com evidência real. Ler `MEMORY.md`, `docs/operations/FIRST-FINANCIAL-CAPABILITY-PROOF.md`, `docs/operations/LEGACY-N8N-DATABASE-MIGRATION-MAP.md` e o contrato de portabilidade.

**Baseline verificado antes desta atualização:** `main@955eda46015d35dbe44a40f9240b821b1f493201`, VPS checkout `87d167969345c3dfcf9deaf36e33ab07a1f9c890`, PRs #230/#231/#233 draft, n8n running, Shadow TEST healthy e execução financeira Shadow desabilitada. A PR #233 em `5b29a89036ac80c1a3a792e8184e96a91662ee5a` falhou no Windows no passo `Whitespace check` do roadmap; CI Linux PASS. Migração completa/paridade financeira **não demonstradas**.

---

# 2026-11-11 — DIRETRIZ VINCULANTE: MIGRAR O SISTEMA EXISTENTE INTEIRO (N8N + BANCO → N8N + LANGGRAPH)

**INSTRUÇÃO EXPLÍCITA MAIS RECENTE DO OPERADOR (prioritária):** o trabalho consiste em **engenharia reversa e migração funcional do Agente Financeiro que já existe**, e NÃO em criar um agente paralelo do zero, apenas elevar a pontuação de 63 perguntas, nem remendar isoladamente parsers/validadores. O alvo é **Produto → n8n (mantido) → LangGraph (inteligência) → Gemini**, com conhecimento financeiro **externalizado, segregado e versionado por tenant**, usando o comportamento real legado como fonte de estudo, **não como hardcode a copiar**.

**DUAS FONTES INDISSOCIÁVEIS DE ORIGEM** antes de afirmar qualquer equivalência:
1. **Fluxo n8n realmente publicado e alcançado pelo Produto:** inventariar **TODOS** os nós (export atualmente observado com 68), conexões, JS, prompts, SQL, condições, credenciais referenciadas (somente IDs/hash), webhooks, permissões, funções, regras, transformação de dados, erros, Gemini, aprovações e execução. Confirmar versão publicada, caminho real do webhook e execução correlacionada. Export histórico/draft não prova o caminho oficial.
2. **Banco e seu backup recuperado:** inventariar **TODOS** os catálogos semânticos, versões, esquemas físicos, relações, dimensões, métricas, aliases, regras, DRE quando existir, mapeamentos, joins, sinais, períodos, filtros, intenções, dados e procedência. Usar evidências G5 com custódia e integridade verificadas, em isolamento somente leitura; separar versões e tenants. Backup/cópia cifrada não comprova significado contábil; não cruzar versões silenciosamente.

**PASSO OBRIGATÓRIO ANTES DE NOVA CAPACIDADE:** construir matriz rastreável **cada nó/branch/prompts/consulta n8n → regra/objeto e versão do banco → função financeira e dependências → destino (n8n determinístico, LangGraph estrutural, catálogo versionado, Produto) → evidência e teste → risco/gap**. Classificar cada regra como STRUCTURAL, TRANSITIONAL ou FORBIDDEN; nenhum literal de negócio em código novo. Não declarar a análise do fluxo ou da base completa com base em flags heurísticas, contagens de tabelas ou seis termos isolados. Faltas de evidência financeira devem ser explicitadas, não preenchidas com suposições ou SQL esperada.

**IMPLEMENTAÇÃO E HOMOLOGAÇÃO:** reconstruir o comportamento completo preservando n8n como orquestrador, LangGraph para interpretação/planejamento/SQL/repair/gates, Produto para autenticação/aprovação/histórico e contexto versionado para semântica. Demonstrar SQL dinâmica para perguntas inéditas, dois contextos materialmente distintos, integração e correlação real do Shadow e paridade com n8n/Gemini. As **63 perguntas históricas** e SQL/respostas antigas são **somente avaliação posterior e cega**; nunca entrar no prompt, no planejador ou no contexto de geração. Não baixar thresholds nem criar pergunta→SQL.

**GATES OPERACIONAIS:** `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` até decisão explícita. Nenhuma alteração de n8n, banco, tenant, credenciais, permissões, produção, merge ou cutover por inferência. Execução de SQL financeira para equivalência numérica depende de autorização read-only separada com menor privilégio. Repair invalida aprovação e exige reaprovação. Gemini × SQL-InfoDive somente após cutover humano homologado. Preservar rastros sanitizados (IDs, fingerprints, commits, versões e evidências) sem publicar SQL bruta, prompts sensíveis ou credenciais.

**PROCEDIMENTO ANTI-DESVIO EM CADA CHAT:** (1) verificar `main`, PRs, CI, VPS e fonte n8n/backup reais; (2) ler este bloco, `MEMORY.md` e `docs/operations/LEGACY-N8N-DATABASE-MIGRATION-MAP.md`; (3) continuar a matriz, eliminar lacunas por investigação das **duas fontes** e então entregar implementação de jornada completa; (4) reportar progresso em **funcionalidades migradas e testes reais**, não quantidade de pequenos PRs/CI. Se evidência ou acesso estiver bloqueado, registrar bloqueio específico; não inventar conclusão nem solicitar sucessivos "prossiga".

---

# 28/10/2026 18:24 UTC — G5 RESTORE REAL PASS / SOURCE AINDA INELEGÍVEL À APOSENTADORIA

**EVIDÊNCIA DA VPS DO OPERADOR:** PR #193 mergeada (`18ca3fcd0227f3ed11bde0bc50ea0e400aa8e444`). Em contêiner rootless `supabase/postgres:17.6.1.136` SHA `f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00`, sem rede/host volumes, GPG→pg_restore com transação única e cleanup: `G5_RESTORED_TABLES=86`, `G5_ISOLATED_CONTAINER_CLEANUP=PASS`, `G5_RESTORE_TEST=PASS`, **`G5_SUPABASE_FULL_RECOVERY=NOT_ATTESTED`**. Restauração PostgreSQL isolada comprovada; **não declarar plataforma, Auth, Storage, Vault/chave, roles/grants, RLS, SQL financeira, paridade ou cutover concluídos**. Não houve alterações SOURCE/DEMO/n8n/Shadow.

**AUDITORIA SELECT-only em SOURCE e DEMO após o ensaio:** 86 tabelas atualmente na SOURCE (47 public, 27 auth, 8 storage, 1 vault, 3 outros); exatamente 86 encontradas na sandbox após pg_restore, confirmando cobertura por contagem de objetos, NÃO igualdade de linhas/dados. DEMO 75 tabelas (10 public, 27 auth, 8 storage, 1 vault, 26 outras). Ambos têm `auth.users`, `storage.buckets`, `storage.objects` e `vault.secrets` com zero registros. SOURCE `public` 47 tabelas sem RLS, 0 policies; DEMO `public` 10 tabelas com 3 RLS e 3 policies. **Não copiar esquema/identidades/ACL, autenticação ou regras de negócio da SOURCE sem mapeamento versionado e autorização.** 16 roles não-sistema SOURCE versus 21 DEMO; considerar grants/roles explicitamente, pois dump G5 usou `--no-owner --no-acl`.

**Evolução de segurança:** prova de RESTORE PASS ≠ custódia de arquivo fora da VPS ≠ recuperação de serviços ≠ migração para DEMO. O gate `scripts/operations/check_supabase_retirement_gate.py` está sendo fortalecido para exigir schema v2 com provas separadas: restore, cópia cifrada offsite, plataforma, identidades, isolamento de tenant, semântica, paridade, sincronização final, rollback, observação e aprovação humana. O verificador `g5_verify_encrypted_copy_readonly.py` confere SHA de cópia externa **sem fazer upload ou declarar custódia externa automaticamente**. Não executar transferências remotas antes de escolher local/destino aprovado.

**Controles imutáveis:** `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. SOURCE continua ativa, sem autorização para migration, mudança DSN/roles, n8n/Produto, cutover ou exclusão. Roadmap issue #155 e `docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md` têm as evidências. Evitar repetir ensaio G5 já PASS; próximo foco é proteger cópia externa e homologar dependências/final sync, sem hardcodes de cliente.

---

# 28/10/2026 — G5: EXTENSION CONTROLS EM SUPABASE PG17 4/4; BOOT-TEST ISOLADO EM PREPARACAO

**Evidencia REAL da VPS (apos PR #192):** a auditoria read-only do backup cifrado SOURCE `nywxpvzhlpqjtcafpdfe` teve `G5_ARCHIVE_TOC_ENTRIES=811`, `G5_ARCHIVE_EXTENSION_COUNT=4`, nomes `pg_stat_statements,pgcrypto,supabase_vault,uuid-ossp`. A imagem comunitaria `postgres:17` (SHA `31ba9c94a03ada9988f2bb493a22a75eef3a185884533e5cdbcd498ea835b08f`) faltou `supabase_vault`; a imagem `supabase/postgres:17.6.1.136` (SHA `f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00`) tem **todos os quatro controles de extensao** presentes, `G5_IMAGE_2_MISSING_COUNT=0`, `G5_IMAGE_2_EXTENSION_COVERAGE=FILES_PRESENT_NOT_RESTORE_PROOF`, `G5_RESTORE_TEST=NOT_PERFORMED`. **NAO afirmar restauracao concluida nem compatibilidade de roles, dados, funcoes ou chave Vault.**

**Entrega atual:** adaptador de teste G5 para imagem Supabase PostgreSQL 17 previamente cached e SHA pinada (sem if por cliente). Novo `--boot-test` deve somente confirmar initdb PostgreSQL 17 em container temporario, nonroot UID/GID descoberto na imagem, network=none, read-only, sem bind/volume/ports, PGDATA/socket/tmp em tmpfs e swap desativado, execucao de initdb estatico sem Supabase migrations nem chave Vault; limpeza verificada antes de PASS. Nao decrypt/restaurar SQL neste teste. `--restore` na nova imagem so depois de **nova autorizacao separada** e token `RESTORE-G5-SUPABASE-ISOLATED`. SQL raw do dump inclui objetos gerenciados Supabase, diferente do processo de export oficial schema+roles+data; se falhar, BLOQUEAR sem remover extensoes/tabelas nem baixar thresholds. Contrato de backup externo/off-VPS segue pendente.

**Arquitetura invariavel:** `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`; SOURCE e DEMO inalterados, n8n preservado, sem migracao de banco, roles, DSN, permissoes ou cutover. A SOURCE continua necessaria para dependencias legadas; ver `docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md` e issue #155.

---

# 28/10/2026 — G5 IMAGE PROBE BLOCKED ON SUPABASE PG17; RESTORE STILL NOT VERIFIED

**Operador executou preflight read-only** depois de PR #191 mergeada e baixou `supabase/postgres:17.6.1.136`; imagem local ID `sha256:f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00`. Auditoria em `postgres:17` e `supabase/postgres:17.6.1.136` interrompeu com `G5_EXTENSION_AUDIT_ERROR=IMAGE_EXTENSION_PROBE_INVALID`, `G5_RESTORE_TEST=NOT_PERFORMED`, **antes de pedir senha ou restaurar SQL**. A causa exata desse erro agrupado nao consta no log: nao atribuir a imagem vazia, nome invalido ou qualquer extensao sem teste.

**Correcao estrutural da auditoria:** de acordo com PostgreSQL 17, distinguir `extensao.control` (primario) de `extensao--versao.control` (secundario); arquivos auxiliares de versao nao sao extensoes adicionais, podendo conter pontos que a regex de nome primario rejeitava. Filtrar auxiliares antes da validacao dos primarios (sem ignora-los para fins de restore) e retornar erros separados, exclusivamente codigos fixos, se nao houver controls ou houver saida inesperada. Testes Linux POSIX simulam pg_config e primarios/secundarios; CI Windows/Linux. Proxima acao apos PR/CI/merge: REEXECUTAR somente a auditoria read-only contra as duas imagens em cache e enviar linhas `G5_`. Nao repetir `--restore`/alterar bancos/baixar mais imagens antes da evidencia.

**Ja comprovado:** arquivo SOURCE cifrado SHA PASS, GPG/decrypt PASS, TOC 811; quatro extensoes `pg_stat_statements`, `pgcrypto`, `supabase_vault`, `uuid-ossp`; imagem comunitaria `postgres:17` SEM `supabase_vault` e bloqueio real `EXTENSION_UNAVAILABLE`. A segunda imagem Supabase ainda nao tem coverage comprovada. SOURCE/DEMO/n8n/Shadow inalterados. G5 restore integral, copia off-VPS, Vault key e dependencias/cutover permanecem pendentes. `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. Ver `docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md`, issue #155.

---

# 28/10/2026 — G5: EXTENSION_UNAVAILABLE REAL, RECUPERACAO SOURCE AINDA BLOQUEADA

**Operador executou segundo teste de restore isolado autorizado na VPS**, com PR #190 mergeada e stderr classificado somente em memoria. Resultado real: `G5_REHEARSAL_MODE=RESTORE`, `G5_IMAGE_CACHED=YES`, `G5_REHEARSAL_RESULT=BLOCKED`, `G5_REHEARSAL_ERROR=ISOLATED_RESTORE_SQL_FAILED`, `G5_RESTORE_FAILURE_CATEGORY=EXTENSION_UNAVAILABLE`, `G5_RESTORE_TEST=NOT_VERIFIED`. O motivo e uma extensao ausente no contêiner PostgreSQL 17 comunitario, mas o **nome exato da primeira extensao que falhou ainda NAO foi comprovado**. Cleanup do container verificado pelo proprio utilitario; SOURCE/DEMO/n8n inalterados. Backup SHA-256/GPG/TOC 811 entradas PASS; nao houve restore efetivo.

**Query READ-ONLY METADATA no Supabase SOURCE feita nesta etapa:** `pg_extension` listou extensoes instaladas `pg_stat_statements 1.11`, `pgcrypto 1.3`, `plpgsql 1.0`, `supabase_vault 0.3.1` e `uuid-ossp 1.1`. `supabase_vault` e principal candidato a indisponibilidade da imagem comunitaria, nao causa provada, e root key do Vault NAO esta no dump. Nao copiar/migrar chaves de projeto implicitamente.

**Entrega em andamento:** `scripts/operations/g5_extension_compatibility_readonly.py` inventaria apenas nomes de EXTENSION na stream criptografada (GPG→pg_restore --list) e compara dinamicamente com `.control` em imagem PostgreSQL 17 local pinada por SHA, usando apenas contêiner de metadados sem rede, UID sem privilegio e sem DSN/backup/SQL de usuario montados. Nenhuma restauracao, nenhum bypass de extensão, nenhum pull automatico de imagem. Candidata selfhost Supabase documentada `supabase/postgres:17.6.1.136` ainda requer download/autorizacao/checagem de digest e novo preflight separado; NAO executa restore automaticamente.

**Proximos gates:** evidenciar extensoes presentes no proprio arquivo vs imagem, testar compatibilidade real numa sandbox Supabase apropriada com autorizacao especifica, copiar arquivo cifrado + manifesto para storage externo privado e verificar hash, preservar chave Vault sob politica separada, mapear consumidores n8n 9 bindings, Shadow e Vercel, paridade, ports multicliente e cutover humano. `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. Ver `docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md` e issue #155.

---

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
