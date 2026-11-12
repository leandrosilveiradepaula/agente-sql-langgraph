## 12/11/2026 - Fonte real n8n ancorada e formula generica externalizada

TAREFA 1 (ORIGEM): no workflow n8n publicado, **41 Code indexados e 24 pontos classificados por SHA-256 de linha em 10 nos** (inclui PostgreSQL 5), indicando destinos: versionamento, aliases/intencoes, metricas, formula de razao, mapa fisico, regras gerenciais e relatorio. Auditor fail-closed compara corpos e 78 arestas ao baseline privado, sem publicar SQL, prompts, valores de negocio ou credenciais. Evidencias: docs/audits/LEGACY-N8N-BUSINESS-RULE-SITES-20261112.md e JSON sanitizado. 24 pontos NAO sao classificacao final de todos os 3.403 literais; o G5 da versao oficial (77 registros) permanece cifrado e nao homologado.

TAREFA 2 (MOTOR): novo contrato opcional metric_source_compositions[].calculation com **ratio_of_sums**, numerador/denominador/escala/refs definidos exclusivamente pelo contexto aprovado por tenant, reutilizando sinais, fontes, filtros, graos e periodos existentes. PostgreSQL faz SUM por grupo antes de dividir e retorna NULL se denominador zero. Rejeita alteracao nao autorizada por validacao fisica, fingerprint do contexto, Security Gate e SQL Contract Gate; sem regra financeira especifica, DRE, cliente, tabela ou pergunta conhecida hardcoded em app. Sem calculo configurado, preserva SQL e fingerprint anteriores.

PROVA: 33 testes de composicao, 7 HTTP Canonical Shadow e 3 testes de origens PASS; PostgreSQL 16 isolado e descartavel (dois esquemas sinteticos materialmente diferentes) confirmou 10 SELECTs read-only, razao numerica, NULL com denominador ausente e 2 tentativas cross-tenant negadas. Nenhuma SQL financeira de cliente, Gemini, benchmark, alteracao n8n/DB, credencial, deploy ou cutover. Essa prova NAO valida que a formula do G5 especifico tenha significado contabil aprovado.

PENDENTE: completar classificacao financeira dos demais sites/literais nos 41 Code e aprovar origens de regras reais no contexto versionado; nao transferir G5 cifrado nem comportamento DEMO para a versao oficial. PR #233 unica; sem merge. OFFICIAL=n8n; SHADOW=LangGraph; LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false.

---

## 12/11/2026 - Prova PostgreSQL descartavel e bloqueio contábil real do Bloco 1

**Evolucao funcional verificavel na PR #233:** gerador multifonte versionado foi exercitado contra um PostgreSQL 16 real e *descartavel* na VPS. Dois catalogos synthetic/tenants materialmente distintos geraram SQL dinamica a partir de perguntas com intervalo de anos, ano unico e agrupamento por dimensao. Foram **6 SELECTs somente leitura e 2 rejeicoes de acesso cruzado por roles separadas**, com checks numericos de agregacao/sinais/filtros e Security + SQL Contract Gates. Resultado: DISPOSABLE_POSTGRES_COMPOSITION=PASS. Teste implementado em scripts/validation/test_generic_multisource_disposable_postgres.py, com gate de ambiente estrito, e integrado a .github/workflows/v11-disposable-postgres.yml. Docker PostgreSQL da VPS encerrado e imagem temporaria removida. **Nao representa execucao de SQL financeira de cliente ou paridade G5.** Validacao local do codigo: composicao 29/29, HTTP Shadow 6/6, hardcode e secrets scanners PASS. Teste no GitHub Actions do novo SHA permanece a confirmar, nao declarar CI aprovado por esta entrega.

**Verificacao externa read-only do bloqueio:** projeto Supabase SOURCE Agente Financeiro continua INACTIVE. G5 contem 77 registros cifrados na unica versao selecionada pelo no n8n 5 e continua sem plaintext validado/aprovacao contabil; a revisao privada requer custodiante da senha GPG em TTY, sem acesso pelo conector VPS. Metadados historicos do projeto DEMO mostram 53 runs oficiais e 211 shadow, com ultimo dia em 10/11; a presenca historica nao comprova correlacao operacional atual nem paridade financeira. Nao misturar DEMO com a versao original G5, nao extrair SQL historica para o gerador.

