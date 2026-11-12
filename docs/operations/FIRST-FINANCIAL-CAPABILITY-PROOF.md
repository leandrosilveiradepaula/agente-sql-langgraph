## 12/11/2026 - Evidencia atualizada de fonte e formula parametrica (sem homologacao G5)

O novo inventario docs/audits/LEGACY-N8N-BUSINESS-RULE-SITES-20261112.md comprova 24 trechos exatos no n8n publicado (linhas e hash, sem SQL/prompts/valores) em 10 nos, com 41 codigos indexados. Identifica dependencia de formula percentual e regras gerenciais antigas, **sem importar metricas ou constantes contabeis** do legado ao runtime. Nao sao 3.403 literais individualmente homologados. A origem G5 (77 registros da versao ativa) continua sem significado contabil aprovado.

O contrato versionado opcional metric_source_compositions[].calculation agora representa uma razao generica de dois somatorios por fontes, com sinais/operadores/escala escolhidos por tenant, e protege divisao por zero. Gerador PostgreSQL dinamico, SQL Security/Contract Gates e HTTP Shadow canonico validados em 2 tenants sintéticos; PostgreSQL 16 descartavel confirmou 10 SELECTs read-only, 2 ACL cross-tenant rejeitadas, valores e NULL com denominador ausente. **Sem execucao SQL de cliente, Gemini real, decriptacao G5 ou benchmark na geracao**. NAO representa paridade financeira do sistema antigo.

---

## 12/11/2026 - Inventario funcional dos 68 nos: ENTREGA ESTATICA FECHADA

**O escopo do inventario funcional de nos foi concluido no export n8n publicado e ativo**, sem edicao nem execucao do workflow. Auditoria no codigo real reconfirmou **68/68 identidades e configuracoes/corpos, 78/78 arestas por porta, 41 Code, 11 PostgreSQL, 10 IF, 2 HTTP, 3 respostas e 1 Webhook**, contra o crosswalk privado anterior. Dos 68, **60 sao alcancaveis pelo webhook e 8 (15,17,18,19,20,21,51,53) estao fora dessa rota**, sem presuncao de que sejam excluiveis. Os 10 IF possuem True/False documentados; IF 25, 29 e 62 sao gates tecnicos, **nao aprovacao humana**. Onze operacoes PostgreSQL foram categorizadas como leitura, cache, auditoria/fila, DDL isolada, preflight ou execucao SQL dinamica, sem executar SQL. Dois HTTP POST sao Gemini geracao/reparo.

**Artefatos rastreaveis:** docs/audits/LEGACY-N8N-FUNCTIONAL-INVENTORY-20261112.md (matriz humana dos 68 nos), docs/audits/legacy-n8n-functional-inventory-20261112.json (matriz por porta, hashes e classes), scripts/operations/legacy_functional_inventory_offline.py (revisor deterministico fail-closed, sem negocio em runtime), testar_legacy_functional_inventory_offline.py (negativas e 68/78). Arquivo de workflow bruto permaneceu PRIVADO na VPS; nao houve SQL/prompt/credencial exposta, benchmark, chamada de modelo, alteracao do n8n, Supabase ou cutover.

**Classificacao preliminar por responsabilidade de no:** 25 STRUCTURAL, 33 TRANSITIONAL, 10 nos com FORBIDDEN de negocio identificado no legado (candidatos a externalizar). Nao equivale a revisao literal individual de 3.403 strings nem a homologacao contabil. A identidade/configuracao e corpos dos 68 nos e todas as arestas conferem com o baseline; hashes dos exports brutos diferem porque ha metadados/serializacao ainda nao homologados no nivel integral de arquivo. Nao confundir com drift funcional demonstrado.

**SEPARACAO DO GATE:** esta entrega encerra o inventario FUNCIONAL ESTATICO dos nos do Bloco 1, mas NAO atesta que a inteligencia financeira foi migrada. Regras/aliases/metricas/joins do G5 (77 registros da versao ativa cifrada) seguem sem aprovacao contabil; paridade real, Gemini e dois clientes reais pertencem a homologacao posterior. OFFICIAL=n8n; SHADOW=LangGraph; LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. PR #233 segue draft, sem merge e sem custo/privilegios ampliados. Nao criar PRs de evidencia parcial.

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

## Estado: mecanismo de composição estrutural executado, contabilidade G5 não comprovada

