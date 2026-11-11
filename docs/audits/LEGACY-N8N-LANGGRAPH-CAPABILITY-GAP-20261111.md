# Matriz de capacidade: n8n legado → Produto + n8n + LangGraph

**Data:** 11/11/2026. **Status:** implementação disponível NÃO é homologia funcional nem financeira. Fundamentado em export n8n publicada de 68 nós, código real do Produto Next.js, módulos LangGraph e manifestos G5; [matriz funcional completa](LEGACY-N8N-PRODUCT-FUNCTIONAL-MAP-20261111.md).

**Execução referenciada:** Produto `leandrosilveiradepaula/Agente-Financeiro` main `5f6d5113cd69ebcc4475a6f6046046051b8250ac`; LangGraph/VPS operacional em `87d167969345c3dfcf9deaf36e33ab07a1f9c890`; PRs #230/#231 de semântica, planejamento e gates **ainda não mergeadas**. O teste de integração virtual de PRs não equivale ao runtime oficial do Shadow.

| Capacidade real | Fonte existente | Código alvo inspecionado | Estado verificado | Gate necessário |
|---|---|---|---|---|
| Entrada, auth, RBAC, políticas e aprovação | Produto Next.js + n8n 1/2/26/27/28/29 | Produto: `app/api/generate-sql`, `app/api/execute-watson` | Implementado no Produto atual; correlação em ambiente efetivo ainda não atestada | Conferir URL/env, fingerprint SQL aprovada, revisão humana e RLS |
| Contexto semântico e versão | n8n 5/7/24/63/64 + G5 cinco coleções | `load_context.py`, `context_repository.py`, `context_normalizer.py` | Código presente; G5 11 versões e semântica financeira não mapeados para contexto ativo | Ler 11 pacotes e versionar regras/aliases/colunas/joins por tenant |
| Intenções dinâmicas | n8n 6 | `classify_intent.py`, `semantic_classification.py`, `intent_resolver.py` | Código de resolução presente; PR #230 fallback opcional não mergeada; sem paridade de significados | Inventariar decisões reais do Code6 e migrar sem palavras-chave no código |
| Plano e métricas | n8n 22/23 | `build_plan.py`, `planner.py`, `semantic_plan_gate.py` | Código presente e testes offline; PR #231 schema ACL não mergeada; contexto histórico insuficiente | Migrar catálogos, período, sinais, unidade, relacionamento/joins, operações |
| Prompt, Gemini e geração | n8n 8/9/10 | `generate_sql.py`, `sql_generation.py`, Gemini/provider adapters | Código presente; sem execução comparativa Gemini real na arquitetura Shadow homologada | Substituir composição n8n por prompt gerado do contexto aprovado |
| Cleaner e normalização SQL | n8n 11/59 | `sql_generation.py`, `sql_analysis.py`, reparo e normalização | Código e parsing disponíveis; equivalência de comportamento n8n não provada | Comparar semântica, proteção contra SQL extra, tags e dialect |
| SQL Security/Contract Gates | n8n 12/23/28 e Product policy | `security_gate.py`, `contract_gate.py`, `sql_security.py`, `sql_contract.py` | Offline PASS; sem prova no SQL/DRE/mapeamento G5 real | Exigir schemas/colunas/joins/tenant/SELECT/limite e fail closed |
| Repair controlado | n8n 55/56/57/58/59 | `repair_sql.py` e `internal_sql_agent_v1_execute_shadow.py` | Proposal e `requires_reapproval` existem no Shadow; paridade e integração ainda pendentes | Nunca executar SQL reparada sob aprovação antiga |
| Preflight e executor | n8n 60/61/62/66/67/68 | `engine_preflight.py`, `execute_sql.py` e executor injetado | Preflight/execução simulados offline; SQL real no Shadow permanece desabilitada | Comprovar separação generate/approve/execute e credenciais de menor privilégio |
| Cache de SQL por contexto | n8n 33-50 e 36/42/46/49/51 | n8n operacional + Produto cache metadata | Cache real n8n presente; não comprovada chave/ACL multifonte no novo fluxo | Manter no n8n, vincular tenant/policy/context/provider/fingerprint e revalidar em hit |
| Logs, filas, recibos e métricas de LLM | n8n 17-21, 52/53; Produto run/audit | Produto `agent-runs`, Shadow evidence/persistence | Código existe; 8 nós do n8n fora da rota inicial; nenhuma trilha oficial+Shadow certificada | Provar persistência idempotente, lineage e evento real com ids correlacionados |
| Relatórios e apresentação | n8n 15/16/19/30/32; Produto | `normalize_result.py`, `serialize_result.py`, UI Next.js | Normalização existe; relatório financeiro de n8n não foi funcionalmente migrado | Externalizar semântica de relatório e apresentar sem dados fabricados |
| Multiempresa e fontes diferentes | g5 P3 e aliases de 11 versões, duas credenciais PG | ContextSnapshot, injeção de PostgresContextRepository | 2 tenants sintéticos testados, nenhum tenant real distinto homologado | Provar isolamento DSN/schema/version/ACL e dialetos sem mudar código |
| Benchmark exclusivamente de qualidade | 63 perguntas e respostas do sistema n8n | avaliador independente offline e Shadow comparativo | 63 perguntas congeladas; apenas comparação parcial de interpretação e estrutura, **zero paridade financeira comprovada** | Só comparar respostas **após** gerar independentemente e obter aprovação read-only para igualdade numérica |

