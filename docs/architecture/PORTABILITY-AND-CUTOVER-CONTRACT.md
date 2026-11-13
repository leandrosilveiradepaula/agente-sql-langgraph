## Atualização factual 13/11/2026 — recuperação criptográfica não equivale à aprovação

A versão G5 selecionada no n8n publicado foi DESCRIPTOGRAFADA pelo operador em TTY; o pacote privado SHA-256 verificado contém 77 registros, preservados em área local restrita, sem expor dados ao gerador/benchmark. O bug de reserialização do arquivo recuperado foi reparado. Verificação técnica privada: 40 aliases identificam unicamente 8 tabelas de catálogo e colunas nelas listadas, mas falta validação de tipos, contabilidade e destinos canônicos. Os 77 registros seguem sem aprovação e com estado UNRESOLVED. Os contratos de portabilidade, critérios G1–G6, aprovação independente, paridade numérica SELECT-only separadamente autorizada, n8n oficial, Shadow sem execução e cutover humano permanecem **inalterados**. Não confundir acesso ao corpus com homologação funcional financeira.

---

## 13/11/2026 — Bloco 1: ponte real de G5 para revisão contábil (SEM homologação)

**Verificado na VPS:** versão G5 selecionada pelo n8n publicado ligada ao manifesto privado de 11 ciphertexts; versão ativa SHA-256 7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485 e 77 registros (18 regras, 40 aliases, 11 DRE, 8 catálogo), com hash do ciphertext íntegro. As 11 versões contêm 1.275 registros sem SQL patterns. Todos seguem ENCRYPTED_NOT_APPROVED; zero significados contábeis validados e zero SQL financeira executada. Fonte e benchmark de 63 perguntas permanecem separados.

**Engenharia nova:** scripts/operations/g5_financial_crosswalk_review.py exige cobertura linha a linha do registro original por hash/versão, classificação STRUCTURAL/FORBIDDEN e, para toda regra de negócio, destino canônico explícito; rejeita TRANSITIONAL/UNRESOLVED, ausência/duplicação de registros, troca de tenant, contexto ou fingerprint, destino inexistente, SQL histórica, assinatura ausente ou inválida. Um aprovador independente precisa autenticar digest integral de revisões, contexto e fonte; o código apenas verifica, não emite assinatura. O script g5_targeted_financial_review_offline.py gera um draft privado junto ao pacote verificado, depois de TTY/passphrase local. A nova g5_financial_crosswalk_review_cli.py verifica todos os artefatos privados em modo read-only e pode emitir somente CANDIDATE_NOT_ACTIVATED. Sem importar/aprovar/ativar catálogos por conta própria. Testes sintéticos em dois contextos e 77 linhas simuladas. Documentação: docs/operations/G5-FINANCIAL-CROSSWALK-REVIEW.md.

**Aceite BLOQUEADO por dependência real:** a passphrase local não está disponível nesta sessão e não existe unapproved-source-packet.json já decifrado. A revisão financeira efetiva de 77 linhas e aprovação independente não foram realizadas. A prova de paridade financeira n8n/Gemini × LangGraph/Gemini continua sem autorização read-only. CI e protótipos sintéticos não substituem isso. Preservar PR #233 sem merge, n8n oficial inalterado, LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. Não anunciar Bloco 1 concluído.

---

# Contrato de portabilidade, equivalência Shadow e cutover do Agente Financeiro

**Decisão operacional explícita:** 2026-10-19. **Status:** objetivo e critérios de aceitação; **não representa cutover autorizado ou concluído**. Em conflito com notas históricas, prevalecem a decisão atual do operador, este contrato e `AGENTS.md`. Consulte `DOCUMENTATION-MAP.md` para precedência.

## Bloqueio obrigatório de entrega: prova funcional, não implementação isolada (11/11/2026)

Uma capacidade financeira migrada exige **nó/branch e regra do n8n legado → objeto/versão G5 e significado contábil aprovado → contexto semântico versionado por tenant → interpretação/plano/SQL dinâmica e gates LangGraph em pergunta inédita**. O resultado só recebe status `PROVEN` com evidência reproduzível e sem SQL financeira real no Shadow. Código disponível, prompt, CI, mocks, documentação e acerto no benchmark não bastam. Expandir prova para todas as capacidades necessárias do legado; a migração não termina na primeira.