**Estado:** Bloco 1 **AINDA ABERTO**, capacidade estrutural *COMPROVADA SOMENTE EM DADOS SINTETICOS*; legado real IMPLEMENTED_UNPROVEN. Nao abrir PRs paralelas para vanity work. OFFICIAL=n8n, SHADOW=LangGraph, LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. Nenhum merge, execucao financeira, ativacao de DB, alteracao n8n, privilégio ou cutover autorizados ou executados. Prioridade para prova real: custodia G5 + validacao de semantica financeira + teste com pergunta inedita e Gemini Shadow correlacionado.

---

## 12/11/2026 - Bloco 1: intervalo de anos-calendario multifonte (generate-only)

- Evolucao funcional: temporal.period_year_range opt-in no catalogo versionado por tenant; politica calendar_range_attested, max_span_years (1..100), phrases com prefixo/separador autorizados. Pergunta inedita pode declarar intervalo fechado de anos (between 2024 and 2026 somente se aprovado no catalogo). Interpretacao e geracao bloqueiam multiplos intervalos, anos extras, anos invertidos, zero/9999, intervalo excessivo, datas exatas ambiguas, texto nao mapeado e falta de granularidade.
- SQL PostgreSQL dinamica: cada fluxo recebe DATE >= inicio-01-01 e DATE < ano-final+1-01-01, antes de UNION ALL e SUM/GROUP BY. Sinais, tabelas, filtros, nomes de datas e graos continuam do catalogo; nenhum hardcode financeiro ou cliente novo.
- Verificacao: testar_metric_source_composition_e2e.py cobre dois tenants de estruturas distintas, Security/Contract gates e alteracao maliciosa dos limites. Nao ha aprovacao contabil nem execucao em banco real.
- Escopo seguro: PR #233 permanece draft, sem merge/cutover/deploy/alteracao n8n/DB, Gemini e executor real nao chamados. OFFICIAL=n8n, SHADOW=LangGraph, LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. Capacidade estrutural sintetica, migracao financeira real IMPLEMENTED_UNPROVEN ate revisao custodiada dos 77 registros do G5 e prova de paridade isolada.
- Evidencias de teste e novo SHA devem ser conferidos no commit da PR, sem confundir com paridade financeira.

---

# Capacidade genérica implementada — composição de métricas com múltiplas fontes

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



**Estado da implementação:** testada com dois contextos inteiramente sintéticos e estruturalmente diferentes, por meio do LangGraph real, em modo generate-only. **Estado da migração financeira do legado:** `IMPLEMENTED_UNPROVEN` até correlacionar e homologar contabilidade G5 por versão. O recurso é opt-in; não foi ativado no fluxo oficial, n8n ou Shadow real.

## Relação com o sistema antigo

O nó publicado n8n 22, função `planDreMensalAnalitica` (linhas 1973–2027), instrui combinar lançamentos diretos e rateados usando `UNION ALL` antes de agregar. Essa é uma **operação estrutural transferível**, mas seus nomes financeiros, regras de sinal, critérios, fatos e mapeamentos permanecem no G5 cifrado e não foram copiados. O novo código só implementa a operação estrutural. Não tem clientes, categorias, DRE obrigatória, valores ou tabelas reais fixos.

## Contrato e autorização

Opcionalmente, o snapshot de tenant pode declarar `metric_source_compositions` (ausência preserva exatamente a baseline e fingerprint antigos). Cada definição contém `composition_ref`, `intent_name`, `metric_ref`, `strategy=union_all_then_aggregate`, `source_use=APPROVED_SEMANTIC_MAPPING`, `accounting_definition_attested=true` e pelo menos duas fontes. Cada fonte define `source_ref`, `target_table` qualificada, `value_column`, `grain_ref`, `sign_multiplier` (+1/-1), `dimension_columns` e `source_filters` com operadores estruturais declarados.

