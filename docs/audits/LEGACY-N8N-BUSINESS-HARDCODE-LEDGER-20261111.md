## 12/11/2026 - Censo de strings e externalizacao estrutural

Inventario n8n publicado: 24 sites concretos anteriores + 1.987 literais longos individualmente indexados, com triagem candidata F=1.144, T=187, S=424, U=232. As 1.416 strings curtas ainda nao foram ancoradas uma a uma. Nao equivale a aprovacao contabil das 3.403 ocorrencias, nem indica que todas sejam regras financeiras. Relatorio e politica exclusivamente audit-only em docs/audits/LEGACY-N8N-LONG-LITERAL-TRIAGE-20261112.md e JSON.

Capacidade generica nova: ranking por termos/direcao/limites do catalogo versionado por tenant sobre fontes assinadas e filtros aprovados, com numerador/denominador opcionais, periodo, agrupamento e contrato SQL. PostgreSQL 16 descartavel em 2 contextos sintéticos PASS (16 SELECTs somente leitura), sem Gemini, SQL financeira real ou benchmarks. G5 ainda requer reconciliacao de regra e significado financeiro homologado antes de ativacao; paridade real pertence ao Shadow posterior.

---

# Inventário inicial de lógica de negócio embutida no n8n — evidência de código

**Data:** 11/11/2026. **Escopo:** workflow n8n publicado, 68 nós, versão ativa coincidente; corpos de 41 Code nodes (14.440 linhas) inspecionados estruturalmente em memória, sem publicar seus literais, prompts ou SQL. Este é um **inventário de blocos/funções observadas**, não a interpretação homologada de todas as regras internas. Origem e topologia em [matriz 68 nós](LEGACY-N8N-PRODUCT-FUNCTIONAL-MAP-20261111.md). Toda regra financeira deve ser reconciliada contra as **11 versões G5**, não contra as 63 respostas do benchmark.

## Regra de classificação aplicada

- **STRUCTURAL:** protocolo, acesso, autorização, parsing, segurança SQL, cache operacional e roteamento genéricos, desde que não carreguem definições de negócio fixas.
- **TRANSITIONAL no legado:** funções ou parâmetros do n8n atual que precisam ser estudados e externalizados antes do cutover; não são aceitos automaticamente no novo motor.
- **FORBIDDEN no novo código:** tabela/coluna, DRE, métricas, fórmula, sinal contábil, aliases, filtros, marcas, unidades e cenários específicos no Python/TypeScript. A implementação genérica pode conhecer o processo, mas o contexto versionado conhece o negócio.

## Evidências identificadas nos arquivos JavaScript reais

| Nó n8n | Identificadores, funções e linhas observadas | Revisão / natureza provável | Destino permitido depois de revisão |
|---:|---|---|---|
| 6 | `termosDre` (281), `termosImpactoNegativoDre` (301), `termosComparacao` (321), `metricasFinanceirasDetectadas` (393) | **TRANSITIONAL**: léxico e condições de intenção; não copiar listas ao motor | Catálogos versionados de intenções/aliases/conceitos, classificação dinâmica LangGraph |
| 7 | `regras`, `entidades`, `dre`, `business_rule` | **REVIEW**: consolidação do contexto com dependência de negócio | Seleção genérica de contexto + regras versionadas |
| 8 | `prompt` (57), template longo; construção contextual de SQL | **TRANSITIONAL**: separar instrução SQL estrutural dos exemplos/condições financeiros específicos | Provider Gemini sob LangGraph, prompt estrutural; semântica exclusivamente do catálogo |
| 11 | limpeza/normalização, referências a DRE e aliases | **REVIEW**: parsing é estrutural, exceção financeira é proibida | SQL cleaner genérico + contexto aprovado |
| 12 | validação SQL, `allowedTableNames`, parsing de DRE/regras/aliáses | **REVIEW**: whitelist e sintaxe devem vir do escopo tenant, não da pergunta | Security/Contract Gates, catálogo e ACL |
| 22 | `TABLES` (853), `filtrosOpex` (874), `filtrosRol` (876), `filtrosDreDespesaCusto` (883) | **TRANSITIONAL / FORBIDDEN no novo código**: mapeamentos físicos e filtros contábeis embutidos | Catálogo de métricas/DRE, predicados e relações por versão; planner genérico |
| 22 | `comparativeFactContract` (1054), `factGrainContract` (1073), `commonManagerialRules` (1105), `planOrcadoVsRealizadoGrupoDre` (1303), `planDreMensalAnalitica` (1973), `planConsultaMetricaFinanceira` (2030) | **TRANSITIONAL**: operações, granularidade, agregações, cenários e regras gerenciais presentes na inteligência antiga | LangGraph planeja dinamicamente; contexto descreve contabilidade, grão, joins e operações |
| 23 | `patterns` (155), `metricasBase` (378), `rankingInstructions` (452), `inferSignContext` (529) | **TRANSITIONAL**: validação de plano com sinais e conceitos de negócio a revisar | Gate estrutural + sinais/ordem/ranking autorizados no catálogo |
| 24 | `runtimeDataSource`, `catalogName`, `schemaName`, `qualifiedPrefix` | **STRUCTURAL condicionado**: namespace/dialeto, não assumir um cliente | Adaptador e esquema explicitamente autorizados |
| 28 | validação de SQL recebida, tabelas e alias | **STRUCTURAL condicionado**: política de permissão e SQL nunca deduzida de benchmark | Security Gate do LangGraph e autorização Produto |
| 32 | `dimensionInfo` (254), `inferIntent` (337), `metricDescriptor` (534), `metricLanguage` (668), `genericSummary` (705), template longo | **TRANSITIONAL**: relatório executivo contém descritores e inferência financeira; não transportar textos de negócio ao código novo | Produto para apresentação; LangGraph/contexto para significado, unidade, sinal e narrativas verificáveis |
| 34 | `fnv1a`, `periodKey`, `rulesVersion`, `schemaVersionCache` | **STRUCTURAL com risco de escopo**: chave/cache precisa tenant, ACL, provider, modelo, versão e fingerprint; valor não é autorização | Cache operacional n8n/Produto, sempre revalidar SQL |
| 54 | `detectDimensions` (110), `detectMetrics` (184), `detectDreFilters` (254), `detectPeriods` (332), `detectComparison` (465) | **TRANSITIONAL / FORBIDDEN no novo código**: heurísticas financeiras/temporais no legado | Interpretação semântica LangGraph com catálogo versionado e evidência |
| 55 | `isWorkflowOrPayloadError` (238), `isRepairableSqlEngineError` (257) | **STRUCTURAL a revisar**: classes de erro reparáveis vs falhas de orquestração/provider | Repair só em erros SQL reparáveis, sem retry/cutover implícito |
| 57 | `collectValidationErrors`, `collectValidationWarnings`, template longo de prompt de reparo | **STRUCTURAL + contexto**: prompt genérico e dados aprovados separados | Repair SQL via Gemini no LangGraph |
| 59 | `normalizeSqlForComparison`, `repairAttempt`, `maxRepairAttempts` | **STRUCTURAL com gate de segurança**: reparo altera fingerprint e perde aprovação | `requires_reapproval=true`; nunca enviar SQL reparada ao executor sem novo gate |
| 63/64 | consulta e aplicação da configuração DuckLake ativa | **TRANSITIONAL se depender de nomes/flags do cliente**, processo genérico permitido | Contexto/adaptador por tenant, sem codificar fonte específica no motor |
| 51 | SQL de criação manual de tabela de cache em nó desconectado | **STRUCTURAL operacional**, não migrar DDL implícita para tráfego de consultas | Migração administrada separada, aprovada e testada |
| Adaptador LangGraph | `app/adapters/postgres/context_repository.py`: `DEFAULT_CONTEXT_TABLES`, `LOAD_SEMANTIC_CONTEXT_SQL_TEMPLATE`, projeção de DRE opcional com campos fixos | **DÍVIDA DE PORTABILIDADE**: defaults DuckLake e colunas DRE ainda refletem modelo histórico. Tabelas são configuráveis, mas estrutura diferente requer prova/adaptador genérico; perfil é descartado na leitura do repo | Source mapping versionado e isolamento por contexto/DSN/tenant validado, sem if cliente |

