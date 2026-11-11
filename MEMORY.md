# MEMORY.md — Continuidade operacional do Agente Financeiro

> **Memória durável do repositório, não a memória pessoal do ChatGPT.** Ler junto com `AGENTS.md` em toda retomada. Decisão recente explícita do operador prevalece sobre notas históricas. Atualizado em 2026-11-11.

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