Os nós 22/8 do legado revelaram uma operação estrutural genérica: combinar lançamentos de diferentes fontes antes de somar, com grão, sinais, filtros e agrupamentos. Foi implementado contrato `metric_source_compositions` por tenant e **comprovada** a interpretação/planejamento/SQL dinâmica/validação e HTTP LangGraph com **dois contextos sintéticos independentes** (sem SQL financeira executada). Ver `docs/architecture/GENERIC-MULTISOURCE-METRIC-COMPOSITION.md`, testes E2E e relatório privado SHA `7d072603f211ad1fde940d809c366246bfa3c2cfdfda77a7b328ea89e6dc2db6`.

**Não elevar para `PROVEN` no legado.** Falta vincular os filtros, fórmulas, sinais e dados físicos à **versão oficial G5** e obter significado financeiro aprovado; 77 registros cifrados permanecem sem revisão. Gemini real, paridade numérica, segundo cliente real, execução SQL read-only e integração n8n+Shadow oficial não foram homologados. O teste usa adapter SQL estrutural injetado, sem LLM e sem respostas do benchmark. Não reivindicar conclusão da migração.

---

# Primeira prova obrigatória — capacidade financeira real n8n/G5 → LangGraph

**Estado inicial: `NOT_MIGRATED` / evidência funcional `NOT_PROVEN`.** Contrato operacional vinculante de 11/11/2026 21:36 UTC. Não é autorização de executar SQL financeira, acessar dados sem permissão, publicar contexto, alterar n8n ou fazer cutover.

## Objetivo de produto

Demonstrar, em ambiente isolado e com pergunta **inédita**, uma capacidade financeira **já presente no sistema antigo**. Extrair o comportamento em conjunto do **workflow publicado com 68 nós** e do **banco/backup G5 na versão correta**. Externalizar sua definição como contexto semântico por tenant, executar a interpretação e planejamento reais do LangGraph, gerar SQL **dinamicamente** e validar os gates sem executar SQL financeira. Depois expandir a prova para todos os comportamentos necessários, com a mesma metodologia e sem `if cliente`.

## Capacidade candidata de investigação (não homologada)

O nó legado 22 contém funções estruturais com nomes `planConsultaMetricaFinanceira`, `factGrainContract`, `comparativeFactContract` e `commonManagerialRules`; o nó 6 faz classificação semântica; os nós 7/8/23/54 tratam regra, prompt, validação e projeção de métricas/dimensões. A cadeia observada de geração envolve **5 → 6 → 54 → 33 → 7 → 24 → 22 → 23 → 8 → 9 → 10 → 11 → 12**, sujeita a ramificações. Isso **não comprova** qual definição financeira, tabela, predicado ou regra por versão foi usado. Essas dependências devem ser confirmadas lendo os corpos reais e sua fonte G5.

**Seleção final:** somente escolher a pergunta inédita e a capacidade após identificar significado financeiro, registro/versão e mapeamento físico autorizados. Não aproveitar SQL de exemplos, baseline do n8n, 63 perguntas ou golden answers.

## Primeiro vínculo de origem verificado na VPS — ainda sem significado contábil aprovado

Foi feita uma **nova inspeção somente leitura** do export publicado n8n e do manifesto G5, com relatório privado em `/tmp` (não entregue ao gerador). Evidência:

- Export n8n publicado e ativo, 68 nós: SHA-256 `19dd24c29d81c61b12dc383f2124ca2e7ba77625776ee161f3be1996d2f09c68`.
- Nó 22 de planejamento financeiro: SHA-256 do código `113ce61f0e6c57b2cf260f70c6e04af1530e92876f4c6d10d5fbaa9c242f5d5f`; função `planConsultaMetricaFinanceira` na linha 2030 com uso na 2347; `factGrainContract` na 1073 e usos; `comparativeFactContract` na 1054 e usos; `commonManagerialRules` na 1105 e outras referências. Essas identificações comprovam **origem do código**, não correção da interpretação financeira.
- Nó 5 de leitura do contexto referencia as cinco coleções históricas: `ai_ducklake_agent_rules`, `ai_ducklake_dre_mapping`, `ai_ducklake_entity_aliases`, `ai_ducklake_sql_patterns` e `ai_ducklake_table_catalog`.
- Manifesto G5: **11 arquivos cifrados de versão presentes**. Conteúdo e significado contábil ainda **não comprovados nem aprovados**. Não usar os 106 padrões históricos como contexto de geração.
- SHA-256 do relatório privado de observação de origem: `e9c23d9e4b8dddd313359742546aa16eea0a2eab0bb40ae50ee1699ae6abe1d6`.

