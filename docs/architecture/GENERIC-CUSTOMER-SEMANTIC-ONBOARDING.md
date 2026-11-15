# Onboarding de semântica financeira para clientes independentes

**Contrato:** onboarding de contexto canônico, segregado por tenant, versionado e aprovado. **Estado:** implementado em código e testado offline; nenhuma ativação, importação de dados, DDL, credencial, SQL financeira real ou cutover. Decisão do operador de 11/11/2026: migrar a inteligência real n8n + banco para LangGraph mantendo n8n como orquestrador, sem negócios hardcoded.

## Separação obrigatória entre processo e conhecimento

A mesma aplicação deve funcionar com empresas cujos dados usam tabelas, colunas, granularidades, métricas, DRE e convenções **completamente diferentes**. O motor conhece somente descoberta controlada, contrato de contexto, interpretação, planejamento dinâmico, SQL, validação, reparo e aprovações. **Não conhece DRE, receita, marcas, contas ou qualquer nome de cliente no código.** Os valores específicos devem estar no catálogo versionado, revisado e aprovado do tenant.

O cliente fornece acesso de **menor privilégio e preferencialmente somente leitura** ao banco/metadata, esquemas/dialetos suportados e responsáveis por definições financeiras. Pode ser necessário um adaptador do dialeto e uma transformação de fonte para o contrato canônico; a ausência de DRE é uma condição válida. Significado contábil desconhecido permanece desconhecido e bloqueia consultas dependentes dele.

## Nova cadeia de configuração (código efetivamente implementado)

