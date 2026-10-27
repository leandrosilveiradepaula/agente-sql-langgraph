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

# AGENTE FINANCEIRO — INSTRUÇÕES PERMANENTES DO PROJETO CHATGPT

## PRIORIDADE EXECUTÁVEL — 26/10/2026

**Não perder o foco novamente.** O próximo resultado exigido é provar **n8n candidato → LangGraph → Gemini → SQL gerada e validada**, com uma pergunta inédita e evidência persistida da mesma tentativa, **sem executar SQL financeira**. Ver [`docs/operations/DELIVERY-FOCUS.md`](docs/operations/DELIVERY-FOCUS.md) e [roadmap #155](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/issues/155).

**Sequência:** P1 geração real isolada no Shadow TEST; P2 Produto autenticado → n8n → LangGraph correlacionado (evitar acionar rota oficial Demo que também executa SQL antes de menor privilégio); P3 segurança de execução, paridade financeira, portabilidade e cutover, cada qual com seus gates próprios. **P1 é smoke real de geração, não G1 completo.**

**Fazer:** inspeção mínima do runtime, prova real e reparo pontual de falhas observadas. **Não fazer:** nova cadeia interminável de micro-PRs, repetir configuração já concluída, copiar hardcodes, usar benchmark como prompt, afrouxar gates, executar SQL real Shadow ou gastar API/alterar banco/produção sem autorização específica. `PUBLIC TEMPORARY=true` permanece bloqueio da role/execução financeira, **não da prova isolada generate-only**.

Ao retomar um chat, verificar HEAD/PR/CI e estado de runtime reais, ler este documento + `AGENTS.md` + plano de foco, reportar somente a **próxima prova concreta**. O contrato normativo e a ordem Shadow → cutover humano → Gemini×SQL-InfoDive não mudam.

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
