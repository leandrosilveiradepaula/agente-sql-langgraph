# Primeira prova obrigatória — capacidade financeira real n8n/G5 → LangGraph

**Estado inicial: `NOT_MIGRATED` / evidência funcional `NOT_PROVEN`.** Contrato operacional vinculante de 11/11/2026 21:36 UTC. Não é autorização de executar SQL financeira, acessar dados sem permissão, publicar contexto, alterar n8n ou fazer cutover.

## Objetivo de produto

Demonstrar, em ambiente isolado e com pergunta **inédita**, uma capacidade financeira **já presente no sistema antigo**. Extrair o comportamento em conjunto do **workflow publicado com 68 nós** e do **banco/backup G5 na versão correta**. Externalizar sua definição como contexto semântico por tenant, executar a interpretação e planejamento reais do LangGraph, gerar SQL **dinamicamente** e validar os gates sem executar SQL financeira. Depois expandir a prova para todos os comportamentos necessários, com a mesma metodologia e sem `if cliente`.

## Capacidade candidata de investigação (não homologada)

O nó legado 22 contém funções estruturais com nomes `planConsultaMetricaFinanceira`, `factGrainContract`, `comparativeFactContract` e `commonManagerialRules`; o nó 6 faz classificação semântica; os nós 7/8/23/54 tratam regra, prompt, validação e projeção de métricas/dimensões. A cadeia observada de geração envolve **5 → 6 → 54 → 33 → 7 → 24 → 22 → 23 → 8 → 9 → 10 → 11 → 12**, sujeita a ramificações. Isso **não comprova** qual definição financeira, tabela, predicado ou regra por versão foi usado. Essas dependências devem ser confirmadas lendo os corpos reais e sua fonte G5.

**Seleção final:** somente escolher a pergunta inédita e a capacidade após identificar significado financeiro, registro/versão e mapeamento físico autorizados. Não aproveitar SQL de exemplos, baseline do n8n, 63 perguntas ou golden answers.

## Primeiro vínculo de origem verificado na VPS — ainda sem significado contábil aprovado

Foi feita uma **nova inspeção somente leitura** do export publicado n8n e do manifesto G5, com relatório privado em `/tmp` (não entregue ao gerador). Evidência:

- Export n8n publicado e ativo, 68 nós: SHA-256 `19dd24c29d81c61b12dc383f2124ca2e7ba77625776ee161f3be1996d2f09c68`.
- Nó 22 de planejamento financeiro: SHA-256 do código `113ce61f0e6c57b2cf260f70c6e04af1530e92876f4c6d10d5fbaa9c242f5d5f`; função `planConsultaMetricaFinanceira` na linha 2030 com uso na 2347; `factGrainContract` na 1073 e usos; `comparativeFactContract` na 1054 e usos; `commonManagerialRules` na 1105 e outras referências. Essas identificações comprovam **origem do código**, não correção da interpretação financeira.
- Nó 5 de leitura do contexto referencia as cinco coleções históricas: `ai_ducklake_agent_rules`, `ai_ducklake_dre_mapping`, `ai_ducklake_entity_aliases`, `ai_ducklake_sql_patterns` e `ai_ducklake_table_catalog`.
- Manifesto G5: **11 arquivos cifrados de versão presentes**. Conteúdo e significado contábil ainda **não comprovados nem aprovados**. Não usar os 106 padrões históricos como contexto de geração.
- SHA-256 do relatório privado de observação de origem: `e9c23d9e4b8dddd313359742546aa16eea0a2eab0bb40ae50ee1699ae6abe1d6`.

**Status:** `SOURCE_CODE_VERIFIED_G5_ACCOUNTING_NOT_ATTESTED` → capacidade continua `NOT_MIGRATED`, primeira prova real continua `NOT_PROVEN`. A próxima etapa não é criar novo parser: é estabelecer o vínculo contábil exato com a versão G5 e então gerar SQL com contexto aprovado. Leitura detalhada dos 11 pacotes exige desbloqueio local por TTY e custódia segura; jamais transmitir senha no chat/GitHub.

### Revisão de acoplamento físico/semântico — nova evidência, ainda NÃO PROVEN

Auditoria de fonte independente verificou que o nó 5 fixa um mesmo `agent_version` nas cinco consultas e lê padrões SQL históricos, que o nó 7 seleciona por intenção e injeta como texto na cadeia de prompt 8→9 (Gemini), e que no nó 22 **4 de 8 bindings físicos literais** têm match textual nos candidatos G5, **todos ambíguos**. Evidências, linhas, hashes e riscos: `docs/audits/LEGACY-N8N-G5-SEMANTIC-COUPLING-20261111.md`; relatório privado SHA `b9fc93f7986020aa4017a9a3641baf770e617eeab0a08d67c8ef36b205c8b179`. **Não há significado contábil aprovado**. Capacidade permanece `NOT_MIGRATED`/`NOT_PROVEN`; nenhuma SQL financeira executada.

### Gate de autorização e regras explícitas identificadas no prompt

