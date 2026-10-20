# Inventário preliminar verificável — workflow legado n8n DuckLake (snapshot v2.2.31)

**Status:** AUDITORIA PARCIAL, SOMENTE EXPORTAÇÃO HISTÓRICA; **NÃO** é atestado de workflow ativo. Data da inspeção: 2026-10-19/20. O objetivo é G2 do contrato de portabilidade/cutover, **não** criar regras de geração a partir do legado.

## Cadeia de custódia da evidência

- Repositório de origem: `leandrosilveiradepaula/Agente-Financeiro`, arquivo [exportação estável n8n v2.2.31](https://github.com/leandrosilveiradepaula/Agente-Financeiro/blob/d8897b347ca4fe8a79aa8ffc14e80b4ecd28143a/workflows/n8n/agente-sql-financeiro-ducklake/Agente%20SQL%20Financeiro%20DuckLake%20-%20v2.2.31-stable-preflight-retry.json).
- Commit que alterou o export: `d8897b347ca4fe8a79aa8ffc14e80b4ecd28143a`, em **2026-07-20** (mensagem: `chore: freeze stable n8n workflow v2.2.31`).
- Blob SHA do arquivo observado no produto `main`: `5c385ee2718f73e74d24c59fa6afbeed3c3570fd`.
- Nome exportado: `Agente SQL Financeiro DuckLake - v2.2.31 Sem LIMIT SQL - IMPORT SAFE + Retry Preflight`. O campo JSON `active=true` indica **apenas o flag registrado na exportação**, não confirma estado/versão da VPS em 2026-10-19/20.
- **75 nós**: 45 Code/JS, 8 Postgres, 6 HTTP Request, 11 IF, 3 Respond to Webhook, 1 Webhook, 1 Wait. Foram inventariados todos os 75 nós por nome/tipo. A classificação substantiva ainda é parcial: **6 nós possuem FORBIDDEN comprovado**; os demais exigem validação individual contra a versão ativa antes de concluir G2.
- O grafo exportado possui um nó `Postgres - Criar Tabela Cache SQL (manual)` (#55) **sem conexões de entrada/saída**; o fato de não estar conectado nessa exportação não garante que outra versão ativa não o execute.
- O produto Next.js em `leandrosilveiradepaula/Agente-Financeiro` contém dispatch Shadow assíncrono configurável via `LANGGRAPH_SHADOW_ENABLED` em `app/api/generate-sql/route.ts` e cliente `lib/langgraph-shadow-client.ts`, mas não há nesta auditoria confirmação de que o sinal está habilitado no deployment ou que há correspondência numérica. O endpoint n8n ainda é parametrizado via environment, com fallback de URL literal em `lib/n8n-endpoint.ts` (dívida de configuração, não regra contábil).

## Achados FORBIDDEN concretos: conteúdo legado, nunca copiar para motor novo

| Nó | Localização aproximada no `jsCode` da exportação | Comportamento hardcoded **comprovado** | Destino permitido / correção genérica |
|---|---|---|---|
| Code - Classificar Intenção DuckLake | 51–66, 103–122, 353–376 | Aliases de marcas fixos no JS; prioridade de classificação orientada por intent esperada de benchmark; scores 0.97/0.96 | Catálogo de entidades/aliases + regras de intenção configuradas por tenant; benchmark separado |
| Code - Montar Plano Query DuckLake | 186–196, 215–239, 251–296 | FQNs formados com dev_lakehouse e main_gold; SQL DRE LIKE por códigos, inferência de categoria/receita/custo | table_catalog, DRE mapping, filtros, métrica e relacionamentos versionados; dialeto autorizado |
| Code - Montar Prompt SQL DuckLake Offline | 43–987 | Prompt SQL ~57 mil caracteres com prescrições de esquema, joins sk, DRE/CMV/OPEX e formas de CTE além de regras estruturais legítimas | Decompor em regras de segurança estrutural e contexto financeiro; geração dinâmica no LangGraph |
| Code - Validar Plano Query Semantico | 263–323, 503–573 | Colunas grupo_dre/conta_contabil fixas; inferência de receita/custo por códigos DRE 01, 02, 03 etc. e strings | Contexto sign_convention/DRE por cliente; contrato de plano genérico; fail-closed |
| Code - Schema Real Watson | 19–280, 331–346 | Catálogo/schema/aliases, IMD, exclusões 97/98/99, orçamento Versão 2 e grupos DRE/CMV/OPEX explícitos | Catalogo de tabelas/joins, aliases, filtros, versões e métricas por tenant; não migrar estrutura literal |
| Code - Montar Relatório Executivo | 305–323, 426–568 | Inferência de intenção por palavras, resumo para cenários fixos e alerta de concentração acima de 50% | Configuração versionada de indicadores/alertas + apresentação genérica no Produto; evitar novos limiares fixos |

**Exceção particularmente grave:** na classificação legada, um comentário documenta que a prioridade de regra visa preservar `intent_esperada` do benchmark. **Tratar esse raciocínio como evidência histórica contaminada e nunca reproduzir no novo classificador.** O correto é modelar operação, métricas, dimensões e regras genericamente, e usar benchmark somente *após* a geração.

**Cuidados adicionais:** schema `dev_lakehouse` embutido no planner pode diferir do contexto de produção; filtros `IMD`, exclusões 97/98/99, versão de orçamento `Versão 2`, aliases e grupos DRE são **exemplos do legado analisado**, não defaults multi-tenant. Não repassar esses valores a novo código, prompt ou benchmark gerador. Limite de relatório `50%` depende de política configurada e não pode ser transportado como threshold estrutural.

## Tabela completa dos 75 nós (triagem inicial)

- `FORBIDDEN_CONFIRMED`: regra cliente-específica identificada no JS exportado; retirar/externalizar no destino, sem interferir no fluxo oficial até paridade.
- `MIXED_TO_VERIFY`: mistura ou potencial de negócio; precisa ler regras e contratos para decidir `STRUCTURAL/TRANSITIONAL/FORBIDDEN` detalhe a detalhe.
- `TRANSITIONAL_PROVIDER`: inteligência/geração/reparo antigo, a desativar *somente* após homologação do LangGraph.
- `TRANSITIONAL_EXECUTION`: integração operacional legada; preservar n8n e planejar adaptador/validação separadamente.
- `RETAIN_TO_VERIFY` / `STRUCTURAL_TO_VERIFY`: nó aparentemente operacional, mas **ainda não liberado** até revisão de seus parâmetros e dependências.
- `DISCONNECTED_MANUAL`: nó isolado no grafo; verificar se há edição mais recente na instância ativa.

| # | Nó | Tipo n8n | JS chars | Status da triagem | Próxima ação |
|---:|---|---|---:|---|---|
| 1 | Webhook - Pergunta | webhook | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 2 | Code - Validar Pergunta | code | 7152 | `MIXED_TO_VERIFY` | Keep validation structural; externalize business hints |
| 3 | Code - Resposta Erro Pergunta | code | 186 | `MIXED_TO_VERIFY` | Review code before retaining |
| 4 | Respond to Webhook Erro Pergunta | respondToWebhook | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 5 | Postgres - Buscar Contexto DuckLake | postgres | 0 | `STRUCTURAL_TO_VERIFY` | Read context with authorization; confirm policies |
| 6 | Code - Classificar Intenção DuckLake | code | 15768 | `FORBIDDEN_CONFIRMED` | Externalize aliases and intent catalog |
| 7 | Code - Consolidar Contexto DuckLake | code | 3044 | `MIXED_TO_VERIFY` | Normalize approved context, no hidden defaults |
| 8 | Code - Montar Prompt SQL DuckLake Offline | code | 56892 | `FORBIDDEN_CONFIRMED` | Remove business/prompt templates from n8n; LangGraph + versioned context |
| 9 | Code - Montar Body Gemini | code | 3032 | `TRANSITIONAL_PROVIDER` | Preserve baseline; replace generation with LangGraph at cutover |
| 10 | Gemini - Gerar SQL | httpRequest | 0 | `TRANSITIONAL_PROVIDER` | Disable direct n8n Gemini SQL generation only after parity |
| 11 | Code - Limpar SQL DuckLake | code | 19300 | `MIXED_TO_VERIFY` | SQL cleaner structural; no business-specific rewrites |
| 12 | Code - Validar SQL DuckLake Offline | code | 16084 | `MIXED_TO_VERIFY` | SQL safety gates in LangGraph; review legacy exceptions |
| 13 | Code - Resposta Erro SQL DuckLake | code | 15143 | `MIXED_TO_VERIFY` | Review code before retaining |
| 14 | Respond to Webhook Erro SQL | respondToWebhook | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 15 | Code - Montar Entrega Query DuckLake | code | 11855 | `MIXED_TO_VERIFY` | Report contract/labels; separate business mapping from formatting |
| 16 | Respond to Webhook | respondToWebhook | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 17 | Code - Montar SQL Log DuckLake | code | 1396 | `MIXED_TO_VERIFY` | Review code before retaining |
| 18 | Postgres - Gravar Log DuckLake | postgres | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 19 | Code - Montar Entrega Watson | code | 13694 | `MIXED_TO_VERIFY` | Retain deterministic delivery; inspect fixed contracts |
| 20 | Code - Montar SQL Question Queue | code | 2313 | `MIXED_TO_VERIFY` | Review code before retaining |
| 21 | Postgres - Gravar Question Queue | postgres | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 22 | Code - Montar Plano Query DuckLake | code | 60830 | `FORBIDDEN_CONFIRMED` | Move dynamic planning to LangGraph, catalog-driven |
| 23 | Code - Validar Plano Query Semantico | code | 29935 | `FORBIDDEN_CONFIRMED` | Move validations/gates; financial DRE/sign mappings into context |
| 24 | Code - Schema Real Watson | code | 9041 | `FORBIDDEN_CONFIRMED` | Externalize full schema, predicates, versions and DRE groups |
| 25 | IF - SQL Aprovada? | if | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 26 | Code - Router de Modo | code | 876 | `MIXED_TO_VERIFY` | Review code before retaining |
| 27 | IF - Modo Execução SQL? | if | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 28 | Code - Validar SQL Recebida | code | 10401 | `MIXED_TO_VERIFY` | Check approval and SQL gate logic against product policies |
| 29 | IF - SQL Recebida Aprovada? | if | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 30 | Code - Config Watson Flow | code | 862 | `TRANSITIONAL_EXECUTION` | Review provider integration; do not disable execution implicitly |
| 31 | HTTP - Gerar Token IBM IAM | httpRequest | 0 | `TRANSITIONAL_EXECUTION` | Credential exchange is operational; preserve until execution adapter approved |
| 32 | Code - Montar Payload Watson Flow | code | 8987 | `TRANSITIONAL_EXECUTION` | Review data contract and provider payload boundary |
| 33 | HTTP - Chamar Watson Flow | httpRequest | 0 | `TRANSITIONAL_EXECUTION` | Official execution integration; separate cutover plan |
| 34 | Code - Normalizar Resultado Flow | code | 2375 | `MIXED_TO_VERIFY` | Review code before retaining |
| 35 | Code - Resposta Erro SQL Recebida | code | 491 | `MIXED_TO_VERIFY` | Review code before retaining |
| 36 | Code - Montar Relatório Executivo | code | 21206 | `FORBIDDEN_CONFIRMED` | Business thresholds/rules into versioned reporting context |
| 37 | Code - Resolver Opções Cache SQL | code | 868 | `MIXED_TO_VERIFY` | Review code before retaining |
| 38 | Code - Normalizar Chave Cache SQL | code | 2514 | `MIXED_TO_VERIFY` | Review code before retaining |
| 39 | IF - Usar Cache SQL? | if | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 40 | Postgres - Buscar Cache SQL | postgres | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 41 | IF - Cache Hit? | if | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 42 | Code - Usar SQL Cacheada | code | 1099 | `MIXED_TO_VERIFY` | Review code before retaining |
| 43 | Code - Cache Miss Metadata | code | 529 | `MIXED_TO_VERIFY` | Review code before retaining |
| 44 | Code - Cache Desativado Metadata | code | 447 | `MIXED_TO_VERIFY` | Review code before retaining |
| 45 | IF - Cache Hit Validado? | if | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 46 | Postgres - Atualizar Hit Cache SQL | postgres | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 47 | Code - Cache Hit Metadata | code | 809 | `MIXED_TO_VERIFY` | Review code before retaining |
| 48 | Code - Preparar Salvar Cache SQL | code | 1527 | `MIXED_TO_VERIFY` | Review code before retaining |
| 49 | IF - Deve Salvar Cache SQL? | if | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 50 | Postgres - Salvar Cache SQL | postgres | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 51 | Code - Cache Salvo Metadata | code | 711 | `MIXED_TO_VERIFY` | Review code before retaining |
| 52 | IF - Cache Hit Reprovado? | if | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 53 | Postgres - Desativar Cache SQL | postgres | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 54 | Code - Cache Rejeitado Fallback IA | code | 776 | `MIXED_TO_VERIFY` | Review code before retaining |
| 55 | Postgres - Criar Tabela Cache SQL (manual) | postgres | 0 | `DISCONNECTED_MANUAL` | DDL node unconnected in snapshot; confirm safe/disabled in live |
| 56 | Code - Criar Run Context | code | 4145 | `MIXED_TO_VERIFY` | Review code before retaining |
| 57 | Code - Anexar Uso LLM | code | 3304 | `MIXED_TO_VERIFY` | Review code before retaining |
| 58 | Code - Montar Semantic Request Observado | code | 14873 | `MIXED_TO_VERIFY` | Audit duplicated semantic rules and evidence fields |
| 59 | Code - Avaliar Reparo SQL | code | 12510 | `MIXED_TO_VERIFY` | Preserve repair approval contract; identify special cases |
| 60 | IF - Deve Reparar SQL? | if | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 61 | Code - Montar Body Reparo SQL | code | 6868 | `TRANSITIONAL_PROVIDER` | Move repair request logic behind LangGraph |
| 62 | Gemini - Reparar SQL | httpRequest | 0 | `TRANSITIONAL_PROVIDER` | Replace direct n8n Gemini repair after parity |
| 63 | Code - Preparar SQL Reparada Para Cleaner | code | 4470 | `MIXED_TO_VERIFY` | Review code before retaining |
| 64 | Code - Montar SQL Preflight Watson | code | 2364 | `TRANSITIONAL_EXECUTION` | Preflight transport; preserve capabilities and safety |
| 65 | Code - Config Watson Preflight SQL | code | 1535 | `TRANSITIONAL_EXECUTION` | Review preflight config and provider adaptation |
| 66 | HTTP - Gerar Token IBM IAM Preflight | httpRequest | 0 | `TRANSITIONAL_EXECUTION` | Review IAM token acquisition lifecycle |
| 67 | Code - Montar Payload Preflight Watson | code | 8436 | `TRANSITIONAL_EXECUTION` | Inspect preflight payload and SQL isolation |
| 68 | HTTP - Chamar Watson Preflight SQL | httpRequest | 0 | `TRANSITIONAL_EXECUTION` | Legacy preflight transport; no automatic PROD changes |
| 69 | Code - Normalizar Preflight SQL | code | 8338 | `MIXED_TO_VERIFY` | Normalize preflight result under LangGraph gates |
| 70 | IF - Preflight SQL Aprovado? | if | 0 | `STRUCTURAL_TO_VERIFY` | Retain branch orchestration after parity |
| 71 | Code - Diagnosticar Retorno Preflight SQL | code | 7896 | `MIXED_TO_VERIFY` | Validate diagnostic reason categories |
| 72 | Code - Avaliar Retry Preflight Transporte | code | 3276 | `STRUCTURAL_TO_VERIFY` | Transport retry only, never SQL semantic repair |
| 73 | IF - Retry Preflight Transporte? | if | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 74 | Wait - Retry Preflight | wait | 0 | `RETAIN_TO_VERIFY` | Retain or migrate orchestration only after review |
| 75 | Code - Preparar Retry Preflight SQL | code | 1893 | `STRUCTURAL_TO_VERIFY` | Transport retry metadata only |

**Distribuição da triagem:** `RETAIN_TO_VERIFY`=21, `MIXED_TO_VERIFY`=30, `STRUCTURAL_TO_VERIFY`=4, `FORBIDDEN_CONFIRMED`=6, `TRANSITIONAL_PROVIDER`=4, `TRANSITIONAL_EXECUTION`=9, `DISCONNECTED_MANUAL`=1. A contagem de ocorrências/bytes **não é** contagem de hardcodes distintos ou prova de conformidade.

## Fluxo de remediação sem reproduzir hardcodes

1. **Confirmar fonte atual:** obter exportação de workflow ativo **sem executá-lo, sem alterar credenciais ou prompts**; comparar hash/identidade de nós e revisão com export histórico. Nunca incluir uma exportação bruta sensível em ChatGPT, logs, PR ou ticket.
2. **Inventariar cada regra concreta:** id/nó/linha de origem, exemplo estrutural e impacto, etiqueta STRUCTURAL/TRANSITIONAL/FORBIDDEN, fonte de verdade da regra, destino do contexto versionado, teste/paridade, risco e data de retirada. Para cada `MIXED_TO_VERIFY`, não marcar como resolvido sem revisão.
3. **Externalizar:** catálogos, métricas, períodos, relações, aliases, mappings DRE quando aplicável, filtros e versões do orçamento ficam no contexto por tenant; validar integridade/fingerprints e campos desconhecidos com fail-closed. Arquitetura: n8n operacional, LangGraph semântico e Produto responsável por apresentação/segurança.
4. **Comparar dois caminhos com Gemini:** n8n/Gemini oficial versus n8n/LangGraph/Gemini Shadow. Registrar divergências por semântica, SQL, políticas, provider e resultados; resultado numérico exige gate específico read-only isolado. Não ajustar SQL por `golden answer`.
5. **Portabilidade e corte:** comprovar ao menos dois contextos diferentes, retirar somente inteligência legada no cutover humano com rollback; preservar integrações determinísticas n8n.

## Comparador de exportações — somente leitura

Script genérico: `scripts/audit_n8n_workflow_export_readonly.py`. Ele **não conhece** DRE, SQLs esperadas, cliente nem marcas. Aceita arquivos locais explicitamente fornecidos, gera somente tipo/nome higienizado, status, indicadores de revisão e fingerprints SHA-256 de parâmetros/código. Não publica URLs, prompts, SQL ou secrets, não conecta no n8n e **não executa SQL**.

```bash
python3 scripts/audit_n8n_workflow_export_readonly.py \
  --workflow /caminho/privado/ao/workflow-atual.json \
  --compare-to /caminho/privado/ao/workflow-anterior.json \
  > /caminho/privado/ao/relatorio-seguro.json
```

- **Atenção:** o arquivo de exportação bruto pode conter prompts e credenciais embutidos nos parâmetros. Mantenha-o fora do repositório e não envie seu conteúdo para o ChatGPT. Compartilhe apenas o relatório sanitizado; preserve evidências privadas no ambiente autorizado.
- Este relatório não constitui auditoria completa do n8n atual, nem autorização de mudança no n8n ou no banco.
- Para a prova de cutover, conferir também versão dos workflows e prompts **ativos** e diferenças de execução/SQL frente ao produto. Não inferir estado atual de um `active: true` arquivado.

## Evidências pendentes por gate

- **G1:** confirmar ativação/dispatch real no produto e correlação auditável ao n8n oficial, não apenas mock ou workflow isolado.
- **G2:** conciliar export histórica x workflow vivo e encerrar `MIXED_TO_VERIFY`; testar externo com dois contextos distintos.
- **G3:** provar paridade funcional e depois equivalência financeira com read-only explicitamente autorizado.
- **G4–G5:** preservar approval/reapproval, isolamento, políticas, canário e rollback antes de substituir apenas inteligência antiga.
- **G6:** comparação Gemini × SQL-InfoDive só após homologar a nova arquitetura.
