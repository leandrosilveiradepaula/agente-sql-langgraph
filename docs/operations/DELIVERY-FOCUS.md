# Foco de entrega operacional — provar NL→SQL com LangGraph

**Direcionamento do operador: 26/10/2026.** Este é o plano de execução imediata para retomar progresso verificável, não uma autorização de produção, custo, banco, privilégios, execução SQL ou cutover. O contrato normativo permanece em [PORTABILITY-AND-CUTOVER-CONTRACT.md](../architecture/PORTABILITY-AND-CUTOVER-CONTRACT.md); o estado vivo e as evidências permanecem no [roadmap #155](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/issues/155).

## Objetivo funcional — sem expandir o escopo

**Hoje (oficial):** Produto/Next.js → n8n + Gemini → SQL → Supabase → resposta financeira.

**Alvo:** Produto/Next.js → n8n (orquestração) → LangGraph (intenção/contexto/plano/geração/gates) → Gemini → SQL com execução autorizada no Supabase → resposta.

O requisito imediato é provar que **uma pergunta inédita** recebida pelo **n8n candidato** chega ao LangGraph, é interpretada com contexto versionado, gera SQL dinâmica com o Gemini, passa pelos gates e produz evidência persistida da mesma tentativa, **sem executar SQL financeira**. Não copiar SQL, regras de DRE, nomes de tabelas, filtros ou respostas do legado para o código. Não chamar isso de equivalência financeira nem de G1 completo.

## Única entrega ativa: P1 — geração real sem execução financeira

**Ambiente preferido:** n8n candidato Shadow de sete nós e LangGraph Shadow TEST já preparados na VPS, isolados da resposta oficial e do Produto Production. O candidato possui chamada interna de geração e leitura de evidência. Antes do teste, **reconfirmar no runtime real**, sem confiar no estado histórico, a publicação do candidato, URL interna, autenticação, versão/contexto/fingerprint, health, provider/model e `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.

1. **Prova técnica sem custo:** usar testes offline já existentes como pré-condição, sem executar novamente suites inteiras sem necessidade. Identificar eventual quebra objetiva na integração do candidato ao endpoint `/v1/internal/sql-agent/generate`. Um teste com stub/fake é só pré-condição, **não** comprova Gemini real.
2. **Prova real com Gemini:** mediante autorização específica de consumo da API paga e de chamada ao ambiente, enviar **uma pergunta inédita e autorizada** via candidato n8n → LangGraph em modo `generate`. Não enviar benchmark/golden answer, não usar a rota oficial do Produto para fazer essa prova, não executar a SQL resultante.
3. **Verificar a mesma tentativa:** preservar identificadores `agent_run_id`, `run_id` e `shadow_record_id`; provider/model, `SEMANTIC_AGENT_VERSION`, fingerprint, status, SQL gerada (somente no ambiente autorizado), gates, erros, tempo, consumo de tokens, recibo HTTP e evidência persistida. HTTP 202, CI verde ou resposta de stub **não** bastam.
4. **Falha real:** registrar o primeiro componente que falhou (n8n envelope/auth/transporte; LangGraph contexto/planejamento/geração/gate; persistência/leitura), corrigir a **causa raiz mínima**, repetir exatamente a prova. Evitar PRs de testes genéricos enquanto não existir erro reproduzido que impeça P1.

**Aceite P1:** uma execução real Gemini com status de sucesso, SQL dinâmica de pergunta inédita **aprovada pelos gates existentes**, identificadores/evidências correlacionados n8n↔LangGraph e ausência comprovada de execução SQL financeira. Registrar commit efetivamente implantado e limites da evidência. SQL rejeitada é diagnóstico, **não P1 concluído**: corrigir contexto ou capacidade sem relaxar o gate. A mera chamada a Gemini não é aceite.

**P1 não é G1:** ainda faltará a correlação completa com o Produto autenticado, paridade e execução financeira sob permissões controladas.

## Ordem imediatamente posterior

- **P2 — Produto → n8n → LangGraph, geração correlacionada.** O `app/api/generate-sql/route.ts` atual chama **primeiro** o fluxo oficial n8n, que na Demo também pode **executar SQL**, e só depois agenda o Shadow. **Não** usá-lo para contornar a falta de role read-only. Propor e homologar, se necessário, um caminho de geração-only autenticado e minimamente invasivo; ou executar o canário existente **somente após** segurança da execução oficial, com gate humano de produção/custo. Confirmar `agent_run_id` no Produto e os identificadores n8n/LangGraph da mesma pergunta. G1 só passa com essa correlação completa.
- **P3 — execução financeira segura e comparação.** O G1 read-only do Supabase continua bloqueado por `PUBLIC TEMPORARY=true`, confirmado na VPS em `main@e7ccff8`; role `finance_g1_readonly` não existe. Resolver o isolamento sem enfraquecer `assert_role_effective_permissions`, sem `REVOKE` global não autorizado, e sem trocar mais que os dois nós oficiais aprovados. Verificar backup/rollback e só então executar SQL financeira sob autorização read-only isolada e comparar números.
- **P4 — fechamento de produto.** Com P1–P3 comprovados, realizar avaliação cega Gemini×Gemini, inventário/externalização de hardcodes, portabilidade com dois contextos realmente distintos, aprovação/cutover reversível, e **depois** Gemini×SQL-InfoDive. O legado é baseline a aposentar somente na inteligência; **n8n permanece**.

## Limites de segurança que NÃO mudam

- `OFFICIAL=n8n+Gemini`; `SHADOW=n8n+LangGraph+Gemini`; `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` até autorização própria de outro ambiente/etapa. Nunca ativar Shadow Production, alterar Vercel/n8n oficial, SQL real, tenants, migrations, permissões, segredos ou custos por inferência.
- Generate, Repair e Execute Approved continuam separados; SQL reparada exige nova aprovação. Gates de autorização, escopo/tenant, SQL e segurança não são reduzidos para fazer P1 passar.
- A permissão `PUBLIC TEMPORARY` **não bloqueia conceitualmente um teste isolado generate-only**; ela **continua bloqueando** o rollout de executor dedicado e qualquer teste que dependa da execução oficial sem privilégio mínimo. Não descartar a remediação, apenas retirar esse trabalho do caminho crítico de P1.
- Benchmark (incluindo 63 perguntas) e baseline n8n são **somente avaliadores após geração**, jamais prompt, planner ou atalho para SQL pronta.
- Não incluir segredos, dados financeiros brutos, SQL sensível, DSNs ou exports contendo chaves em GitHub/ChatGPT.

## Protocolo obrigatório para todo novo chat / bloco de trabalho

1. Conferir GitHub real (HEAD, PRs, CI) e, quando possível, evidência de n8n/TEST/Vercel. Ler `AGENTS.md`, `CHATGPT-PROJECT-INSTRUCTIONS.md`, o contrato, este foco, `PROJECT-STATUS.md` e o roadmap #155. **Separar fato observado, último relato e hipótese.**
2. Declarar a **única próxima demonstração operacional**: P1 até ela passar; depois P2; depois P3. Não reiniciar configuração de Python/CA/DSN, workflows, token de webhook ou deploy já comprovados sem evidência de regressão.
3. Trabalhar autonomamente nas ações reversíveis e autorizadas. Bloqueio específico → uma causa raiz, um reparo, uma repetição da prova. **Não acumular PRs ou refatorações genéricas sem aproximação demonstrável do aceite da etapa.**
4. Ao concluir: informar artefato/PR/SHA real, CI se executado, runtime validado (ou não), evidência do objetivo, riscos, autorização pendente e **exatamente qual prova vem a seguir**.
5. O trabalho com segurança, portabilidade e zero hardcode permanece obrigatório para a entrega final. **A ordem de demonstração é progressiva; não é uma exceção a nenhum gate.**

## Evidência de partida (26/10/2026; não é prova de P1)

- GitHub LangGraph `main@e7ccff858506097e02c3e5d89ecb0016a9180664`, PR #172 mergeada.
- Produto Demo Vercel com deployment Production `READY` no commit `7d784ec14568599049f039532805905036c52705` (PR #31; canário por identidade disponível, sem comprovação de ativação).
- Último relato operacional: n8n candidato de sete nós publicado e Shadow TEST saudável; **reconfirmar runtime antes de usar**.
- Auditoria Supabase read-only: `G1_PUBLIC_TEMPORARY=TRUE`, `G1_PUBLIC_CREATE=FALSE`, `G1_TARGET_ROLE_EXISTS=FALSE`; nenhuma autorização de revogação global.
- `G1_CORRELATED_EXECUTION=NOT_TESTED`. Não há evidência de prova P1 com Gemini real n8n→LangGraph nesta linha de base.

## Critério de não desvio

Antes de iniciar qualquer atividade, responder: **“Qual evidência concreta essa ação produzirá para P1/P2/P3?”** Se a resposta for apenas “mais documentação”, “mais testes offline”, “mais uma PR” ou “mais uma auditoria sem decisão”, **não executar**, salvo solicitação explícita do operador, falha real bloqueante ou segurança imediata.
