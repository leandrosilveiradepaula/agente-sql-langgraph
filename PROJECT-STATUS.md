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
indexa 75 nós e documenta **seis** nós com hardcodes FORBIDDEN
comprovados no legado: classificação/aliases, prompt SQL, planner, gates
semânticos de DRE, schema e filtros fixos, e relatórios financeiros. O
script `scripts/audit_n8n_workflow_export_readonly.py` permite comparar
exportações locais sem reproduzir SQL, prompts ou credenciais. Nenhum dado
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
| G2 — inventário n8n + eliminação FORBIDDEN + 2 contextos | **Parcial:** 75 nós de exportação histórica indexados; 6 FORBIDDEN comprovados no arquivo; VPS ativa e 2 contextos pendentes |
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
