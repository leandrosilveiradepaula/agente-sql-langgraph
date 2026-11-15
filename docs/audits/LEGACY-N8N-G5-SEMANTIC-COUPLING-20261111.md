# Evidência funcional do legado: acoplamento n8n × G5 (11/11/2026)

> **Origem real examinada, migração contábil ainda NÃO demonstrada.** Relatório privado da VPS `source-coupling-evidence-v1.json`, SHA-256 `b9fc93f7986020aa4017a9a3641baf770e617eeab0a08d67c8ef36b205c8b179`, criado com permissões de owner-only. Este documento não contém código JS bruto, SQL histórica, credenciais ou dados financeiros.

## Fonte e método

- Workflow n8n **ativo e versão publicada coincidente**, 68 nós. Export SHA-256 `19dd24c29d81c61b12dc383f2124ca2e7ba77625776ee161f3be1996d2f09c68`.
- Fontes G5: cinco coleções no `source-semantic-inventory.json`, 579 candidatos do relatório de identifiers e 11 versões cifradas verificadas no manifesto. SQL patterns históricos permanecem `EVALUATION_ONLY_NOT_GENERATOR_INPUT` e não foram entregues ao motor.
- Auditor reutilizável: `scripts/operations/legacy_semantic_static_coupling_offline.py`. Entradas externas; **nenhum nome de cliente/conta/tabela/schema é codificado nele**. Analisa SQL de consulta a catálogo e objetos literais JS simples, cruza candidatos físicos por nome exato, produz hashes e contagens sanitizadas, sem DB, GPG, LLM, n8n write, SQL financeira ou rede.
- Testes `testar_legacy_semantic_static_coupling.py`: oito cenários sintéticos, incluindo duas estruturas de clientes, versões múltiplas, HTML/SQL/literais não exportados, bloqueio de evidência não publicada e falha segura. O mecanismo **não pode concluir equivalência contábil por ocorrência textual**.

## Descobertas comprovadas no código antigo

| Fonte | Prova observável | Implicação de migração |
|---|---|---|
| **Nó PostgreSQL 5** | As cinco consultas têm `agent_version` igual a **um mesmo literal fixo**, hash SHA-256 `7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485`; **nenhuma** possui referência explícita a coluna `tenant_id` ou `organization_id`. | No produto novo, versão/escopo vêm de contexto aprovado e credencial/identidade do tenant. A ausência de coluna no SELECT **não prova** inexistência de RLS/isolamento por banco no legado. |
| **Nó PostgreSQL 5** | Lê também `ai_ducklake_sql_patterns`, classificada como **EVALUATION_ONLY** no G5 recuperado. | **Não importar essa coleção histórica ao planejador/LLM novo**. Projetar padrões operacionais estruturais somente após aprovação independente e segregação. |
| **Nó Code 7** | Linhas 28, 41 e 55–56: lê `ctx.padroes`, seleciona `padraoSelecionado` por `intent_name` e serializa JSON como **PADRÃO SQL RELEVANTE** no `contexto_texto`. | O legado usava padrões persistidos como sinais diretos de geração; não é autorização para reaproveitar SQL/golden answer histórica. |
| **Nó Code 8** | Linhas 34 e 934–935: injeta `contexto_texto` no prompt de geração. Seções de prompt nas linhas 588 (**REGRAS FINANCEIRAS FIXAS**), 628 e 730 (**REGRAS ESPECÍFICAS POR MODELO PLANEJADO**). | Mover regras/descritores contábeis ao catálogo; deixar apenas instruções estruturais de segurança e SQL no prompt LangGraph. |
| **Nó Code 9** | Linhas 39, 59 e 61–67: recebe o prompt já montado e o incorpora ao payload para Gemini. | Cadeia 5 → 7 → 8 → 9 demonstra fluxo de contexto até payload LLM, não prova execução efetiva de cada ramo em produção. |
| **Nó Code 22** | Linha 853: objeto com **8 bindings físicos literais**. Análise contra os 579 hints do G5: **4 bindings** com correspondência textual e **4 sem**, todos os encontrados com `AMBIGUOUS_TABLE_NAME`. Um objeto mapeado é ainda dependente de versão (algumas correspondências só em uma versão). | Nenhum binding pode ser promulgado como regra aprovada. Externalizar tabelas/chaves/joins/filters via catálogo e adaptador. |
| **Nó Code 22** | Funções `factGrainContract` (1073), `commonManagerialRules` (1105), `planConsultaMetricaFinanceira` (2030). | Separar regras de grão e algoritmo reutilizável das tabelas, sinais e métricas financeiras concretas. |
| **Nó Code 23** | `metricasBase` (378–396) inclui campos de orçamento/realizado/variação fixos para contexto de comparação. | Migração deve modelar métricas/derivações como conceitos/bindings por cliente, preservando significado e tolerância, nunca como colunas obrigatórias genéricas. |
| **Nó Code 54** | `detectDimensions` (110) e `detectMetrics` (184) usam conjuntos explícitos de marcas, contas e métricas; entre outras fontes aparecem termos por cliente. | Externalizar aliases/dimensões/intents; não copiar listas ao LangGraph. |
| **Nó Code 32** | `metricDescriptor` (534), `metricLanguage` (668) e rotas de resumo executivo. | Apresentação genérica deve receber metadados financeiros aprovados, sem inferir fórmula ou sinal do nome da coluna. |

