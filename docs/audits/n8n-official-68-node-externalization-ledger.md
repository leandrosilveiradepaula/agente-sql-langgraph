# Inventário operacional de externalização — n8n oficial (68 nós)

**Data da análise:** 2026-10-23. **Fonte:** export JSON do fluxo oficial fornecido pelo operador em 2026-10-20, disponível no acervo do Projeto; o arquivo bruto não faz parte do GitHub. Este documento é um **plano de migração por nó**, não um atestado da versão publicada da VPS. A checagem de workflow publicado, IDs e hash continua condicionada à coleta separada e autorizada descrita em `docs/audits/n8n-published-workflow-readonly-runbook.md`.

## Resultado reprodutível sobre o snapshot recebido

- **68 nós:** 41 Code, 11 Postgres, 10 IF, 3 Respond, 2 HTTP e 1 Webhook.
- **60 nós alcançáveis** a partir do Webhook de pergunta; **8 inalcançáveis** (#15, #17, #18, #19, #20, #21, #51 e #53). A presença desses oito no JSON não comprova execução em produção.
- Triagem mais conservadora **por responsabilidade principal de cada nó**: 15 candidatos FORBIDDEN, 21 TRANSITIONAL e 32 STRUCTURAL a revisar. **Não substituir** com essas contagens o resultado histórico de 14/19/35 da auditoria de 20/10: classificações em granularidades diferentes, e um nó pode misturar comportamentos de várias classes.
- **Nenhum segredo, SQL de negócio, prompt, payload, DSN ou expressão dinâmica** do arquivo foi copiado para este documento. Nomes de nós e papéis são evidências de inventário, não configurações executáveis.

## Matriz dos 68 nós

| # | Nó no snapshot | Fluxo | Categoria preliminar | Destino / ação |
|---:|---|---|---|---|
| 1 | Webhook - Pergunta | Alcançável | STRUCTURAL (a revisar) | n8n interface e processo; não inteligência |
| 2 | Code - Validar Pergunta | Alcançável | FORBIDDEN (candidato) | Catálogos versionados + LangGraph |
| 3 | Code - Resposta Erro Pergunta | Alcançável | STRUCTURAL (a revisar) | n8n interface e processo; não inteligência |
| 4 | Respond to Webhook Erro Pergunta | Alcançável | STRUCTURAL (a revisar) | n8n interface e processo; não inteligência |
| 5 | Postgres - Buscar Contexto DuckLake | Alcançável | TRANSITIONAL (candidato) | Config/adaptador por tenant + contexto |
| 6 | Code - Classificar Intenção DuckLake | Alcançável | FORBIDDEN (candidato) | Catálogos versionados + LangGraph |
| 7 | Code - Consolidar Contexto DuckLake | Alcançável | FORBIDDEN (candidato) | Catálogos versionados + LangGraph |
| 8 | Code - Montar Prompt SQL DuckLake Offline | Alcançável | FORBIDDEN (candidato) | Catálogos versionados + LangGraph |
| 9 | Code - Montar Body Gemini | Alcançável | TRANSITIONAL (candidato) | Provider configurável LangGraph; credencial externa |
| 10 | Gemini - Gerar SQL | Alcançável | TRANSITIONAL (candidato) | Provider configurável LangGraph; credencial externa |
| 11 | Code - Limpar SQL DuckLake | Alcançável | FORBIDDEN (candidato) | LangGraph (gates/repair), sem reescrever SQL por negócio |
| 12 | Code - Validar SQL DuckLake Offline | Alcançável | FORBIDDEN (candidato) | LangGraph (gates/repair), sem reescrever SQL por negócio |
| 13 | Code - Resposta Erro SQL DuckLake | Alcançável | TRANSITIONAL (candidato) | n8n interface e processo; não inteligência |
| 14 | Respond to Webhook Erro SQL | Alcançável | STRUCTURAL (a revisar) | n8n interface e processo; não inteligência |
| 15 | Code - Montar Entrega Query DuckLake | Inalcançável | FORBIDDEN (candidato) | Produto (resposta auditável); não copiar inferência |
| 16 | Respond to Webhook | Alcançável | STRUCTURAL (a revisar) | n8n interface e processo; não inteligência |
| 17 | Code - Montar SQL Log DuckLake | Inalcançável | STRUCTURAL (a revisar) | Produto/n8n observabilidade, IDs e fingerprints |
| 18 | Postgres - Gravar Log DuckLake | Inalcançável | STRUCTURAL (a revisar) | Produto/n8n observabilidade, IDs e fingerprints |
| 19 | Code - Montar Entrega Watson | Inalcançável | FORBIDDEN (candidato) | Produto (resposta auditável); não copiar inferência |
| 20 | Code - Montar SQL Question Queue | Inalcançável | STRUCTURAL (a revisar) | Produto/n8n observabilidade, IDs e fingerprints |
| 21 | Postgres - Gravar Question Queue | Inalcançável | STRUCTURAL (a revisar) | Produto/n8n observabilidade, IDs e fingerprints |
| 22 | Code - Montar Plano Query DuckLake | Alcançável | FORBIDDEN (candidato) | Catálogos versionados + LangGraph |
| 23 | Code - Validar Plano Query Semantico | Alcançável | FORBIDDEN (candidato) | Catálogos versionados + LangGraph |
| 24 | Code - Schema Real Data Source | Alcançável | FORBIDDEN (candidato) | Catálogos versionados + LangGraph |
| 25 | IF - SQL Aprovada? | Alcançável | STRUCTURAL (a revisar) | n8n roteamento determinístico e falha segura |
| 26 | Code - Router de Modo | Alcançável | TRANSITIONAL (candidato) | n8n roteamento determinístico e falha segura |
| 27 | IF - Modo Execução SQL? | Alcançável | STRUCTURAL (a revisar) | n8n roteamento determinístico e falha segura |
| 28 | Code - Validar SQL Recebida | Alcançável | FORBIDDEN (candidato) | LangGraph (gates/repair), sem reescrever SQL por negócio |
| 29 | IF - SQL Recebida Aprovada? | Alcançável | STRUCTURAL (a revisar) | n8n roteamento determinístico e falha segura |
| 30 | Code - Normalizar Resultado Postgres Demo | Alcançável | TRANSITIONAL (candidato) | n8n interface e processo; não inteligência |
| 31 | Code - Resposta Erro SQL Recebida | Alcançável | STRUCTURAL (a revisar) | n8n roteamento determinístico e falha segura |
| 32 | Code - Montar Relatório Executivo | Alcançável | FORBIDDEN (candidato) | Produto (resposta auditável); não copiar inferência |
| 33 | Code - Resolver Opções Cache SQL | Alcançável | STRUCTURAL (a revisar) | n8n cache operacional com namespace tenant+versão |
| 34 | Code - Normalizar Chave Cache SQL | Alcançável | TRANSITIONAL (candidato) | n8n cache operacional com namespace tenant+versão |
| 35 | IF - Usar Cache SQL? | Alcançável | STRUCTURAL (a revisar) | n8n cache operacional com namespace tenant+versão |
| 36 | Postgres - Buscar Cache SQL | Alcançável | TRANSITIONAL (candidato) | n8n cache operacional com namespace tenant+versão |
| 37 | IF - Cache Hit? | Alcançável | STRUCTURAL (a revisar) | n8n cache operacional com namespace tenant+versão |
| 38 | Code - Usar SQL Cacheada | Alcançável | TRANSITIONAL (candidato) | n8n cache operacional com namespace tenant+versão |
| 39 | Code - Cache Miss Metadata | Alcançável | STRUCTURAL (a revisar) | n8n cache operacional com namespace tenant+versão |
| 40 | Code - Cache Desativado Metadata | Alcançável | STRUCTURAL (a revisar) | n8n cache operacional com namespace tenant+versão |
| 41 | IF - Cache Hit Validado? | Alcançável | STRUCTURAL (a revisar) | n8n cache operacional com namespace tenant+versão |
| 42 | Postgres - Atualizar Hit Cache SQL | Alcançável | STRUCTURAL (a revisar) | n8n cache operacional com namespace tenant+versão |
| 43 | Code - Cache Hit Metadata | Alcançável | STRUCTURAL (a revisar) | n8n cache operacional com namespace tenant+versão |
| 44 | Code - Preparar Salvar Cache SQL | Alcançável | TRANSITIONAL (candidato) | n8n cache operacional com namespace tenant+versão |
| 45 | IF - Deve Salvar Cache SQL? | Alcançável | STRUCTURAL (a revisar) | n8n cache operacional com namespace tenant+versão |
| 46 | Postgres - Salvar Cache SQL | Alcançável | TRANSITIONAL (candidato) | n8n cache operacional com namespace tenant+versão |
| 47 | Code - Cache Salvo Metadata | Alcançável | STRUCTURAL (a revisar) | n8n cache operacional com namespace tenant+versão |
| 48 | IF - Cache Hit Reprovado? | Alcançável | STRUCTURAL (a revisar) | n8n cache operacional com namespace tenant+versão |
| 49 | Postgres - Desativar Cache SQL | Alcançável | STRUCTURAL (a revisar) | n8n cache operacional com namespace tenant+versão |
| 50 | Code - Cache Rejeitado Fallback IA | Alcançável | TRANSITIONAL (candidato) | n8n cache operacional com namespace tenant+versão |
| 51 | Postgres - Criar Tabela Cache SQL (manual) | Inalcançável | STRUCTURAL (a revisar) | n8n cache operacional com namespace tenant+versão |
| 52 | Code - Criar Run Context | Alcançável | TRANSITIONAL (candidato) | Produto/n8n observabilidade, IDs e fingerprints |
| 53 | Code - Anexar Uso LLM | Inalcançável | STRUCTURAL (a revisar) | Provider configurável LangGraph; credencial externa |
| 54 | Code - Montar Semantic Request Observado | Alcançável | FORBIDDEN (candidato) | Catálogos versionados + LangGraph |
| 55 | Code - Avaliar Reparo SQL | Alcançável | TRANSITIONAL (candidato) | LangGraph (gates/repair), sem reescrever SQL por negócio |
| 56 | IF - Deve Reparar SQL? | Alcançável | STRUCTURAL (a revisar) | n8n interface e processo; não inteligência |
| 57 | Code - Montar Body Reparo SQL | Alcançável | TRANSITIONAL (candidato) | LangGraph (gates/repair), sem reescrever SQL por negócio |
| 58 | Gemini - Reparar SQL | Alcançável | TRANSITIONAL (candidato) | Provider configurável LangGraph; credencial externa |
| 59 | Code - Preparar SQL Reparada Para Cleaner | Alcançável | TRANSITIONAL (candidato) | LangGraph (gates/repair), sem reescrever SQL por negócio |
| 60 | Code - Montar SQL Preflight Postgres Demo | Alcançável | TRANSITIONAL (candidato) | n8n somente Execute Approved; LangGraph valida |
| 61 | Code - Normalizar Preflight Postgres Demo | Alcançável | TRANSITIONAL (candidato) | n8n somente Execute Approved; LangGraph valida |
| 62 | IF - Preflight SQL Aprovado? | Alcançável | STRUCTURAL (a revisar) | n8n somente Execute Approved; LangGraph valida |
| 63 | Postgres - Buscar Config DuckLake Ativa | Alcançável | FORBIDDEN (candidato) | Config/adaptador por tenant + contexto |
| 64 | Code - Aplicar Config DuckLake | Alcançável | TRANSITIONAL (candidato) | Config/adaptador por tenant + contexto |
| 65 | Code - Resposta Erro Config DuckLake | Alcançável | STRUCTURAL (a revisar) | n8n roteamento determinístico e falha segura |
| 66 | Postgres - Preflight SQL Demo | Alcançável | STRUCTURAL (a revisar) | n8n somente Execute Approved; LangGraph valida |
| 67 | Postgres - Executar SQL Demo | Alcançável | STRUCTURAL (a revisar) | n8n somente Execute Approved; LangGraph valida |
| 68 | Code - Preparar Execucao SQL Demo | Alcançável | TRANSITIONAL (candidato) | n8n somente Execute Approved; LangGraph valida |

### Achados prioritários por evidência do snapshot

| ID | Problema operacional a eliminar | Prova exigida para aceitação |
|---|---|---|
| #2 | Vocabulário financeiro em validação | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #6 | Classificação com léxico e regras financeiras | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #7 | Montagem de contexto com referências contábeis | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #8 | Prompt extenso com catálogo/schema/regra específicos | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #10 | Acesso LLM legado; revisar segredos | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #11 | Limpeza que altera significado SQL: bloquear reescrita de negócio | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #12 | Gate com referências físicas locais | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #15 | Inalcançável; contém semântica legada | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #19 | Inalcançável; inferência legada | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #22 | Plano extenso com critérios contábeis | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #23 | Gate do plano dependente do cliente | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #24 | Schema físico derivado de literais | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #28 | Validação de SQL recebida por regras locais | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #30 | Normalização pode alterar tipo/zero/nulos | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #32 | Relatório com inferência financeira duplicada | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #34 | Isolamento da chave de cache não atestado | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #36 | Consultas cache: demonstrar tenant e versão | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #38 | Reuso SQL cacheada exige revalidar acesso | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #46 | Persistência da cache requer isolamento | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #54 | Consolidação de sinais de semântica | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #55 | Gates de reparo e reaprovação separados | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #58 | Acesso provedor de reparo; revisar segredos | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #59 | Reparo não revalida aprovação automaticamente | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #60 | Preflight sem execução financeira real | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #61 | Tratar falhas preflight sem resposta contábil inventada | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #63 | Consulta de configuração retorna valores fixos | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #64 | Vínculo datasource/tenant explícito | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #67 | Execução SQL legada não autoriza cutover | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |
| #68 | Execução aprovada deve ser distinta de generate | Evidência de catálogo/versão/tenant e teste de pergunta inédita ou gate negativo antes de ativar |

## Sequência real de externalização, sem reimplantar hardcodes

1. **Congelar linha de base publicada:** comparar snapshot recebido com export `--published` do workflow oficial e rota usada pelo Produto; não tratar export draft como prova. Sem isso, a matriz acima é inventário do arquivo do operador, não do runtime atual.
2. **Catálogos e aliases:** para entradas e classificação (#2, #5-8, #22-24, #54), colocar métricas, relações, intenções, sinônimos, DRE/contabilidade quando existir, filtros e mapeamentos no contexto semântico versionado do tenant. Não transferir dicionários, SQL ou thresholds do JavaScript para o motor.
3. **Semântica de SQL e gates:** retirar a regra de alteração de SQL pelo cleaner (#11), substituindo-a por geração dinâmica + validação estrutural/autorização de colunas/tabelas a partir do contexto. Gerar, reparar e executar SQL aprovada são ações diferentes; reparo invalida aprovação anterior.
4. **Relatórios e resultados:** manter no Produto a apresentação e histórico; nunca inferir novamente valores financeiros ou transformar NULL em zero sem metadado contábil explícito (#30, #32).
5. **Configuração e portabilidade:** tornar conectores, source catalog e política de tenant externos (#5, #63-64). `app/adapters/postgres/context_repository.py` carrega tabelas canônicas de contexto, inclusive mapeamento DRE: provar caminho alternativo de contexto para cliente sem DRE, não alterar o código por cliente e não tratar `user_profile` ignorado no adapter como enforcement de RBAC.
6. **Cache e auditoria:** especificar namespace isolado `tenant + semantic_agent_version + authz + fingerprint` e recusa de cache sem identidade atestada. Capturar IDs e metadados confiáveis; não voltar a usar respostas anteriores como exemplos no gerador.
7. **Preflight e execução:** n8n mantém orquestração determinística e execução controlada apenas após gate humano; LangGraph faz interpretação e avaliação sem executar SQL real no Shadow. Os nós de execução legados #66-68 ficam na linha oficial até paridade e cutover humano.
8. **Remoção segura:** os oito nós inalcançáveis e a geração/validação antiga só podem ser excluídos do workflow oficial depois de homologação, snapshot/rollback e cutover explícito. Não ativar este plano como migração.

## Critérios negativos obrigatórios

- Recusar qualquer campo contábil desconhecido e qualquer join/filtro que não possa ser justificado por catálogo/versão e permissões; não inventar semântica de DRE em clientes que não a possuem.
- Testar pelo menos **dois contextos materialmente diferentes** com perguntas inéditas e mesmos componentes LangGraph, sem difusão de tabelas, aliases ou credenciais entre tenants.
- Usar os `business_question_examples`, SQL esperada e golden answers **apenas no avaliador posterior**; jamais injetá-los no gerador ou no planner.
- Confirmar paridade SQL/funcional entre n8n+Gemini e n8n+LangGraph+Gemini com IDs/fingerprints auditáveis; paridade numérica demanda autorização separada para SELECT isolado com menor privilégio.
- Permanecem `OFFICIAL=n8n`, `SHADOW=LangGraph` e `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`; esta matriz não altera n8n, banco, credenciais, configuração Vercel, provedor, versão semântica ou cutover.

## Observações sobre a classificação

Os rótulos desta matriz são **triagem de migração**, não uma conclusão de revisão manual de todas as expressões JavaScript e queries. `FORBIDDEN (candidato)` significa que a responsabilidade contém ou aparenta conter conteúdo contábil/cliente-específico a externalizar; `TRANSITIONAL` identifica integração legada com dívida operacional; `STRUCTURAL (a revisar)` indica processo genérico, mas ainda depende de validação de ausência de regras específicas antes de copiar ou descartar. Nenhum código antigo deve ser portado automaticamente.
