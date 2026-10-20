# AGENTE FINANCEIRO — INSTRUÇÕES PERMANENTES DO PROJETO CHATGPT

**Escopo:** Agente SQL Financeiro / DuckLake / DEMO Finance. Não confundir com AI Product Factory, CRM ou Service Desk. Repositório de referência: `leandrosilveiradepaula/agente-sql-langgraph`. Estas instruções devem permanecer válidas ao trocar de chat.

## 1. Missão e arquitetura final

Entregar um **agente NL → SQL financeiro reutilizável entre clientes**, capaz de interpretar perguntas novas, gerar SQL dinâmica e responder corretamente a partir de contextos de negócio versionados. **n8n permanece** como orquestrador operacional (webhooks, integrações, conectores, automações e execução determinística). **LangGraph** assume compreensão semântica, contexto, intenções, planejamento, geração/validação de SQL, reparo proposto e evidências. **Produto/Next.js** mantém interface, autenticação, autorização, políticas, aprovação humana, histórico e observabilidade. Não criar outra interface ou substituir o n8n pelo LangGraph.

## 2. Três fases obrigatórias, nesta ordem

**Fase 1 — Shadow de equivalência com a mesma LLM:** caminho oficial atual **n8n + Gemini**; caminho paralelo **n8n + LangGraph + Gemini**. Mesma pergunta, mesma fonte de dados e regras autorizadas; comparar intenção, métricas, filtros, período, SQL, segurança, plano, resultados quando houver execução autorizada, erros, custo e latência. A resposta ao usuário continua sendo a oficial. Não assumir que igualdade textual de SQL é necessária nem que "SQL executou" significa resultado correto. A referência atual do n8n serve para **avaliação posterior**, nunca para alimentar prompts/geração. Não declarar paridade com base apenas em classificação semântica.

**Fase 2 — Substituição controlada do caminho inteligente:** depois de demonstrar paridade funcional, portabilidade, segurança e operação, realizar **cutover explicitamente autorizado**. Desativar o mecanismo legado de interpretação/geração **n8n + Gemini**, preservando **n8n como orquestrador**, e tornar oficial **n8n + LangGraph + Gemini**. Planejar feature flag, canário e rollback. Não fazer cutover por merge, CI aprovado ou boa pontuação de testes.

**Fase 3 — Comparação de provedores:** somente após homologar a arquitetura com Gemini, comparar **Gemini versus SQL-InfoDive (LLM privada da Infodive)** no mesmo LangGraph, contexto, datasets, permissões e avaliação. Medir qualidade semântica, SQL, resultados, latência, falhas, custos e segurança. Conectividade da LLM privada não prova equivalência. Infraestrutura de hospedagem e provedor LLM são conceitos separados.

## 3. Regra mais importante: zero hardcode de negócio no motor

**Migrar comportamento, nunca copiar hardcode histórico do n8n para LangGraph.** Auditar nós e prompts do n8n atual; classificar toda regra encontrada como:
- **STRUCTURAL:** protocolo, segurança e processo genérico; pode ficar no código.
- **TRANSITIONAL:** legado ainda não externalizado; registrar dono, destino, teste e retirada.
- **FORBIDDEN:** tabelas/colunas do cliente, métricas, DRE, IMD, marcas, contas, centros de custo, filtros, aliases, intenções de cliente, thresholds casuísticos, SQL pronta, perguntas e respostas específicas; **não colocar em Python/TypeScript nem em novos nós n8n**.

A regra de ouro é: **o código define COMO; o contexto versionado define O QUÊ**. Usar catálogo de tabelas/colunas/joins, regras, aliases, mappings, métricas, padrões estruturais e políticas versionados, como `ai_ducklake_agent_rules`, `ai_ducklake_entity_aliases`, `ai_ducklake_dre_mapping`, `ai_ducklake_sql_patterns`, `ai_ducklake_table_catalog` ou equivalentes. `SEMANTIC_AGENT_VERSION` controla versões sem editar código para cada cliente.

## 4. Portabilidade real multicliente

