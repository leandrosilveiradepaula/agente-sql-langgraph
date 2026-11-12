## 12/11/2026 - Fonte real n8n ancorada e formula generica externalizada

TAREFA 1 (ORIGEM): no workflow n8n publicado, **41 Code indexados e 24 pontos classificados por SHA-256 de linha em 10 nos** (inclui PostgreSQL 5), indicando destinos: versionamento, aliases/intencoes, metricas, formula de razao, mapa fisico, regras gerenciais e relatorio. Auditor fail-closed compara corpos e 78 arestas ao baseline privado, sem publicar SQL, prompts, valores de negocio ou credenciais. Evidencias: docs/audits/LEGACY-N8N-BUSINESS-RULE-SITES-20261112.md e JSON sanitizado. 24 pontos NAO sao classificacao final de todos os 3.403 literais; o G5 da versao oficial (77 registros) permanece cifrado e nao homologado.

TAREFA 2 (MOTOR): novo contrato opcional metric_source_compositions[].calculation com **ratio_of_sums**, numerador/denominador/escala/refs definidos exclusivamente pelo contexto aprovado por tenant, reutilizando sinais, fontes, filtros, graos e periodos existentes. PostgreSQL faz SUM por grupo antes de dividir e retorna NULL se denominador zero. Rejeita alteracao nao autorizada por validacao fisica, fingerprint do contexto, Security Gate e SQL Contract Gate; sem regra financeira especifica, DRE, cliente, tabela ou pergunta conhecida hardcoded em app. Sem calculo configurado, preserva SQL e fingerprint anteriores.

PROVA: 33 testes de composicao, 7 HTTP Canonical Shadow e 3 testes de origens PASS; PostgreSQL 16 isolado e descartavel (dois esquemas sinteticos materialmente diferentes) confirmou 10 SELECTs read-only, razao numerica, NULL com denominador ausente e 2 tentativas cross-tenant negadas. Nenhuma SQL financeira de cliente, Gemini, benchmark, alteracao n8n/DB, credencial, deploy ou cutover. Essa prova NAO valida que a formula do G5 especifico tenha significado contabil aprovado.

PENDENTE: completar classificacao financeira dos demais sites/literais nos 41 Code e aprovar origens de regras reais no contexto versionado; nao transferir G5 cifrado nem comportamento DEMO para a versao oficial. PR #233 unica; sem merge. OFFICIAL=n8n; SHADOW=LangGraph; LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false.

---

## 12/11/2026 - Inventario funcional dos 68 nos: ENTREGA ESTATICA FECHADA

**O escopo do inventario funcional de nos foi concluido no export n8n publicado e ativo**, sem edicao nem execucao do workflow. Auditoria no codigo real reconfirmou **68/68 identidades e configuracoes/corpos, 78/78 arestas por porta, 41 Code, 11 PostgreSQL, 10 IF, 2 HTTP, 3 respostas e 1 Webhook**, contra o crosswalk privado anterior. Dos 68, **60 sao alcancaveis pelo webhook e 8 (15,17,18,19,20,21,51,53) estao fora dessa rota**, sem presuncao de que sejam excluiveis. Os 10 IF possuem True/False documentados; IF 25, 29 e 62 sao gates tecnicos, **nao aprovacao humana**. Onze operacoes PostgreSQL foram categorizadas como leitura, cache, auditoria/fila, DDL isolada, preflight ou execucao SQL dinamica, sem executar SQL. Dois HTTP POST sao Gemini geracao/reparo.

**Artefatos rastreaveis:** docs/audits/LEGACY-N8N-FUNCTIONAL-INVENTORY-20261112.md (matriz humana dos 68 nos), docs/audits/legacy-n8n-functional-inventory-20261112.json (matriz por porta, hashes e classes), scripts/operations/legacy_functional_inventory_offline.py (revisor deterministico fail-closed, sem negocio em runtime), testar_legacy_functional_inventory_offline.py (negativas e 68/78). Arquivo de workflow bruto permaneceu PRIVADO na VPS; nao houve SQL/prompt/credencial exposta, benchmark, chamada de modelo, alteracao do n8n, Supabase ou cutover.

