# Inventario funcional integral do n8n publicado - Bloco 1

> Revisao estatica de todos os nos e todas as rotas por porta.
> Nao representa homologacao contabil, paridade financeira ou autorizacao de cutover.

## Proveniencia e verificacao

- Workflow publicado e ativo: versao atual e publicada coincidem.
- Identidades, parametros, corpos de Code, queries e 78 conexoes: MATCH contra o crosswalk privado anterior.
- Hash do export bruto: 01f2d383bc184fab9da0be96e11df74b9258e30b1428bb3547524f1911f8b11c
- Hash do export anterior: 19dd24c29d81c61b12dc383f2124ca2e7ba77625776ee161f3be1996d2f09c68
- O hash bruto mudou; os 68 corpos/parametros e as 78 arestas conferem. Nao tratar metadados do export como equivalencia de respostas.
- Nos: 68/68; conexoes dirigidas: 78/78; tipos: {'code': 41, 'httpRequest': 2, 'if': 10, 'postgres': 11, 'respondToWebhook': 3, 'webhook': 1}
- Alcancaveis pelo webhook: 60; fora da rota do webhook: 8.
- Metodo: export publicado privado e auditoria read-only; apenas hashes, sinais tecnicos e topologia sao publicos.
- A coluna Responsabilidade veio da matriz funcional previamente inspecionada e foi reconfirmada contra a mesma configuracao e codigo publicado; nao atribui sucesso em runtime.

## Matriz completa dos 68 nos

Classes: S = STRUCTURAL; T = TRANSITIONAL (equivalencia ainda pendente); F = FORBIDDEN de portar como literal de negocio (codigo legado pode permanecer ate cutover).
Os 10 casos F sao **pontos de hardcode identificados**, nao 10 itens que representem todos os literais do legado.