**Status:** `SOURCE_CODE_VERIFIED_G5_ACCOUNTING_NOT_ATTESTED` → capacidade continua `NOT_MIGRATED`, primeira prova real continua `NOT_PROVEN`. A próxima etapa não é criar novo parser: é estabelecer o vínculo contábil exato com a versão G5 e então gerar SQL com contexto aprovado. Leitura detalhada dos 11 pacotes exige desbloqueio local por TTY e custódia segura; jamais transmitir senha no chat/GitHub.

### Revisão de acoplamento físico/semântico — nova evidência, ainda NÃO PROVEN

Auditoria de fonte independente verificou que o nó 5 fixa um mesmo `agent_version` nas cinco consultas e lê padrões SQL históricos, que o nó 7 seleciona por intenção e injeta como texto na cadeia de prompt 8→9 (Gemini), e que no nó 22 **4 de 8 bindings físicos literais** têm match textual nos candidatos G5, **todos ambíguos**. Evidências, linhas, hashes e riscos: `docs/audits/LEGACY-N8N-G5-SEMANTIC-COUPLING-20261111.md`; relatório privado SHA `b9fc93f7986020aa4017a9a3641baf770e617eeab0a08d67c8ef36b205c8b179`. **Não há significado contábil aprovado**. Capacidade permanece `NOT_MIGRATED`/`NOT_PROVEN`; nenhuma SQL financeira executada.

### Gate de autorização e regras explícitas identificadas no prompt

Os IF 25 e 29 do n8n são acionados por verificações técnicas, **não comprovam aprovação humana**: nó 12 `success = validationErrors.length === 0` e nó 28 `aprovado = errors.length === 0`. Reparo e preflight devem permanecer separados de `Execute Approved` sob política Next.js. O prompt do nó 8 contém fórmula de percentual, convenção de sinal de orçamento e grupos DRE fixos, a migrar para contexto financeiro aprovado e **não para código**. Auditor completo: `docs/audits/LEGACY-N8N-G5-SEMANTIC-COUPLING-20261111.md`; relatório privado atualizado SHA `e5d6f3886730f16f484d40a1f818fb83d6ec563a5d2b8f2d34270bfb46fe612a`. Primeira capacidade ainda `NOT_PROVEN`.

## M1 — Escopo financeiro do workflow oficial reduzido a um pacote

Hash do seletor agent_version do nó 5: **7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485**, único entre as 11 versões do manifesto G5 (pacote 10/11). Esse pacote contém **18 regras, 40 aliases, 11 mapeamentos DRE, 8 registros de catálogo = 77 registros** (sem SQL histórica), com 48 hints físicos. O auditor version-aware mostra **3/8 bindings físicos** do nó 22 com match apenas textual nesse pacote, todos ambíguos; a análise de 4/8 cruzava outras versões e não será utilizada para declarar correspondência. Evidência privada SHA-256 **e376d3a3555d67467b57ece1949af4d26e1ca622f54487fc922c7d921521fbea**.

**Nova barreira em código:** contexto canônico bloqueia SQL examples / sql_pattern não vazio, business_question_examples, notas livres e padrões sem fonte estrutural aprovada mesmo se histórico declarado excluído; loader legado permanece intacto. Ainda não existe prova LangGraph com regra financeira real. Para desbloqueio seguro sob custódia TTY local, veja docs/operations/G5-ACTIVE-VERSION-LOCAL-REVIEW.md. A revisão privada não promove conhecimento automaticamente nem executa SQL financeira.

## Matriz de aceite por evidência