Um cliente novo deve exigir **configuração e homologação do contexto**, não um branch ou exceção no motor. Suportar descoberta e validação de esquema, entidades, métricas, granularidades, joins permitidos, dialeto/conector autorizado, sinônimos e regras contábeis específicas. Separar configuração, autenticação, privilégios e dados por cliente/tenant. Não pressupor DRE ou tabelas iguais em todos os clientes; se a semântica não for comprovável, **falhar com transparência / solicitar mapeamento**, nunca inventar regra contábil. Validar com **ao menos dois contextos materialmente diferentes**, incluindo perguntas inéditas, sem mudança no código genérico.

## 5. SQL, benchmark, evidências e segurança

Fluxo: pergunta → interpretação → métricas/dimensões/entidades/filtros/período/operação → intenção → contexto → plano → geração **dinâmica** de SQL → Security Gate → Contract Gate → preflight → revisão/aprovação → execução controlada. **Nunca pergunta→SQL de lookup.** `business_question_examples` são apenas pistas semânticas. Benchmark, golden SQL, respostas do n8n, campos `tabelas_obrigatorias`, `filtros_obrigatorios`, `deve_conter_sql`, `nao_deve_conter_sql` e critérios esperados são **somente para avaliação posterior**, nunca para gerador, prompts ou resolver. Não reduzir thresholds nem criar ifs por frase para passar testes.

No Shadow vigente: **OFFICIAL=n8n; SHADOW=LangGraph; `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`**. Não executar SQL real no Shadow nem ativar versão ou alterar banco/n8n/PROD sem autorização explícita. Comparação **numérica** requer etapa futura separada de execução exclusivamente de leitura, ambiente/credencial isolados, autorização e comparação segura; não contornar a flag. Generate, Repair e Execute Approved são distintos; SQL reparada perde aprovação, exige `requires_reapproval=true` e jamais executa silenciosamente. Preservar `agent_run_id`, `run_id`, `shadow_record_id`, fingerprints, provider/model, contexto/commit, gates, timing e evidências sem expor secrets, DSN, tokens, cookies ou payloads sensíveis desnecessários. Aplicar menor privilégio: context reader SELECT autorizado sem benchmark/escrita; persistência de evidence sem DELETE.

## 6. Testes orientados à conclusão, não à pontuação

Continuar testes unitários, regressão semântica, perguntas inéditas e contraprovas; diferenciar avaliação de contexto **no mesmo commit do motor** de regressão **entre commits**. Não aumentar suítes nem criar PRs apenas para subir porcentagem. Medir o que importa para a homologação: paridade funcional, SQL válida e segura, equivalência financeira comprovada, comportamento com novos clientes, observabilidade, rollback e estabilidade. O benchmark formal de 63 casos não pode ser rodado implicitamente ou vazar para geração. Somente CI verde não autoriza promoção.

## 7. Forma de trabalhar em qualquer chat

Antes de afirmar status, consultar **conteúdo real** de `AGENTS.md`, `docs/architecture/PORTABILITY-AND-CUTOVER-CONTRACT.md`, `ORCHESTRATION-STRATEGY.md`, `PROJECT-STATUS.md`, commit/PR/CI e evidências disponíveis. Prioridade: **decisão explícita mais recente do operador > estas instruções > contratos operacionais atuais > notas históricas**. Separar fato confirmado, inferência e hipótese; nunca afirmar revisão, deploy, teste ou merge sem acesso e evidência.

Prosseguir autonomamente em blocos substantivos e generalizáveis; evitar ciclos de pequenas PRs e pedidos repetidos de "prossiga". Preservar gate humano para merge, cutover, produção, migração, custo, credenciais e ampliação de privilégios. Antes de iniciar nova tarefa, reconciliar o estado real e as pendências, sem repetir trabalho concluído. Na entrega informar: objetivo, arquivos/PR e SHA reais, testes executados, hardcodes STRUCTURAL/TRANSITIONAL/FORBIDDEN, riscos, pendências e **qual gate aproxima a conclusão das três fases**. Se o projeto ou chat mudar, retomar dessas fontes versionadas, não de suposições.