| No | Tipo | Responsabilidade do legado | Entrada | Saida por porta | Efeito | Classe | Prova SHA-12 |
|---:|---|---|---|---|---|:---:|---|
| 1 | webhook | Webhook da pergunta | - | 0:52 | WEBHOOK_ENTRY | S | 3a7ae75c04d6 |
| 2 | code | Validação da pergunta, identidade operacional e run IDs | 27 | 0:5,1:3 | CODE_TRANSFORM | S | ea4ad1f60747 |
| 3 | code | Formato de erro da pergunta | 2 | 0:4 | CODE_TRANSFORM | S | ef88e7fb0167 |
| 4 | respondToWebhook | Resposta HTTP de erro | 3 | - | WEBHOOK_RESPONSE | S | 976f0859a9a6 |
| 5 | postgres | Consulta dos cinco catálogos DuckLake | 2 | 0:6 | SEMANTIC_CATALOG_READ | F | 18a85778ece7 |
| 6 | code | Classificação de intenção por regras e aliases | 5 | 0:54 | CODE_TRANSFORM | F | 90d259d64c2a |
| 7 | code | Consolidação de regras/entidades/DRE | 39,40,50 | 0:24 | CODE_TRANSFORM | F | 61499bc96810 |
| 8 | code | Construção de prompt e plano SQL | 23 | 0:9 | CODE_TRANSFORM | F | 6b1b96ed439c |
| 9 | code | Preparação da chamada Gemini | 8 | 0:10 | CODE_TRANSFORM | T | 5a5ce1e26d2e |
| 10 | httpRequest | Chamada externa de geração Gemini | 9 | 0:11 | GEMINI_REQUEST | T | f90455e389bc |
| 11 | code | Limpeza e normalização da SQL | 10,59 | 0:12,1:13 | CODE_TRANSFORM | T | 71b3e25f1196 |
| 12 | code | Validação física e semântica da SQL | 11,38 | 0:25,1:55 | CODE_TRANSFORM | T | c1429e201b87 |
| 13 | code | Preparação de erros de geração | 11,56 | 0:14 | CODE_TRANSFORM | T | 6b94b3008899 |
| 14 | respondToWebhook | Resposta HTTP de erro SQL | 13,31,65 | - | WEBHOOK_RESPONSE | S | 976f0859a9a6 |
| 15 | code | Preparação de entrega da consulta | - | 0:19 | CODE_TRANSFORM | F | 328116f02655 |
| 16 | respondToWebhook | Resposta HTTP final | 32,53 | - | WEBHOOK_RESPONSE | S | 976f0859a9a6 |
| 17 | code | Formatação de SQL de auditoria legado | 19 | 0:18 | CODE_TRANSFORM | T | 6b449f2b82e0 |
| 18 | postgres | Persistência de log SQL | 17 | - | AUDIT_LOG_WRITE_DYNAMIC | T | 8bfc77cf8e6f |
| 19 | code | Entrega alternativa Watson | 15 | 0:17,0:20,0:53 | CODE_TRANSFORM | F | 51879dea6154 |
| 20 | code | Montagem da fila de perguntas | 19 | 0:21 | CODE_TRANSFORM | T | 66e5fb0dbba7 |
| 21 | postgres | Persistência da fila de perguntas | 20 | - | QUESTION_QUEUE_WRITE_DYNAMIC | T | 8bfc77cf8e6f |
| 22 | code | Planejamento de consulta com contexto/operadores | 24 | 0:23 | CODE_TRANSFORM | F | 113ce61f0e6c |
| 23 | code | Gate de validação do plano semântico | 22 | 0:8 | CODE_TRANSFORM | F | 6af9ec775f82 |
| 24 | code | Normalização de fonte física e namespace | 7 | 0:22 | CODE_TRANSFORM | T | 15bb13d8f399 |
| 25 | if | Desvio por status de validação SQL | 12 | 0:60,1:48 | TECHNICAL_VALIDATION_SUCCESS | S | b43a07c89269 |
| 26 | code | Roteador gerar versus executar | 64 | 0:27 | CODE_TRANSFORM | S | f6649dbc9282 |
| 27 | if | Desvio pelo modo de execução | 26 | 0:28,1:2 | EXECUTE_MODE | S | 8bf720709640 |
| 28 | code | Validação da SQL recebida | 27 | 0:29 | CODE_TRANSFORM | T | 92a9289c7803 |
| 29 | if | Desvio por status da SQL recebida | 28 | 0:68,1:31 | TECHNICAL_VALIDATION_APPROVED_FLAG | S | 9b12c94e3327 |
| 30 | code | Normalização do resultado PostgreSQL | 67 | 0:32 | CODE_TRANSFORM | T | 6fe5ab77a7ea |
| 31 | code | Erro de SQL recebida | 29 | 0:14 | CODE_TRANSFORM | S | 4ec95f3b6c3d |
| 32 | code | Montagem de relatório executivo | 30 | 0:16 | CODE_TRANSFORM | F | c4bd1c3ef302 |
| 33 | code | Resolver opção de cache SQL | 54 | 0:34 | CODE_TRANSFORM | T | 3ca7924d8dfe |
| 34 | code | Chave cache: contexto, período, versão, fingerprint | 33 | 0:35 | CODE_TRANSFORM | T | b747a38d5f6f |
| 35 | if | Desvio usar cache | 34 | 0:36,1:40 | CACHE_ENABLED | S | 84944f886673 |
| 36 | postgres | Leitura PostgreSQL de cache | 35 | 0:37 | SQL_CACHE_READ | T | 6e06533ab361 |
| 37 | if | Desvio acerto cache | 36 | 0:38,1:39 | CACHE_ROW_EXISTS | S | d096b0403143 |
| 38 | code | Recuperar SQL cacheada | 37 | 0:12 | CODE_TRANSFORM | T | 83f3e91fc97d |
| 39 | code | Metadata de miss cache | 37 | 0:7 | CODE_TRANSFORM | S | bb6c5fa38849 |
| 40 | code | Metadata cache desativado | 35 | 0:7 | CODE_TRANSFORM | S | a39b9f773ab8 |
| 41 | if | Desvio cache hit após preflight | 62 | 0:42,1:44 | PREFLIGHT_CACHE_HIT | S | a07da2ca6127 |
| 42 | postgres | Atualizar hits do cache | 41 | 0:43 | SQL_CACHE_HIT_WRITE | T | 8010761367f1 |
| 43 | code | Metadata hit cache | 42 | 0:68 | CODE_TRANSFORM | S | 83aea392af61 |
| 44 | code | Preparar gravação cache | 41 | 0:45 | CODE_TRANSFORM | T | c63292713489 |
| 45 | if | Desvio de gravação cache | 44 | 0:46,1:68 | CACHE_WRITE_ELIGIBLE | S | 54f6cf09d8c8 |
| 46 | postgres | Gravar cache PostgreSQL | 45 | 0:47 | SQL_CACHE_UPSERT | T | 8f17cb366a87 |
| 47 | code | Metadata cache gravado | 46 | 0:68 | CODE_TRANSFORM | S | 13fa5e8e8a8a |
| 48 | if | Desvio cache inválido | 25 | 0:49,1:55 | CACHE_HIT_INVALIDATION | S | 4c930d90bf20 |
| 49 | postgres | Invalidar cache PostgreSQL | 48 | 0:50 | SQL_CACHE_INVALIDATION | T | e66714f73691 |
| 50 | code | Retorno à IA após cache rejeitado | 49 | 0:7 | CODE_TRANSFORM | S | 49971da8b323 |
| 51 | postgres | DDL manual de tabela cache | - | - | MANUAL_DDL_UNREACHABLE | T | a2d73dfe7422 |
| 52 | code | Criação de run context e correlação | 1 | 0:63 | CODE_TRANSFORM | S | c57fd567b7a4 |
| 53 | code | Registro de tokens/uso de LLM | 19 | 0:16 | CODE_TRANSFORM | T | dcee0948670b |
| 54 | code | Projeção da requisição semântica observada | 6 | 0:33 | CODE_TRANSFORM | F | 95f7145b2125 |
| 55 | code | Avaliar necessidade de reparo | 12,48,62 | 0:56 | CODE_TRANSFORM | T | c17085e68260 |
| 56 | if | Desvio condicional reparo | 55 | 0:57,1:13 | REPAIR_REQUIRED | S | 7e5a9aeaad80 |
| 57 | code | Construção de requisição de reparo | 56 | 0:58 | CODE_TRANSFORM | T | f3383414718b |
| 58 | httpRequest | Chamada Gemini para reparo | 57 | 0:59 | GEMINI_REQUEST | T | f90455e389bc |
| 59 | code | Normalização de SQL reparada | 58 | 0:11 | CODE_TRANSFORM | T | f02b389cee52 |
| 60 | code | Preparação de SQL para preflight | 25 | 0:66 | CODE_TRANSFORM | T | 1dc5a85fd467 |
| 61 | code | Interpretação de resposta de preflight | 66 | 0:62 | CODE_TRANSFORM | T | 87d822dc2d3d |
| 62 | if | Gate após preflight | 61 | 0:41,1:55 | PREFLIGHT_TECHNICAL_SUCCESS | S | 6bb426bf9e2d |
| 63 | postgres | Consulta de configuração DuckLake ativa | 52 | 0:64 | RUNTIME_CONFIG_READ | T | 71da82668406 |
| 64 | code | Aplicação de configuração física/dialeto | 63 | 0:26,1:65 | CODE_TRANSFORM | T | 8d9beca92806 |
| 65 | code | Resposta de erro configuração | 64 | 0:14 | CODE_TRANSFORM | S | 1e1cd39abada |
| 66 | postgres | Execução de preflight PostgreSQL | 60 | 0:61 | PREFLIGHT_DYNAMIC | T | 71e8bcfdd8a2 |
| 67 | postgres | Execução real da SQL no PostgreSQL | 68 | 0:30 | SQL_EXECUTION_DYNAMIC | T | af41a13f73f0 |
| 68 | code | Preparação da chamada de execução real | 29,43,45,47 | 0:67 | CODE_TRANSFORM | T | b31f19b53735 |

