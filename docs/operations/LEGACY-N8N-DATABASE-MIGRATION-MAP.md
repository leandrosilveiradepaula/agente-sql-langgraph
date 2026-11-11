# Engenharia reversa da migração: n8n legado + base → n8n + LangGraph

**Status:** contrato de execução / inventário integral **AINDA NÃO CONCLUÍDO**. Decisão do operador em 2026-11-11. Repositório: `leandrosilveiradepaula/agente-sql-langgraph`.

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