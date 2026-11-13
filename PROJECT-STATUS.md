## 13/11/2026 — Bloco 1 G5/P3: original físico recuperado; revisão financeira ainda não aprovada

**Evidência REAL:** P3 original preservado pelo operador e confirmado na VPS, 137 linhas físicas, 16 tabelas em dois schemas; SHA coincide exatamente com o G5 original de 77 registros. A indisponibilidade de P3 registrada em seções anteriores foi resolvida. Nova matriz de 48 indícios físicos (40 aliases, 8 catálogos) validada sem SQL: 0/8 schemas originais coincidem com identidade física, 6/8 nomes de tabela multi-schema, 32/40 colunas de aliases com somente um candidato literal, 8/40 sem candidato literal. Nenhuma é correspondência financeira aprovada. Arquivos JSON e HTML de trabalho **privados** (0600, root; não enviar ao LLM/GitHub), nome `g5-p3-original-physical-worklist` sob diretório da revisão original; o dossiê 77 registros permanece intacto.

**Correção funcional de gate:** oito indícios de catálogo P3 possuem `source_table_ref=null`; o validador anterior nunca conseguiria aprovar a fonte real. Agora obtém identificadores do registro G5 vinculado por SHA, distingue referência original de destino físico, e para mudança explícita de schema, tabela ou coluna exige `physical_remap_evidence_sha256` incluído na aprovação HMAC independente. Prova sintética de dois tenants, tabelas homônimas, nomes de coluna diferentes, recibos adulterados e recusa de preenchimento automático. Verificação de dados reais agora para no bloqueio correto `G5_PHYSICAL_DECISIONS_INCOMPLETE`, não mais `G5_P3_ORIGINAL_METADATA_REQUIRED`.

**Não concluído:** 77 classificações contábeis, 48 decisões físicas, contexto canônico com tenant/version/fingerprint aprovado e assinado, teste de perguntas inéditas em duas empresas reais, paridade funcional e financeira; SELECT financeira real somente com autorização separada. OFFICIAL=n8n, SHADOW=LangGraph, SQL real=false. Nenhum merge/produção/DB/n8n/cutover. Contrato detalhado em `docs/operations/G5-P3-ORIGINAL-PHYSICAL-WORKLIST.md`.

---

## 13/11/2026 — P3: custódia exata preparada, original ainda não localizado

Verifiquei cinco artefatos históricos privados do G5/P3: todos indicam o mesmo
SHA-256 de snapshot físico P3 registrado no pacote original recuperado. Isso
não recupera os dados nem autoriza mapeamento. Um scan em 1.535 arquivos
acessíveis do serviço não encontrou os bytes correspondentes. O serviço MCP
usa PrivateTmp; o antigo caminho `/tmp/p3-source-audit.7DIc9fUP/physical-metadata.json`
pode ainda existir no SSH do operador, mas não foi conferido nesse namespace.

Criado `scripts/operations/g5_preserve_p3_custody_offline.py` para receber
somente arquivo P3 original em custódia privada, verificar o SHA exatamente
contra G5 selado, formato/flags sem SQL, copiar bytes idênticos a arquivo 0600
no diretório 0700 da revisão financeira. Falha fechada se inexistente,
alterado, com permissões amplas ou se já existir destino. Testes sintéticos
de dois schemas, hash adulterado, permissões e symlink. Nenhum banco, n8n,
sistema oficial, benchmark ou LLM acessado. Guia:
`docs/operations/G5-P3-ORIGINAL-CUSTODY.md`. O gate de aprovação dos 77
registros/48 vínculos continua pendente; fonte não ativada.

---

## 13/11/2026 — CI Windows: teste de recuperação corrigido; custódia P3 ainda pendente

**Resultado confirmado do CI no SHA 7e324b5:** `Offline validation` falhou somente no job Windows, em `testar_g5_targeted_financial_review_offline.py`: o teste recém-criado exigia retorno PASS do endpoint de recuperação em Windows, embora o próprio endpoint de segurança deva sempre retornar BLOCKED fora de POSIX. A suíte Linux Shadow e a migração PostgreSQL descartável passaram. Teste alterado para verificar **bloqueio seguro no Windows sem arquivo de saída**, mantendo conferência independente do SHA original em ambas as plataformas. Código de produção e controle POSIX não foram afrouxados. Novo CI do SHA corrigido precisa ser conferido.

**Busca por P3 real:** verificados por hash exato 1.535 arquivos candidatos (JSON/JSONL/TXT/snapshot) em raízes privadas autorizadas da VPS e áreas de código; **zero correspondências** ao `p3_snapshot_sha256` selado na fonte G5 original. Não declarar P3 recuperado, nem substituir por arquivo reconstruído ou sintético. Continua pendente localizar/transferir para custódia privada o snapshot físico P3 original e realizar a revisão financeira independente dos 77 registros. Sem SELECT financeira, ativação de contexto, modificação n8n ou cutover.

---

## 13/11/2026 — G5 real: dossiê 77/77 e prova física P3 independente (não homologado)

Após recuperar a versão G5 original, confrontei os 48 indícios P3 com as declarações do próprio catálogo. **Resultado real:** 40 aliases mapeiam internamente a 8 tabelas, mas P3 identifica 40 aliases e 6 tabelas como AMBIGUOUS_TABLE_NAME (46), 40 colunas como COLUMN_UNRESOLVED e duas tabelas somente TABLE_NAME_ONLY. Nenhuma equivalência física ou financeira foi aprovada. O arquivo HTML de revisão dos 77 registros, com conteúdo original e indícios P3, foi gerado só na VPS privada como 0600/root; não enviar valores ao GitHub/LLM. A ferramenta estruturada é genérica em relação aos nomes/contas de cada cliente; HTML estático com escape e CSP, sem comunicação de rede.

**Nova defesa de segurança funcional:** o `verified_review` exige, para pacotes com indícios P3, os bytes exatos do snapshot P3 original vinculados ao SHA do pacote, lista de decisões explícitas de schema/tabela/coluna por indício, tipos físicos compatíveis com o contexto canônico versionado, e HMAC de aprovação incluindo SHA do P3 e das decisões. A CLI aceita `--p3-metadata-file` privado. Sem snapshot, sem decisão ou com tabela homônima em outro schema, a candidatura financeira permanece bloqueada; nenhum SQL real ou alteração de serviço foi feita. G5 original 77/77 continua UNRESOLVED; 48 vínculos físicos sem atestação. Testes locais específicos: 8/8 de dossier, 7/7 de prova física, 6/6 crosswalk, 8/8 recuperação, 47/47 composição e 11/11 Shadow; hardcodes/segredos PASS. Sem comprovação de cliente real, homologação contábil, paridade numérica, CI pós-commit ou cutover.

---

