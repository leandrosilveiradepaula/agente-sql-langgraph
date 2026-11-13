## Prioridade factual 13/11/2026 — G5 e P3 originais recuperados, ainda sem aprovação

O operador recuperou G5 real (77 registros) e P3 original (137 metadados físicos, 16 tabelas/2 schemas) com SHA verificado. **Não pedir novamente senha nem coleta P3**. Todo trabalho P3 deve basear-se nos originais autenticados privados. Worklist técnica de 48 indícios: 32 aliases com opção literal única, 8 sem, 6 tabelas homônimas em múltiplos schemas, 0/8 schemas legados fisicamente idênticos. Não mapear automaticamente nem criar hardcodes; revisar significados financeiros. O verificador não depende mais de `source_table_ref` presente nos 8 indícios catálogo, mas resolve por source row autenticada; renomeações só com evidência individual SHA vinculada ao recibo HMAC independente. Os arquivos privados não vão a GitHub, benchmark ou prompts. Continuar com aprovação contábil independente dos 77, assinatura dos 48 vínculos, homologação de dois tenants reais, Shadow/paridade; SQL real separadamente autorizado; nenhum merge, banco, contexto ativo, produção ou cutover.

---

## 13/11/2026 — G5 revisão técnica X identidade física P3

A recuperação do G5 original (77 linhas) é fato, mas a verificação do P3 revelou ambiguidade: **40/40 aliases e 6/8 tabelas** não têm tabela física exclusiva; 40 colunas não resolvidas. A anterior afirmação de 40/40 era apenas consistência ENTRE aliases e catálogo legado, não validação física/contábil. Há dossiê confidencial local root-only para revisão dos 77 registros, nunca enviar ao GitHub/LLM. Crosswalk agora exige snapshot P3 completo com hash original presente na origem, decisões explícitas dos vínculos físicos com tipos compatíveis ao catálogo aprovado e atestação independente assinada. O arquivo original P3 ainda não foi identificado para validação nesta sessão; fail-closed correto. Manter 77 classificações UNRESOLVED até revisão humana e não inferir sinais/contas. Não pedir novamente senha G5, não usar benchmark como gerador, não executar SQL real, não alterar n8n/DB, não fazer merge/cutover automaticamente.

---

## Atualização operacional vinculante — 13/11/2026, G5 original recuperado

A dependência de **descriptografia** da versão financeira G5 publicada no n8n foi resolvida pelo operador em TTY local. Há um pacote privado autêntico de **77 registros** (18 regras, 40 aliases, 11 DRE, 8 tabelas) recuperado em /var/lib/agente-financeiro-mcp-admin/g5-financial-review-20261113/active-version-financial-review-private na VPS. A reserialização prévia havia alterado o hash; o arquivo foi restaurado em bytes exatos e a CLI de recuperação corrigida na mesma PR #233 para não repetir. O digest da origem foi conferido, assim como 40/40 vínculos unívocos de alias->tabela e coluna declarada; candidatos PRIVADOS ainda não aprovados. **Não solicitar nova senha para esta leitura, não enviar valores financeiros nem plaintext ao GitHub/LLM/benchmark.** Revisão por especialista e aprovação independente dos 77 registros, contexto validado e prova de funcionalidade/paridade ainda não foram feitos. A execução de SQL financeira continua proibida sem autorização separada. OFFICIAL=n8n, SHADOW=LangGraph, real SQL=false. Sem cutover, merge automático, mudança de serviços ou banco.

---

## 13/11/2026 — Bloco 1: ponte real de G5 para revisão contábil (SEM homologação)

**Verificado na VPS:** versão G5 selecionada pelo n8n publicado ligada ao manifesto privado de 11 ciphertexts; versão ativa SHA-256 7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485 e 77 registros (18 regras, 40 aliases, 11 DRE, 8 catálogo), com hash do ciphertext íntegro. As 11 versões contêm 1.275 registros sem SQL patterns. Todos seguem ENCRYPTED_NOT_APPROVED; zero significados contábeis validados e zero SQL financeira executada. Fonte e benchmark de 63 perguntas permanecem separados.