**Classificacao preliminar por responsabilidade de no:** 25 STRUCTURAL, 33 TRANSITIONAL, 10 nos com FORBIDDEN de negocio identificado no legado (candidatos a externalizar). Nao equivale a revisao literal individual de 3.403 strings nem a homologacao contabil. A identidade/configuracao e corpos dos 68 nos e todas as arestas conferem com o baseline; hashes dos exports brutos diferem porque ha metadados/serializacao ainda nao homologados no nivel integral de arquivo. Nao confundir com drift funcional demonstrado.

**SEPARACAO DO GATE:** esta entrega encerra o inventario FUNCIONAL ESTATICO dos nos do Bloco 1, mas NAO atesta que a inteligencia financeira foi migrada. Regras/aliases/metricas/joins do G5 (77 registros da versao ativa cifrada) seguem sem aprovacao contabil; paridade real, Gemini e dois clientes reais pertencem a homologacao posterior. OFFICIAL=n8n; SHADOW=LangGraph; LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. PR #233 segue draft, sem merge e sem custo/privilegios ampliados. Nao criar PRs de evidencia parcial.

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

## 12/11/2026 — BLOCO 1: calendario com ano filtrado, SQL multifonte e provider pinado (sem ativar n8n)

**Entrega verificada no checkout isolado da VPS:** a composição `union_all_then_aggregate` ganhou agrupamento por período **dinâmico**, com `day/week/month/quarter/year` definidos por termos/versionamento do tenant e **datas diferentes em cada fonte**. PostgreSQL compila `date_trunc` para DATE aprovado; `timestamp/timestamptz` sem timezone homologado falha. Filtros, sinais +1/-1, dimensão e grão são vinculados ao catálogo físico. Colunas de medida só podem ser numéricas (`numeric/decimal/smallint/integer/bigint`) e devem constar em `metric_columns`; `grain_ref` deve coincidir com o catálogo de cada fonte. Mudanças alteram o fingerprint. Ano-calendário em pergunta inédita é agora resolvido **somente** quando `temporal.period_year` aprova `calendar_year_attested=true`, referências textuais e a política `allow_bare_year`; cada fonte recebe limite `>= YYYY-01-01` e `< (YYYY+1)-01-01` antes da união. Anos ambíguos, exercícios fora do alcance, ano sem política aprovada, trimestre relativo, ano fiscal e timestamp com fuso não homologado falham com segurança (não gerar total de todos os anos silenciosamente).

**Prova numérica adicional:** usando duas estruturas sintéticas diferentes, o mesmo SQL gerado foi executado em SQLite in-memory com `date_trunc` emulada; mês de 2026 retornou **70** ao excluir registros sintéticos de 2025 e 2027. O ano em cada filtro foi extraído de **pergunta inédita**, sem SQL pronta/golden answer. A política de ano pertence ao catálogo (não a Python). Dois catálogos × duas granularidades de ano filtrado produziram quatro hashes SQL distintos; relatório privado SHA-256 `b085eadba30c4125f215c722d8363591a631e0eafebb0bdfb87e5b66fc8f1db5`.

**Evidência funcional, NÃO financeira real:** `testar_metric_source_composition_e2e.py` **26/26 PASS**, incluindo duas estruturas sintéticas com SQLs diferentes, agrupamento mês/ano, sinais, filtros, e **resultado numérico realmente calculado em SQLite in-memory** (função date_trunc simulada, **não** um PostgreSQL real). `testar_canonical_composition_shadow_e2e.py` **6/6 PASS**, no HTTP/ASGI LangGraph completo em contêiner descartável `--network none`, usando **o adaptador real** `CatalogCompositionSqlGenerator` injetado, autorizado apenas com `canonical_snapshot + semantic_version + fingerprint`. **Gemini não chamado**, nenhuma SQL de cliente executada ou contexto ativado. Regressões Planner 105 e SQL Contract 102 PASS; scanners hardcodes/segredos PASS. Evidência privada de quatro combinações context/period + gates: SHA-256 `b085eadba30c4125f215c722d8363591a631e0eafebb0bdfb87e5b66fc8f1db5`.

**Gates intactos:** PR #233 continua draft, sem merge; `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. **Capacidade genérica demonstrada com dados sintéticos**; migração contábil verdadeira `IMPLEMENTED_UNPROVEN` enquanto os 77 registros da versão G5 original não forem interpretados/aprovados. Portabilidade entre **dois clientes reais**, paridade financeira n8n+Gemini, SQL de produção, cutover e comparação de LLMs seguem não comprovados. Adaptador estrutural **não está registrado como padrão na produção**. Não usar a DEMO nem benchmark como substituto do G5.