## Censo do novo auditor

- **68 nós** percorridos, **11 versões** G5 conferidas.
- **4 objetos JavaScript literais simples** encontrados em nós 22, 52 e 53, com **12 bindings candidatos**. Apenas **4** apresentam referência física textual no relatório G5; trata-se de matches de **um mapa no nó 22**, não de quatro significados financeiros homologados.
- **5 seletores de versão literais** identificados no nó 5 e leitura de material `EVALUATION_ONLY` no mesmo nó.
- Nenhum SQL financeiro, chamada LLM ou autorização/ativação de contexto foi realizado.

## Confirmação adicional de semântica financeira e gates — 11/11/2026

1. **Fórmula no prompt de geração, não atestada no G5:** o nó 8 contém, nas linhas 648–653, regra explícita de percentual de resultado líquido sobre ROL (divisão protegida por `NULLIF`). A fórmula pode ser historicamente válida para um cliente/cenário, mas **não é definição universal de métrica** e não será copiada ao LangGraph. Necessita definição e sinal aprovados no catálogo do tenant.
2. **DRE e orçamento client-specific:** nas linhas 744–784 do nó 8 há regras de estouro orçamentário, convenção de sinal e exigências de dimensões/métricas; um modelo de ROL fixa grupos DRE numéricos (01/02/03) e regras de marca/ranking. Esses valores dependem de mapeamento financeiro validado; não são lógica estrutural reutilizável no código.
3. **Gates técnicos, não aprovação humana:** auditor do workflow real identificou **10 nós IF**. No **IF 25** o campo `success` vem do nó 12 (`validationErrors.length === 0`, linha 525); no **IF 29** o campo `aprovado` vem do nó 28 (`errors.length === 0`, linha 439). No ramo do preflight, nó 61 também monta `success` conforme resultado técnico, consumido no IF 62. **Nenhum desses sinais sozinho comprova autorização humana**. A autorização permanece responsabilidade do Produto, vinculada a tenant, usuário, fingerprint SQL, contexto e aprovação específica. O auditor é conservador: os demais IF ficam com `SIGNAL_PROVENANCE_NOT_ESTABLISHED`, não marcados como seguros.
4. **Segregação do histórico:** o nó 5 coleta padrões SQL, o nó 7 os injeta em `contexto_texto`, os nós 8/9 os incorporam à requisição Gemini. No motor novo, os 106 registros históricos do G5 são avaliação somente, não exemplos de geração. O loader legado atual do LangGraph ainda possui `sql_patterns` em sua consulta; o catálogo novo deverá ter validação de proveniência e isolamento efetivo, não apenas declaração.
5. **Custódia do conteúdo G5:** os 11 pacotes por versão permanecem cifrados e há manifesto íntegro. Uma tentativa única de acesso **sem senha** confirmou que não há desbloqueio GPG local em cache (`CACHED_LOCAL_DECRYPTION_AVAILABLE=false`). Nenhuma senha foi solicitada, lida ou impressa. Para atestar fórmulas/sinais/regras, será preciso desbloqueio via TTY sob custódia autorizada, sem divulgar a senha no chat ou GitHub.