Benchmarks: 63 perguntas e SQL históricas usadas **somente em avaliação comparativa posterior**. Sem hardcodes, `if cliente`, DRE obrigatório, thresholds casuísticos ou SQL conhecida por pergunta. Em caso de campo contábil ambíguo, validar mapeamento e falhar com segurança. Preservar Fase 1 oficial n8n+Gemini, Shadow n8n+LangGraph+Gemini com SQL real desabilitada; Generate/Repair/Execute Approved separados; testes numéricos SELECT-only exigem autorização adicional; cutover humano. A estimativa de 12–20 semanas foi **retirada** por falta de medição.

Especificação de aceite: `docs/operations/FIRST-FINANCIAL-CAPABILITY-PROOF.md`.

## Objetivo verificável

Entregar o caminho oficial **Produto → n8n (orquestração) → LangGraph (inteligência SQL) → LLM configurada**, com aprovação e execução controlada, sem regras cliente-específicas embutidas no código do motor ou nos nós operacionais do n8n. Primeiro homologar com **Gemini**; somente depois avaliar **Gemini × SQL-InfoDive**. Não aposentar n8n: aposentar **a inteligência legada implementada em nós n8n com Gemini direto**.

**Equivalência no cliente atual não basta.** Também é necessário demonstrar que o mesmo motor funciona com contextos materialmente distintos, sem alterações de Python/TypeScript para acomodar tabelas, contas, regras, nomes ou exceções de cada cliente.

## Fronteiras de responsabilidade

| Parte | Responsabilidade permanente | Não deve assumir |
|---|---|---|
| Produto/Next.js | UI, BFF, authn/authz, políticas, aprovação humana, histórico, observabilidade, escolha de tenant/provedor autorizada | Prompts financeiros ou bypass de SQL gates |
| n8n | Webhooks, orquestração operacional, conectores, integrações, tarefas previsíveis, execução autorizada/coordenação | Classificação semântica cliente-específica ou SQL baseada em scripts hardcoded |
| LangGraph | Resolver intenções dinamicamente, selecionar contexto, planejar, gerar e validar SQL, propor repair, produzir evidence e governar comportamento | Orquestrador genérico, UI paralela, respostas lookup ou configurações financeiras em Python |
| Contexto versionado por tenant | Catálogos físicos/autorizados, métricas, dimensões, aliases, modelos contábeis, filtros, joins, dialetos, padrões estruturais, regras e tolerâncias aprovadas | Código executável de bypass ou golden answers |
| LLM | Ajudar na interpretação e geração/reparo dentro dos contratos do LangGraph | Decidir políticas, permissões, configurações desconhecidas ou executar SQL sem aprovação |

## Três fases de entrega — sequência fechada

### Fase 1 — Shadow comparativo, mesmo Gemini

1. Manter **OFFICIAL = fluxo atual Produto/n8n + Gemini**. O fluxo do produto/n8n despacha uma tentativa isolada para **SHADOW = n8n + LangGraph + Gemini** sem alterar o retorno oficial.
2. Correlacionar mesma pergunta, identidade/tenant autorizado, snapshot de dados compatível, contexto versionado, `agent_run_id`, `run_id`, `shadow_record_id`, modelo/configuração Gemini, fingerprints, timing, plano, SQL e gates.
3. Conferir **interpretação**, **SQL semântica**, **gates**, **status**, **erros** e, na etapa explicitamente autorizada, **resultados numéricos**. Não exigir SQL textualmente igual; exigir mesma semântica, joins/filtros e resultado correto.
4. `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` continua obrigatório no Shadow atual. **Enquanto assim, não existe prova de equivalência numérica via execução da SQL Shadow.** Planejar aprovação separada de teste read-only com credenciais e ambiente isolados, sem alterar silenciosamente o Shadow, para obter resultados financeiros e comparar.
5. Registrar divergências com hipóteses rastreáveis e classificá-las: contexto/regra ausente, intenção/plano, SQL, provider, temporal, permissão, resultado, integração ou infraestrutura. Corrigir capacidade geral, não perguntas.
6. A resposta n8n/Gemini historicamente aceita é **baseline para avaliação posterior**, não verdade infalível nem dado permitido no prompt. Quando existir divergência, consultar evidência contábil/regras autorizadas, nunca forçar SQL para mimetizar a baseline.
7. Definir e registrar critérios de aceite de paridade por modalidade, cobertura de cenários, severidade de divergência e tolerâncias monetárias/temporais com aprovação humana. **Não inventar limite de erro ou taxa de sucesso.**

### Fase 2 — Cutover controlado, n8n permanece

