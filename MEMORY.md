# MEMORY.md — Continuidade operacional do Agente Financeiro

> **Memória durável do repositório, não a memória pessoal do ChatGPT.** Ler junto com `AGENTS.md` em toda retomada. Decisão recente explícita do operador prevalece sobre notas históricas. Atualizado em 2026-11-11.

## Prioridade operacional inequívoca — 11/11/2026 21:36 UTC

**Não considerar progresso financeiro certificado apenas por código, documentação ou benchmark.** A primeira prova exige uma capacidade **real** extraída conjuntamente dos 68 nós do n8n e do banco/backup G5: fonte/versionamento/significado aprovado → contexto de tenant → pergunta inédita → LangGraph (interpretação, plano, geração SQL dinâmica e gates). Sem SQL financeira real no Shadow. O aceite detalhado consta em `docs/operations/FIRST-FINANCIAL-CAPABILITY-PROOF.md`.

**Classificação única por capacidade:** `NOT_MIGRATED`, `IMPLEMENTED_UNPROVEN`, `PROVEN`. Registrar origem n8n/G5, risco, responsáveis, SHA/PR, testes e evidência. Não transportar hardcodes; nem 63 perguntas, SQL histórica ou golden answers entram no gerador. Dois clientes materialmente distintos serão requeridos. Não inventar prazo: a antiga estimativa de 12–20 semanas foi retirada.

**Estado a reconfirmar:** PRs #230/#231/#233 draft, `main@955eda46`, VPS `87d16796`, n8n oficial preservado, Shadow SQL real false. CI da PR #233 SHA `5b29a890` falhou em Windows **somente** no `Whitespace check` (espaços no roadmap), apesar de outros passos daquele job PASS. Corrigir e revalidar. Não há prova de migração financeira integral ou paridade numérica.

**Controles:** OFFICIAL=n8n, SHADOW=LangGraph, Generate/Repair/Execute Approved separados, reparo invalida aprovação; DB, produção, merge/cutover/credenciais e SQL real exigem gates humanos.

---

### Evidência inicial independente (G5↔n8n, sem homologação)

Export ativo da VPS SHA-256 `19dd24c29d81c61b12dc383f2124ca2e7ba77625776ee161f3be1996d2f09c68`; nó 22 (planner) SHA-256 `113ce61f0e6c57b2cf260f70c6e04af1530e92876f4c6d10d5fbaa9c242f5d5f`, com funções `planConsultaMetricaFinanceira` (linha 2030), `factGrainContract` (1073), `comparativeFactContract` (1054) e `commonManagerialRules` (1105). Nó 5 consulta 5 coleções semânticas do G5; existem 11 pacotes de versão cifrados. Relatório privado SHA-256 `e9c23d9e4b8dddd313359742546aa16eea0a2eab0bb40ae50ee1699ae6abe1d6`. Isso **prova localização da origem, não semântica contábil nem SQL LangGraph**: primeira capacidade `NOT_MIGRATED`; revisão por versão/validação financeira pendentes. Detalhes em `docs/operations/FIRST-FINANCIAL-CAPABILITY-PROOF.md`.

## Missão invariável

**Fazer engenharia reversa do agente financeiro EXISTENTE** — n8n publicado (observado com 68 nós) **E** banco/backup G5 recuperado — para reconstruir suas capacidades no fluxo **Produto + n8n + LangGraph + LLM configurável**. Não criar agente do zero nem tentar ensinar o legado por 63 SQLs/respostas prontas. Migrar o comportamento, não copiar hardcodes. Conhecimento de cliente pertence a contexto semântico versionado por tenant; o motor é agnóstico.

A matriz obrigatória é: **nó/branch/JS/prompt/SQL legado ↔ esquema/tabelas/regras/aliases/métricas/relacionamentos e versão do banco ↔ significado financeiro validado ↔ destino na arquitetura ↔ teste de paridade ↔ risco/proprietário**. É proibido declarar descoberta completa com base em flags heurísticas ou encontrar apenas 6 termos. Necessária revisão do corpo real de cada nó e de objetos do banco, sem expor dados sensíveis.

## Estado observado em 2026-11-11 — revalidar sempre