## Portas dos IF e natureza do sinal

Porta 0 = verdadeiro, 1 = falso. As expressoes abaixo foram conferidas no export publicado; apenas nomes de campos tecnicos e hashes sao expostos.

| IF | Condicao tecnica (campos lidos) | True:0 | False:1 | SHA-12 condicao |
|---:|---|---|---|---|
| 25 | $json.success | 60 | 48 | a09aa6db394a |
| 27 | $json.modo_execucao_sql | 28 | 2 | 73a1a0000ed7 |
| 29 | $json.aprovado | 68 | 31 | 950b2e26b98c |
| 35 | $json.options?.use_sql_cache | 36 | 40 | db55a4e9c6ee |
| 37 | $json.id | 38 | 39 | 3641e42104fa |
| 41 | $json.cache?.hit | 42 | 44 | 411fffa6e0e9 |
| 45 | $json.cache?.hit, $json.options?.use_sql_cache, $json.validacao_offline?.status, $json.validation_status_cache | 46 | 68 | 29a8f04a9d4e |
| 48 | $json.cache?.hit | 49 | 55 | 37910fb9a1c8 |
| 56 | $json.deve_reparar_sql | 57 | 13 | c020e046f627 |
| 62 | $json.success | 41 | 55 | 27b1fc4b6f9e |

O IF 25 testa sucesso de validacao tecnica do no 12; IF 29 testa aprovacao tecnica do no 28; IF 62 testa resultado de preflight. Nenhum equivale a aprovacao humana.

## Onze pontos de PostgreSQL e seus efeitos