**Continuidade exigida:** executar autonomamente GitHub/VPS, não transferir SSH ao usuário, não interromper turno com progresso/desculpas/`prossiga`; relatar **somente entregas finais**. Próximo bloqueio funcional: intervalos entre exercícios, ano fiscal, timezones, joins dimensionais com cardinalidade, regras contábeis G5, mesmo provedor Gemini em Shadow n8n e dois clientes reais. Contrato: `docs/architecture/GENERIC-MULTISOURCE-METRIC-COMPOSITION.md`.

---

## DECISÃO DO OPERADOR — CONTINUIDADE AUTÔNOMA E SÓ RESULTADO FINAL (11/11/2026 23:56 UTC)

**Não interromper uma execução substancial com mensagens de progresso, desculpas ou pedido de `prossiga`.** O operador quer **somente o resultado final**, depois de completar todo o trabalho técnico seguro executável naquele turno. Não alegar trabalho em segundo plano, prometer entrega futura ou fazer alterações sujeitas a gate humano; continuar autonomamente com GitHub e VPS até haver uma entrega funcional ou bloqueio externo incontornável. Se houver pausa técnica, resolver sem enviar relatório intermediário. Consultar o código e evidências reais a cada retomada.

**Entrega funcional desta execução:** implementado o mecanismo universal *multi-source fact stream → `UNION ALL` → aggregate* encontrado estruturalmente no nó n8n 22, com contexto versionado por tenant, granularidade, sinais, filtros, dimensões, SQL dinâmica e contrato SQL que **não aceita** semântica de união alterada. **Dois contextos sintéticos diferentes passaram** no LangGraph HTTP real em contêiner sem rede com adaptador estrutural injetado; nenhum LLM, DB financeira ou benchmark foi chamado. A documentação de mecanismo/evidências está em `docs/architecture/GENERIC-MULTISOURCE-METRIC-COMPOSITION.md`; `testar_metric_source_composition_e2e.py` (15) + `testar_canonical_composition_shadow_e2e.py` (3) e regressões aprovados. Evidência privada SHA `7d072603f211ad1fde940d809c366246bfa3c2cfdfda77a7b328ea89e6dc2db6`.

**Estado honesto:** capacidade **estrutural demonstrada somente em cenários sintéticos**; a migração financeira real permanece `IMPLEMENTED_UNPROVEN`/`NOT_PROVEN` porque o pacote G5 original da versão oficial contém 77 registros cifrados sem aprovação contábil. Não usar a DEMO como substituto, não inventar signo, fórmula, join ou coluna, não declarar paridade com n8n+Gemini. Sem deploy/migration/merge, n8n oficial não alterado, SQL real Shadow false. Expandir para outros comportamentos com a mesma abordagem, sem hardcode. O código do renderer está isolado, **não** substituiu o provider Gemini em produção.

---

## 11/11/2026 — FONTE DEMO NÃO É A SEMÂNTICA DO LEGADO (VERIFICAÇÃO REAL)

**Sem perguntar ao operador nem executar SQL financeira**, foram verificadas as duas fontes Supabase já conectadas. O projeto SOURCE original do Agente Financeiro está `INACTIVE` e sua API de esquema retorna indisponível. A DEMO está `ACTIVE_HEALTHY` e, além das 13 tabelas do schema `public` anteriormente examinadas, **possui as cinco coleções `ai_ducklake_*` no schema `semantic_context`** (regra, aliases, DRE, catálogo e padrões históricos). Na DEMO, SELECT agregado **somente de hashes de versão e contagens** sobre as quatro coleções de conhecimento — sem tocar as linhas de `sql_patterns` ou consultar valores financeiros — confirmou **10 versões**, totalizando 110 regras, 605 aliases, 130 DRE e 80 registros de catálogo. Os 10 hashes foram comparados ao manifesto G5 original na VPS: **0/10 versões comuns às 11 versões do G5**. A versão selecionada pelo workflow oficial permanece **somente no G5** (`7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485`).