- GitHub `main` observado: `955eda46015d35dbe44a40f9240b821b1f493201`; VPS checkout observada: `87d167969345c3dfcf9deaf36e33ab07a1f9c890`. Essas SHAs envelhecem: consultar GitHub/VPS novamente.
- PRs `#230` (fallback semântico) e `#231` (papéis/ACL) abertas em *draft* com CI Linux/Windows verde na última inspeção. Não foram mergeadas nem ativadas pelo agente.
- Export sanitizado somente leitura do workflow n8n `2E6mbYg8CEJhGhqs`: **68 nós** (41 Code, 11 PostgreSQL, 10 If, 2 HTTP, 3 Respond-to-Webhook, 1 Webhook); na leitura, `active=true` e `versionId == activeVersionId`. **Rota Produto→workflow não atestada**; não inferir pelos nomes.
- Backups e evidências privadas G5 e perguntas-only disponíveis na VPS. Snapshot das 63 perguntas recuperado e congelado; nem backup nem benchmark equivalem a semântica contábil homologada. A recuperação G5 contém múltiplas versões: não misturar contextos.
- Diagnóstico offline anterior: 63 perguntas com snapshot histórico, 26 intenções/planos aceitos e 37 rejeitados; **isso não é qualidade financeira certificada**. Nove, 16, seis aliases e demais números antigos são diagnósticos específicos, não meta de implementação.
- Rastros de seis termos de métricas encontrados em 14 nós Code do legado (44 ocorrências); referência textual não implica equivalência. Pacotes privados temporários podem desaparecer; não tratá-los como artefatos persistidos garantidos. Recriar a partir de fonte com integridade quando necessário.

## Trabalho obrigatório e gates

1. Fonte n8n publicada + Produto: capturar inventário completo, conectividade, dependências, funções e SQL/LLM legado. Separar **observação** de **classificação revisada**.
2. Fonte banco/backup: inventário por versão e tenant, definição contábil respaldada, dependência física, mapeamentos e trilha de proveniência. Não presumir que backup cifrado = significado de campo. Não reutilizar golden answers.
3. Consolidar matriz e separar STRUCTURAL (processo), TRANSITIONAL (dívida legado) e FORBIDDEN (negócio hardcoded no código novo); migrar capacidades completas e testar com perguntas inéditas + dois clientes distintos.
4. Provar Fase 1 Shadow correlacionado n8n + Gemini vs n8n + LangGraph + Gemini, sem impactar oficial. SQL read-only para paridade numérica exige autorização específica; nada em produção sem aprovação.
5. Cutover humano Fase 2 com rollback; comparar Gemini × SQL-InfoDive apenas na Fase 3.

**Invariantes:** `OFFICIAL=n8n`; `SHADOW=LangGraph`; `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`; geração, repair e Execute Approved separados; SQL reparada requer reaprovação. Não fazer merge, migração, mudança n8n/banco/tenant/credenciais/permissões, deploy produtivo ou custos sem o gate humano correspondente. Não expor prompts/SQL bruta, DSNs, dados pessoais nem segredos em GitHub.

## Continuar sem desvio

Consultar `docs/operations/LEGACY-N8N-DATABASE-MIGRATION-MAP.md` para o backlog rastreável por fonte e capacidade; `docs/architecture/PORTABILITY-AND-CUTOVER-CONTRACT.md` e `ORCHESTRATION-STRATEGY.md` para arquitetura; `PROJECT-STATUS.md` e issue #155 para pendências. A primeira entrega substantiva pendente é a **matriz integral do workflow e do banco**, não outra versão de scoring.

## Evidência objetiva posterior ao contrato (11/11/2026)

- PR #233 em draft `docs/legacy-reverse-engineering-contract-20261111`: auditor `scripts/operations/legacy_migration_source_crosswalk_offline.py` e seis testes sintéticos. Inventário do fluxo n8n publicado: 68 nós, 78 arestas, 60 alcançáveis do webhook, 8 não alcançáveis. Banco/backup G5: cinco coleções, 11 versões cifradas e 1.381 linhas, 106 SQL patterns restritos a avaliação.
- Evidência sanitizada por nó e por versão: `docs/audits/LEGACY-N8N-G5-TRACE-20261111.md`; relatório privado completo em /tmp, SHA-256 `e33a1b93f25a0809a644e5e83a9f7a82a360f73adb146511772d19d6181edbff`. Somente 20 nós têm coocorrência textual com identificadores G5; NÃO há regras financeiras homologadas, e todo conteúdo por versão ainda requer revisão.
- SHA do contexto antigo do Shadow não coincide diretamente com as 11 versões G5 pelos hashes verificados; não misturar as fontes para produzir SQL. A rota Produto→workflow n8n ainda precisa de testemunha real.
- **Próxima ação:** inspecionar efetivamente corpo dos 68 nós e fontes cifradas por versão; extrair regras, SQL, filtros, transações e seus efeitos e provar dependências em matriz, antes de decidir mapeamentos/implementação. Não se contentar com índice de nomes e indicadores textuais.

## Continuidade após engenharia reversa funcional — 11/11/2026