Os IF 25 e 29 do n8n são acionados por verificações técnicas, **não comprovam aprovação humana**: nó 12 `success = validationErrors.length === 0` e nó 28 `aprovado = errors.length === 0`. Reparo e preflight devem permanecer separados de `Execute Approved` sob política Next.js. O prompt do nó 8 contém fórmula de percentual, convenção de sinal de orçamento e grupos DRE fixos, a migrar para contexto financeiro aprovado e **não para código**. Auditor completo: `docs/audits/LEGACY-N8N-G5-SEMANTIC-COUPLING-20261111.md`; relatório privado atualizado SHA `e5d6f3886730f16f484d40a1f818fb83d6ec563a5d2b8f2d34270bfb46fe612a`. Primeira capacidade ainda `NOT_PROVEN`.

## Matriz de aceite por evidência

| Camada | Prova exigida | Estado atual |
|---|---|---|
| Origem do legado | SHA do export n8n publicado; nó/branch/condição; prova de efeito, entrada e saída; hashes do JS/prompt/SQL, sem código sensível no GitHub | Inventário estrutural disponível; comportamento da capacidade ainda não atestado |
| Fonte financeira | Registro e versão específica do G5, relação física, cardinalidade/granularidade, fórmula/sinal/período, confirmação do significado contábil | 11 versões/manifestos disponíveis; semântica desta capacidade **não validada** |
| Contexto autorizado | Métrica/dimensão/regra/filtro/alias em catálogo versionado e aprovado, vinculado a tenant, versão e fingerprint, sem SQL histórica | Loader canônico existe na PR #233; pacote real não aprovado/ativado |
| Motor | Mesma pergunta inédita interpretada, com plano verificável, geração dinâmica por LLM configurada, sem hardcode por cliente | Não comprovado com esta capacidade real |
| Segurança | Security/Contract Gates de escopo/SELECT, logs/fingerprints e `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`; Repair requer reaprovação | Mecanismos existentes; não testados em jornada completa desta capacidade |
| Independência | Outro contexto com estrutura materialmente diferente, mesmo motor sem alterar código, falha fechada para campo não mapeado | Testes sintéticos existentes, segunda empresa real pendente |
| Correlação | Run e artifacts auditáveis com fonte/context/provider/model/tokens e resultados; não usar benchmark para implementar | Não produzido para esta capacidade |

**Estados:** `NOT_MIGRATED` (não existe prova ou implementação suficiente), `IMPLEMENTED_UNPROVEN` (código presente, não há jornada real comprovada) e `PROVEN` (toda cadeia acima demonstrada, com evidência reproduzível). A marcação `PROVEN` não equivale a paridade numérica, que exige outro gate.

## Bloco de execução sem microtarefas artificiais

1. **Auditar o conteúdo real das funções e ramificações implicadas**, não só nomes/lexemas; isolar a lógica estruturante de fórmulas, métricas e filtros cliente-específicos. Marcar STRUCTURAL/TRANSITIONAL/FORBIDDEN e fonte de cada comportamento.
2. **Confrontar com o G5 por versão.** Usar os pacotes/backup mediante custódia autorizada, sem copiar segredos nem SQL histórica para prompts. Se a descompactação/decriptação exigir interação humana, informar esse único bloqueio legítimo e continuar o código genérico seguro.
3. **Validar definição financeira com responsável.** Não deduzir que alias e campo com grafia semelhante são equivalentes; se não houver definição, bloquear sem inventar.
4. **Externalizar no catálogo versionado.** Usar o carregador canônico e semântica aprovada por tenant, com relações, métricas, dimensões e operações configuráveis. Nenhum nome específico no novo código.
5. **Provar com pergunta inédita.** Ejecutar apenas geração/validação SQL autorizada; preservar provenance, fingerprint, provider/model, gates e status. Não executar SQL financeira nem disparar LLM paga sem autorização de custo.
6. **Provar o negativo:** contexto sem mapeamento, tenant incorreto, coluna não autorizada, join desconhecido, reparo sem reaprovação, schema diferente. Cada falha deve ser segura e auditável.
7. **Consolidar PR e evidências** em bloco substantivo: código, testes, hashes, resultado, comportamento migrado e pendências. Só então marcar uma capacidade `PROVEN` e avançar à seguinte.

## O que permanece vedado

- **63 perguntas + SQL/resultados históricos:** exclusivamente controle cego de qualidade **após** a geração independente; não instruções de negócio, golden SQL de entrada, thresholds de tuning, fontes de regras ou atalhos de benchmark.
- **Hardcodes financeiros:** não transportar fórmulas, contas, DRE, métricas, dimensões, aliases, filtros ou SQL pronta dos nós para Python/TS. Clientes com bases diferentes devem ser configuráveis, sem DRE obrigatória.
- **Execução:** `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. SQL read-only para equivalência numérica exige autorização separada e isolamento. Aprovações, permissões, credenciais, migrações, produção, merge e cutover dependem de gates humanos.
- **Prazos:** cronograma de 12–20 semanas retirado por falta de medição; não emitir estimativa nova a partir de quantidade de PRs ou testes.

## Critério de encerramento do projeto

**Além da primeira prova:** inventário completo e externalização das regras necessárias dos 68 nós + G5, todos os caminhos de negócio requeridos funcionando, duas empresas/contextos reais distintos sem alterar motor, integração real Produto/n8n/Shadow e paridade financeira com execução read-only autorizada, aprovação/reparos/rollback testados e cutover humano. Comparar Gemini versus SQL-InfoDive somente depois da Fase 2.