**Consequência obrigatória:** jamais copiar a semântica da DEMO para substituir a fonte antiga ou declarar paridade só porque os nomes das cinco tabelas coincidem. O workflow n8n usa duas identidades de credencial PG: grupo G1 (nó 5 e outros de contexto/cache), grupo G2 (nós 66/67 preflight/executor); IDs separados **não provam** bancos nem autorizações iguais. As definições contábeis dos 77 registros da versão oficial permanecem cifradas e **não homologadas**; requerem custódia GPG legítima, que não deve ser contornada nem exigida ao operador como tarefa de rotina. Continuar engenharia reversa dos JS e mecanismos genéricos com as fontes disponíveis. SQL financeira real, alterações de banco, ativação de contexto, cutover e merges continuam bloqueados pelos gates humanos.

**Correção de CI:** no commit `86733408284d728caf91bc3735a24d6d6ab22de5`, o teste GPG trata Windows de forma *fail-closed* sem enfraquecer Linux POSIX. A suíte local (7 testes G5 + 16 de versão + 10 de crosswalk) passou; CI do HEAD deve ser reconfirmado. Acesso à VPS já está concedido: **não pedir comandos SSH ao usuário**.

---

## 11/11/2026 — ACESSO À VPS JÁ AUTORIZADO: NÃO TRANSFERIR OPERAÇÃO AO USUÁRIO

**Decisão explícita do operador:** o ChatGPT já dispõe do conector Agente Financeiro VPS e deve executar autonomamente nele as leituras, análises, inspeções, testes e verificações permitidas. **Não pedir ao operador para copiar/colar comandos SSH ou reiterar “autorize usar VPS”.** Tratar somente gates realmente indelegáveis (segredo de criptografia indisponível, aprovação contábil, alteração de privilégios/DB, execução financeira SQL, produção, merge e cutover) como bloqueios distintos. Acesso administrativo à VPS **não fornece automaticamente a senha GPG**; jamais procurá-la em locais não autorizados, contornar a criptografia ou solicitar envio de segredos pelo chat.

**Apuração do próprio agente:** fonte Supabase original do Agente Financeiro está `INACTIVE` e a API de schema respondeu indisponível; DEMO está ativa, mas as coleções G5 não foram encontradas entre as tabelas do schema `public` consultado. No acervo privado G5 examinado na VPS há 11 pacotes cifrados, índices/lineages/hints e evidências sanitizadas; **não foi verificado texto contábil legível**. Não tratar metadados de versões nem coincidências de nomes como mapeamento aprovado. Continuar reversão dos 68 nós e melhorias genéricas com ferramentas existentes, sem questionamento repetitivo.

**Falha real CI #233 identificada:** runner Windows `Full offline checks` rejeitou criação privada porque o teste tentava atestar `0700/0600` em sistema de arquivos sem semântica POSIX. Correção em `86733408284d728caf91bc3735a24d6d6ab22de5`: o utilitário G5 recusa persistência em Windows, o teste exige recusa segura, Linux mantém restrições. Testes locais 7 G5 + 16 reconciliação + 10 crosswalk PASS; revalidar CI do HEAD efetivo. Sem prova financeira nem SQL real.

---

## 11/11/2026 — M1 verificado: versão oficial única + fronteira de avaliação no loader

Foi verificado na VPS que os **cinco SELECTs de contexto do nó 5** fixam a mesma versão semântica, SHA-256 7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485. **Um único pacote do manifesto G5**, índice 10/11, tem exatamente esse hash: **77 registros** (18 regras, 40 aliases, 11 mapeamentos DRE, 8 registros de catálogo) e 48 hints. Na versão correta, **3 dos 8 bindings de tabelas do nó 22** têm match textual, todos AMBIGUOUS_TABLE_NAME; análise agregada entre versões indicava 4/8 e não pode servir de mapeamento contábil. Relatório privado SHA-256 e376d3a3555d67467b57ece1949af4d26e1ca622f54487fc922c7d921521fbea. Nenhum conteúdo contábil cifrado foi aberto ou aprovado.

No modo canônico (não no legado), app/domain/canonical_source_boundary.py bloqueia SQL pronta, exemplos de perguntas, notas livres e padrões sem proveniência estrutural aprovada, mesmo com flag historical_evaluation_sql_excluded=true: **correção efetiva**, não declaração. Testes de isolamento/negativas com dois clientes sintéticos passaram, sem LLM, SQL financeira, mudança n8n ou cutover. O bloqueio GPG real continua: próxima etapa é desbloquear **somente a versão selecionada** no terminal local e revisar seus 77 registros sob custódia. Ver docs/operations/G5-ACTIVE-VERSION-LOCAL-REVIEW.md. Isso não é prova financeira ou produto concluído.

