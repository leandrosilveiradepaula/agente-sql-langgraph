## 12/11/2026 - Prova funcional de filtros aprovados sem omissao silenciosa

Nova integracao planner -> composicao -> gerador -> SQL Contract Gate aplica resolved_filter_bindings a todos os fact streams por conceito e dimension_columns declarado pelo tenant. Corrigiu lacuna critica: no HTTP Canonical Shadow os matched terms do resolvedor desapareciam se o campo semantic_signals opcional faltasse, gerando SQL geral apesar de filtro solicitado. O termo agora cruza com segurança a fronteira do classificador, e cada fonte deve comprovar coluna correspondente. Termos sem binding, tipos incompativeis, joins nao aprovados e alteracao de plano rejeitam antes de gerar SQL. Evidencia: dois schemas diferentes, perguntas sinonimas, filtros =/IN/NOT IN, verificacoes de SQL, 28 SELECTs sinteticos read-only no PostgreSQL 16 descartavel e 2 ACL cross-tenant bloqueadas. Sem SQL cliente, Gemini, n8n editado, G5 plaintext ou benchmark usado no gerador.

G5 original ainda requer mapeamentos contabeis aprovados a partir de 77 registros cifrados, e paridade real n8n+Gemini x LangGraph+Gemini. OFFICIAL=n8n; SHADOW=LangGraph; LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. PR #233 draft, sem merge.

---

## 12/11/2026 - Censo AST reconciliado e motor de cálculo portável

A fonte publicada do n8n foi relida e os 41 Code validados por hash no crosswalk 68 nós/78 conexões. Censo sintático Acorn: 3.698 strings/templates, 1.719 curtos, 1.979 longos, discrepância +295 contra o heurístico 3.403 (18 nós diferem). O relatório docs/audits/LEGACY-N8N-AST-LITERAL-RECONCILIATION-20261112.md substitui o contador antigo para localização sintática. Classificações por fonte são **candidatos automatizados** F=1.732, T=371, S=830, U=765; não atestam significado financeiro real. O parsing usou imagem n8n descartável sem rede, sem executar corpos JS, SQL, Gemini ou benchmark.

Operação genérica weighted_sum_of_sums com todos os coeficientes e fontes no catálogo tenant, normalizados e verificados antes do planejador/gerador, preservando fonte, versão, fingerprint, aprovação externa e gates. SQL PostgreSQL sintética comprovada, 22 SELECTs read-only em dois contextos distintos, aritmética com frações e ranking+ponderação, 2 ACL cross-tenant bloqueadas. Nada foi inferido dos 77 registros G5 cifrados; aprovação contábil, portabilidade em dois clientes reais e paridade oficial/Shadow não demonstradas.

Operação continua OFFICIAL=n8n, SHADOW=LangGraph, LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false; sem merge, deploy, modificação n8n, banco cliente, permissões ou cutover.

---

## 12/11/2026 - Censo de strings e externalizacao estrutural

Inventario n8n publicado: 24 sites concretos anteriores + 1.987 literais longos individualmente indexados, com triagem candidata F=1.144, T=187, S=424, U=232. As 1.416 strings curtas ainda nao foram ancoradas uma a uma. Nao equivale a aprovacao contabil das 3.403 ocorrencias, nem indica que todas sejam regras financeiras. Relatorio e politica exclusivamente audit-only em docs/audits/LEGACY-N8N-LONG-LITERAL-TRIAGE-20261112.md e JSON.

Capacidade generica nova: ranking por termos/direcao/limites do catalogo versionado por tenant sobre fontes assinadas e filtros aprovados, com numerador/denominador opcionais, periodo, agrupamento e contrato SQL. PostgreSQL 16 descartavel em 2 contextos sintéticos PASS (16 SELECTs somente leitura), sem Gemini, SQL financeira real ou benchmarks. G5 ainda requer reconciliacao de regra e significado financeiro homologado antes de ativacao; paridade real pertence ao Shadow posterior.

---

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

# Engenharia reversa da migração: n8n legado + base → n8n + LangGraph

**Status:** contrato de execução / inventário integral **AINDA NÃO CONCLUÍDO**. Decisão do operador em 2026-11-11. Repositório: `leandrosilveiradepaula/agente-sql-langgraph`.

## Execução prioritária: primeira capacidade financeira efetivamente demonstrada (11/11/2026)

Não continuar produzindo somente matrizes, scores e infraestrutura. **Selecionar uma capacidade real** a partir dos 68 nós n8n e das 11 versões G5; ler conteúdo/ramificações necessárias com custódia autorizada, validar o significado contábil e externalizar a regra em contexto por tenant. Demonstrar **pergunta inédita → LangGraph → plano explicável → SQL dinâmica generate-only e security gates**, sem execução financeira. Anexar hashes/versão e prova reproduzível. Se faltar vínculo de origem, semântica ou permissão, marcar `IMPLEMENTED_UNPROVEN` ou `NOT_MIGRATED`, nunca `PROVEN`.

