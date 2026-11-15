# Inventario n8n + G5 para engenharia reversa (11/11/2026)

> **Censo estrutural completo, semantica e migracao AINDA NAO atestadas.** Export do n8n publicado e manifestos G5, sem exportar SQL/prompt/credencial para GitHub. Referencias fisicas significam somente coocorrencia textual.

## Evidencia verificada

- Export SHA256: `19dd24c29d81c61b12dc383f2124ca2e7ba77625776ee161f3be1996d2f09c68`. Ativo e versao atual = versao publicada; rota do Produto NAO atestada.
- Auditor: `scripts/operations/legacy_migration_source_crosswalk_offline.py`; relatorio privado SHA256 `e33a1b93f25a0809a644e5e83a9f7a82a360f73adb146511772d19d6181edbff`.
- 68 nos, 78 conexoes, 60 nos alcancaveis a partir do Webhook, 8 nao alcancaveis e 60 em caminhos de resposta.
- 579 candidatos de referencias G5 sem aprovacao; 20 nos com coocorrencias, 376 registros de origem e 4813 coocorrencias em 11 versoes; **nenhuma equivalencia contábil comprovada**.
- 106 SQL patterns historicos segregados como avaliacao, NAO enviados ao modelo/gerador.
- Snapshot usado no Shadow anterior nao apresenta correspondencia exata do hash da string de versao com os 11 fingerprints G5; nao misturar contextos.

## Inventario das colecoes G5

| Colecao da fonte | Registros | Uso |
|---|---:|---|
| `ai_ducklake_agent_rules` | 318 | CONTEXT_REVIEW_ONLY |
| `ai_ducklake_dre_mapping` | 121 | CONTEXT_REVIEW_ONLY |
| `ai_ducklake_entity_aliases` | 738 | CONTEXT_REVIEW_ONLY |
| `ai_ducklake_sql_patterns` | 106 | EVALUATION_ONLY |
| `ai_ducklake_table_catalog` | 98 | CONTEXT_REVIEW_ONLY |

## Onze pacotes de versoes recuperadas (SQL patterns excluidos)

| Prefixo SHA da versao | Registros revisaveis | Roundtrip cifrado |
|---|---:|---|
| `2949ad92e5493d62` | 117 | verificado |
| `3d2089cccaffc163` | 136 | verificado |
| `3ed7fab0421fb76f` | 107 | verificado |
| `6214ad76528a7fcc` | 116 | verificado |
| `6301b0bdfe2e9e44` | 117 | verificado |
| `6726e5e213e7822f` | 121 | verificado |
| `67e69aaaa35ab3e3` | 121 | verificado |
| `68747c6ea8521a76` | 117 | verificado |
| `704c2f29557df325` | 125 | verificado |
| `7f36f6619fe64b5d` | 77 | verificado |
| `d11136a64e3f5e61` | 121 | verificado |

## Matriz sanitizada: cada um dos 68 nos e suas conexoes

Legenda: `G5` = coocorrencias textuais nao homologadas; `flags` = sinais de revisao, nao classificacoes financeiras; `query` = formato estrutural sem conter SQL. Todos os nos seguem REVIEW_REQUIRED para regra/efeito, ainda que alguns conectores estruturais permaneçam no n8n.