**Engenharia nova:** scripts/operations/g5_financial_crosswalk_review.py exige cobertura linha a linha do registro original por hash/versão, classificação STRUCTURAL/FORBIDDEN e, para toda regra de negócio, destino canônico explícito; rejeita TRANSITIONAL/UNRESOLVED, ausência/duplicação de registros, troca de tenant, contexto ou fingerprint, destino inexistente, SQL histórica, assinatura ausente ou inválida. Um aprovador independente precisa autenticar digest integral de revisões, contexto e fonte; o código apenas verifica, não emite assinatura. O script g5_targeted_financial_review_offline.py gera um draft privado junto ao pacote verificado, depois de TTY/passphrase local. A nova g5_financial_crosswalk_review_cli.py verifica todos os artefatos privados em modo read-only e pode emitir somente CANDIDATE_NOT_ACTIVATED. Sem importar/aprovar/ativar catálogos por conta própria. Testes sintéticos em dois contextos e 77 linhas simuladas. Documentação: docs/operations/G5-FINANCIAL-CROSSWALK-REVIEW.md.

**Aceite BLOQUEADO por dependência real:** a passphrase local não está disponível nesta sessão e não existe unapproved-source-packet.json já decifrado. A revisão financeira efetiva de 77 linhas e aprovação independente não foram realizadas. A prova de paridade financeira n8n/Gemini × LangGraph/Gemini continua sem autorização read-only. CI e protótipos sintéticos não substituem isso. Preservar PR #233 sem merge, n8n oficial inalterado, LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. Não anunciar Bloco 1 concluído.

---

## 12/11/2026 - Filtros semanticos multifonte no Shadow: lacuna funcional corrigida

Correcao funcional real na PR #233: planejador aplica filtros solicitados em linguagem natural a TODAS as fontes de uma composicao por filter_concept, resolved_filter_bindings e dimension_columns, exclusivamente do contexto versionado tenant. Nao inventa coluna, entidade ou valor, nao consulta benchmark nem copia regras do n8n. Exige origem vinculada, coerencia de operador/valor, mapeamento do conceito em todas as fontes e tipos compativeis, sem joins novos. Operadores para multisource: =, <>, IN e NOT IN. Referencias fisicas incorretas, valores malformados, fontes sem mapeamento e join nao aprovado provocam REJEICAO antes do provedor. SQL Contract Gate rejeita remocao/alteracao dos predicados.

Bug real corrigido no HTTP Canonical Shadow: a passagem classificador -> planejamento descartava termos matched quando semantic_signals opcional estava ausente. O HTTP gerava total geral em vez do filtro pedido. A projecao preserva apenas evidencias matched/normalizadas, sem expor regra de negocio. Teste HTTP comprova filtros nas duas fontes; testes negativos comprovam que nao ha geracao de SQL com source nao mapeada, binding invalido ou fingerprint alterado.

Provas: 46 testes de composicao, 11 HTTP Canonical Shadow, 6 testes de build_plan, 102 regressões SQL Contract e PostgreSQL 16 descartavel: 28 SELECTs read-only em dois esquemas distintos, 2 ACL cross-tenant negadas, perguntas sinonimas, colunas de nomes distintos, filtros =/IN/NOT IN com calculos e ranking. Sem SQL financeira real, Gemini, benchmark gerador, migracao G5 ou n8n alterado. OFFICIAL=n8n; SHADOW=LangGraph; LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false.

Limitacoes: o reconhecimento do filtro depende de conceito identificado pelo resolvedor e binding aprovado; nao se infere semantica contabil de palavras novas. G5 cifrado e homologacao de 77 registros, paridade real e dois clientes reais continuam ABERTOS. PR #233 unica, draft, sem merge.

---

## 12/11/2026 - AST validada do n8n e expressão aritmética ponderada por contexto

**Fato novo contra a contagem histórica:** parse do workflow publicado de 68 nós/78 conexões (41 Code, hashes exatos) com Acorn 8.15.0 detectou **3.698 strings/templates sintáticos**, NÃO 3.403: 1.719 curtos e 1.979 longos pela definição AST, diferença líquida +295 e 18 nós com divergências. O censo anterior era heurístico, não deve ser tomado como contagem sintática exata. Todos os 3.698 receberam referência exata de offset/linha/coluna e classe candidata F=1.732/T=371/S=830/U=765, sem texto/SQL/valor/hash dos próprios literais publicado. Categorias são triagem audit-only, não classificação contábil homologada nem contagem de regras financeiras. Relatório: docs/audits/LEGACY-N8N-AST-LITERAL-RECONCILIATION-20261112.md, JSON sanitizado e auditor JS isolado (scripts/operations/legacy_js_ast_literal_audit.cjs). O baseline 3.403/1.987/1.416 continua somente como comparação histórica. Nenhum plaintext G5 ou benchmark foi usado.

