## 13/11/2026 — Bloco 1: ponte real de G5 para revisão contábil (SEM homologação)

**Verificado na VPS:** versão G5 selecionada pelo n8n publicado ligada ao manifesto privado de 11 ciphertexts; versão ativa SHA-256 7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485 e 77 registros (18 regras, 40 aliases, 11 DRE, 8 catálogo), com hash do ciphertext íntegro. As 11 versões contêm 1.275 registros sem SQL patterns. Todos seguem ENCRYPTED_NOT_APPROVED; zero significados contábeis validados e zero SQL financeira executada. Fonte e benchmark de 63 perguntas permanecem separados.

**Engenharia nova:** scripts/operations/g5_financial_crosswalk_review.py exige cobertura linha a linha do registro original por hash/versão, classificação STRUCTURAL/FORBIDDEN e, para toda regra de negócio, destino canônico explícito; rejeita TRANSITIONAL/UNRESOLVED, ausência/duplicação de registros, troca de tenant, contexto ou fingerprint, destino inexistente, SQL histórica, assinatura ausente ou inválida. Um aprovador independente precisa autenticar digest integral de revisões, contexto e fonte; o código apenas verifica, não emite assinatura. O script g5_targeted_financial_review_offline.py gera um draft privado junto ao pacote verificado, depois de TTY/passphrase local. A nova g5_financial_crosswalk_review_cli.py verifica todos os artefatos privados em modo read-only e pode emitir somente CANDIDATE_NOT_ACTIVATED. Sem importar/aprovar/ativar catálogos por conta própria. Testes sintéticos em dois contextos e 77 linhas simuladas. Documentação: docs/operations/G5-FINANCIAL-CROSSWALK-REVIEW.md.

**Aceite BLOQUEADO por dependência real:** a passphrase local não está disponível nesta sessão e não existe unapproved-source-packet.json já decifrado. A revisão financeira efetiva de 77 linhas e aprovação independente não foram realizadas. A prova de paridade financeira n8n/Gemini × LangGraph/Gemini continua sem autorização read-only. CI e protótipos sintéticos não substituem isso. Preservar PR #233 sem merge, n8n oficial inalterado, LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. Não anunciar Bloco 1 concluído.

---

## 12/11/2026 - Prova funcional de filtros aprovados sem omissao silenciosa

Nova integracao planner -> composicao -> gerador -> SQL Contract Gate aplica resolved_filter_bindings a todos os fact streams por conceito e dimension_columns declarado pelo tenant. Corrigiu lacuna critica: no HTTP Canonical Shadow os matched terms do resolvedor desapareciam se o campo semantic_signals opcional faltasse, gerando SQL geral apesar de filtro solicitado. O termo agora cruza com segurança a fronteira do classificador, e cada fonte deve comprovar coluna correspondente. Termos sem binding, tipos incompativeis, joins nao aprovados e alteracao de plano rejeitam antes de gerar SQL. Evidencia: dois schemas diferentes, perguntas sinonimas, filtros =/IN/NOT IN, verificacoes de SQL, 28 SELECTs sinteticos read-only no PostgreSQL 16 descartavel e 2 ACL cross-tenant bloqueadas. Sem SQL cliente, Gemini, n8n editado, G5 plaintext ou benchmark usado no gerador.

G5 original ainda requer mapeamentos contabeis aprovados a partir de 77 registros cifrados, e paridade real n8n+Gemini x LangGraph+Gemini. OFFICIAL=n8n; SHADOW=LangGraph; LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. PR #233 draft, sem merge.

---

## Extensão de calendário e prova numérica — 12/11/2026

**Contrato opcional versionado:** cada `metric_source_compositions[]` pode incluir `temporal` com `require_explicit_grain` boolean, `granularities` (granularidade `day/week/month/quarter/year` e `terms` arbitrários do tenant) e `source_dates` (um `source_ref` e uma `target_column` DATE por fonte). `unhandled_period_terms` opcional declara referências que, se solicitadas, **não podem ser ignoradas** enquanto falta uma projeção de intervalo. A ausência de `temporal` preserva a SQL e o fingerprint de snapshots legados sem composição temporal.