## 13/11/2026 — Recuperação G5 concluída; crosswalk financeiro permanece PENDING

**Verificado na VPS:** o operador recuperou a versão G5 publicada no n8n (SHA-256 da versão 7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485), com 77/77 registros de fonte: 18 regras, 40 aliases, 11 DRE, 8 entradas de catálogo. O plaintext confidencial permanece privado, em arquivos 0600 sob diretório 0700. Nenhum dado da origem, SQL histórica ou senha foi enviado ao gerador ou GitHub.

**Bug de integração identificado e reparado:** o recuperador persistia JSON reserializado, cujo hash diferia do plaintext selado; o verificador de crosswalk exigia bytes originais, portanto bloquearia a revisão. O arquivo privado real foi restaurado ao hash de origem usando representação JSON idêntica e confirmado com `verify_decrypted_packet`. Código corrigido para armazenar o `content` original sem recodificação; teste E2E sintético novo cobre preservação exata de bytes e rejeição de reformatação. Testes: 8/8 recuperação G5, 6/6 crosswalk, 47/47 composição em checkout isolado.

**Linhagem técnica dos registros reais:** 40/40 referências de aliases a tabelas não qualificadas foram vinculadas univocamente às 8 entradas de catálogo; suas 40 colunas constam nas listas de colunas declaradas. Criado candidato de linhagem **privado e não aprovado**, sem inferir tipos físicos, sinais, classificações DRE, joins ou regras financeiras. Todos os **77 mapeamentos seguem UNRESOLVED**; a recuperação não constitui homologação. Próximos gates: revisão contábil independente, catálogos e fingerprints por tenant aprovados, capacidades funcionais em perguntas inéditas, comparativo Shadow n8n/Gemini, futura paridade financeira read-only somente com autorização separada. OFFICIAL=n8n, SHADOW=LangGraph, SQL real desabilitado. Nenhum merge, importação, serviço, banco ou n8n foi modificado.

---

## 13/11/2026 — SQL quoted identifiers: erro funcional corrigido na PR #233 (sem homologação G5)

Bug reproduzido em pergunta sintética: catálogo físico com `gross_units`, plano com `GROSS_UNITS` era aceito pelo normalizador, SQL Security e SQL Contract, apesar de identificadores distintos em PostgreSQL quando entre aspas. Correção na mesma branch da PR #233: verificação **exata** de esquema/tabela/colunas em composição multifonte, filtros semânticos, agrupamentos, DATE e gate independente pré-provedor; aliases e conceitos semânticos continuam insensíveis a caixa. Regressão agora rejeita adulteração do contexto/plano e aceita coluna mista explicitamente cadastrada. Testes VPS: 47/47 composição, 11/11 Shadow canônico, 6 build_plan, 13/13 G5, hardcodes/segredos PASS. Não equivale a validação de dois clientes reais. G5 da versão oficial segue cifrado sem homologação contábil e sem autorização para SQL financeira. OFFICIAL=n8n, SHADOW=LangGraph, LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. Sem alteração de n8n/DB/serviços/cutover.

---

**Vinculação adicional 13/11/2026:** a CLI exige agora evidência local e privada de seleção da versão n8n publicada; hashes e row_counts dos 77 registros devem coincidir com o pacote cifrado. G5 não pode ser substituído por DEMO nem outra versão ao construir a prova de migração. Testes positivos/negativos com origem sintética; verificado também, sem decrypt, o manifesto real 77/77 vinculado à versão do n8n. Nenhuma ativação ou aprovação contábil.

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

# 11/11/2026 — M1: EVIDÊNCIA DE FORMULAS FINANCEIRAS E GATES TÉCNICOS DO N8N

Foi confirmado no prompt do nó 8: fórmula de percentual do resultado, parâmetros DRE fixos, critérios de orçamento/variação e modelos dimensionais específicos; **não portar esses textos ao código**. IF 25 (`success` do nó 12) e IF 29 (`aprovado` do nó 28) são booleanos derivados de contagem de erros técnicos, não aprovação humana. IF 62 consome preflight; os demais IF não são tratados como autorização. Auditor genérico aprimorado: 10 testes offline PASS; evidência do workflow real 10 IF, SHA privado `e5d6f3886730f16f484d40a1f818fb83d6ec563a5d2b8f2d34270bfb46fe612a`. Chave local GPG não está em cache; conteúdo contábil das 11 versões do G5 **não atestado**. Produto oficial/Shadow intocados, SQL real false, primeira capacidade `NOT_PROVEN`. Ver `docs/audits/LEGACY-N8N-G5-SEMANTIC-COUPLING-20261111.md`.

---

# M1 — EVIDÊNCIA REAL DE ACOPLAMENTO SEMÂNTICO N8N/G5, CONTINUA SEM PROVA FINANCEIRA

Auditor `legacy_semantic_static_coupling_offline.py` executado na VPS sobre 68 nós publicados, 11 versões G5 e 579 hints: nó PostgreSQL 5 possui cinco seletores fixos da mesma versão e carrega SQL patterns históricos (avaliação somente), nó 7 escolhe padrão/intent e passa via contexto texto→prompt nó 8→payload Gemini nó 9. Nó 22 fixa 8 bindings físicos; 4 correspondem textualmente a identificadores G5, todos `AMBIGUOUS_TABLE_NAME`, 4 não correspondem. 4 objetos literais simples/12 bindings no grafo; 4 referências físicas textuais. 8 testes sintéticos PASS; scanner de hardcode e git diff check PASS. Relatório privado SHA `b9fc93f7986020aa4017a9a3641baf770e617eeab0a08d67c8ef36b205c8b179`; `docs/audits/LEGACY-N8N-G5-SEMANTIC-COUPLING-20261111.md`. **Sem validação contábil das 11 versões cifradas, sem SQL financeira real, sem migração funcional comprovada.**

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

# 2026-11-11 — CAPACIDADE GENÉRICA DE CONFIGURAÇÃO POR TENANT (PR #233 DRAFT)

**Implementado e testado offline, sem ativação:** adapter de descoberta física PostgreSQL read-only em `information_schema.columns`; pré-validação de semântica versus tabelas/colunas autorizadas; loader JSONB de contexto canônico com tenant/versão/fingerprint e aprovação; seleção desse loader via variáveis de deploy, preservando modo antigo como default. Testes com dois clientes de esquemas distintos, recusando alias/tabelas/colunas inventados. Ver `docs/architecture/GENERIC-CUSTOMER-SEMANTIC-ONBOARDING.md`. Isso ainda não extrai integralmente o conhecimento contábil G5 cifrado, nem comprova homologação multicliente, versionamento publicado, UI de onboarding, rotas de execução n8n ou paridade financeira. **Benchmark 63 casos somente avaliação posterior.** Nenhuma modificação em produção/n8n/banco; merge humano pendente.

---

