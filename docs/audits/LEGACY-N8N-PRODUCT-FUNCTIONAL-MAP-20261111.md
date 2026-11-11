# Matriz funcional de migração: 68 nós n8n + Produto + G5

**Data:** 11/11/2026. **Classificação:** engenharia reversa em andamento, sem migração ou aprovação contábil. Versão publicada de workflow do n8n verificada em memória; SHA de exportação e a matriz estrutural completa estão em [LEGACY-N8N-G5-TRACE-20261111.md](LEGACY-N8N-G5-TRACE-20261111.md). Este documento não contém SQL bruta, prompts, dados financeiros ou credenciais.

## Contrato funcional e fonte

A tarefa é migrar **o Agente Financeiro existente**, não treinar um agente novo com 63 exemplos. A matriz abaixo atribui **candidatos de responsabilidade**, com base nas identidades dos nós, suas configurações, símbolos JavaScript e 78 conexões observadas. **A migração funcional de cada nó permanece pendente de revisão de regras/efeitos e teste; estes destinos não são aprovações.** Regras casuísticas das 41 funções JavaScript nunca serão copiadas como condições de negócio no Python ou TypeScript.

**A arquitetura resultante deverá conservar:** Produto/Next.js (autenticação, políticas, aprovação, histórico e apresentação), n8n (orquestração, conectores, webhooks, cache e efeitos autorizados), LangGraph (interpretação, intenção, seleção de contexto, plano, SQL dinâmica, validação, repair e evidência) e **catálogos versionados por tenant** (toda semântica de negócio).

## Decomposição por responsabilidade

### Entrada, contexto, interpretação e geração

| Nó | Responsabilidade observada / candidato de migração | Destino proposto, sujeito a revisão |
|---:|---|---|
| 1 | Webhook da pergunta | n8n |
| 2 | Validação da pergunta, identidade operacional e run IDs | Produto / n8n |
| 3 | Formato de erro da pergunta | n8n |
| 4 | Resposta HTTP de erro | n8n |
| 5 | Consulta dos cinco catálogos DuckLake | n8n conector → contexto versionado |
| 6 | Classificação de intenção por regras e aliases | LangGraph |
| 7 | Consolidação de regras/entidades/DRE | LangGraph + catálogo |
| 8 | Construção de prompt e plano SQL | LangGraph + catálogo |
| 9 | Preparação da chamada Gemini | LangGraph/provider |
| 10 | Chamada externa de geração Gemini | LangGraph/provider |
| 11 | Limpeza e normalização da SQL | LangGraph |
| 12 | Validação física e semântica da SQL | LangGraph gates |
| 13 | Preparação de erros de geração | LangGraph evidência → n8n |
| 14 | Resposta HTTP de erro SQL | n8n |
| 15 | Preparação de entrega da consulta | Produto / n8n |
| 16 | Resposta HTTP final | n8n |
| 17 | Formatação de SQL de auditoria legado | Produto / n8n observabilidade |
| 18 | Persistência de log SQL | Produto / n8n |
| 19 | Entrega alternativa Watson | Produto / n8n adaptador |
| 20 | Montagem da fila de perguntas | n8n / Produto |
| 21 | Persistência da fila de perguntas | n8n / Produto |
| 22 | Planejamento de consulta com contexto/operadores | LangGraph |
| 23 | Gate de validação do plano semântico | LangGraph |
| 24 | Normalização de fonte física e namespace | Contexto + LangGraph |

### Aprovação, execução e relatórios

| Nó | Responsabilidade observada / candidato de migração | Destino proposto, sujeito a revisão |
|---:|---|---|
| 25 | Desvio por status de validação SQL | n8n; não substitui aprovação humana |
| 26 | Roteador gerar versus executar | n8n |
| 27 | Desvio pelo modo de execução | n8n |
| 28 | Validação da SQL recebida | LangGraph + Produto |
| 29 | Desvio por status da SQL recebida | n8n; não substitui aprovação humana |
| 30 | Normalização do resultado PostgreSQL | n8n adaptador / Produto |
| 31 | Erro de SQL recebida | n8n |
| 32 | Montagem de relatório executivo | Produto + contexto financeiro versionado |

### Cache, auditoria de economia e invalidação