| No | Papel em workflow | Expressao SQL | Verbos visiveis no texto |
|---:|---|---|---|
| 5 | SEMANTIC_CATALOG_READ | LITERAL | SELECT |
| 18 | AUDIT_LOG_WRITE_DYNAMIC | DYNAMIC_EXPRESSION | (comando dinamico/nao visivel) |
| 21 | QUESTION_QUEUE_WRITE_DYNAMIC | DYNAMIC_EXPRESSION | (comando dinamico/nao visivel) |
| 36 | SQL_CACHE_READ | DYNAMIC_EXPRESSION | SELECT |
| 42 | SQL_CACHE_HIT_WRITE | DYNAMIC_EXPRESSION | UPDATE |
| 46 | SQL_CACHE_UPSERT | DYNAMIC_EXPRESSION | INSERT,UPDATE |
| 49 | SQL_CACHE_INVALIDATION | DYNAMIC_EXPRESSION | UPDATE |
| 51 | MANUAL_DDL_UNREACHABLE | LITERAL | CREATE |
| 63 | RUNTIME_CONFIG_READ | LITERAL | SELECT |
| 66 | PREFLIGHT_DYNAMIC | DYNAMIC_EXPRESSION | (comando dinamico/nao visivel) |
| 67 | SQL_EXECUTION_DYNAMIC | DYNAMIC_EXPRESSION | (comando dinamico/nao visivel) |

## Hardcodes identificados: nao migrar valores para Python/TypeScript

| No | Achado funcional localizado | Tratamento |
|---:|---|---|
| 5 | CATALOG_VERSION_FIXED | Externalizar via contexto financeiro versionado e aprovado, sem copiar literal |
| 6 | INTENT_ALIAS_LITERALS | Externalizar via contexto financeiro versionado e aprovado, sem copiar literal |
| 7 | HISTORICAL_PATTERN_TO_PROMPT | Externalizar via contexto financeiro versionado e aprovado, sem copiar literal |
| 8 | INLINE_FINANCIAL_FORMULAS_AND_MODELS | Externalizar via contexto financeiro versionado e aprovado, sem copiar literal |
| 15 | AGENT_VERSION_FIXED | Externalizar via contexto financeiro versionado e aprovado, sem copiar literal |
| 19 | LEGACY_PROVIDER_VERSION | Externalizar via contexto financeiro versionado e aprovado, sem copiar literal |
| 22 | PHYSICAL_TABLE_MAP_AND_METRIC_RULES | Externalizar via contexto financeiro versionado e aprovado, sem copiar literal |
| 23 | METRIC_COMPARISON_DESCRIPTORS | Externalizar via contexto financeiro versionado e aprovado, sem copiar literal |
| 32 | FINANCIAL_REPORT_DESCRIPTORS | Externalizar via contexto financeiro versionado e aprovado, sem copiar literal |
| 54 | METRIC_DIMENSION_LEXICONS | Externalizar via contexto financeiro versionado e aprovado, sem copiar literal |

## Dependencias corretamente separadas

- Os nos fora da rota inicial do webhook sao: 15, 17, 18, 19, 20, 21, 51, 53. Nao exclui-los sem verificar chamada indireta, conexao manual ou efeitos historicos.
- Os nos 10 e 58 fazem POST HTTP ao provider LLM. Nao ha prova de invocacao real nesta auditoria.
- Os nos 66/67 recebem SQL por expressao dinamica. Preflight nao autoriza execucao; SQL reparada exige nova aprovacao no Produto.
- O G5 selado e os 77 registros da versao do no 5 continuam sem interpretacao financeira homologada. Esta dependencia nao invalida o inventario estatico concluido.
- FORBIDDEN nesta matriz sinaliza trechos de negocio confirmados no codigo legado, nao auditoria item a item dos milhares de literais existentes.
- Conectores, webhooks, cache e persistencia continuam no n8n; inteligencia dinamica e regras aprovadas vao para LangGraph/contexto sem hardcode.
- Nao foram executados workflow, SQL financeira, LLM, descriptografia, alteracoes de n8n ou de banco.

## Resultado de aceite desta tarefa

**Inventario funcional estatico dos 68 nos: CONCLUIDO.**
**Censo da operacao publicado e historico: 68 identidades, 68 corpos/configuracoes conferidos, 78 arestas, 10 IF, 11 PostgreSQL e 2 HTTP.**
**Significado contabil, portabilidade entre clientes reais, Gemini Shadow e paridade numerica: NAO HOMOLOGADOS; fases posteriores.**