| # | Tipo n8n | ID SHA prefixo | De | Para | G5 | Flags | Query |
|---:|---|---|---|---|---:|---|---|
| 1 | webhook | `a70b8ef947a3` | - | 52 | 0 | - | - |
| 2 | code | `f2e7d1030af7` | 27 | 3,5 | 203 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 3 | code | `c7d099bcc53a` | 2 | 4 | 0 | INLINE_CODE_REVIEW | - |
| 4 | respondToWebhook | `eece5d9a83fb` | 3 | - | 0 | - | - |
| 5 | postgres | `524438678dd1` | 2 | 6 | 64 | INLINE_QUERY_REVIEW | UNPARSED_REVIEW_REQUIRED |
| 6 | code | `aab03c6a3488` | 5 | 54 | 203 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 7 | code | `74a7a5809813` | 39,40,50 | 24 | 64 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 8 | code | `7e1cebf8e0fa` | 23 | 9 | 366 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 9 | code | `9c3dd422c7e4` | 8 | 10 | 0 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 10 | httpRequest | `7c8d1c3b06a0` | 9 | 11 | 0 | EXTERNAL_REQUEST_REVIEW | - |
| 11 | code | `1e59d1384f81` | 10,59 | 12,13 | 350 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 12 | code | `d24653c07dd1` | 11,38 | 25,55 | 360 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 13 | code | `fb61aff5e02e` | 11,56 | 14 | 0 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS | - |
| 14 | respondToWebhook | `872f792cba84` | 13,31,65 | - | 0 | - | - |
| 15 | code | `388b579dd55c` | - | 19 | 355 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 16 | respondToWebhook | `03c755ed02b9` | 32,53 | - | 0 | - | - |
| 17 | code | `6d59c41da1c7` | 19 | 18 | 0 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS | - |
| 18 | postgres | `3970946013ed` | 17 | - | 0 | INLINE_QUERY_REVIEW | DYNAMIC_EXPRESSION |
| 19 | code | `f6bbe82ed1bc` | 15 | 17,20,53 | 203 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 20 | code | `a113cc2e65be` | 19 | 21 | 0 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 21 | postgres | `7b6f30ec5dcc` | 20 | - | 0 | INLINE_QUERY_REVIEW | DYNAMIC_EXPRESSION |
| 22 | code | `0922c07fac4d` | 24 | 23 | 360 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 23 | code | `74abbfe88b40` | 22 | 8 | 64 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 24 | code | `cec543231d2b` | 7 | 22 | 376 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 25 | if | `c5f4f0b9c928` | 12 | 48,60 | 0 | - | - |
| 26 | code | `8e0da972a7e8` | 64 | 27 | 0 | INLINE_CODE_REVIEW | - |
| 27 | if | `6f42c5c64eee` | 26 | 2,28 | 0 | - | - |
| 28 | code | `53c18d2a3092` | 27 | 29 | 355 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 29 | if | `f29e98c3edc2` | 28 | 31,68 | 0 | - | - |
| 30 | code | `95f210faeeed` | 67 | 32 | 0 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS | - |
| 31 | code | `6e58fe8f8de6` | 29 | 14 | 0 | INLINE_CODE_REVIEW | - |
| 32 | code | `826da3e7ea58` | 30 | 16 | 208 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 33 | code | `9da983052f9d` | 54 | 34 | 0 | INLINE_CODE_REVIEW | - |
| 34 | code | `5387899ef63e` | 33 | 35 | 0 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 35 | if | `55ed79d2d761` | 34 | 36,40 | 0 | - | - |
| 36 | postgres | `5b0a6a11dc0e` | 35 | 37 | 0 | INLINE_QUERY_REVIEW | DYNAMIC_EXPRESSION |
| 37 | if | `42d705c985e4` | 36 | 38,39 | 0 | - | - |
| 38 | code | `141699cc586c` | 37 | 12 | 0 | INLINE_CODE_REVIEW | - |
| 39 | code | `2e29e193d411` | 37 | 7 | 0 | INLINE_CODE_REVIEW | - |
| 40 | code | `01c40f0a2ba4` | 35 | 7 | 203 | INLINE_CODE_REVIEW | - |
| 41 | if | `75aa2e67b323` | 62 | 42,44 | 0 | - | - |
| 42 | postgres | `af38979382db` | 41 | 43 | 0 | INLINE_QUERY_REVIEW | DYNAMIC_EXPRESSION |
| 43 | code | `917748b9c021` | 42 | 68 | 203 | INLINE_CODE_REVIEW | - |
| 44 | code | `c185e53c6016` | 41 | 45 | 0 | INLINE_CODE_REVIEW | - |
| 45 | if | `f9bd0cc77a55` | 44 | 46,68 | 0 | - | - |
| 46 | postgres | `2965d6fd89b9` | 45 | 47 | 0 | INLINE_QUERY_REVIEW | DYNAMIC_EXPRESSION |
| 47 | code | `7fdb0eb83a0e` | 46 | 68 | 203 | INLINE_CODE_REVIEW | - |
| 48 | if | `0393dd92b17e` | 25 | 49,55 | 0 | - | - |
| 49 | postgres | `e0fcddb308ed` | 48 | 50 | 0 | INLINE_QUERY_REVIEW | DYNAMIC_EXPRESSION |
| 50 | code | `55c5a595d075` | 49 | 7 | 0 | INLINE_CODE_REVIEW | - |
| 51 | postgres | `60a01da52746` | - | - | 0 | INLINE_QUERY_REVIEW | UNPARSED_REVIEW_REQUIRED |
| 52 | code | `dcf392245ceb` | 1 | 63 | 0 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS | - |
| 53 | code | `4f0f96f51909` | 19 | 16 | 0 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS | - |
| 54 | code | `a5e8e790e46b` | 6 | 33 | 267 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 55 | code | `873882018c57` | 12,48,62 | 56 | 203 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 56 | if | `86fb44b0a4c0` | 55 | 13,57 | 0 | - | - |
| 57 | code | `feb54b43bced` | 56 | 58 | 203 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 58 | httpRequest | `5a036c4b93a4` | 57 | 59 | 0 | EXTERNAL_REQUEST_REVIEW | - |
| 59 | code | `92af3a9d3bef` | 58 | 11 | 0 | INLINE_CODE_REVIEW | - |
| 60 | code | `3d0724d2005c` | 25 | 66 | 0 | INLINE_CODE_REVIEW | - |
| 61 | code | `24e9a25e0b7d` | 66 | 62 | 0 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS | - |
| 62 | if | `c00bd2deef49` | 61 | 41,55 | 0 | - | - |
| 63 | postgres | `272a547318e9` | 52 | 64 | 0 | INLINE_QUERY_REVIEW | UNPARSED_REVIEW_REQUIRED |
| 64 | code | `09c1d5e7e393` | 63 | 26,65 | 0 | INLINE_CODE_REVIEW,MANY_INLINE_STRING_LITERALS,SQL_SHAPED_CODE_REVIEW | - |
| 65 | code | `d3c906b27ab1` | 64 | 14 | 0 | INLINE_CODE_REVIEW | - |
| 66 | postgres | `abccb2cc9e50` | 60 | 61 | 0 | INLINE_QUERY_REVIEW | DYNAMIC_EXPRESSION |
| 67 | postgres | `32a1a9a74981` | 68 | 30 | 0 | INLINE_QUERY_REVIEW | DYNAMIC_EXPRESSION |
| 68 | code | `726b7109e466` | 29,43,45,47 | 67 | 0 | INLINE_CODE_REVIEW | - |

