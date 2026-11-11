# Primeira prova obrigatória — capacidade financeira real n8n/G5 → LangGraph

**Estado inicial: `NOT_MIGRATED` / evidência funcional `NOT_PROVEN`.** Contrato operacional vinculante de 11/11/2026 21:36 UTC. Não é autorização de executar SQL financeira, acessar dados sem permissão, publicar contexto, alterar n8n ou fazer cutover.

## Objetivo de produto

Demonstrar, em ambiente isolado e com pergunta **inédita**, uma capacidade financeira **já presente no sistema antigo**. Extrair o comportamento em conjunto do **workflow publicado com 68 nós** e do **banco/backup G5 na versão correta**. Externalizar sua definição como contexto semântico por tenant, executar a interpretação e planejamento reais do LangGraph, gerar SQL **dinamicamente** e validar os gates sem executar SQL financeira. Depois expandir a prova para todos os comportamentos necessários, com a mesma metodologia e sem `if cliente`.

## Capacidade candidata de investigação (não homologada)

O nó legado 22 contém funções estruturais com nomes `planConsultaMetricaFinanceira`, `factGrainContract`, `comparativeFactContract` e `commonManagerialRules`; o nó 6 faz classificação semântica; os nós 7/8/23/54 tratam regra, prompt, validação e projeção de métricas/dimensões. A cadeia observada de geração envolve **5 → 6 → 54 → 33 → 7 → 24 → 22 → 23 → 8 → 9 → 10 → 11 → 12**, sujeita a ramificações. Isso **não comprova** qual definição financeira, tabela, predicado ou regra por versão foi usado. Essas dependências devem ser confirmadas lendo os corpos reais e sua fonte G5.

**Seleção final:** somente escolher a pergunta inédita e a capacidade após identificar significado financeiro, registro/versão e mapeamento físico autorizados. Não aproveitar SQL de exemplos, baseline do n8n, 63 perguntas ou golden answers.

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