- Inventário funcional proposto **68/68 nós** e fluxo real Produto Next.js em `docs/audits/LEGACY-N8N-PRODUCT-FUNCTIONAL-MAP-20261111.md` (destinos candidatos; regras/SQL de cada função e efeito contábil ainda precisam ser homologados). 41 Code = 14.440 linhas JS estáticas; cache, repair, preflight, executor, dados, relatórios e fila presentes no n8n.
- Topologia: geração/SQL reparada **podem alcançar** o executor do n8n; exigir separação Generate/Repair/Execute Approved e `requires_reapproval=true`. 8 nós não alcançáveis do Webhook, incluindo logs/fila e DDL manual; não removê-los sem revisar efeitos.
- 11 PostgreSQL n8n usam 2 referências de credencial distintas: contexto/cache/log/configuração (9 nós) versus preflight/execução (2 nós); IDs não demonstram hosts ou privilégios. SOURCE Supabase INACTIVE; DEMO ACTIVE com 13 tabelas públicas. Leitura do conteúdo de 11 pacotes semânticos cifrados ainda pendente.
- Recontagem G5: 579 hints de 11 versões representam **11 referências físicas distintas**, **58 padrões distintos nó/referência**, 447 tabelas ambíguas, 110 não localizadas e 481 colunas não resolvidas. Não confundir 4.813 ocorrências por versão com dependências aprovadas.
- O fallback de URL do Produto não coincide com o path Webhook publicado; **env efetivo não verificado**, portanto não declarar falha de produção nem route parity. Os 63 casos de benchmark são **somente controle de qualidade comparativa posterior**.

## Conclusão da análise de cobertura de capacidades — 11/11/2026

- `docs/audits/LEGACY-N8N-LANGGRAPH-CAPABILITY-GAP-20261111.md` documenta 14 capacidades do n8n legado, os módulos realmente existentes no Produto/LangGraph, seus gaps e critérios para certificar a migração. **Existência de módulo ou teste offline não é migração completa.**
- Scan privado de 41 funções JavaScript: 14.440 linhas, 3.403 literais de string (1.987 com tamanho >=10), templates longos em nós 8, 32, 57; maior quantidade de literais em 22, 32 e 6. Esses números NÃO equivalem a hardcodes de negócio aprovados. A classificação literal/branch precisa ser feita com dados versionados do backup e significados contábeis.
- O adaptador PostgreSQL atual do LangGraph recebe DSN/schema/version por injeção e permite catálogo configurado, mas mantém template compatível com nomes DuckLake, projeção de DRE tipada e leitura `load_active_context(user_profile)` que ignora o perfil ao consultar. Prova de routing do tenant ao adaptador e portabilidade de esquemas/colunas materialmente distintos permanece pendente. São pontos do porting e não autorização para if por cliente.
- O leitor de contexto legado contém `sql_patterns`; os 106 SQL patterns históricos G5 são **apenas avaliação**, nunca contexto do gerador. Não misturar essa coleção criptografada com padrões estruturais novos autorizados.
- SOURCE Supabase inativo, pacotes G5 cifrados separados por 11 versões; análises das linhas contábeis originais exigem **desbloqueio seguro em TTY, sem senha em chat/arquivo/env/log**. Inventário do conteúdo integral ainda não foi realizado. n8n e Shadow não foram modificados, SQL financeira real segue false.

## 2026-11-11 — Caminho de onboarding sem hardcode implementado na PR #233

**Decisão do operador:** migrar a inteligência financeira real do legado n8n (68 nós) e G5 para n8n+LangGraph, mas o motor deve atender clientes com qualquer nomenclatura/esquema mediante configurações, acesso e definições fornecidas/validadas. **Nenhum hardcode de cliente no código**; as 63 perguntas históricas **somente controle de qualidade posterior**.

**Implementação nesta branch ainda sem merge/cutover:**
- `app/adapters/postgres/physical_catalog_reader.py` inspeciona apenas `information_schema.columns` em transação READ ONLY e lista explícita de schemas, sem ler dados financeiros;
- `app/domain/tenant_semantic_readiness.py` faz pré-validação física sem inferir semântica, nunca promove mapeamento automaticamente;
- `app/adapters/postgres/canonical_context_repository.py` carrega JSONB de contexto versionado, já aprovado, vinculado a tenant/versão/fingerprint e exclusivo de SQL de avaliação;
- `app/config/postgres_context.py` e `app/bootstrap.py` habilitam modo `canonical_snapshot` por configuração autenticada mantendo `legacy_tables` como default;
- `docs/architecture/GENERIC-CUSTOMER-SEMANTIC-ONBOARDING.md` descreve pré-requisitos por cliente, publicação governada e lacunas.

**Testes isolados:** 4+6+8 novos com dois esquemas sintéticos materialmente distintos; regressão legada do repositório/config/bootstrap; container efêmero sem rede e testado em usuário não-root, removido depois. **Não provam clientes reais, publicação, autorização per-request, paridade financeira ou cutover.**

**Gates inalterados:** n8n oficial preservado, Shadow sem execução real; nenhum SQL financeiro, banco, produção, credencial, contexto ativo, merge ou migração alterados. Próxima entrega de produto: ler o conteúdo cifrado G5 com custódia adequada, externalizar cada regra do legado e provar contextos reais, roteamento tenant, aprovações e paridade antes de substituir inteligência n8n.