| Nó | Responsabilidade observada / candidato de migração | Destino proposto, sujeito a revisão |
|---:|---|---|
| 33 | Resolver opção de cache SQL | n8n / Produto |
| 34 | Chave cache: contexto, período, versão, fingerprint | n8n cache + política tenant |
| 35 | Desvio usar cache | n8n |
| 36 | Leitura PostgreSQL de cache | n8n conector |
| 37 | Desvio acerto cache | n8n |
| 38 | Recuperar SQL cacheada | n8n, sujeita a gates LangGraph |
| 39 | Metadata de miss cache | n8n observabilidade |
| 40 | Metadata cache desativado | n8n observabilidade |
| 41 | Desvio cache hit após preflight | n8n |
| 42 | Atualizar hits do cache | n8n conector |
| 43 | Metadata hit cache | n8n |
| 44 | Preparar gravação cache | n8n, só SQL validada |
| 45 | Desvio de gravação cache | n8n |
| 46 | Gravar cache PostgreSQL | n8n conector |
| 47 | Metadata cache gravado | n8n observabilidade |
| 48 | Desvio cache inválido | n8n |
| 49 | Invalidar cache PostgreSQL | n8n conector |
| 50 | Retorno à IA após cache rejeitado | n8n → LangGraph |
| 51 | DDL manual de tabela cache | Operação manual separada, não no runtime |

### Correlação, reparo, preflight, configuração e execução real

| Nó | Responsabilidade observada / candidato de migração | Destino proposto, sujeito a revisão |
|---:|---|---|
| 52 | Criação de run context e correlação | Produto + n8n |
| 53 | Registro de tokens/uso de LLM | LangGraph provider + Produto |
| 54 | Projeção da requisição semântica observada | LangGraph |
| 55 | Avaliar necessidade de reparo | LangGraph |
| 56 | Desvio condicional reparo | n8n sob decisão LangGraph |
| 57 | Construção de requisição de reparo | LangGraph |
| 58 | Chamada Gemini para reparo | LangGraph/provider |
| 59 | Normalização de SQL reparada | LangGraph; exige reaprovação |
| 60 | Preparação de SQL para preflight | LangGraph + adaptador n8n |
| 61 | Interpretação de resposta de preflight | LangGraph |
| 62 | Gate após preflight | LangGraph decide; n8n orquestra |
| 63 | Consulta de configuração DuckLake ativa | n8n conector → catálogo versionado |
| 64 | Aplicação de configuração física/dialeto | LangGraph + contexto |
| 65 | Resposta de erro configuração | n8n |
| 66 | Execução de preflight PostgreSQL | n8n executor isolado e autorizado |
| 67 | Execução real da SQL no PostgreSQL | n8n apenas após aprovação explícita |
| 68 | Preparação da chamada de execução real | n8n / Produto com recibo de aprovação |

## Conexões estruturais importantes

- **Entrada de geração:** 1 → 52 → 63 → 64 → 26 → 27 (ramo não execução) → 2 → 5 → 6 → 54 → 33 (cache) → 7 → 24 → 22 → 23 → 8 → 9 → 10 → 11 → 12. Isso indica que contexto, catálogo, regras e plano atualmente passam por JavaScript no n8n antes e depois do Gemini; devem ser reconstruídos por contexto + LangGraph.
- **SQL recebida para execução:** ramo de execução do nó 27 → 28 → 29 → 68 → 67 → 30 → 32 → 16. O gate do nó 29 usa o campo `aprovado`, mas a revisão ainda deve distinguir **validação técnica** de **aprovação humana** e respectivo fingerprint de SQL.
- **SQL gerada pode alcançar execução real:** 12 → 25 → 60 → 66 → 61 → 62 → 41 → 42/44/45/46 → 68 → 67 → 30 → 32 → 16. Cada aresta está presente no grafo publicado; a realização de uma ramificação depende de condições de runtime. O nome de nó `IF - SQL Aprovada` não é uma prova de consentimento humano.
- **Reparo Gemini pode retornar ao executor:** 55 → 56 → 57 → 58 → 59 → 11 → 12 → 25 → preflight → 68 → 67. A arquitetura nova deve **impedir aprovação herdada após reparo**: `requires_reapproval=true`, nenhum SQL reparado executado silenciosamente.
- **Nó 51 com DDL manual de cache** não é alcançável a partir do webhook, assim como 15/17/18/19/20/21/53 (total **8 nós não alcançáveis**). Não remover esses caminhos automaticamente: verificar execução manual, invocação indireta e consequências de side effects. A trilha oficial de auditoria pode depender do Produto, não dessas conexões.
- **Efeitos em DB fora do catálogo semântico:** os nós 18, 21, 36, 42, 46, 49, 51, 63, 66 e 67 têm finalidades distintas (logs, fila, cache, configuração, preflight, execução). Não confundir gravações determinísticas de observabilidade/cache com SQL financeira gerada; precisam de autorização, idempotência e rastreio próprios.

## Banco/backup G5 — o que foi realmente relacionado