1. Concluir inventário e externalização de hardcodes (abaixo), testes multicliente, paridade funcional, política de autorização, integração com o produto, capacidade de rollback e observabilidade.
2. Executar canário/feature flag e revisão humana explícita dos riscos, autorizações e divergências remanescentes; validar que aprovações e execução não serão duplicadas.
3. **Somente após autorização específica:** tornar oficial **Produto → n8n → LangGraph → Gemini**, desabilitando o caminho de interpretação/geração Gemini legada dentro do n8n. Preservar toda orquestração operacional, webhooks, conectores e tarefas determinísticas do n8n.
4. Preservar rollback testado, versionamento, status da implantação e monitoramento de qualidade. Merge, CI verde, benchmark alto ou conectividade não são autorização de cutover.

### Fase 3 — Comparação de LLMs em arquitetura estabilizada

Usar **o mesmo LangGraph, mesmo contexto, mesmas bases/autorizações e mesmos critérios** para comparar Gemini com a LLM privada da Infodive (**SQL-InfoDive**). Medir interpretação, SQL, Security/Contract Gates, taxa de reparo, equivalência financeira, custo/tokens, latência, falhas e exposição de dados. Não fazer a troca de provedores para mascarar problemas da Fase 1. Hospedar a LLM em uma infraestrutura de nuvem não significa reintroduzir dependências Watson/IBM IAM no motor.

## Inventário de hardcodes do n8n legado: obrigação para concluir

Auditar o **conteúdo real** de nós, scripts, configurações, prompts e conectores do fluxo n8n atualmente oficial, sem supor que já foi auditado. Por achado registrar: workflow/nó/caminho; condição/regra/texto observados; efeito em métricas/SQL/resposta; origem/evidência; classificação; destino de migração; versão de contexto; teste e critério de remoção; proprietário e status.

| Classe | Critério | Tratamento |
|---|---|---|
| **STRUCTURAL** | Segurança, orquestração, protocolos, parsing e regras de processo genéricas | Pode permanecer no código, com testes |
| **TRANSITIONAL** | Hardcode operacional ou de negócio herdado ainda ativo no legado | Dívida inventariada e isolada até extração segura |
| **FORBIDDEN** | Tabela/coluna de cliente, DRE, IMD, unidade, marca, conta, centro de custo, filtros contábeis, aliases, intenção específica, resposta pronta, SQL de pergunta, threshold casuístico | **Nunca em código novo** LangGraph/Next.js nem novos nós hardcoded; colocar em contexto versionado ou eliminar |

**Critério:** migrar comportamento, **não copiar hardcode**. Não desativar comportamento legado necessário antes de validar sua equivalência, mas não permitir que a dívida transicional vire fundamento do motor genérico.

## Contrato de contexto multicliente

O mesmo código deve aceitar clientes por **configuração versionada**, não por branches cliente-específicas:

1. **Conectar com menor privilégio:** identidade do tenant, segredo externo, autorização por banco/schema, dialeto, limites de recursos e operação somente leitura onde aplicável. Segregar clientes e impedir leitura cruzada.
2. **Descobrir esquema com metadados autorizados:** tabelas, colunas, tipos, chaves, relacionamentos e granularidade, sem tentar adivinhar políticas ou dados sensíveis.
3. **Modelar semântica de negócio:** catálogo de métricas e fórmulas, dimensões, filtros, conceito de período, regras de agregação, convenções de sinal, aliases e padrões SQL **estruturais**. DRE e IMD são opcionais e específicos do contexto; não pressupor sua existência.
4. **Autorizar e publicar contexto:** versionar `rules`, `aliases`, `dre_mappings` quando aplicáveis, `sql_patterns` sem SQL pronta por pergunta, `table_catalog`, política e `SEMANTIC_AGENT_VERSION`; validar integridade e fingerprint. Uma versão ativa por tenant/escopo de maneira auditável.
5. **Validar perguntas novas:** cenários diferentes dos usados no desenvolvimento, incluindo ambiguidade, ausência de mapeamento, joins múltiplos, períodos, negativas, permissões e dados inexistentes. Falhar fechado quando não for possível verificar a regra, em vez de inventar SQL financeiramente incorreta.
6. **Testar independência do motor:** ao menos dois contextos com esquemas e nomenclaturas materialmente diferentes. Alterar o contexto e/ou o adaptador de dialeto, sem adicionar `if client == ...`, SQLs ou mapeamentos no motor.

Fontes preferenciais: `ai_ducklake_agent_rules`, `ai_ducklake_entity_aliases`, `ai_ducklake_dre_mapping`, `ai_ducklake_sql_patterns`, `ai_ducklake_table_catalog` e equivalentes auditáveis. `business_question_examples` podem ser apenas sinais semânticos; nunca lookup.