Expandir por comportamento até migrar toda a inteligência financeira necessária, mantendo cache/conectores/orquestração no n8n e Produto como autoridade de políticas. Não copiar hardcodes nem usar 63 perguntas/golden SQL como entrada de geração; elas serão apenas o avaliador cego posterior. Não criar estimativa de conclusão sem medir a complexidade real. Ver `docs/operations/FIRST-FINANCIAL-CAPABILITY-PROOF.md` e `AGENTS.md`.

## Resultado obrigatório

Reconstituir o comportamento **real existente** do Agente Financeiro, combinando **o workflow n8n publicado com 68 nós** e **a origem persistida no banco/backup G5**, preservando rastreabilidade, controles humanos e semântica financeira. Isso não é greenfield; não é acertar 63 exemplos por imitação. Migrar toda a inteligência e as regras legítimas para a arquitetura alvo, **sem transportar hardcodes de negócio para Python/TypeScript**.

## Entradas, identidade, integridade e limites

| Fonte | Evidência inicial a verificar | Não inferir |
|---|---|---|
| Workflow n8n | Versão publicada, ID, SHA do export, 68 nós, body JS, prompts, queries, conexões, ramificações, erros, webhooks, Gemini e aprovações | Export de draft = publicado; presença de SQL/literal = regra financeira comprovada |
| Produto/Next.js | Rota oficial que alcança o n8n, auth/RBAC, políticas, geração, aprovação, execução, histórico e correlação | Que webhook ativo na VPS seja o efetivamente chamado |
| Banco/backup G5 | SHA/TOC, versões semanticamente isoladas, tabelas e colunas, chaves, relacionamentos, métricas, aliases, regras, DRE/IMD se existir, dados e proveniência | Que arquivo cifrado ou coluna com nome financeiro defina significado contábil |
| Benchmark n8n | 63 perguntas e testemunhas congeladas separadas do gerador | Usar SQL/resposta histórica para criar mappings, SQL pronta, thresholds ou prompt |
| LangGraph/Shadow | Código, provider Gemini, contexto, fingerprints, gates, logs sanitizados, plano e SQL após autorização | CI verde = paridade; `planned` = resposta financeiramente correta |

Para acesso sensível usar isolamento somente leitura, menor privilégio e diretórios privados; não publicar conteúdo bruto de prompts, consultas, dados de clientes ou credenciais no GitHub. Anotar SHA/versão sem incluir valores de segredo. Nunca descompactar/descriptografar G5 em local público.

## Matriz mandatória de rastreabilidade (um registro por comportamento, NÃO por teste)

| ID | Nó/branch/artefato legado | Objeto/versão do banco | Semântica e evidência | Classe | Destino | Teste/gate | Status |
|---|---|---|---|---|---|---|---|
| WF-001…WF-068 | Export publicado: IDs/índices e fingerprints a inventariar; relações por branch | Vincular tabelas, regras e dados somente após cruzamento real | Inspecionar JS, expressões, prompts, queries, formato I/O, predicados, efeitos e origem | STRUCTURAL / TRANSITIONAL / FORBIDDEN, após revisão | n8n / LangGraph / Produto / contexto versionado | comportamento antigo vs caminho novo, com isolamento | **PENDENTE DE INVENTÁRIO INTEGRAL** |
| DB-version × object | Inventário físico e semântico do backup por versão, referência de checksum | Regras, entidades, aliases, métricas, dimensionamento, joins, fórmulas, DRE etc. | Não misturar versões nem inventar sentidos | contexto autorizado / bloqueio para revisão | catálogo versionado por tenant | validação física + aprovação contábil | **PENDENTE DE CROSSWALK INTEGRAL** |
| INTEGRATION | Webhook Produto→n8n e Shadow n8n→LangGraph | mesma versão e escopo permitidos | IDs e footprints correlacionados | STRUCTURAL | n8n + Produto + LangGraph | witness de pedido real, sem SQL real | **NÃO CERTIFICADO** |

Não declarar cada linha preenchida por simples classificação automática. Uma regra é **migrada** somente depois de sua evidência de origem, destino, implementação e teste; uma lacuna contábil é **não homologada** até aprovação.

## Ordem de execução que bloqueia novas distrações