---

# MEMORY.md — Continuidade operacional do Agente Financeiro

> **Memória durável do repositório, não a memória pessoal do ChatGPT.** Ler junto com `AGENTS.md` em toda retomada. Decisão recente explícita do operador prevalece sobre notas históricas. Atualizado em 2026-11-11.

## Prioridade operacional inequívoca — 11/11/2026 21:36 UTC

**Não considerar progresso financeiro certificado apenas por código, documentação ou benchmark.** A primeira prova exige uma capacidade **real** extraída conjuntamente dos 68 nós do n8n e do banco/backup G5: fonte/versionamento/significado aprovado → contexto de tenant → pergunta inédita → LangGraph (interpretação, plano, geração SQL dinâmica e gates). Sem SQL financeira real no Shadow. O aceite detalhado consta em `docs/operations/FIRST-FINANCIAL-CAPABILITY-PROOF.md`.

**Classificação única por capacidade:** `NOT_MIGRATED`, `IMPLEMENTED_UNPROVEN`, `PROVEN`. Registrar origem n8n/G5, risco, responsáveis, SHA/PR, testes e evidência. Não transportar hardcodes; nem 63 perguntas, SQL histórica ou golden answers entram no gerador. Dois clientes materialmente distintos serão requeridos. Não inventar prazo: a antiga estimativa de 12–20 semanas foi retirada.

**Estado a reconfirmar:** PRs #230/#231/#233 draft, `main@955eda46`, VPS `87d16796`, n8n oficial preservado, Shadow SQL real false. CI da PR #233 SHA `5b29a890` falhou em Windows **somente** no `Whitespace check` (espaços no roadmap), apesar de outros passos daquele job PASS. Corrigir e revalidar. Não há prova de migração financeira integral ou paridade numérica.

**Controles:** OFFICIAL=n8n, SHADOW=LangGraph, Generate/Repair/Execute Approved separados, reparo invalida aprovação; DB, produção, merge/cutover/credenciais e SQL real exigem gates humanos.

---

### Evidência inicial independente (G5↔n8n, sem homologação)

Export ativo da VPS SHA-256 `19dd24c29d81c61b12dc383f2124ca2e7ba77625776ee161f3be1996d2f09c68`; nó 22 (planner) SHA-256 `113ce61f0e6c57b2cf260f70c6e04af1530e92876f4c6d10d5fbaa9c242f5d5f`, com funções `planConsultaMetricaFinanceira` (linha 2030), `factGrainContract` (1073), `comparativeFactContract` (1054) e `commonManagerialRules` (1105). Nó 5 consulta 5 coleções semânticas do G5; existem 11 pacotes de versão cifrados. Relatório privado SHA-256 `e9c23d9e4b8dddd313359742546aa16eea0a2eab0bb40ae50ee1699ae6abe1d6`. Isso **prova localização da origem, não semântica contábil nem SQL LangGraph**: primeira capacidade `NOT_MIGRATED`; revisão por versão/validação financeira pendentes. Detalhes em `docs/operations/FIRST-FINANCIAL-CAPABILITY-PROOF.md`.

### Nova evidência M1: versão fixa, padrões históricos e tabelas no legado

Nó 5 do n8n publicado usa **5 seletores `agent_version` literais iguais**, sem coluna de tenant explícita, e lê `ai_ducklake_sql_patterns` (G5 `EVALUATION_ONLY`). Nó 7 serializa padrão por intenção no contexto; nó 8 incorpora esse contexto ao prompt; nó 9 prepara Gemini. Nó 22 contém mapa físico com 8 bindings, apenas 4 com correspondência G5 (ambíguos); 4 faltam. Os nós 23/54 fixam métricas/aliases e o prompt do nó 8 contém regras financeiras fixas. **Não importar SQL histórica nem negócios do legado como código ou contexto de geração não aprovado.** Auditor genérico `scripts/operations/legacy_semantic_static_coupling_offline.py`, testes de dois esquemas sintéticos, relatório privado SHA `b9fc93f7986020aa4017a9a3641baf770e617eeab0a08d67c8ef36b205c8b179`; detalhes `docs/audits/LEGACY-N8N-G5-SEMANTIC-COUPLING-20261111.md`. G5 ainda cifrado sem homologação de conteúdos; `NOT_MIGRATED`.

