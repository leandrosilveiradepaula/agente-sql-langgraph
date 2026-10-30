# SQL-InfoDive: prova real de geracao e reparo no Shadow

Decisão do operador em 29/10/2026: sem novos créditos Gemini; usar SQL-InfoDive na API privada IBM Cloud em **ambos** os caminhos, mantendo n8n oficial.

## Evidencia obtida na VPS

- Workflow n8n oficial: 68 nós; Stored com `activeVersionId == versionId`, `active=true`.
- Fonte armazenada sem drift: fingerprint `37725fe765f5f727838c7b5de31bbcf01c25b5deecdef338ead60917e4d70b6d`. **Nao é hash da versão historica da PR; nao atesta o webhook sozinho.**
- Quatro nós de Gemini identificados: dois HTTP de geração/reparo e dois consumidores; ferramenta de migração somente em memória foi entregue na PR #204.
- Shadow indica `INFODIVE_SHADOW_CONFIG=READY_FOR_TEST`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.
- Gemini `generateContent` devolveu HTTP 402; `GET /models` retornou 200, mas não representava autorização de geração.
- A CLI n8n v2.4.8 nao implementa `export:workflow --published`; a verificação por `activeVersionId == versionId` passou na VPS. A opção CLI não deve ser usada novamente.

## Bug estrutural eliminado na PR #205

Antes da PR, o campo `llm_selection` selecionava SQL-InfoDive somente na etapa **generate**. Um preflight com falha reparável invocava `GoogleGeminiSqlRepairerAdapter` mesmo após a seleção SQL-InfoDive, e a resposta podia falhar com faturamento Gemini.

A PR adiciona `SqlRepairerRegistry` versionado e `OpenAiCompatibleSqlRepairerAdapter`; o `GenerateSqlUseCase` resolve **ambos** antes da primeira chamada. Em seleção explícita, ausência de repairer retorna `INTERNAL_LLM_SELECTION_UNAVAILABLE` sem chamada LLM. O branch de Execute Approved mantém o contrato existente e **nao** recebe autorização para executar SQL financeira.

## Default privado para a orquestração n8n -> Shadow

A PR também introduz a configuração estrutural opt-in `SHADOW_DEFAULT_LLM_SELECTION_JSON`. Ela é aplicada **somente** no build/restart do runtime Shadow, mediante alteração operacional autorizada, e seleciona simultaneamente gerador e reparador para requisições que não transportem `llm_selection`:

```json
{"provider_key":"infodive_ibm_cloud","model_key":"<modelo-efetivamente-configurado>","config_version":"<versao-efetivamente-configurada>"}
```

Os dois valores entre sinais angulares são marcadores; obter da configuração existente de `OPENAI_COMPATIBLE_SQL_MODEL` e `OPENAI_COMPATIBLE_SQL_CONFIG_VERSION`. Não reutilizar literalmente os marcadores. O seletor é neutro a clientes, sem SQL ou conhecimento contábil. Se modelo/provedor/versão não estiverem cadastrados, o runtime falha fechado em vez de recorrer ao Gemini. A variável não é ativada por esta PR.

## Prova Shadow no runtime implantado (após merge e deploy controlado)

O código versionado desta PR precisa estar presente no runtime Shadow. `git pull` do repositório da VPS não atualiza por si só o container Docker já iniciado. Antes da prova, confirmar `LANGGRAPH_COMMIT`/image e seguir o processo de build/restart TEST já homologado; nao fazer deploy implícito.

Para um teste **sem** chamada à LLM (preflight):

```bash
docker exec -i agente-sql-langgraph-shadow-test-langgraph-shadow-test-1 python - \
  --question 'Quais unidades de negocio tiveram os maiores valores no segundo trimestre de 2025?' \
  < scripts/operations/g3_infodive_generate_canary.py
```

Para uma única tentativa de geração privada **explicitamente autorizada**, depois de confirmar container atualizado:

```bash
docker exec -i agente-sql-langgraph-shadow-test-langgraph-shadow-test-1 python - \
  --invoke-private-provider \
  --question 'Quais unidades de negocio tiveram os maiores valores no segundo trimestre de 2025?' \
  < scripts/operations/g3_infodive_generate_canary.py
```

O script usa o serviço interno existente, autenticação S2S, `llm_selection` real da configuração, permite somente operações HTTP `openai_compatible_chat_completions`, imprime **apenas** status, intenção, fingerprints e contagem de chamadas. Não imprime SQL, pergunta, resposta bruta, tokens secretos ou DSN. Não chama Gemini. O canário pode inserir **evidência Shadow**, mas não executa SQL financeira. Em ambiente tenant-bound, ele bloqueia; usar a rota do Produto com identidade real e autorização.

**O script só é uma prova de geração/reparo quando os respectivos gates são observados.** Uma execução sem reparo não comprova caminho de reparo; o teste offline dedicado cobre isoladamente o roteamento do reparador. `preflight.executed=false` é obrigatório para PASS.

## Troca oficial no n8n continua uma operacao separada

O workflow oficial n8n não foi modificado pela PR #205. Para alterar os quatro nós de Gemini, é preciso antes atestar que o endpoint/credencial privados estão disponíveis **no container n8n** (nao apenas no Shadow), preparar credencial de autenticação segura (sem segredo no JSON versionado), diff do workflow publicado, backup privado 0600 e rollback. Não publicar o candidato diretamente em produção sem canário isolado por causa do caminho legado de execução PostgreSQL.

A PR #202 (fonte/catálogo/role) permanece pendente. Nenhuma equivalência numerica deve ser declarada por CI ou canário sem execução somente-leitura autorizada separadamente.