A normalização exige: datas fisicamente presentes em cada `table_catalog[].date_columns` e `columns` com `data_type=date`; dados do tipo timestamp/timestamptz são recusados, para não inventar timezone. Exige também que a medida conste em `metric_columns`, seja numérica (`numeric/decimal/smallint/integer/bigint`) e que `source.grain_ref` coincida exatamente com `table_catalog[].grain.grain_ref`. Tudo isso é **metadado aprovado por tenant**, sem tabelas, métricas, contas, nomes, datas ou sinais financeiros hardcoded no motor.

O planner identifica somente termos de granularidade presentes no contexto e monta `temporal_grouping`, preservando as datas distintas. O compilador PostgreSQL usa `date_trunc` em cada SELECT da união, faz `UNION ALL`, depois `SUM` e `GROUP BY time_bucket` (com dimensões por fonte quando pedidas). `SqlGeneration` encaminha toda a proveniência. `SqlContract` verifica a equivalência estrutural ao renderer construído do QueryPlan aprovado, inclusive sinal, filtros, grão, agrupamento e fonte. Uma alteração do mês para ano, ausência de filtro, data divergente, `UNION` deduplicante ou coluna não autorizada falha no gate antes de qualquer execução.

**Ano-calendário dinâmico por contexto:** `temporal.period_year` é opcional e estritamente versionado. Exige `calendar_year_attested=true`, `allow_bare_year` boolean, `require_year` boolean e `year_terms` fornecidos pelo tenant. Para a pergunta inédita `monthly in 2026`, o plano extrai 2026 somente quando essa política foi autorizada; a SQL de cada fonte inclui `DATE >= '2026-01-01' AND DATE < '2027-01-01'` antes de `UNION ALL` e da agregação. Mudanças de ano alteram a SQL; mudar fonte, filtrar data errada ou omitir os limites é rejeitado pelo Contract Gate. Sem política, com anos ambíguos, `9999`, referência não autorizada ou `unhandled_period_terms` (ex.: trimestre anterior), o planejador falha sem produzir total de outros exercícios. **Ano fiscal, intervalos plurianuais e timestamp/timestamptz não são inferidos e continuam pendentes.** Os anos de exemplo são **sintéticos**, sem ligação ao G5.

**Provas:** 26 testes na suíte `testar_metric_source_composition_e2e.py`, incluindo SQLite em memória com duas estruturas sintéticas, sinais, filtros e três meses distintos; resultados sintéticos mensais **130, 55, -5** e anual **180** nos dois contextos. SQLite usa uma função de bucketing de data *simulada*, portanto **não valida dialeto PostgreSQL nem evidencia números financeiros reais**. Outras 6 verificações atravessaram o endpoint interno real em Docker sem rede (LangGraph, tenant, contexto versionado, adapter real pinned, gates e evidência); 13 testes canônicos e 5 de integração do grafo passaram. Evidência sanitizada SHA-256 `b085eadba30c4125f215c722d8363591a631e0eafebb0bdfb87e5b66fc8f1db5`, arquivo privado na VPS. Nenhuma consulta a clientes, Gemini, G5 plaintext ou benchmark.

**Resultado numérico adicional com filtro de ano:** a SQL gerada para duas estruturas sintéticas filtrou corretamente os dados de 2025 e 2027, retornando **70** para janeiro de 2026 em ambos os contextos. O banco do teste é SQLite em memória com `date_trunc` simulada, não PostgreSQL real nem finanças de cliente. `metric-composition-calendar-year-evidence-v4.json` privado contém hashes de 2 contextos × 2 granularidades, com SHA-256 `b085eadba30c4125f215c722d8363591a631e0eafebb0bdfb87e5b66fc8f1db5`.

**Adapter explícito:** `app/adapters/postgres/catalog_composition_sql_generator.py` implementa a mesma porta `SqlGenerator`, **somente** se instanciado para `canonical_snapshot` e com `expected_context_version` e `expected_context_fingerprint` válidos. Não é registrado automaticamente no runtime ou Gemini, não substitui LLM de ninguém, não executa SQL e informa consumo de tokens zero. Inconsistência de contexto/versão/SQL retorna reason code sanitizado, sem revelar DSN, tabela ou segredo.