O contrato rejeita itens extras contendo SQL histórica, sinais sem origem, tabelas/colunas fora do catálogo, medidas sem marcação de coluna métrica, fontes duplicadas, operadores/valores de filtro inválidos, dimensões sem mapeamento em **todas** as fontes, composição com metric/filter/comparison/temporal plan incompatível e alteração de plano antes do provedor.

**Importante:** declarar `accounting_definition_attested=true` não constitui aprovação contábil independente. O `CanonicalContextRepository` exige snapshot aprovado, tenant, versão e fingerprint configurados fora da pergunta; a auditoria financeira real e a governança da publicação continuam sendo gates humanos/operacionais. Não usar regras G5 cifradas como se estivessem atestadas.

## Funcionamento

1. `app/domain/context_normalizer.py`: inclui as composições apenas se o catálogo fornecido pelo cliente as contém; assim alterações de sinais/colunas/filters passam a alterar o fingerprint da versão e exigem nova aprovação.
2. `app/domain/planner.py`: escolhe a definição por intenção **já resolvida pelo catálogo**, valida grão/colunas por fonte, exige tabelas já selecionadas e dimension bindings explícitos, falha sem tentativas de inferir operação financeira do texto.
3. `app/domain/sql_generation.py`: transmite a composição verificada ao gerador de SQL com instruções genéricas de `UNION ALL` e agregação **somente após** a união. A configuração semântica permanece fora do Python.
4. `app/adapters/postgres/metric_source_composition_sql.py`: renderer estrutural PostgreSQL isolado constrói SQL read-only **dinamicamente** a partir das mesmas fontes do plano, preservando sinais, filtros e agrupamentos, sem joins entre fatos, sem SQL pronta por pergunta e sem acesso a banco.
5. `app/domain/sql_contract.py`: **fail closed** quando o candidato da LLM não permite comprovar fontes/sinais/filtros/UNION ALL/agrupamento. Até existir prova semântica AST equivalente, compara os tokens do candidato ao renderer derivado do plano autorizado; não são golden answers do benchmark. A validação de agrupamentos verifica todas as dimensões por fonte e suas projeções pós-UNION.

## Evidência reproduzível e escopo

- `testar_metric_source_composition_e2e.py`: **15 testes PASS** de normalização, dois contextos distintos, versões/fingerprints, geração de SQL dinâmica, Security+Contract Gates, agrupamentos e rejeições adversariais de fonte, coluna, filtro, sinal, SQL histórica e manipulação do plano.
- `testar_canonical_composition_shadow_e2e.py`: **3 testes PASS** em contêiner isolado sem rede, com fluxo HTTP real `/v1/internal/sql-agent/generate` → contexto canônico por tenant → LangGraph → geração dinâmica via adapter estrutural *injetado* → gates → evidências, e bloqueios de principal/tenant e fingerprint. Sem chamadas externas/LLM.
- Regressões selecionadas: planner **105**, SQL Contract **102**, além de SQL generation, normalizer, validator, filtros planejados, dois contextos Shadow pré-existentes e integração grafo (**5 PASS** em contêiner isolado).
- Relatório privado da VPS (JSON sem SQL, dados financeiros ou credenciais), SHA-256 `7d072603f211ad1fde940d809c366246bfa3c2cfdfda77a7b328ea89e6dc2db6`: **dois fingerprints de contexto**, **dois fingerprints de request e SQL distintos**, **Security+Contract Gates aprovados** sem executar SQL financeira.

**Não comprovado:** regras e sinais da versão G5 original (77 registros cifrados), uso do Gemini real com esse contrato, paridade de números, dois clientes reais, execução SELECT autorizada e cutover. A primeira capacidade financeira do legado continua `NOT_PROVEN`; somente sua **operação estrutural genérica** funciona demonstravelmente com dados sintéticos. A comparação das 63 perguntas continua exclusivamente no avaliador posterior.

**Limites atuais intencionais:** composição multitemporal, joins de dimensão externa, fórmulas derivadas, comparação interfonte e filtros dinâmicos da pergunta não estão cobertos por esse contrato e devem resultar em recusa segura em vez de SQL especulativa. Para outros dialetos, implementar adaptador estrutural autorizado: nenhum `if cliente`.