> Identificadores e linhas são **marcadores de rastreabilidade** do código real publicado, não uma reprodução de SQL ou prompt. O nome `filtrosOpex`, por exemplo, demonstra existência de estrutura a revisar, mas não comprova que seu predicado ou significado contábil deva ser aceito. Os corpos de cada regra continuam em evidências privadas e exigem reconciliação com a fonte versionada do banco. As 63 respostas não serão utilizadas para reconstruí-los.

## Fonte e cenário de externalização

- A consulta do nó **5** referencia as cinco coleções G5: `ai_ducklake_agent_rules`, `ai_ducklake_dre_mapping`, `ai_ducklake_entity_aliases`, `ai_ducklake_sql_patterns`, `ai_ducklake_table_catalog`. Isso prova origem textual do SELECT legado, **não** qual versão contábil foi usada em cada execução.
- G5: 318 registros de regras (315 ativos e 3 inativos no recorte recuperado), 738 aliases, 121 mapeamentos DRE com indicação de sinal, 98 registros de catálogo e 106 SQL patterns históricos reservados somente à avaliação. São 11 versões cifradas independentes. O inventário atual tem 447 candidatos com tabela ambígua, 110 sem tabela correspondente e 481 colunas não resolvidas; nenhum mapeamento aprovado por significado contábil.
- A cadeia real de planejamento **5 → 6 → 54 → 33 → 7 → 24 → 22 → 23 → 8** deverá ser acompanhada por provas de versão, escopo e regra. O conteúdo de G5 ainda não foi integralmente desbloqueado, logo nenhuma regra de cliente pode ser promovida a contexto ativo.
- **Não tratar `ai_ducklake_sql_patterns` histórica como prompts ou respostas do gerador.** Somente padrões estruturais novos, aprovados e versionados podem ser utilizados como conhecimento reutilizável.
- Testes de migração devem cobrir dois contextos materialmente diferentes, perguntas inéditas, segurança, plano e execução aprovada; as 63 perguntas são somente o comparador de qualidade n8n × n8n+LangGraph.

## O que falta para encerrar este inventário

1. Abrir **com segurança e em memória** cada um dos 11 pacotes cifrados do G5, depois reconciliar a regra/alias/métrica/filtro sinalizada em cada nó com a versão, origem, função financeira e target físico. Sem inventar correspondências.
2. Classificar **cada literal e condição relevante**, com evidência do efeito real no nó, como STRUCTURAL/TRANSITIONAL/FORBIDDEN; os 3.403 literais não foram todos aprovados, e nem todos são regras financeiras.
3. Externalizar regra por regra e substituir inteligência n8n por componentes LangGraph + contexto autorizado, preservando id/versão e gates.
4. Demonstrar a rota real do Produto e paridade funcional antes de habilitar SQL financeira read-only isolada. O benchmark de 63 casos não alimentará a migração.

**Status:** inventário de famílias de hardcode encontrado e rastreável, não concluído nem homologado. Sem mudança do n8n, banco, credenciais, runtime, produção, permissões ou SQL financeira.