## Dependências de portabilidade observadas na implementação

O adaptador real `app/adapters/postgres/context_repository.py` usa um `PostgresContextRepository` parametrizado por DSN, `semantic_agent_version`, schema e nomes de tabelas; consulta via SQL parametrizada e pode validar fingerprint esperado. Isso é uma base estrutural de portabilidade, mas:

- O `ContextRepository` do grafo recebe apenas `user_profile` como argumento de leitura. A implementação PostgreSQL **descarta explicitamente `user_profile`**; o escopo depende da injeção externa do DSN/schema/version. Para instância multicliente compartilhada, deve existir prova de vinculação inequívoca do principal/tenant ao adaptador correto. Não é evidência de violação por si só.
- O template legado e as tabelas padrão do adaptador ainda usam identificadores DuckLake e projeção com colunas DRE fixas (inclusive fallback tipado para DRE opcional). Isso **exige revisão para portabilidade entre esquemas contábeis materialmente diferentes**; simples mudança de nome de tabela não prova que outras fontes/colunas sejam aceitas. É dívida de externalização a inventariar, não licença para adicionar `if` por cliente.
- A projeção do adaptador consulta também `sql_patterns`; no G5 há 106 padrões históricos explicitamente reservados à **avaliação somente**. Antes de qualquer importação, provar que SQL histórica/golden answer não alcança o contexto de geração, mesmo que padrões **estruturais** versionados possam existir em contextos aprovados.
- Os fluxos físicos do n8n usam 2 referências distintas de credenciais PostgreSQL (9 nós de contexto/cache/log/configuração; 2 de preflight/execução). IDs distintos **não provam** isolação física ou privilégios. O Shadow jamais deve importar credenciais operacionais de outro tenant nem ativar SQL real por conveniência.
- O banco SOURCE Supabase permanece INACTIVE; DEMO apresenta 13 tabelas `public` de controle/Produto. Os conteúdos dos 11 pacotes G5 cifrados ainda não foram descriptografados/homologados nesta etapa, embora existam manifests e lineage verificáveis.

## Hardcodes: o que a inspeção realmente mostrou

O corpo de todos os 41 Code nodes foi percorrido lexicalmente: **14.440 linhas**, **3.403 ocorrências de literais de string** (das quais 1.987 com dez ou mais caracteres) e 3 templates longos nos nós 8, 32 e 57; relatório privado com hashes/linhas, sem texto de SQL ou prompt, SHA-256 `0cf84e8e577f32f35493d4c64852022c9545649dc5bcde4f78c606b1057e8b58`. Os nós 22 (726 literais), 32 (495), 6 (256) concentram muitas referências e requerem prioridade em revisão. **Não afirmar que cada literal é hardcode financeiro**: constantes de interface, SQL determinística e textos de erro são distintos de regras de negócio. A classificação item a item STRUCTURAL/TRANSITIONAL/FORBIDDEN continua pendente até contexto e comportamento serem revisados.

## Aceite e sequência inalterável

1. Crosswalk real **regra n8n + ramo → versão G5 + objeto físico → definição contábil → destino → teste**, com aprovação de significado financeiro.
2. Externalização de regras e implementação das funcionalidades faltantes no LangGraph e no n8n, mantendo o Produto. Resolver o gate de tenant/versão e os percursos geração/reparo → execução.
3. Testar perguntas **inéditas** sob dois contextos reais materialmente diferentes e autorizações isoladas, preservando evidências e denominadores.
4. Comparar 63 perguntas **somente como controle de qualidade posterior**, nunca corpus para gerar SQL, sem ajustar thresholds ou copiar golden answers.
5. Fase 1 Shadow `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. Equivalência financeira numérica exige autorização read-only distinta; cutover humano e reversível somente depois da paridade; comparação Gemini × SQL-InfoDive na Fase 3.

**Não concluído:** engenharia contábil plena das versões G5, SQL real, paridade, incorporação de PRs #230/#231, proof of Product routing, tenants reais, implementação completa e cutover.