**Capacidade nova no LangGraph:** cálculo genérico weighted_sum_of_sums opcional em metric_source_compositions[].calculation: termos {source_ref, coefficient} versionados por tenant, decimal canônico explícito e vinculação exata a todas as fontes permitidas. O motor soma por grão cada fonte com seu sinal já aprovado e coeficiente declarado; não inventa orçamento, DRE, receita, cliente ou taxa. Projeção, normalização, fingerprint, SQL Security/Contract Gates, HTTP Canonical Shadow e PostgreSQL foram exercitados. Aceita ranking genérico; rejeita coeficiente inválido, SQL embutida, fonte omitida/duplicada/desconhecida, zero, mudança de plano e fingerprint. Dados sintéticos: 42 testes composição, 9 HTTP, PostgreSQL 16 descartável 22 SELECTs read-only em dois esquemas distintos, 2 ACL cross-tenant bloqueadas, frações decimais exatas. Nenhum SQL financeiro de cliente foi executado nem a flag accounting_definition_attested substitui aprovação contábil.

**Segurança operacional:** PR #233 única, sem merge, ativação de contexto, mudança n8n, banco cliente, produção ou cutover. OFFICIAL=n8n; SHADOW=LangGraph; LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. G5 real cifrado e paridade oficial/Shadow seguem condicionados a custódia, aprovação contábil e gates humanos específicos.

---

## 12/11/2026 - Triagem ampla dos literais e ranking generico versionado

Fonte n8n: export publicado e ativo, auditado somente em ambiente privado. Todos os 41 Code conferidos por SHA no baseline de 68 identidades/78 arestas. Dos 3.403 literais registrados, **1.987 longos possuem indice e linha**, 1.416 curtos NAO possuem ancora individual. Manifesto audit-only aponta CANDIDATOS: 1.144 FORBIDDEN, 187 TRANSITIONAL, 424 STRUCTURAL e 232 INDETERMINADOS. Triagem por linha/familia de funcao, NAO aprovacao contabil individual; falsos positivos/negativos sao possiveis. Politica de termos versionada em docs/audits/legacy-n8n-review-signal-policy-v1.json, fora do runtime. Relatorio completo: docs/audits/LEGACY-N8N-LONG-LITERAL-TRIAGE-20261112.md e JSON sanitizado de ocorrencias sem palavras, valores, SQL, prompts ou hashes dos valores das strings.

Externalizacao: contrato opcional metric_source_compositions[].ranking com termos e direcao asc/desc, default_limit e maximum_limit configurados pelo contexto versionado do tenant. Planejador interpreta perguntas ineditas sem termos hardcoded, exige grao/dimensao autorizada e rejeita ambiguidades, numeros fora da politica, sinais invalidos e planos alterados. Gerador PostgreSQL soma fontes/razoes antes do ORDER BY metric_value e LIMIT, com empate deterministico, NULLS LAST e SQL Contract Gate. Sem regra topN fixa por cliente, DRE, conta, marca ou SQL historica. Ajuste no parser SQL para NULLS FIRST/LAST em ordenacao preserva colunas homonimas.

Prova local: 38 testes E2E de composicao, 8 HTTP Canonical Shadow, 4 testes de triagem; hardcode/secret scanners PASS. PostgreSQL 16 descartavel em dois contextos sinteticos diferentes: 16 SELECTs read-only, 2 tentativas cross-tenant negadas, agregacao, razao, ranking e ranking+razao numericamente corretos. Nenhuma SQL financeira real, G5 plaintext, benchmark, n8n modificado, merge, producao ou cutover. PR #233 unica. OFFICIAL=n8n; SHADOW=LangGraph; LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false.

Pendencias: certificacao contabil das regras, ancora individual dos 1.416 curtos, revisao humana dos 1.987 candidatos, mapeamentos G5 homologados e equivalencia oficial/Shadow. Nao declarar financeiramente completo.

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

# 2026-11-11 21:36 UTC — ORDEM VINCULANTE: PROVAR A MIGRAÇÃO FINANCEIRA REAL

**Missão única:** migrar a inteligência do Agente Financeiro EXISTENTE, estudando juntos o workflow n8n publicado (**68 nós, 78 conexões**) e as **11 versões semânticas do banco/backup G5**, para Produto + n8n (preservado) + LangGraph + Gemini. Não criar outro agente, não confundir com Factory/CRM, não copiar código/SQL/regras casuísticas ou hardcodes financeiros do n8n para Python/TypeScript.

**Próxima entrega, antes de mais infraestrutura/benchmark/documentação:** selecionar uma capacidade financeira **real** do legado e demonstrar rastreavelmente **nó/branch do n8n + regra/registro/versão G5 + significado financeiro validado → contexto semântico versionado por tenant → pergunta inédita → interpretação/plano LangGraph → SQL dinâmica generate-only e gates**. Depois expandir até cobrir os comportamentos necessários, preservando logs, cache, relatórios, aprovações e outros efeitos na camada correta. Sem vínculo contábil aprovado não afirmar migração.