### Segurança real encontrada no legado — gates técnicos ≠ aprovação humana

No n8n publicado, IF 25 recebe `success` do nó 12 baseado em `validationErrors.length === 0`; IF 29 recebe `aprovado` do nó 28 baseado em `errors.length === 0`. Nenhum deles é recibo humano. IF 62 consome resultado técnico de preflight. Auditor genérico foi ampliado com fluxo direto IF, **10 testes offline PASS** e execução no workflow real: 10 IF, 2 derivados diretamente de contador de erros, 8 sem origem estabelecida estaticamente. Relatório privado SHA `e5d6f3886730f16f484d40a1f818fb83d6ec563a5d2b8f2d34270bfb46fe612a`. Nó 8 contém fórmula percentual, regra de sinal de orçamento e grupos DRE fixos: **externalizar após validar com G5**, não copiar ao Python. Tentativa única de desbloqueio GPG sem credencial local em cache falhou; 11 pacotes continuam íntegros/cifrados e aguardam custódia local. Nenhuma SQL financeira ou LLM executada.

## Missão invariável

**Fazer engenharia reversa do agente financeiro EXISTENTE** — n8n publicado (observado com 68 nós) **E** banco/backup G5 recuperado — para reconstruir suas capacidades no fluxo **Produto + n8n + LangGraph + LLM configurável**. Não criar agente do zero nem tentar ensinar o legado por 63 SQLs/respostas prontas. Migrar o comportamento, não copiar hardcodes. Conhecimento de cliente pertence a contexto semântico versionado por tenant; o motor é agnóstico.

A matriz obrigatória é: **nó/branch/JS/prompt/SQL legado ↔ esquema/tabelas/regras/aliases/métricas/relacionamentos e versão do banco ↔ significado financeiro validado ↔ destino na arquitetura ↔ teste de paridade ↔ risco/proprietário**. É proibido declarar descoberta completa com base em flags heurísticas ou encontrar apenas 6 termos. Necessária revisão do corpo real de cada nó e de objetos do banco, sem expor dados sensíveis.

## Estado observado em 2026-11-11 — revalidar sempre

- GitHub `main` observado: `955eda46015d35dbe44a40f9240b821b1f493201`; VPS checkout observada: `87d167969345c3dfcf9deaf36e33ab07a1f9c890`. Essas SHAs envelhecem: consultar GitHub/VPS novamente.
- PRs `#230` (fallback semântico) e `#231` (papéis/ACL) abertas em *draft* com CI Linux/Windows verde na última inspeção. Não foram mergeadas nem ativadas pelo agente.
- Export sanitizado somente leitura do workflow n8n `2E6mbYg8CEJhGhqs`: **68 nós** (41 Code, 11 PostgreSQL, 10 If, 2 HTTP, 3 Respond-to-Webhook, 1 Webhook); na leitura, `active=true` e `versionId == activeVersionId`. **Rota Produto→workflow não atestada**; não inferir pelos nomes.
- Backups e evidências privadas G5 e perguntas-only disponíveis na VPS. Snapshot das 63 perguntas recuperado e congelado; nem backup nem benchmark equivalem a semântica contábil homologada. A recuperação G5 contém múltiplas versões: não misturar contextos.
- Diagnóstico offline anterior: 63 perguntas com snapshot histórico, 26 intenções/planos aceitos e 37 rejeitados; **isso não é qualidade financeira certificada**. Nove, 16, seis aliases e demais números antigos são diagnósticos específicos, não meta de implementação.
- Rastros de seis termos de métricas encontrados em 14 nós Code do legado (44 ocorrências); referência textual não implica equivalência. Pacotes privados temporários podem desaparecer; não tratá-los como artefatos persistidos garantidos. Recriar a partir de fonte com integridade quando necessário.

## Trabalho obrigatório e gates