1. **Censo do fluxo:** obter export do n8n publicado, atestar versão e rota pelo Produto, produzir índice *de TODOS os 68 nós*, campos de código/prompts/SQL, todas as arestas/branches, dependências e características de execução; revisar conteúdos privadamente, contar gaps. Confirmar 41 Code, 11 Postgres, 10 If, 2 HTTP, 3 Respond, 1 Webhook como **observações iniciais a revalidar**, não resultado final.
2. **Censo do banco:** inspecionar o backup restaurado/arquivos semânticos existentes e linhas necessárias por versão, sem vazamento. Capturar inventário de tabelas, colunas, tipos, relações, regras, aliases, métricas, exemplos semânticos, DRE e mapeamentos, documentando a fonte contábil e os controles de integridade.
3. **Crosswalk real:** cada branch/nó/SQL/regra legado → objeto e versão → efeito financeiro → classificação → destino; não deduzir por coocorrência textual. Guardar evidência bruta **privada** e manifestos sanitizados/versionados no GitHub.
4. **Desenho e implementação de migração por jornada:** n8n continua com autenticações de integração, webhooks, conectores, coordenadas de aprovação; LangGraph recebe interpretação/planejamento/SQL dinâmica/gates/repair; Produto gerencia usuários, políticas, aprovação e observabilidade; contexto conhece as definições do negócio.
5. **Validação de portabilidade + segurança:** dois tenants materialmente diferentes sem `if` por cliente; campos desconhecidos bloqueados; gerar SQL somente após planejamento fisicamente autorizado; nenhuma permissão ampliada.
6. **Shadow Gemini:** comparar as mesmas perguntas e contextos com n8n+Gemini em paralelo, correlação real e logs sanitizados; 63 casos somente avaliação posterior, além de perguntas inéditas. SQL financeira read-only apenas com autorização específica.
7. **Decisão humana de cutover e rollback:** preservar n8n, desabilitar exclusivamente inteligência antiga após provas e aprovação. Fase 3 Gemini versus SQL-InfoDive **somente depois**.

## Critérios de aceite

- **Cobertura 100% dos nós, conexões, prompts, SQL, regras e relações pertinentes com o banco**; classificação de cada achado e teste de função, sem fingir que algumas flags representam inventário completo.
- **Semântica versionada aprovada** para cada métrica, dimensão e cálculo usado; múltiplos contextos com esquemas diferentes; nenhum hardcode de cliente no motor.
- **Paridade funcional e financeira comprovada**, com execução numérica em ambiente isolado somente após autorização; aprovação, governança, rollback e logs reais.
- Sem merges, alterações de produção, n8n, DB, credenciais ou cutover implícitos. `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.

**Censo estrutural verificado (11/11/2026):** `docs/audits/LEGACY-N8N-G5-TRACE-20261111.md` indexa 68/68 nós e 78/78 arestas de um workflow n8n ativo com versão publicada coincidente, com 60 nós alcançáveis pelo webhook e 8 não alcançáveis. Backup G5: 11 versões, 5 coleções, 1.381 registros, dos quais 106 SQL patterns restritos à avaliação. Auditor genérico reexecutável `scripts/operations/legacy_migration_source_crosswalk_offline.py`, testes unitários com clientes estruturalmente distintos, validação real offline. Esse censo NÃO representa leitura/revisão integral dos corpos dos nós nem homologação contábil das 11 versões cifradas; 20 nós contêm coocorrências com 376 registros-candidatos (4.813 coocorrências), sem equivalência certificada. A rota Produto→n8n e a identidade semântica entre snapshot Shadow e versões G5 ainda não foram provadas.

**Próxima entrega substantiva:** revisão funcional nó por nó + conteúdo financeiro do G5 isolado por versão + crosswalk de regra/efeito/dados/destino, não novas exceções por 63 perguntas.

**Cobertura e implementação real:** consultar `docs/audits/LEGACY-N8N-PRODUCT-FUNCTIONAL-MAP-20261111.md` (68 nós, destinos propostos, rotas e segurança) e `docs/audits/LEGACY-N8N-LANGGRAPH-CAPABILITY-GAP-20261111.md` (14 capacidades e código existente/ausente). Fonte de regras de negócio continua no n8n + G5, não no benchmark. O alinhamento de 11 pacotes criptografados exige leitura isolada com credencial de desbloqueio fornecida localmente, nunca no GitHub/Chat. Fonte SOURCE está inativa; DEMO tem tabelas de Produto/controle, não é prova de equivalência do G5.

**Onboarding multicliente no código:** a branch da PR #233 oferece `physical_catalog_reader.py`, `tenant_semantic_readiness.py`, `canonical_context_repository.py` e bootstrap configurável `POSTGRES_CONTEXT_SOURCE_MODE=canonical_snapshot`. O mesmo motor recebe contexto canônico versionado independente do esquema do cliente. Integridade, tenant, versão, aprovação e schema são gates distintos; sem inferência contábil e sem dados de benchmark na geração. Ver `docs/architecture/GENERIC-CUSTOMER-SEMANTIC-ONBOARDING.md`. É código ainda não integrado ao n8n oficial nem homologado com dois clientes reais.