# 11/11/2026 — MATRIZ DE 14 CAPACIDADES E DÍVIDAS DE PORTABILIDADE

Adicionada `docs/audits/LEGACY-N8N-LANGGRAPH-CAPABILITY-GAP-20261111.md`: 14 capacidades inventariadas n8n→Produto/LangGraph, status verdadeiro do código, provas pendentes e source gate. Scan seguro 41 Code nodes (14.440 linhas JS, 3.403 literais) preservado com hash; **nem literais nem coocorrências são regras contábeis atestadas**. Portabilidade requer resolver adapter com defaults DuckLake/DRE e vínculo de contexto versionado por tenant. G5 cifrado e SOURCE inativo ainda impedem avaliação completa dos 11 pacotes. Os 63 casos são somente controle posterior de qualidade, sem alimentar gerador. Nenhuma mudança de dados, n8n, permissões, credenciais, runtime ou cutover.

---

# 11/11/2026 — REVISÃO FUNCIONAL DO LEGADO, PRODUTO E LIMITES DO G5

A PR #233 documenta 68/68 nós funcionais com destinos provisórios e revisou as 78 arestas. Comprovado estaticamente: 41 Code (~14.440 linhas), 2 referências de credenciais PostgreSQL separando 9 nós de contexto/cache/log/config e 2 nós de preflight/execução; os ramos de SQL gerada e reparada podem alcançar o executor. Produto Next.js efetivo possui `/api/generate-sql` e `/api/execute-watson` com políticas e eventos Shadow distintos; o webhook fallback do código não coincide com o path do n8n publicado (variáveis efetivas ainda não verificadas). Source Supabase INACTIVE; DEMO ACTIVE com 13 tabelas públicas. No G5, 579 hints por 11 versões equivalem a 11 pares tabela/coluna e 58 pares nó/referência textuais; 447 status de ambiguidade, 110 sem correspondência, 481 colunas não resolvidas. NADA disso equivale a semântica contábil aprovada, migração concluída ou paridade. Os pacotes cifrados exigem revisão por versão e o benchmark de 63 perguntas é **apenas controle de qualidade posterior**.

---

# 11/11/2026 — CENSO ESTRUTURAL N8N+G5 VERIFICADO; REVISAO FUNCIONAL AINDA PENDENTE

Na PR #233 (draft, ainda sem merge), a engenharia reversa verificou em memória a versão n8n ativa (`versionId == activeVersionId`) com 68 nós, 78 conexões, 60 nós alcançáveis pelo webhook e 8 fora desse caminho. G5: 11 versões cifradas, 5 coleções/1.381 registros e 579 candidatos de referência física ainda não aprovados. O auditor genérico produziu o índice sanitizado `docs/audits/LEGACY-N8N-G5-TRACE-20261111.md`, com 20 nós que possuem ocorrências textuais de identificadores do backup (4.813 coocorrências). **Nenhuma associação contábil foi aprovada**; conteúdo de JS/prompts/SQL e regras G5 por versão ainda exigem investigação conjunta. O snapshot Shadow não foi equiparado a uma versão G5 e a rota Produto→n8n não está atestada. Esse progresso NÃO certifica migracao, geração SQL dinâmica, paridade ou cutover.

---

# 2026-11-11 — FOCO OPERACIONAL MAIS RECENTE: MIGRAÇÃO INTEGRAL DO N8N + BANCO EXISTENTES

O operador reafirmou: **engenharia reversa do sistema financeiro atual**, analisando conjuntamente o n8n **publicado** (workflow observado com 68 nós) e **todo o conhecimento e dependências pertinentes do banco/backup G5**, para migrar comportamento à arquitetura **n8n + LangGraph** preservando n8n e zero hardcodes de negócio no novo motor. A análise de seis aliases, scoring, SQL histórica ou CI é insuficiente para declarar migração. Matriz por nó/branch/SQL/prompt→objetos/versões do banco→comportamento financeiro→destino e provas é a entrega prioritária. **Ainda não foi concluída**. Ver `AGENTS.md`, `MEMORY.md` e `docs/operations/LEGACY-N8N-DATABASE-MIGRATION-MAP.md`.

**Não aprovado:** merge, ativação de contexto, alterações de n8n/banco/produto, execução SQL financeira real, mudança de provider/cutover. O curso obrigatório é Shadow n8n+Gemini vs n8n+LangGraph+Gemini, read-only financeiro somente em autorização separada, cutover humano controlado, depois Gemini×SQL-InfoDive.

---

# 29/10/2026 — G3: APROVAÇÃO PERSISTIDA NA DEMO; SHADOW WITNESS EM PR; EXECUÇÃO REAL BLOQUEADA

**SUPABASE REAL (verificado por conector):** SOURCE `nywxpvzhlpqjtcafpdfe` = `INACTIVE` (pausa reversível, NÃO apagada nem aposentada); DEMO `cenhadslwxgykqtuobgc` = `ACTIVE_HEALTHY`. Migrações efetivamente registradas na DEMO:
- `20261029043453` — `candidate_sql_review_gates_20261029` (ledger de SQL/revisões com RLS);
- `20261029103634` — `tenant_onboarding_execute_intent_20261029` (identidade nomeada + solicitação imutável `pending_authorization`);
- `20261029111200` — `lockdown_legacy_agent_data_api_20261029` (RLS + REVOKE nas 7 tabelas legadas; acesso direto de `postgres` preservado, `anon`/`authenticated`/`service_role` sem leitura/gravação).

**ESTADO DA DEMO VERIFICADO:** 0 organizações, 0 memberships, 0 propostas, 0 intenções; estrutura e ACL de intent verificadas (RLS true, roles `anon`/`authenticated`/`service_role` sem leitura/gravação). Nenhum tenant ou usuário sintético foi provisionado. Código do Produto exige organização/identidade autorizada; só uma pessoa admin real não permite homologação de aprovação independente.