1. Fonte n8n publicada + Produto: capturar inventário completo, conectividade, dependências, funções e SQL/LLM legado. Separar **observação** de **classificação revisada**.
2. Fonte banco/backup: inventário por versão e tenant, definição contábil respaldada, dependência física, mapeamentos e trilha de proveniência. Não presumir que backup cifrado = significado de campo. Não reutilizar golden answers.
3. Consolidar matriz e separar STRUCTURAL (processo), TRANSITIONAL (dívida legado) e FORBIDDEN (negócio hardcoded no código novo); migrar capacidades completas e testar com perguntas inéditas + dois clientes distintos.
4. Provar Fase 1 Shadow correlacionado n8n + Gemini vs n8n + LangGraph + Gemini, sem impactar oficial. SQL read-only para paridade numérica exige autorização específica; nada em produção sem aprovação.
5. Cutover humano Fase 2 com rollback; comparar Gemini × SQL-InfoDive apenas na Fase 3.

**Invariantes:** `OFFICIAL=n8n`; `SHADOW=LangGraph`; `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`; geração, repair e Execute Approved separados; SQL reparada requer reaprovação. Não fazer merge, migração, mudança n8n/banco/tenant/credenciais/permissões, deploy produtivo ou custos sem o gate humano correspondente. Não expor prompts/SQL bruta, DSNs, dados pessoais nem segredos em GitHub.

## Continuar sem desvio

Consultar `docs/operations/LEGACY-N8N-DATABASE-MIGRATION-MAP.md` para o backlog rastreável por fonte e capacidade; `docs/architecture/PORTABILITY-AND-CUTOVER-CONTRACT.md` e `ORCHESTRATION-STRATEGY.md` para arquitetura; `PROJECT-STATUS.md` e issue #155 para pendências. A primeira entrega substantiva pendente é a **matriz integral do workflow e do banco**, não outra versão de scoring.

## Evidência objetiva posterior ao contrato (11/11/2026)

- PR #233 em draft `docs/legacy-reverse-engineering-contract-20261111`: auditor `scripts/operations/legacy_migration_source_crosswalk_offline.py` e seis testes sintéticos. Inventário do fluxo n8n publicado: 68 nós, 78 arestas, 60 alcançáveis do webhook, 8 não alcançáveis. Banco/backup G5: cinco coleções, 11 versões cifradas e 1.381 linhas, 106 SQL patterns restritos a avaliação.
- Evidência sanitizada por nó e por versão: `docs/audits/LEGACY-N8N-G5-TRACE-20261111.md`; relatório privado completo em /tmp, SHA-256 `e33a1b93f25a0809a644e5e83a9f7a82a360f73adb146511772d19d6181edbff`. Somente 20 nós têm coocorrência textual com identificadores G5; NÃO há regras financeiras homologadas, e todo conteúdo por versão ainda requer revisão.
- SHA do contexto antigo do Shadow não coincide diretamente com as 11 versões G5 pelos hashes verificados; não misturar as fontes para produzir SQL. A rota Produto→workflow n8n ainda precisa de testemunha real.
- **Próxima ação:** inspecionar efetivamente corpo dos 68 nós e fontes cifradas por versão; extrair regras, SQL, filtros, transações e seus efeitos e provar dependências em matriz, antes de decidir mapeamentos/implementação. Não se contentar com índice de nomes e indicadores textuais.

## Continuidade após engenharia reversa funcional — 11/11/2026

- Inventário funcional proposto **68/68 nós** e fluxo real Produto Next.js em `docs/audits/LEGACY-N8N-PRODUCT-FUNCTIONAL-MAP-20261111.md` (destinos candidatos; regras/SQL de cada função e efeito contábil ainda precisam ser homologados). 41 Code = 14.440 linhas JS estáticas; cache, repair, preflight, executor, dados, relatórios e fila presentes no n8n.
- Topologia: geração/SQL reparada **podem alcançar** o executor do n8n; exigir separação Generate/Repair/Execute Approved e `requires_reapproval=true`. 8 nós não alcançáveis do Webhook, incluindo logs/fila e DDL manual; não removê-los sem revisar efeitos.
- 11 PostgreSQL n8n usam 2 referências de credencial distintas: contexto/cache/log/configuração (9 nós) versus preflight/execução (2 nós); IDs não demonstram hosts ou privilégios. SOURCE Supabase INACTIVE; DEMO ACTIVE com 13 tabelas públicas. Leitura do conteúdo de 11 pacotes semânticos cifrados ainda pendente.
- Recontagem G5: 579 hints de 11 versões representam **11 referências físicas distintas**, **58 padrões distintos nó/referência**, 447 tabelas ambíguas, 110 não localizadas e 481 colunas não resolvidas. Não confundir 4.813 ocorrências por versão com dependências aprovadas.
- O fallback de URL do Produto não coincide com o path Webhook publicado; **env efetivo não verificado**, portanto não declarar falha de produção nem route parity. Os 63 casos de benchmark são **somente controle de qualidade comparativa posterior**.