## Proximos passos obrigatorios, sem atalhos

1. **Revisao funcional individual** de JS/prompt/SQL/condicoes/transformacoes/erros para cada no do workflow, correlacionando entrada, saida e todas as branches; 8 nos fora do caminho do Webhook exigem checar ativacao indireta antes de considerar exclusao.
2. **Leitura segura dos pacotes G5 por versao** para estudar regras, aliases, mapeamentos, chaves, formulas e dependencias reais. A evidencia cifrada existe, mas seu conteudo por versao nao foi integralmente revisado neste censo.
3. **Crosswalk contabil validado**: regra do no/branch -> objeto/versao do banco -> semantica -> STRUCTURAL, TRANSITIONAL ou FORBIDDEN -> dono do comportamento (n8n deterministico, LangGraph, Produto, contexto versionado) -> teste de paridade. Nenhum if por cliente ou pergunta->SQL.
4. **Homologacao real**: rota Produto/n8n certificada, 2 clientes distintos, SQL dinamica para perguntas ineditas, Shadow Gemini correlacionado; benchmark 63 somente avaliacao posterior; teste financeiro read-only apenas com autorizacao especifica.

Controles: `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. Nenhum merge, deploy ou cutover implicado por este censo.


## Fila de revisao funcional, baseada no codigo real do n8n

O codigo/parametros de cada um dos 68 nos foi inspecionado **somente em memoria** para detectar indicadores estruturais genericos (SQL, prompt, provider, condicionais, conectores). A triagem abaixo **nao atribui propriedade final ao LangGraph, n8n ou Produto**, nem substitui leitura funcional/manual de cada branch. Nenhuma SQL ou prompt bruto foi mantido no relatorio.

| Prioridade de revisao | Nos por indice da exportacao | Total |
|---|---|---:|
| P1 — provedor, interpretacao, geracao e prompts | 8, 9, 10, 11, 13, 23, 24, 34, 39, 40, 50, 53, 54, 55, 57, 58, 59 | 17 |
| P2 — montagem SQL, bindings, consultas e efeitos | 5, 12, 15, 18, 19, 21, 22, 26, 28, 30, 36, 42, 46, 49, 51, 60, 61, 63, 66, 67, 68 | 21 |
| P3 — roteamento, regras condicionais e transformacoes | 2, 3, 6, 7, 17, 20, 25, 27, 29, 31, 32, 33, 35, 37, 38, 41, 43, 44, 45, 47, 48, 52, 56, 62, 64, 65 | 26 |
| P4 — infraestrutura/webhook/resposta e conectores gerais | 1, 4, 14, 16 | 4 |
| **Cobertura do inventario de triagem** | **68/68, sem duplicatas** | **68** |

Indicadores de busca (somente triagem): 9 Code nodes mencionam provider LLM, 10 contem estrutura associada a prompts, 16 contem formatos associados a SQL, 32 contem logica condicional; os 2 HTTP nodes usam endereco estatico de API Google. **Sinais lexicais nao provam papel funcional nem que sejam todos os caminhos efetivamente executados.** Em particular, queries PostgreSQL dinamicas e nodos de escrita nao devem ser desligados apenas por aparecerem nessa lista.

A sequencia de revisao deve combinar cada item P1/P2 com sua cadeia de conexoes e respectivos objetos G5; em seguida analisar todas as condicoes P3 e efeitos P4, cobrindo tambem 8 nos fora da rota iniciada pelo webhook. Revisao completa permanece **PENDENTE**.

## Síntese corrigida da multiplicação por versão

Os 4.813 links por ocorrência dos 579 hints de 11 versões **não** representam dependências financeiras independentes. A auditoria em `scripts/operations/legacy_migration_source_crosswalk_offline.py` agora distingue **11 pares únicos tabela/coluna** e **58 pares únicos nó/referência**. Há 447 candidatos com tabela ambígua, 110 sem correspondência, 22 somente com nome de tabela e 481 com coluna não resolvida. Nenhuma associação está homologada. Credenciais PostgreSQL da exportação pertencem a 2 grupos de IDs: nós 5/18/21/36/42/46/49/51/63 versus 66/67 (nenhum segredo acessado). Confirmação do banco físico e isolamento por tenant pendentes.