**Relatório privado de gates:** SHA-256 `e5d6f3886730f16f484d40a1f818fb83d6ec563a5d2b8f2d34270bfb46fe612a`; 68 nós/10 IF analisados, aprovação humana não inferida por nenhum IF. A saída sanitizada é apenas evidência estática; não comprova execução, paridade ou equivalência financeira.

## Reconciliação por versão (nova evidência independente)

O seletor literal repetido em cinco consultas no nó PostgreSQL 5 possui hash SHA-256 7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485. Ele corresponde a **exatamente uma** das 11 versões seladas no manifesto: **pacote 10/11, 77 registros** distribuídos em 18 regras, 11 DRE, 40 aliases, 8 catálogos, além de **48 hints não aprovados**. O auditor compara hashes de versões, preserva a distribuição por coleção e bloqueia seleção implícita de outra versão; não lê os campos contábeis cifrados.

**Correção de escopo:** a análise anterior de mapa estático contra **todas as versões** encontrava quatro de oito referências do nó 22. Limitando-se à **versão que o workflow realmente seleciona**, existem **três de oito** matches textuais, classificados como ambíguos. Logo não é válido copiar tabelas/joins do legado como conhecimento universal, nem tratar aliases históricos de outra versão como equivalentes. Relatório privado SHA-256 e376d3a3555d67467b57ece1949af4d26e1ca622f54487fc922c7d921521fbea.

**Procedimento GPG em código, pendente de execução humana local:** scripts/operations/g5_targeted_financial_review_offline.py exige TTY, recebe passphrase apenas via getpass e FD anônimo, verifica ciphertext/plaintext SHA-256 e conteúdo, escreve pacote não aprovado e resumo privado com permissões 0600; não conecta ao banco nem liga o contexto. Sete testes de integridade, isolamento e falha segura passaram. Preflight sem TTY no pacote real falhou de modo esperado, sem criação de arquivo. Ver docs/operations/G5-ACTIVE-VERSION-LOCAL-REVIEW.md.

**Nova barreira do gerador:** app/domain/canonical_source_boundary.py exige padrões estruturais aprovados e vazios de SQL histórica, exemplos de perguntas e texto livre. O antigo leitor continua preservado para Shadow não ativado. Conteúdos financeiros das regras G5 ainda não são semanticamente homologados.

## Limite explícito desta prova

Esta é **engenharia reversa estrutural e de acoplamento** com achados novos e rastreáveis, não extração contábil final. O G5 preserva 11 pacotes cifrados; o auditor vê **identificadores e proveniência**, não fórmulas/definições dentro do conteúdo cifrado. A leitura detalhada exige desbloqueio sob custódia no terminal da VPS, sem senha no chat/log/GitHub. Também devem ser examinadas todas as funções/branches/SQL e seus efeitos, para classificar cada regra relevante em STRUCTURAL, TRANSITIONAL ou FORBIDDEN. Não colocar a primeira capacidade em `PROVEN` antes de demonstrar o significado financeiro, o contexto aprovado e o pipeline LangGraph generate-only com pergunta inédita.

**Próxima intervenção técnica obrigatória:** validar um registro financeiro verdadeiro do G5 por versão e associá-lo a uma regra consumida por 6/7/8/22/23/54; separar fontes físicas, granularidade, sinais, operações e filtros, externalizar os vínculos e demonstrar sua interpretação/plano/SQL dinâmica. Benchmark de 63 perguntas só entra após essa geração independente na fase de controle de qualidade.