## Conclusão da análise de cobertura de capacidades — 11/11/2026

- `docs/audits/LEGACY-N8N-LANGGRAPH-CAPABILITY-GAP-20261111.md` documenta 14 capacidades do n8n legado, os módulos realmente existentes no Produto/LangGraph, seus gaps e critérios para certificar a migração. **Existência de módulo ou teste offline não é migração completa.**
- Scan privado de 41 funções JavaScript: 14.440 linhas, 3.403 literais de string (1.987 com tamanho >=10), templates longos em nós 8, 32, 57; maior quantidade de literais em 22, 32 e 6. Esses números NÃO equivalem a hardcodes de negócio aprovados. A classificação literal/branch precisa ser feita com dados versionados do backup e significados contábeis.
- O adaptador PostgreSQL atual do LangGraph recebe DSN/schema/version por injeção e permite catálogo configurado, mas mantém template compatível com nomes DuckLake, projeção de DRE tipada e leitura `load_active_context(user_profile)` que ignora o perfil ao consultar. Prova de routing do tenant ao adaptador e portabilidade de esquemas/colunas materialmente distintos permanece pendente. São pontos do porting e não autorização para if por cliente.
- O leitor de contexto legado contém `sql_patterns`; os 106 SQL patterns históricos G5 são **apenas avaliação**, nunca contexto do gerador. Não misturar essa coleção criptografada com padrões estruturais novos autorizados.
- SOURCE Supabase inativo, pacotes G5 cifrados separados por 11 versões; análises das linhas contábeis originais exigem **desbloqueio seguro em TTY, sem senha em chat/arquivo/env/log**. Inventário do conteúdo integral ainda não foi realizado. n8n e Shadow não foram modificados, SQL financeira real segue false.

## 2026-11-11 — Caminho de onboarding sem hardcode implementado na PR #233

**Decisão do operador:** migrar a inteligência financeira real do legado n8n (68 nós) e G5 para n8n+LangGraph, mas o motor deve atender clientes com qualquer nomenclatura/esquema mediante configurações, acesso e definições fornecidas/validadas. **Nenhum hardcode de cliente no código**; as 63 perguntas históricas **somente controle de qualidade posterior**.

**Implementação nesta branch ainda sem merge/cutover:**
- `app/adapters/postgres/physical_catalog_reader.py` inspeciona apenas `information_schema.columns` em transação READ ONLY e lista explícita de schemas, sem ler dados financeiros;
- `app/domain/tenant_semantic_readiness.py` faz pré-validação física sem inferir semântica, nunca promove mapeamento automaticamente;
- `app/adapters/postgres/canonical_context_repository.py` carrega JSONB de contexto versionado, já aprovado, vinculado a tenant/versão/fingerprint e exclusivo de SQL de avaliação;
- `app/config/postgres_context.py` e `app/bootstrap.py` habilitam modo `canonical_snapshot` por configuração autenticada mantendo `legacy_tables` como default;
- `docs/architecture/GENERIC-CUSTOMER-SEMANTIC-ONBOARDING.md` descreve pré-requisitos por cliente, publicação governada e lacunas.

**Testes isolados:** 4+6+8 novos com dois esquemas sintéticos materialmente distintos; regressão legada do repositório/config/bootstrap; container efêmero sem rede e testado em usuário não-root, removido depois. **Não provam clientes reais, publicação, autorização per-request, paridade financeira ou cutover.**

**Gates inalterados:** n8n oficial preservado, Shadow sem execução real; nenhum SQL financeiro, banco, produção, credencial, contexto ativo, merge ou migração alterados. Próxima entrega de produto: ler o conteúdo cifrado G5 com custódia adequada, externalizar cada regra do legado e provar contextos reais, roteamento tenant, aprovações e paridade antes de substituir inteligência n8n.