**REPOS/PRs:** Produto [#37](https://github.com/leandrosilveiradepaula/Agente-Financeiro/pull/37) mergeada; [#38](https://github.com/leandrosilveiradepaula/Agente-Financeiro/pull/38) **mergeada; migração aplicada e validada na DEMO** (7/7 RLS + ACL sem acesso REST, advisors sem erro de RLS desabilitado); [#39](https://github.com/leandrosilveiradepaula/Agente-Financeiro/pull/39) prepara ledger de witness e rota Produto→n8n Shadow (ainda NÃO aplicada); LangGraph/n8n [#198](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/pull/198) prepara webhook `execute-approved-shadow` de validação sem SQL financeira, **inativo**. Os PRs abertos não são autorização para importação/ativação.

**PRÓXIMO ACEITE OPERACIONAL:** após merges humanos e migrations aprovadas, identificar tenant e segundo revisor reais; confirmar os bindings de produção, runtime TEST/Shadow `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`, credenciais S2S e contexto, com ativação específica. Sem esses controles não declarar aprovação real ou paridade financeira. A testemunha Shadow apenas valida pré-execução, não roda SELECT financeira. Separadamente exigir autorização de SQL read-only, isolamento, custos de LLM, paridade, rollback e cutover humano. `OFFICIAL=n8n`, `SHADOW=LangGraph`, sem migração automática dos hardcodes do n8n.

**CUSTÓDIA G5:** backup SOURCE restaurado em PostgreSQL isolado, mas cópia cifrada externa, recuperação gerenciada Supabase, vínculos remanescentes, paridade numérica e cutover permanecem pendentes. SOURCE INACTIVE não satisfaz aposentadoria definitiva.

---

# 28/10/2026 18:24 UTC — G5 RESTORE REAL PASS / SOURCE AINDA INELEGÍVEL À APOSENTADORIA

**EVIDÊNCIA DA VPS DO OPERADOR:** PR #193 mergeada (`18ca3fcd0227f3ed11bde0bc50ea0e400aa8e444`). Em contêiner rootless `supabase/postgres:17.6.1.136` SHA `f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00`, sem rede/host volumes, GPG→pg_restore com transação única e cleanup: `G5_RESTORED_TABLES=86`, `G5_ISOLATED_CONTAINER_CLEANUP=PASS`, `G5_RESTORE_TEST=PASS`, **`G5_SUPABASE_FULL_RECOVERY=NOT_ATTESTED`**. Restauração PostgreSQL isolada comprovada; **não declarar plataforma, Auth, Storage, Vault/chave, roles/grants, RLS, SQL financeira, paridade ou cutover concluídos**. Não houve alterações SOURCE/DEMO/n8n/Shadow.

**AUDITORIA SELECT-only em SOURCE e DEMO após o ensaio:** 86 tabelas atualmente na SOURCE (47 public, 27 auth, 8 storage, 1 vault, 3 outros); exatamente 86 encontradas na sandbox após pg_restore, confirmando cobertura por contagem de objetos, NÃO igualdade de linhas/dados. DEMO 75 tabelas (10 public, 27 auth, 8 storage, 1 vault, 26 outras). Ambos têm `auth.users`, `storage.buckets`, `storage.objects` e `vault.secrets` com zero registros. SOURCE `public` 47 tabelas sem RLS, 0 policies; DEMO `public` 10 tabelas com 3 RLS e 3 policies. **Não copiar esquema/identidades/ACL, autenticação ou regras de negócio da SOURCE sem mapeamento versionado e autorização.** 16 roles não-sistema SOURCE versus 21 DEMO; considerar grants/roles explicitamente, pois dump G5 usou `--no-owner --no-acl`.

**Evolução de segurança:** prova de RESTORE PASS ≠ custódia de arquivo fora da VPS ≠ recuperação de serviços ≠ migração para DEMO. O gate `scripts/operations/check_supabase_retirement_gate.py` está sendo fortalecido para exigir schema v2 com provas separadas: restore, cópia cifrada offsite, plataforma, identidades, isolamento de tenant, semântica, paridade, sincronização final, rollback, observação e aprovação humana. O verificador `g5_verify_encrypted_copy_readonly.py` confere SHA de cópia externa **sem fazer upload ou declarar custódia externa automaticamente**. Não executar transferências remotas antes de escolher local/destino aprovado.

**Controles imutáveis:** `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. SOURCE continua ativa, sem autorização para migration, mudança DSN/roles, n8n/Produto, cutover ou exclusão. Roadmap issue #155 e `docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md` têm as evidências. Evitar repetir ensaio G5 já PASS; próximo foco é proteger cópia externa e homologar dependências/final sync, sem hardcodes de cliente.

---

# 28/10/2026 — G5: EXTENSION CONTROLS EM SUPABASE PG17 4/4; BOOT-TEST ISOLADO EM PREPARACAO

**Evidencia REAL da VPS (apos PR #192):** a auditoria read-only do backup cifrado SOURCE `nywxpvzhlpqjtcafpdfe` teve `G5_ARCHIVE_TOC_ENTRIES=811`, `G5_ARCHIVE_EXTENSION_COUNT=4`, nomes `pg_stat_statements,pgcrypto,supabase_vault,uuid-ossp`. A imagem comunitaria `postgres:17` (SHA `31ba9c94a03ada9988f2bb493a22a75eef3a185884533e5cdbcd498ea835b08f`) faltou `supabase_vault`; a imagem `supabase/postgres:17.6.1.136` (SHA `f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00`) tem **todos os quatro controles de extensao** presentes, `G5_IMAGE_2_MISSING_COUNT=0`, `G5_IMAGE_2_EXTENSION_COVERAGE=FILES_PRESENT_NOT_RESTORE_PROOF`, `G5_RESTORE_TEST=NOT_PERFORMED`. **NAO afirmar restauracao concluida nem compatibilidade de roles, dados, funcoes ou chave Vault.**

**Entrega atual:** adaptador de teste G5 para imagem Supabase PostgreSQL 17 previamente cached e SHA pinada (sem if por cliente). Novo `--boot-test` deve somente confirmar initdb PostgreSQL 17 em container temporario, nonroot UID/GID descoberto na imagem, network=none, read-only, sem bind/volume/ports, PGDATA/socket/tmp em tmpfs e swap desativado, execucao de initdb estatico sem Supabase migrations nem chave Vault; limpeza verificada antes de PASS. Nao decrypt/restaurar SQL neste teste. `--restore` na nova imagem so depois de **nova autorizacao separada** e token `RESTORE-G5-SUPABASE-ISOLATED`. SQL raw do dump inclui objetos gerenciados Supabase, diferente do processo de export oficial schema+roles+data; se falhar, BLOQUEAR sem remover extensoes/tabelas nem baixar thresholds. Contrato de backup externo/off-VPS segue pendente.

**Arquitetura invariavel:** `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`; SOURCE e DEMO inalterados, n8n preservado, sem migracao de banco, roles, DSN, permissoes ou cutover. A SOURCE continua necessaria para dependencias legadas; ver `docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md` e issue #155.

---

# 28/10/2026 — G5 IMAGE PROBE BLOCKED ON SUPABASE PG17; RESTORE STILL NOT VERIFIED

**Operador executou preflight read-only** depois de PR #191 mergeada e baixou `supabase/postgres:17.6.1.136`; imagem local ID `sha256:f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00`. Auditoria em `postgres:17` e `supabase/postgres:17.6.1.136` interrompeu com `G5_EXTENSION_AUDIT_ERROR=IMAGE_EXTENSION_PROBE_INVALID`, `G5_RESTORE_TEST=NOT_PERFORMED`, **antes de pedir senha ou restaurar SQL**. A causa exata desse erro agrupado nao consta no log: nao atribuir a imagem vazia, nome invalido ou qualquer extensao sem teste.

**Correcao estrutural da auditoria:** de acordo com PostgreSQL 17, distinguir `extensao.control` (primario) de `extensao--versao.control` (secundario); arquivos auxiliares de versao nao sao extensoes adicionais, podendo conter pontos que a regex de nome primario rejeitava. Filtrar auxiliares antes da validacao dos primarios (sem ignora-los para fins de restore) e retornar erros separados, exclusivamente codigos fixos, se nao houver controls ou houver saida inesperada. Testes Linux POSIX simulam pg_config e primarios/secundarios; CI Windows/Linux. Proxima acao apos PR/CI/merge: REEXECUTAR somente a auditoria read-only contra as duas imagens em cache e enviar linhas `G5_`. Nao repetir `--restore`/alterar bancos/baixar mais imagens antes da evidencia.

**Ja comprovado:** arquivo SOURCE cifrado SHA PASS, GPG/decrypt PASS, TOC 811; quatro extensoes `pg_stat_statements`, `pgcrypto`, `supabase_vault`, `uuid-ossp`; imagem comunitaria `postgres:17` SEM `supabase_vault` e bloqueio real `EXTENSION_UNAVAILABLE`. A segunda imagem Supabase ainda nao tem coverage comprovada. SOURCE/DEMO/n8n/Shadow inalterados. G5 restore integral, copia off-VPS, Vault key e dependencias/cutover permanecem pendentes. `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. Ver `docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md`, issue #155.

---

# 28/10/2026 — G5: EXTENSION_UNAVAILABLE REAL, RECUPERACAO SOURCE AINDA BLOQUEADA

**Operador executou segundo teste de restore isolado autorizado na VPS**, com PR #190 mergeada e stderr classificado somente em memoria. Resultado real: `G5_REHEARSAL_MODE=RESTORE`, `G5_IMAGE_CACHED=YES`, `G5_REHEARSAL_RESULT=BLOCKED`, `G5_REHEARSAL_ERROR=ISOLATED_RESTORE_SQL_FAILED`, `G5_RESTORE_FAILURE_CATEGORY=EXTENSION_UNAVAILABLE`, `G5_RESTORE_TEST=NOT_VERIFIED`. O motivo e uma extensao ausente no contêiner PostgreSQL 17 comunitario, mas o **nome exato da primeira extensao que falhou ainda NAO foi comprovado**. Cleanup do container verificado pelo proprio utilitario; SOURCE/DEMO/n8n inalterados. Backup SHA-256/GPG/TOC 811 entradas PASS; nao houve restore efetivo.

**Query READ-ONLY METADATA no Supabase SOURCE feita nesta etapa:** `pg_extension` listou extensoes instaladas `pg_stat_statements 1.11`, `pgcrypto 1.3`, `plpgsql 1.0`, `supabase_vault 0.3.1` e `uuid-ossp 1.1`. `supabase_vault` e principal candidato a indisponibilidade da imagem comunitaria, nao causa provada, e root key do Vault NAO esta no dump. Nao copiar/migrar chaves de projeto implicitamente.

**Entrega em andamento:** `scripts/operations/g5_extension_compatibility_readonly.py` inventaria apenas nomes de EXTENSION na stream criptografada (GPG→pg_restore --list) e compara dinamicamente com `.control` em imagem PostgreSQL 17 local pinada por SHA, usando apenas contêiner de metadados sem rede, UID sem privilegio e sem DSN/backup/SQL de usuario montados. Nenhuma restauracao, nenhum bypass de extensão, nenhum pull automatico de imagem. Candidata selfhost Supabase documentada `supabase/postgres:17.6.1.136` ainda requer download/autorizacao/checagem de digest e novo preflight separado; NAO executa restore automaticamente.

**Proximos gates:** evidenciar extensoes presentes no proprio arquivo vs imagem, testar compatibilidade real numa sandbox Supabase apropriada com autorizacao especifica, copiar arquivo cifrado + manifesto para storage externo privado e verificar hash, preservar chave Vault sob politica separada, mapear consumidores n8n 9 bindings, Shadow e Vercel, paridade, ports multicliente e cutover humano. `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. Ver `docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md` e issue #155.

---

# 28/10/2026 — G5 REAL RESTORE ISOLADO FALHOU; CAUSA AINDA NAO IDENTIFICADA

**Operador VPS executou o primeiro ensaio real autorizado** do arquivo criptografado SOURCE `nywxpvzhlpqjtcafpdfe` em PostgreSQL 17 isolado, após `--plan` PASS e confirmacao local. Retornou `G5_REHEARSAL_RESULT=BLOCKED`, `G5_REHEARSAL_ERROR=ISOLATED_RESTORE_SQL_FAILED`, `G5_RESTORE_TEST=NOT_VERIFIED`. O original descartava stderr do pg_restore: NAO e comprovado se faltou extensao, role, privilegio ou outro requisito. Nao afirmar restore nem aposentar SOURCE. Como a excecao foi devolvida apos `cleanup_container`, a remocao do container foi confirmada pelo script; caso contrario seria `ISOLATED_CLEANUP_UNVERIFIED`. Nenhum Supabase foi alterado. Backup cifrado original SHA PASS, senha/GPG PASS, TOC 811 entradas PASS.

**Correcao em andamento:** `scripts/operations/g5_restore_isolated_rehearsal.py` deve drenar stderr do pg_restore SOMENTE em memoria e expor apenas uma categoria sanitizada fixa (extensao, role, dependencia, permissao, conflito, recurso etc.). Mantem `G5_RESTORE_TEST=NOT_VERIFIED` e erro bloqueado; **nunca imprimir SQL, objeto, DSN, erro bruto, senha ou dados**. Ensaiar nos testes offline e CI antes de qualquer nova tentativa. Um ensaio diagnostico posterior continua em container isolado com confirmacao typed; nunca autorizar importar no DEMO/SOURCE, desativar n8n, alterar roles/DSN ou pular objetos para tornar testes verdes.

**Permanecem pendentes:** restauração integral real aprovada, cópia cifrada fora da VPS comprovada e custódia, inventario das dependencias SOURCE (n8n oficial com 9 bindings, Shadow persistence, Vercel), portabilidade, hardcodes n8n, paridade e cutover humano. `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. Evidencias e limites em `docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md`, issue #155.

---

# 28/10/2026 — G5: BACKUP REAL LEGIVEL, RESTAURACAO ISOLADA AINDA NAO EXECUTADA

**Ultima evidencia operador VPS:** `G5_ARCHIVE_DECRYPTION=PASS`, `G5_PG_RESTORE_TOC=PASS`, `G5_PG_RESTORE_TOC_ENTRIES=811`, `G5_DECRYPTED_ARCHIVE_BYTES=25905751`, `G5_RESTORE_TEST=NOT_PERFORMED` no arquivo criptografado SOURCE `nywxpvzhlpqjtcafpdfe` capturado e SHA-256 PASS. O teste confirmou a senha e leitura integral do catalogo, mas **NENHUMA SQL do arquivo foi restaurada em qualquer PostgreSQL**. PR #188 mergeada no GitHub, SHA `4f189574a92816d9693a4a3c4557eb0a60beb643`.

**Proxima entrega em codigo (sem executar restauracao):** `scripts/operations/g5_restore_isolated_rehearsal.py` usa Docker PostgreSQL 17 ja em cache, sem rede/portas, sem bind/volumes de host, rootfs read-only, tmpfs, menor privilegio e limite de recursos. `--plan` verifica apenas readiness. `--restore` exige **nova autorizacao explicita do operador** e confirmacao tipada, senha offline e destrucao verificada do container; falhar em qualquer extensao/grant/DDL interrompe e NUNCA declara restauro concluido. Ver `docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md`. O script nunca aponta para SOURCE/DEMO ou executa SQL financeira real fora da sandbox.

**Persistem como bloqueios:** copia segura do arquivo cifrado fora da VPS ainda nao atestada, recuperacao logica integral/roles/Auth/Storage/Edge ainda nao homologada, 9 referencias SOURCE no n8n oficial, Shadow LangGraph DSN SOURCE, Vercel databases nao atestados, tenant real sem membership e cutover/hardcodes ainda nao certificados. **Nao** realizar restore, mudanca n8n/Supabase/DSN/roles, SQL financeira em Shadow, cutover ou remocao SOURCE implicitamente. `OFFICIAL=n8n`, `SHADOW=LangGraph` e `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.

---

# 28/10/2026 — G5 SOURCE BACKUP CRIPTOGRAFADO REAL CAPTURADO, RESTORE AINDA NAO VERIFICADO

**Evidencia VPS confirmada pelo operador:** G5 exportou PostgreSQL SOURCE `nywxpvzhlpqjtcafpdfe` com autorizacao read-only, `G5_ARCHIVE_RESULT=ENCRYPTED_CAPTURED`, `G5_ARCHIVE_INTEGRITY=ENCRYPTED_DIGEST_PASS`; manifesto em caminho root-only `/root/.local/share/agente-sql-langgraph/source-archives/source-nywxpvzhlpqjtcafpdfe-20261028T145054Z-1557baa82308af9b.dump.gpg.manifest.json`. **NAO declarar recuperacao provada:** `G5_ARCHIVE_RESTORE=NOT_VERIFIED`; senha armazenada pelo operador fora do chat. Nunca copiar arquivo cifrado para GitHub.

**Nova entrega proposta:** fluxo offline de inspecao com senha (decriptacao GPG em pipe anonimo e `pg_restore --list` somente em stdin, sem banco, gravacao de plaintext, DSN ou log de nomes). Objetivo e atestar senha de recuperacao e legibilidade do TOC; NAO equivale a restauracao integral. A prova de restore isolado precisa de autorizacao propria. Preservar copia cifrada fora da VPS, SHA-256, manifesto e senha sob custodia separada.

**Bloqueios SOURCE ainda reais:** nove referencias PostgreSQL legadas no n8n oficial, persistencia Shadow LangGraph apontando SOURCE, Vercel DATABASE_URL dos dois Produtos ainda sem destino confirmado, identidade tenant/membership real indisponivel, hardcodes legados nao externalizados, paridade financeira/cutover nao atestados. NAO alterar n8n, DEMO, SOURCE, roles, credenciais, DSNs, Vercel, producao ou SQL financeira em Shadow por causa do backup. `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. Ver docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md e issue #155.

---

# 28/10/2026 — G5: PRIMEIRA CAPTURA AUTORIZADA FALHOU, SOURCE AINDA ATIVA

Operador autorizou exportacao SOMENTE LEITURA de SOURCE `nywxpvzhlpqjtcafpdfe` para backup privado com senha. Na VPS, `--capture` retornou `G5_ARCHIVE_RESULT=BLOCKED`, `G5_ARCHIVE_ERROR=ENCRYPTED_DUMP_FAILED`, `G5_ARCHIVE_RESTORE=NOT_VERIFIED`; nenhum backup completo foi comprovado. O stderr estava descartado e o codigo antigo misturava falha pg_dump e GPG, portanto a causa real NAO e conhecida. A sessao SSH encerrou depois do erro; nao afirmar que banco caiu. Consulta independente de metadados confirmou PostgreSQL SOURCE 17.6 respondendo.

**Proxima acao atual:** homologar correcao G5 que classifica stderr apenas em codigos sanitizados e verifica digest criptografado dentro de `--capture`. Apos PR/CI/merge humano, repetir uma captura de forma simples (sem pipe/tee/subshell), informar senha e DSN somente na VPS, nunca no chat. Essa exportacao esta AUTORIZADA; qualquer restore/import DEMO, mudanca de DSN/n8n/roles, cutover e exclusao SOURCE NAO esta. Prova de restauracao isolada e custodia externa do arquivo/senha permanecem obrigatorias. `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` nao muda.

---

# 28/10/2026 — G5 PREPARACAO DO ARQUIVO E IDENTIDADE (PR #185, SEM MERGE)

**Operador confirmou na VPS:** workflow oficial armazenado 68 nos, uma credencial SOURCE em 9 referencias e uma DEMO em 2; os 2 bindings G1 sao DEMO. Shadow n8n 7 nos sem credenciais Postgres diretas; LangGraph ainda grava evidencias SOURCE e le contexto DEMO. SQL real Shadow desativada. Dois Produtos Vercel DATABASE_URL continuam sem destino atestado. O banco SOURCE nao pode ser apagado.

**Entrega proposta:** [PR #185](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/pull/185) cria ferramenta de arquivo **criptografado e read-only** com captura interativa especificamente autorizada (nenhuma captura realizada), testes de recibo SHA-256 e gate de login Shadow que requer organizacao UUID ativa + membership ativa do Produto. DEMO tem zero organizacoes/memberships: P3 continua bloqueado ate autorizacao/cadastro real.

**NUNCA** confundir backup logico com restauro provado, nem autorizar restore no DEMO. Nao executar SQL financeira, alterar n8n, DSNs, banco, roles ou Vercel sem aprovacao independente; nao ativar cutover nem apagar SOURCE implicitamente. Manter OFFICIAL=n8n, SHADOW=LangGraph e LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. O merge desta PR nao autoriza executar --capture.

---

# ATUALIZACAO OPERACIONAL 28/10/2026 — G5 APOSENTADORIA DO SUPABASE ANTIGO (PR #183)

**Decisao mais recente do operador:** objetivo imediato e consolidar a operacao
do Agente Financeiro, preservar o historico necessario e poder eliminar a
origem Supabase `nywxpvzhlpqjtcafpdfe`. Manter destino DEMO
`cenhadslwxgykqtuobgc`. O projeto nao esta pronto para exclusao.
**Nao confundir a migracao P3 de 200 evidencias com a consolidacao do banco.**

Auditoria 28/10: 200/200 evidencias Shadow com checksum identico, mas existem
47 tabelas public na origem vs 10 no DEMO, 238 vs 42 runs Produto, 10 vs 1
usuario, e contextos diferentes (11 versoes legadas em public vs 10 versoes
DEMO em semantic_context). Nao misturar conhecimentos, benchmarks, SQL ou
DRE de clientes diferentes. Dois Produtos Vercel Production READY possuem
DATABASE_URL protegido cujo destino real nao foi certificado. O n8n oficial
usa credenciais proprias e o ultimo PUT publicado teve drift nao reconciliado.
Shadow tem DSNs separados para persistencia e contexto.

**Entrega ativa:** PR [#183](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/pull/183)
unifica inventario, verificacao offline e auditoria local da VPS/n8n sem
exibir segredos. A auditoria viva so conta depois de executada na VPS:
nao substituir evidencia por CI verde. Procedimento e bloqueios:
[docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md](docs/operations/SUPABASE-SOURCE-RETIREMENT-GATE.md).

**Proibido por efeito desta etapa:** deletar/desativar qualquer Supabase,
executar SQL financeira, modificar n8n, Vercel, DSN, credenciais, roles,
deploy, cutover ou ativar flags. Offical continua n8n+Gemini, Shadow continua
n8n+LangGraph+Gemini, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.
Merge e delete de banco permanecem gates humanos independentes.

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

# STATUS EXECUTIVO / PRIORIDADE IMEDIATA — 26/10/2026

**Única entrega ativa: P1 = prova real de geração no caminho n8n candidato → LangGraph → Gemini, sem execução SQL financeira.** O passo seguinte é P2 (correlação Produto autenticado); a execução financeira read-only/role G1 é P3. [Plano operacional e regra anti-desvio](docs/operations/DELIVERY-FOCUS.md); [roadmap #155](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/issues/155).

**Fatos confirmados:** GitHub `main@e7ccff858506097e02c3e5d89ecb0016a9180664`, PR #172 mergeada; auditoria real na VPS sob `HEAD=e7ccff8`: `G1_PUBLIC_TEMPORARY=TRUE`, `G1_PUBLIC_CREATE=FALSE`, `G1_TARGET_ROLE_EXISTS=FALSE`, `G1_AUDIT_RESULT=REVIEW_REQUIRED`; nenhum banco alterado pela auditoria. Produto Demo Vercel último deployment Production consultado em `READY` no commit `7d784ec14568599049f039532805905036c52705` (PR #31). **Não foi feita nova verificação n8n/LangGraph vivo nesta atualização**; a condição publicada/healthy permanece último relato, a confirmar antes do teste.

**O que ainda NÃO foi provado:** geração real com Gemini via n8n candidato e LangGraph; execução completa Produto→n8n→LangGraph com `agent_run_id/run_id/shadow_record_id`; paridade financeira ou multicliente real. `G1_CORRELATED_EXECUTION=NOT_TESTED`. Shadow Production segue desabilitado segundo último diagnóstico autenticado; nenhuma nova leitura autenticada do valor da flag nesta atualização.

**Decisão de foco:** não usar `/api/generate-sql` da Demo para o teste P1, pois o fluxo oficial gera **e pode executar** SQL. O problema de `PUBLIC TEMPORARY` não será ignorado nem resolvido por revogação global sem aprovação: é bloqueador para rollout read-only e execução P3, **não para P1 em modo generate-only isolado**. Antes de P1 com Gemini real, confirmar ambiente e obter autorização de custo/chamada; `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` permanece obrigatório. Não realizar benchmark 63, SQL financeira, deploy, migração ou alteração de permissões por efeito deste documento.

**Próximo bloco:** pré-verificar candidato n8n e runtime LangGraph TEST, confirmar rota de geração isolada e evidência, e executar **uma** pergunta inédita via Gemini quando autorizada; registrar o erro real encontrado e corrigi-lo até obter SQL validada e evidência correlacionada. Arquivos/ensaios offline não fecham P1/G1.

> As seções datadas abaixo são **histórico**, não substituem esta prioridade. Não reabrir etapas concluídas sem evidência nova.

---

## Gate G1 — preflight real no Supabase DEMO: PUBLIC TEMPORARY bloqueia criação (25/10/2026)

- **Evidência real fornecida pelo operador** em `main@76b9e70`: VPS PostgreSQL com `psycopg[binary]==3.3.4` e CA oficial Supabase Root 2021 válida; `--dry-run` (sem escrita) passou `G1_ROLE=NOT_APPLIED`, `G1_N8N_BINDINGS=PREFLIGHT:0eee554daf77`, `G1_ROLLBACK=READY`.
- Auditoria SQL catalogal **read-only** do projeto financeiro confirmou `G1_PUBLIC_TEMPORARY=TRUE`, `G1_PUBLIC_DATABASE_CREATE=FALSE`, `G1_PUBLIC_ACL_CHECK=PASS`. Qualquer nova role herdará `TEMPORARY` por `PUBLIC`. `NOINHERIT` ou `REVOKE ... FROM` apenas da role não resolve.
- **Correção candidata desta PR:** `--dry-run`/ `--apply` verificam ACL efetiva `PUBLIC` no database antes de `CREATE ROLE`; falham fechado caso `TEMPORARY` ou `CREATE` esteja ativo. Testes offline simulam ACLs, bloqueio de criação, inexistência de POST n8n e fluxo positivo preservado.
- **Não autorizado:** `REVOKE TEMPORARY ON DATABASE postgres FROM PUBLIC` ou qualquer alteração global de grants, permissões n8n ou migração. Depende de inventário de impacto, plano de rollback e decisão explícita. Nenhuma alteração de banco/n8n/Shadow executada por esta PR. `OFFICIAL=n8n`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`, `G1_CORRELATED_EXECUTION=NOT_TESTED`.
- **Evidência e detalhes:** `docs/runbooks/g1-readonly-single-step-operator.md`; acompanhamento operacional [#155](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/issues/155). Não confundir PASS de TLS/preflight antigo com homologação G1.

---

## Gate G2 — inventário integral de encaminhamento (2026-10-23, snapshot do operador)

- Inventário sanitizado de **68 nós** do JSON fornecido pelo operador em 20/10: `docs/audits/n8n-official-68-node-externalization-ledger.md`.
- Grafo estático do arquivo: **60 nós alcançáveis**, **8 inalcançáveis**; os oito não comprovam comportamento ativo. Triagem por responsabilidade com candidatos FORBIDDEN, TRANSITIONAL e STRUCTURAL; não é auditoria de cada expressão nem reconciliação com `--published`.
- Principal direção: externalizar métricas, aliases, filtros, schema, prompt, planos e relatórios em contexto versionado; **não** transportar os hardcodes do cleaner para LangGraph. Cache/credenciais/tenant e pré-aprovação exigem gates próprios.
- **Candidata nesta branch:** o adapter PostgreSQL agora aceita mapeamento configurável de nomes das tabelas semânticas e DRE opcional via `CONTEXT_CATALOG_TABLES_JSON`, preservando o default antigo. Testes offline exercitam dois contextos físicos distintos e validação contra injeções. **Ainda não há implantação nem comprovação de paridade multicliente em bancos reais.** Enforcements de RBAC/tenant não foram implementados neste loader; continuam pendentes.
- Workflow oficial e versões/credenciais runtime não foram alterados por este inventário. G1/G2 e paridade financeira continuam pendentes.

---

## Gate G1 — evidência operacional observada em 2026-10-21 (UTC)

- Na VPS, o operador confirmou n8n **2.4.8**, um contêiner detectado,
  CLI `n8n import:workflow` disponível e
  `LANGGRAPH_SHADOW_INTERNAL_BASE_URL` **ausente** no ambiente do n8n.
  O teste foi read-only; não identifica importação ou ativação do candidato.
- Último Shadow TEST operacionalmente validado pelo operador: imagem e
  runtime `136da3419a18ec79bf67b5d42fcb7b3acdce16ba`,
  `SEMANTIC_AGENT_VERSION=demo-finance-v9`, Gemini configurado,
  execução SQL real desativada e conectividade n8n→Shadow confirmada.
  A inspeção local posterior mostrou checkout VPS também nesse commit.
- O GitHub `main` avançou para `d4f6718e0cb333fdadc0dfa94060cb629cc4fbe8`
  pela PR #143 (transporte opcional de `llm_selection`). **Esse commit
  não foi confirmado como implantado na VPS**; apenas o candidato n8n
  versionado mudou. Não há motivo para trocar o runtime sem evidência.
- A Demo `demo/grupo-horizonte` recebeu a PR #17 no commit
  `687447c8314d6706d9853fc595a262316afeb3ca`, com deploy Vercel
  READY. As variáveis `LANGGRAPH_SHADOW_TRANSPORT`,
  `LANGGRAPH_SHADOW_N8N_WEBHOOK_URL` e
  `N8N_SHADOW_WEBHOOK_TOKEN` ainda não constavam no inventário de
  configuração da Demo; nenhuma ativação foi comprovada.
- Gate G1 continua **pendente**: workflow paralelo de sete nós não
  comprovadamente importado/ativo, sem correlação real Produto→n8n→
  LangGraph e sem prova de paridade financeira. n8n + Gemini **oficial**
  permanece intocado.
- Para n8n 2.x, o template candidato usa `$env` nas URLs internas, cuja
  disponibilidade pode estar bloqueada por padrão. O renderizador
  `scripts/n8n/render_parallel_shadow_workflow.py` prepara um arquivo
  privado/inativo com destino interno autorizado **sem alterar a proteção
  global de ambiente n8n**. A preparação é offline e não autoriza a
  importação, credenciais, ativação ou qualquer chamada paga.
- Importação/publicação do workflow, credenciais, configuração Vercel,
  uso real de LLM e execução SQL read-only continuam exigindo suas
  autorizações separadas. Não considerar G1/G2/G3 concluídos pelo CI.

---

## Rastreabilidade de provedor/modelo na comparação Shadow — candidato

A nova comparação expõe apenas identificadores sanitizados de
`sql_generation_result` (e reparo quando presente), retirados da
evidência persistida/fingerprint-validada. O Produto pode confrontar
esses identificadores com `llm_provider` e `llm_model` do run
oficial, sem passar resultado oficial ao gerador, criar aliases
hardcoded ou gastar LLM. Isso **não** prova Gemini paritário quando
a configuração do runtime não foi verificada. Integração real G1/G3
permanece pendente; `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.

---

## Comparador pós-geração proposto — 2026-10-20

Implementação candidada: `POST /v1/internal/sql-agent/compare-shadow-sql`,
atrás da autenticação interna S2S atual. Compara SQL **oficial já gerada**
com a SQL LangGraph previamente persistida, usando o mesmo `agent_run_id`,
`shadow_record_id`, pergunta e identidade de principal/tenant autorizados.
Diferenças estruturais de tabelas, joins, filtros, projeções,
agregações e ordenação são reportadas sem retornar a SQL, nomes
físicos ou literais. A comparação não chama gerador, LLM nem executor.
`normalized_sql_match` **não** significa paridade financeira.
A falta de tenant identificado impede alegar isolamento completo.
Integração no Produto e paridade financeira seguem pendentes.

---

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
indexa 75 nós e documenta **13** nós com hardcodes FORBIDDEN
comprovados no legado: classificação/aliases, prompt SQL, planner, gates
semânticos de DRE, schema e filtros fixos, e relatórios financeiros. O
script `scripts/audit_n8n_workflow_export_readonly.py` permite comparar
exportações locais sem reproduzir SQL, prompts ou credenciais. A revisão
estendida confirmou sete outros nós hardcoded no mesmo snapshot histórico,
incluindo reescrita automática de SQL no cleaner, tabelas fixas em gate e
inferência duplicada de métricas/dimensões. O comparador agora acompanha
deriva de topologia e configuração runtime além dos parâmetros. Nenhum dado
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
| G2 — inventário n8n + eliminação FORBIDDEN + 2 contextos | **Parcial:** 75 nós de exportação histórica indexados; 13 FORBIDDEN comprovados no arquivo; VPS ativa e 2 contextos pendentes |
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

## Gate G1 — prepared read-only binding verification (2026-10-21)

- Operator reported the three n8n credentials configured on the newly imported
  seven-node candidate `LwUsMRWi34D2ARWu1YzgV`. Browser read confirms
  seven node labels and a **Publish** button, not credential attachment or
  successful authentication. The 68-node official workflow was not changed.
- Added a fail-closed draft-export binding audit for the exact candidate ID.
  It checks inactive state, node/code/topology drift, two distinct credential
  boundaries and private Docker endpoint without printing credential IDs,
  names, secrets or node code. Synthetic offline negative tests cover
  missing/misbound credentials and unsafe changes.
- **Operational evidence pending:** the audit has not run on the VPS;
  n8n credential *values* and S2S authorization are not validated. No
  workflow publication, HTTP 202, persisted correlation, real SQL, LLM call,
  numeric parity or cutover is implied by this code change.