## Paridade: avaliação por camadas, sem contaminação

| Camada | Evidência necessária | Limite |
|---|---|---|
| Semântica | Métrica, entidade, dimensão, filtros, período, granularidade, operação e intenção | Acerto isolado de intenção não é resposta financeira |
| Planejamento | Fonte/catálogo autorizado, joins, agregação, time bindings, sinal, ambiguidade e plano | Planejado não significa executável nem correto |
| SQL | Geração dinâmica e semântica equivalente, Security Gate, Contract Gate, preflight/repair | SQL textual diferente pode ser correta; SQL válida pode produzir número errado |
| Dados (gate separado) | Resultado monetário e linhas comparados em mesma visão temporal/dados sob execução read-only autorizada | Execução no Shadow atual está **desabilitada** |
| Produto e operação | Mesmas aprovações, respostas, histórico, latência tolerável, observabilidade, falhas e rollback | Não alterar resposta oficial em Fase 1 |
| Generalização multicliente | Novos esquemas/terminologias sem mudanças de motor | Não declarar universalidade sem prova |

Campos de benchmark (`tabelas_obrigatorias`, `filtros_obrigatorios`, `deve_conter_sql`, `nao_deve_conter_sql`, critérios, golden answer, SQL/resposta esperada) são **avaliação pós-execução**, nunca dados do resolver/planner/generator. Não criar pergunta → SQL, special-case textual, `if` por benchmark nem reduzir threshold para atingir meta. Testes de contexto **no mesmo commit do motor** não provam estabilidade **entre commits**; registrar ambos.

## Segurança, aprovação e auditoria

- **Current Shadow:** `OFFICIAL=n8n`, `SHADOW=LangGraph`, `real_sql_execution=false`. Nenhum cutover, migrations, mudança de banco, workflow n8n ou produção implícitos.
- **Generate ≠ Repair ≠ Execute Approved.** SQL modificada exige `requires_reapproval=true`, não pode executar com aprovação da SQL anterior.
- Isolar `langgraph_context_reader` (SELECT somente em tabelas autorizadas, sem benchmark, sem escrita) de `langgraph_shadow` (evidence mínima, sem DELETE). Só ampliar privilégios com necessidade demonstrada e autorização explícita.
- Preservar `agent_run_id`, `run_id`, `shadow_record_id`, versões, fingerprints, provider/model, tokens quando disponíveis, gates, timeline e status. Não imprimir/retornar cookies, Authorization, DSN, secrets, API keys ou respostas brutas de provider desnecessárias.
- Fail-closed na ausência de política, mapeamento, ambiguidade material ou fonte autorizada; revisão humana de decisões financeiras ambíguas.

## Gates verificáveis de conclusão

**G1 — Integração e observabilidade:** dispatch oficial/Shadow real e correlação consistente, sem interferência no retorno oficial.

**G2 — Contexto reutilizável:** inventário n8n completo, hardcodes `FORBIDDEN` removidos do caminho novo, versionamento e isolamento tenant, prova com dois contextos materialmente diferentes.

**G3 — Paridade de Gemini:** semântica, SQL e planos equivalentes; resultados financeiros somente após gate de execução read-only; métricas/tolerâncias definidas e divergências revisadas por humano.

**G4 — Segurança/execução:** gates, aprovação/reaprovação, mínima permissão, segurança de integração, evidência e rollback demonstrados.

**G5 — Cutover humano:** autorização explícita, implantação controlada, fluxo inteligente legado desativado, n8n operacional preservado, verificação pós-corte e rollback.

**G6 — Comparação de modelos:** somente após G5, Gemini versus SQL-InfoDive em ambiente e contexto controlados.

Nenhum gate é cumprido apenas por criação de arquivos, PR mergeada ou suite semântica verde.

## Continuidade entre chats e entregas

No começo de cada nova sessão, ler `AGENTS.md`, `CHATGPT-PROJECT-INSTRUCTIONS.md`, este contrato, `ORCHESTRATION-STRATEGY.md`, `PROJECT-STATUS.md` e evidência real dos PRs/CI/deploys. Não usar notas históricas sem data como estado atual. Trabalhar em blocos substanciais sem pedir `prossiga` para tarefas reversíveis e autorizadas, mas parar em dependências reais/custo/credenciais/produção, manter gates humanos. Reportar evidência, versão, progresso por G1–G6, hardcodes remanescentes e próximo bloqueio. **Sem inventar acesso ou validação.**