**Estado de migração financeira:** `IMPLEMENTED_UNPROVEN`. A operação estrutural da união usada no n8n foi portada; a semântica dos lançamentos/rateios, fórmula, natureza das contas, mapeamento da versão G5 com 77 registros cifrados e fidelidade dos números permanecem **não aprovados/não demonstrados**. A afirmação de portabilidade é **somente para dois contextos sintéticos**, não para clientes reais. O benchmark de 63 perguntas não participou do gerador, dos testes nem desta evidência.

---

## Atualização de lacuna — mecanismo de composição de fatos (11/11/2026)

**Lacuna estrutural reduzida:** nó 22, `planDreMensalAnalitica` (1973–2027), prescreve `UNION ALL` de fatos antes de somar. O novo mecanismo `metric_source_compositions` seleciona fontes/medidas/sinais/grãos/filters por catálogo sem código cliente e compila SQL dinâmica de leitura; o SQL Contract exige equivalência estrutural exata por token ao plano derivado, e os dois cenários sintéticos passaram inclusive pelo LangGraph HTTP isolado (gerador injetado). `docs/architecture/GENERIC-MULTISOURCE-METRIC-COMPOSITION.md` detalha evidência e limites.

**Permanece ABERTO:** transferência dos significados contábeis, dos 77 registros G5 da versão oficial cifrada, prova com Gemini real, operação n8n Shadow correlacionada e igualdade numérica autorizada. Estado da capacidade do legado = `IMPLEMENTED_UNPROVEN`, não `PROVEN`. Dois catálogos sintéticos não substituem dois clientes reais.

---

## 11/11/2026 — FONTE DEMO NÃO É A SEMÂNTICA DO LEGADO (VERIFICAÇÃO REAL)

**Sem perguntar ao operador nem executar SQL financeira**, foram verificadas as duas fontes Supabase já conectadas. O projeto SOURCE original do Agente Financeiro está `INACTIVE` e sua API de esquema retorna indisponível. A DEMO está `ACTIVE_HEALTHY` e, além das 13 tabelas do schema `public` anteriormente examinadas, **possui as cinco coleções `ai_ducklake_*` no schema `semantic_context`** (regra, aliases, DRE, catálogo e padrões históricos). Na DEMO, SELECT agregado **somente de hashes de versão e contagens** sobre as quatro coleções de conhecimento — sem tocar as linhas de `sql_patterns` ou consultar valores financeiros — confirmou **10 versões**, totalizando 110 regras, 605 aliases, 130 DRE e 80 registros de catálogo. Os 10 hashes foram comparados ao manifesto G5 original na VPS: **0/10 versões comuns às 11 versões do G5**. A versão selecionada pelo workflow oficial permanece **somente no G5** (`7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485`).

**Consequência obrigatória:** jamais copiar a semântica da DEMO para substituir a fonte antiga ou declarar paridade só porque os nomes das cinco tabelas coincidem. O workflow n8n usa duas identidades de credencial PG: grupo G1 (nó 5 e outros de contexto/cache), grupo G2 (nós 66/67 preflight/executor); IDs separados **não provam** bancos nem autorizações iguais. As definições contábeis dos 77 registros da versão oficial permanecem cifradas e **não homologadas**; requerem custódia GPG legítima, que não deve ser contornada nem exigida ao operador como tarefa de rotina. Continuar engenharia reversa dos JS e mecanismos genéricos com as fontes disponíveis. SQL financeira real, alterações de banco, ativação de contexto, cutover e merges continuam bloqueados pelos gates humanos.

**Correção de CI:** no commit `86733408284d728caf91bc3735a24d6d6ab22de5`, o teste GPG trata Windows de forma *fail-closed* sem enfraquecer Linux POSIX. A suíte local (7 testes G5 + 16 de versão + 10 de crosswalk) passou; CI do HEAD deve ser reconfirmado. Acesso à VPS já está concedido: **não pedir comandos SSH ao usuário**.

---

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