- **Nó 5** referencia explicitamente as **cinco coleções semânticas históricas**: `ai_ducklake_agent_rules`, `ai_ducklake_dre_mapping`, `ai_ducklake_entity_aliases`, `ai_ducklake_sql_patterns` e `ai_ducklake_table_catalog`. Esse é o vínculo mais forte entre consulta n8n e as coleções do backup; **o uso exato de cada registro pela classificação, prompt e planejador ainda deve ser comprovado no caminho 5 → 6/7/22/8**.
- O G5 preserva 11 versões e 1.381 registros nas cinco coleções, incluindo **106 padrões SQL históricos** que permanecem exclusivamente em avaliação posterior. SQL histórica não será repassada ao planejador, contexto gerador ou LLM.
- Os 579 candidatos a referências físicas e as 4.813 coocorrências textuais em 20 nós **não são mapeamentos validados**. Nomes repetidos em 11 versões podem inflar contagens. Somente fonte física, cardinalidade, contexto versionado e significado contábil aprovado permitem considerar um vínculo válido.
- **Nó 5 não apresentou seletor explícito `tenant_id`/`organization_id` na consulta examinada.** Isso não prova ausência de isolamento (podem existir banco/credencial/RLS por tenant), mas impede presumir isolamento multicliente sem revisão de credenciais, grants, políticas e escopo.
- Os demais nós PostgreSQL tratam cache, operações e execução; essas tabelas **não foram automaticamente associadas às cinco coleções semânticas**. O backup PostgreSQL completo contém mais objetos do que o extrato semântico; a revisão desses objetos ainda é exigida.
- Os 11 pacotes financeiros por versão continuam criptografados/segregados. Os manifestos e fingerprints foram verificados, mas **o conteúdo integral das regras e mapeamentos por versão não foi homologado nesta revisão**. Necessário acesso isolado e autorizado para analisar, sem misturar versões.

## Integração real do Produto Next.js

No repositório `leandrosilveiradepaula/Agente-Financeiro` (main observado em `5f6d5113cd69ebcc4475a6f6046046051b8250ac`):

- `app/api/generate-sql/route.ts`: controla sessão e política de geração, consulta webhook n8n, persiste SQL, tokens/cache e dispara Shadow **após** responder, quando habilitado.
- `app/api/execute-watson/route.ts`: caminho atual efetivo de execução aprovada do Produto; recebe SQL, verifica perfil/política e envia `modo=executar_sql` ao n8n; também prevê evento Shadow distinto `execute_approved`. O contrato novo deve adaptar este endpoint real, não supor que já exista `/api/execute-sql` com mesma semântica.
- `lib/langgraph-shadow-client.ts`: feature flag `LANGGRAPH_SHADOW_ENABLED`, eventos separados `generate` e `execute_approved`. A disponibilidade de código não comprova transporte real ativado ou correlação operacional.
- `lib/n8n-endpoint.ts`: o caminho de webhook **fallback** estático no repositório é diferente do caminho publicado no nó n8n auditado. A URL efetiva pode ser substituída pelas variáveis de ambiente; **não declarar erro de produção nem paridade de rota sem verificar o binding realmente usado**.
- `app/api/admin/runs/[id]/shadow-comparison/route.ts` observa que a SQL oficial capturada pode ser posterior a limpeza e execução pelo n8n; comparar apenas texto não comprova significado financeiro ou controle de aprovação.

## Falhas de migração que não podem passar no cutover

1. **Separação de estados:** gerar ≠ aprovar ≠ executar. Reparo sempre invalida aprovação; verificação por IDs/fingerprint vinculados a tenant, política e contexto. Cuidado especial com o caminho geração → executor e reparo → executor existente no legado.
2. **Portabilidade:** não transportar do JavaScript n8n listas de marcas, contas, aliases, períodos e regras DRE para Python/TypeScript. Externalizar em contexto por cliente, com correspondência física aprovada e versão explícita.
3. **Gates SQL:** no LangGraph estrutural, validar catálogo autorizado, colunas, joins, agregação, filtros, dialeto, esquema/tenant, limite, read-only; execução somente em n8n/adaptador autorizado e aprovada.
4. **Cache e relatórios:** chave inclui tenant/escopo/contexto/version/provider/model/política/fingerprint; cache hit nunca pula segurança. Relatório executivo não pode introduzir interpretação contábil hardcoded.
5. **Rota real:** conferir URL/webhook e correlação de runs do Produto (incluindo ambiente efetivo), n8n e Shadow, além de mecanismos de rollback.
6. **Comparação de qualidade:** 63 perguntas históricas são **somente controle de qualidade posterior**, junto de perguntas inéditas. SQL esperada, resposta anterior e scoring não são contexto nem alvos para respostas prontas. A comparação financeira numérica exige autorização read-only isolada específica.

## Critério de conclusão deste documento

**Concluído:** enumeração funcional preliminar 68/68, análise das 78 arestas, identificação dos caminhos de geração, reparo e executor, vínculo direto do nó 5 às cinco coleções e revisão do roteamento do Produto. **Ainda não concluído:** extração de todas as regras contábeis dos scripts, de todas as versões G5 criptografadas, assinatura/aprovação financeira dos vínculos, identificação da rota real em produção, implementação da migração e certificação de paridade. Nenhuma mutação de n8n/banco/Produto/Shadow, nenhuma execução financeira real e nenhum cutover nesta etapa.