**Zero hardcode e multicliente:** motor conhece processo, catálogo aprovado/versionado conhece o negócio. Sem nomes de clientes, tabelas, colunas, DRE obrigatória, métricas, aliases, joins, sinais, filtros ou fórmulas no código novo; clientes podem ter estruturas distintas e exigir adaptadores de dialeto. Significado contábil não comprovado gera falha segura/pendência humana. Testar pelo menos dois contextos materialmente diferentes e perguntas inéditas.

**Métrica de progresso por capacidade:** `NOT_MIGRATED`, `IMPLEMENTED_UNPROVEN` ou `PROVEN`, com SHA/PR, fonte, versão/fingerprint, teste, resultado e riscos. CI verde, número de documentos, 68 nós enumerados, mocks ou benchmark alto **não** provam migração. A estimativa de 12–20 semanas anterior foi **retirada**: não inventar novos prazos ou percentuais sem medição real.

**Benchmark e SQL histórica:** 63 perguntas oficiais e 106 padrões SQL históricos são **somente para avaliação cega posterior** n8n+Gemini versus n8n+LangGraph+Gemini, nunca exemplos, prompt, input do planner, SQL esperada ou resposta a copiar. Correção de divergência deve ser genérica, não por benchmark.

**Gates:** `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. `Generate`, `Repair` e `Execute Approved` separados; SQL reparada exige `requires_reapproval=true`. SQL financeira read-only para comparação numérica requer autorização separada em isolamento; merge, migração, alteração de DB/n8n/produção/permissões, custos e cutover são humanos. Gemini × SQL-InfoDive somente após cutover homologado.

**Retomada e execução:** verificar GitHub HEAD/PRs #230/#231/#233, CI, runtime VPS e fontes reais; trabalhar em blocos substantivos sem pedir `prossiga` a cada microtarefa. Não reauditar continuamente o que já foi provado. Relatar apenas capacidades com evidência real. Ler `MEMORY.md`, `docs/operations/FIRST-FINANCIAL-CAPABILITY-PROOF.md`, `docs/operations/LEGACY-N8N-DATABASE-MIGRATION-MAP.md` e o contrato de portabilidade.

**Baseline verificado antes desta atualização:** `main@955eda46015d35dbe44a40f9240b821b1f493201`, VPS checkout `87d167969345c3dfcf9deaf36e33ab07a1f9c890`, PRs #230/#231/#233 draft, n8n running, Shadow TEST healthy e execução financeira Shadow desabilitada. A PR #233 em `5b29a89036ac80c1a3a792e8184e96a91662ee5a` falhou no Windows no passo `Whitespace check` do roadmap; CI Linux PASS. Migração completa/paridade financeira **não demonstradas**.

---

# INSTRUÇÃO PRIORITÁRIA — 11/11/2026: MIGRAÇÃO INTEGRAL DO LEGADO

**A tarefa não é desenvolver outro agente financeiro.** É analisar profundamente e **em conjunto** o workflow n8n publicado com 68 nós e o banco/backup G5 (todas as versões, tabelas, regras, entidades, semântica, relacionamentos e dados pertinentes) para migrar integralmente o comportamento do sistema existente para **n8n + LangGraph**. n8n continua como orquestrador; só a inteligência antiga deixa o n8n depois de provar paridade e autorização humana. Business rules ficam em catálogos semânticos versionados por tenant, sem hardcodes de cliente.

**Sequência:** verificar fontes reais e hashes → inventariar cada nó/prompt/JS/SQL/branch e cada objeto relevante do banco → cruzar evidências em matriz nó→regra/dado→capacidade→destino → migrar comportamento sem copiar SQL hardcoded → gerar SQL dinamicamente para perguntas inéditas → avaliar cegamente as 63 perguntas e casos extras → validar 2 tenants distintos → Shadow auditável/paridade/execução read-only separadamente autorizada → cutover humano → só então Gemini × SQL-InfoDive. Não perseguir pontuação/bugs laterais em detrimento dessa jornada, não classificar 6 aliases ou 63 casos como inventário integral.

**Obrigatório em toda retomada:** `AGENTS.md`, `MEMORY.md`, `docs/operations/LEGACY-N8N-DATABASE-MIGRATION-MAP.md` e contratos atuais, além de HEAD/PRs/CI/VPS verificados. `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`; zero SQL financeira real sem autorização isolada, zero ativação/migração/merge/cutover implícitos. Benchmark é somente avaliação posterior, nunca contexto de geração.

---

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