| Camada | Prova exigida | Estado atual |
|---|---|---|
| Origem do legado | SHA do export n8n publicado; nó/branch/condição; prova de efeito, entrada e saída; hashes do JS/prompt/SQL, sem código sensível no GitHub | Inventário estrutural disponível; comportamento da capacidade ainda não atestado |
| Fonte financeira | Registro e versão específica do G5, relação física, cardinalidade/granularidade, fórmula/sinal/período, confirmação do significado contábil | 11 versões/manifestos disponíveis; semântica desta capacidade **não validada** |
| Contexto autorizado | Métrica/dimensão/regra/filtro/alias em catálogo versionado e aprovado, vinculado a tenant, versão e fingerprint, sem SQL histórica | Loader canônico existe na PR #233; pacote real não aprovado/ativado |
| Motor | Mesma pergunta inédita interpretada, com plano verificável, geração dinâmica por LLM configurada, sem hardcode por cliente | Não comprovado com esta capacidade real |
| Segurança | Security/Contract Gates de escopo/SELECT, logs/fingerprints e `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`; Repair requer reaprovação | Mecanismos existentes; não testados em jornada completa desta capacidade |
| Independência | Outro contexto com estrutura materialmente diferente, mesmo motor sem alterar código, falha fechada para campo não mapeado | Testes sintéticos existentes, segunda empresa real pendente |
| Correlação | Run e artifacts auditáveis com fonte/context/provider/model/tokens e resultados; não usar benchmark para implementar | Não produzido para esta capacidade |

**Estados:** `NOT_MIGRATED` (não existe prova ou implementação suficiente), `IMPLEMENTED_UNPROVEN` (código presente, não há jornada real comprovada) e `PROVEN` (toda cadeia acima demonstrada, com evidência reproduzível). A marcação `PROVEN` não equivale a paridade numérica, que exige outro gate.

## Bloco de execução sem microtarefas artificiais

1. **Auditar o conteúdo real das funções e ramificações implicadas**, não só nomes/lexemas; isolar a lógica estruturante de fórmulas, métricas e filtros cliente-específicos. Marcar STRUCTURAL/TRANSITIONAL/FORBIDDEN e fonte de cada comportamento.
2. **Confrontar com o G5 por versão.** Usar os pacotes/backup mediante custódia autorizada, sem copiar segredos nem SQL histórica para prompts. Se a descompactação/decriptação exigir interação humana, informar esse único bloqueio legítimo e continuar o código genérico seguro.
3. **Validar definição financeira com responsável.** Não deduzir que alias e campo com grafia semelhante são equivalentes; se não houver definição, bloquear sem inventar.
4. **Externalizar no catálogo versionado.** Usar o carregador canônico e semântica aprovada por tenant, com relações, métricas, dimensões e operações configuráveis. Nenhum nome específico no novo código.
5. **Provar com pergunta inédita.** Ejecutar apenas geração/validação SQL autorizada; preservar provenance, fingerprint, provider/model, gates e status. Não executar SQL financeira nem disparar LLM paga sem autorização de custo.
6. **Provar o negativo:** contexto sem mapeamento, tenant incorreto, coluna não autorizada, join desconhecido, reparo sem reaprovação, schema diferente. Cada falha deve ser segura e auditável.
7. **Consolidar PR e evidências** em bloco substantivo: código, testes, hashes, resultado, comportamento migrado e pendências. Só então marcar uma capacidade `PROVEN` e avançar à seguinte.

## O que permanece vedado

- **63 perguntas + SQL/resultados históricos:** exclusivamente controle cego de qualidade **após** a geração independente; não instruções de negócio, golden SQL de entrada, thresholds de tuning, fontes de regras ou atalhos de benchmark.
- **Hardcodes financeiros:** não transportar fórmulas, contas, DRE, métricas, dimensões, aliases, filtros ou SQL pronta dos nós para Python/TS. Clientes com bases diferentes devem ser configuráveis, sem DRE obrigatória.
- **Execução:** `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. SQL read-only para equivalência numérica exige autorização separada e isolamento. Aprovações, permissões, credenciais, migrações, produção, merge e cutover dependem de gates humanos.
- **Prazos:** cronograma de 12–20 semanas retirado por falta de medição; não emitir estimativa nova a partir de quantidade de PRs ou testes.

## Critério de encerramento do projeto

**Além da primeira prova:** inventário completo e externalização das regras necessárias dos 68 nós + G5, todos os caminhos de negócio requeridos funcionando, duas empresas/contextos reais distintos sem alterar motor, integração real Produto/n8n/Shadow e paridade financeira com execução read-only autorizada, aprovação/reparos/rollback testados e cutover humano. Comparar Gemini versus SQL-InfoDive somente depois da Fase 2.