1. **Descoberta física PostgreSQL:** \`app/adapters/postgres/physical_catalog_reader.py\` recebe DSN fornecida por mecanismo seguro, lista explícita de schemas permitidos e consulta *somente* \`information_schema.columns\`, em transação \`READ ONLY\`. É proibido fornecer schemas com base no texto de uma pergunta. Não examina registros financeiros; outro dialeto usa outro adaptador aprovado.
2. **Validação física da proposta de contexto:** \`app/domain/tenant_semantic_readiness.py\` recebe o snapshot proposto, a identidade/versão externa do tenant e as colunas de descoberta autorizada. Compara tabelas, chaves, métricas e datas declaradas com o esquema físico. Respostas inválidas bloqueiam o onboarding sem retornar dados nem nomes sensíveis. Um resultado positivo é **PHYSICALLY_CONSISTENT_REQUIRES_BUSINESS_APPROVAL**, não autorização de geração.
3. **Aprovação independente:** o responsável do cliente confirma definição das métricas, significado contábil, fórmulas, sinais, relacionamentos, cardinalidade, granularidade, períodos, moedas, fontes e filtros; políticas do Produto confirmam permissões do tenant. Toda evidência conserva hashes, versão e responsável. A etapa de publicação/assinatura de contexto **não está automatizada por esta PR**.
4. **Contexto canônico aprovado:** em repositório de metadados com controle de acesso, persistir um snapshot JSONB do contrato físico esperado por \`normalize_context_snapshot\` — com \`tenant_id\`, \`semantic_agent_version\`, \`source_approval_status=APPROVED\`, \`historical_evaluation_sql_excluded=true\`, contexto completo e fingerprint aprovado. São metadados de negócio versionados, não SQL pronta.
5. **Leitura pelo mesmo LangGraph:** \`app/adapters/postgres/canonical_context_repository.py\` seleciona pelo par **tenant/versão**, exige \`is_active=true\`, \`is_approved=true\`, exatamente um resultado, correspondência com o tenant e versão dentro do JSON, declaração de segregação do benchmark, fingerprint e validador de contexto. Falha fechada em qualquer incongruência. \`app/bootstrap.py\` escolhe o leitor em configuração, sem alterar o grafo, o provider ou o planejador.
6. **Operação:** n8n mantém webhooks, conectores, cache, histórico e ações determinísticas; LangGraph recebe semântica aprovada para perguntas **inéditas**. Generate, Repair e Execute Approved separados; reparar invalida aprovação. No Shadow, não executar SQL financeira real. As 63 perguntas históricas entram somente **depois** na comparação independente de qualidade n8n+Gemini e n8n+LangGraph+Gemini.

## Configuração do modo novo (somente exemplo de chaves, sem valores reais)

| Variável de configuração de deployment por tenant | Regra |
|---|---|
| \`POSTGRES_CONTEXT_SOURCE_MODE=canonical_snapshot\` | Habilita adapter novo; default continua \`legacy_tables\` (sem comportamento alterado) |
| \`POSTGRES_DSN\` | DSN do catálogo canônico, **nunca em log, GitHub ou payload HTTP** |
| \`POSTGRES_CONTEXT_SCHEMA\` | Schema privado dos metadados aprovados |
| \`POSTGRES_CANONICAL_CONTEXT_TABLE\` | Tabela do catálogo canônico, nome de identificador validado |
| \`CONTEXT_TENANT_ID\` | Escopo escolhido pela configuração autenticada; **nunca derivado da pergunta** |
| \`SEMANTIC_AGENT_VERSION\` | Versão aprovada e explícita da semântica |
| \`SEMANTIC_CONTEXT_EXPECTED_FINGERPRINT\` | SHA-256 canônico aprovado exigido no novo modo |

O contrato da relação de metadados pressupõe colunas estruturais \`tenant_id\` (text), \`semantic_agent_version\` (text), \`is_active\` (boolean), \`is_approved\` (boolean), \`snapshot_payload\` (JSONB). Qualquer criação de tabela/migração é **operação separada sujeita a aprovação**; esta PR não cria nem altera tabelas. Restringir acesso por identidade de tenant, privilégios de leitura e RLS quando exposto ao Data API; o filtro SQL por tenant é defesa adicional, não substitui autenticação/autorização. Nenhuma role de banco deve ter acesso aos 63 casos de benchmark.

**Importante:** o adapter é vinculado a um tenant em seu *composition root*; uma instância única de grafo compartilhada entre múltiplas organizações requer *routing* seguro e isolado antes de uso real. O código atual **não** comprova por si só esse roteamento por request nem homologação de segurança RLS.

## Evidência de testes (não substitui integração real)

| Suite | Evidência |
|---|---|
| \`testar_physical_catalog_reader.py\` | 4 testes: schemas/colunas distintos, transação somente leitura, recusa de schemas inválidos e pipeline prévio |
| \`testar_tenant_semantic_readiness.py\` | 6 testes: dois contextos materialmente distintos, coluna ou tabela ausente, metadados falsos, ausência de DRE |
| \`testar_canonical_context_repository.py\` | 8 testes: tenant/version/fingerprint pin, aprovação e benchmark excluído, bootstrap config |
| \`testar_postgres_context_runtime_config.py\` | 9 testes legados sem regressão |
| \`testar_postgres_context_repository.py\` | 11 testes legados sem regressão |
| \`testar_postgres_context_graph_bootstrap.py\` | 21 testes de integração de composição sem conexão real |

Executados em contêiner temporário **sem rede**, usando imagem instalada que contém LangGraph, com permissões não-root para processos de teste. O container temporário foi removido. Nenhuma conexão financeira ou consulta a dados de cliente foi feita. Testes de integração real com dados de dois clientes e prova de equivalência financeira seguem pendentes.

## Fronteira do contexto gerador — proteção adicional em código

O loader canônico (não o reader legado) verifica agora, antes da normalização, os padrões reais presentes no snapshot. Padrões de intenção devem declarar source_use=APPROVED_SEMANTIC_STRUCTURAL, com sql_pattern vazio, business_question_examples vazio e sem notes livres. Ele **não confia apenas** no booleano historical_evaluation_sql_excluded. Isso impede a rota histórica do n8n — padrões SQL serializados no contexto e passados ao prompt — de ser reproduzida acidentalmente. Os exemplos de perguntas podem ser sinais semânticos **somente quando houver cadeia de proveniência independente**; por segurança, o modo canônico atual os bloqueia, enquanto aliases aprovados continuam disponíveis. Essa restrição não altera o loader legado e não substitui aprovação externa, assinatura/controle de origem ou inspeção contábil dos outros campos.

## Lacunas antes de dizer que o produto está pronto

- **Engenharia reversa completa do comportamento:** analisar conteúdo financeiro das 11 versões G5 cifradas, cruzar todas as regras de negócio do n8n antigo com semântica real e implementar funções faltantes no motor dinâmico. Não criar regras a partir de golden answers.
- **Publicação governada:** criar processo de aprovação, assinatura e persistência do pacote canônico por tenant, com versão e rollback. Nunca importar automaticamente backups históricos.
- **Enrutamento seguro:** vincular request autenticada do Produto ao repository/DSN/version corretos e provar RLS/ACL de tenant no banco de metadados e no executor.
- **Portabilidade real:** testar dois clientes **reais** com esquemas/dialetos e semânticas materialmente distintos, não só mocks. Para fontes não PostgreSQL, implementar adaptador de introspecção/dialeto; o motor LangGraph permanece o mesmo.
- **Paridade Shadow:** correlação n8n+Gemini vs n8n+LangGraph+Gemini, aprovação, repair, preflight, resultados, 63 perguntas somente QC posterior; SQL numérica read-only exige autorização separada.
- **Cutover humano e reversível:** oficial n8n continua intacto; não migrar/executar/ativar sem avaliação e autorização.

**Conclusão honesta:** esta entrega cria **um caminho real de configuração genérica e isolada** até o bootstrap LangGraph, mas **não declara o Agente Financeiro totalmente migrado ou pronto para produção**.
