# P3 — Classificar dependências SOURCE antes de decidir migração ou aposentadoria

**Finalidade:** transformar o inventário agregado `SOURCE=6` / `DEMO=2` do P3 em um **rascunho privado, identificável por nó**, usando exclusivamente evidências locais já existentes. O utilitário é genérico: não conhece nomes de tabelas, DRE, SQL, métricas, clientes ou finalidade de um nó. Ele **não** altera n8n, contextos, banco, roles, DSNs, produção, provedor de LLM ou permissões.

## Por que há esta etapa

O relatório P3 do operador confirmou que os dois executores financeiros usam o login mínimo DEMO, mas existem seis outros nós PostgreSQL potencialmente alcançáveis que ainda referenciam SOURCE. O inventário de 68 nós de 20/10 sugere que são carregamento de contexto/configuração e cache, mas **isso era uma hipótese até haver correlação por identidade de nó**. Não migrar a conexão de todos sem distinguir responsabilidades futuras do n8n e inteligência legada que LangGraph substituirá.

O utilitário faz a correlação **sem abrir n8n nem exportar credenciais novamente**:

1. Lê o snapshot privado **pré-PUT**, validado pelo verificador G1 (propriedade, SHA-256 do workflow, política e credencial de origem).
2. Lê os relatórios privados **G1 e P3 da mesma execução** em `0700`/`0600`, exigindo identidade de workflow, nós, vínculos, privilégios dos dois executores e destinos agregados observados.
3. Reconstrói, em memória, somente a classificação dos dois nós explicitamente rebindeados: `DEMO`; os nós não rebindeados mantêm a credencial original. Percorre **todos os ramos** do workflow, sem executar nós ou queries, e confere o número de nós `SOURCE`/`DEMO` com a auditoria P3 real.
4. Grava um `p3-source-node-review.json` **privado** no mesmo diretório, sem sobrescrever arquivo anterior. Contém apenas índices, nomes/IDs de nós, classe de operação estrutural, destino observado e campos de decisão **nulos**. Nenhum SQL, prompt, senha, DSN, payload financeiro, credencial ID ou bearer token entra no relatório.
5. Imprime somente status e **índices posicionais**; os nomes dos nós e o JSON integral não devem ser encaminhados ao chat ou a PRs.

## Executar no host VPS, após merge e CI aprovado

Não repetir a auditoria P3 nem pedir API key. O diretório deve ser o da auditoria P3 já concluída; **não é necessário que o serviço IBM Cloud esteja ligado**.

```bash
cd /docker/agente-sql-langgraph-repo || exit 1
git fetch -q origin && git checkout -q main && git pull --ff-only -q origin main || exit 1

.venv/bin/python -m scripts.operations.p3_source_node_review_readonly \
  --audit-dir /CAMINHO-PRIVADO-EXATO-DA-AUDITORIA-P3
```

Esperado, se os arquivos forem exatamente aqueles da auditoria previamente registrada:

```text
P3_NODE_REVIEW=OFFLINE_DRAFT_CREATED
P3_REVIEW_SOURCE_NODE_COUNT=6
P3_REVIEW_DEMO_EXECUTOR_COUNT=2
P3_REVIEW_SOURCE_ORDINALS=...      # derivados da posição no snapshot, não uma lista hardcoded
P3_REVIEW_EXECUTOR_ORDINALS=...    # idem
P3_REVIEW_G1_STATUS=SETTINGS_DRIFT_REVIEW
P3_REVIEW_CUTOVER_AUTHORIZED=false
P3_REVIEW_FINANCIAL_SQL_EXECUTED=false
P3_REVIEW_LLM_CALLS=0
```

Os números de nós são **ordinais do snapshot G1 pré-PUT**, não IDs estáveis entre alterações de ordenação. Compará-los à matriz histórica só depois de verificar que a versão/ordenação coincide. O algoritmo utiliza a classificação agregada da auditoria P3 e **não comprova que o n8n foi executado** nem revalida a configuração atual após aquela auditoria. `SETTINGS_DRIFT_REVIEW` continua um gate de publicação pendente, mesmo quando o rascunho é criado.

Se um único vínculo não bater, o resultado será `P3_NODE_REVIEW=BLOCKED` com razão fixa e nada será escrito. O comando não faz login, nem sequer lê uma senha de banco; não contorna um relatório P3 bloqueado, apenas o explica estruturalmente.

## Decisão de engenharia posterior (não automatizada)

Para cada um dos nós SOURCE, o operador deve definir **fora do gerador e sob aprovação humana** se a responsabilidade será:

- **Substituída pela inteligência LangGraph** após paridade e cutover (contexto, plano, gerador, validadores de negócio); não transportar sua query legada ao motor.
- **Preservada no n8n como operação determinística**, com contrato, segurança/tenant e credencial de destino aprovados separadamente.
- **Descontinuada por obsolescência**, apenas depois de prova de não uso e rollback.

Campos `business_purpose`, `cutover_disposition`, `replacement_dependency`, `owner_approval_evidence` começam nulos de propósito. Editar o arquivo **não equivale a autorização** de merge, migração, SQL financeira, mudança de credencial, produção ou cutover. A aprovação só pode existir no fluxo apropriado do Produto/operador, com evidências e políticas.

## Dependências que este inventário não resolve

- Persistência de evidências Shadow ainda em SOURCE; o DEMO contém histórico migrado, mas a role `langgraph_shadow` NOLOGIN e RLS **não equivalem** a login tenant-bound ativado. Há gate específico de organização e DSN.
- `demo-finance-v9` aponta para `demo_lakehouse`, enquanto a credencial financeira DEMO lê `rivatti_demo_masked`. O rascunho físico de P3 contém somente nomes/tipos: são obrigatórios mapeamentos contábeis humanos de métricas, grain, joins, períodos, sinais e DRE quando aplicável.
- A versão publicada do workflow n8n ainda exige a revisão conservadora do `settings.callerPolicy`; o auditor automático não deu `STRICT_PASS`.
- Execução financeira Shadow segue **desabilitada**. A comparação de equivalência numérica exige aprovação específica para SELECT read-only isolado. Primeiro Gemini/Gemini e cutover humano; somente depois Gemini/SQL-InfoDive.

Código e testes: `scripts/operations/p3_source_node_review_readonly.py` e `scripts/test_p3_source_node_review_readonly.py`.

## 30/10 — corrigida a hipótese de credencial única no snapshot pré-PUT

A primeira execução da PR #206 retornou `P3_NODE_REVIEW_REASON=UNEXPECTED_SNAPSHOT_CREDENTIAL`.
Esse resultado **não comprova** que algum nó foi alterado no n8n: a primeira
versão do utilitário exigia incorretamente que **todos** os nós PostgreSQL
usassem a `old_credential_id` do G1 no snapshot original. A política G1
só vincula essa identidade aos **dois nós executores** selecionados para
rebinding, não aos demais nós que permaneceram no workflow.

A correção mantém o bloqueio quando a credencial original **de um executor**
não é exatamente a esperada; preserva as identidades distintas dos outros
nós, não as imprime, e reconstrói a cardinalidade das referências após o
rebinding. Essa cardinalidade precisa coincidir com o total de credenciais
PostgreSQL da auditoria P3 — inclusive considerando nós desconectados.
Exige também que a contagem de nós alcançáveis `SOURCE`, `DEMO`, `UNKNOWN` e
`OTHER_SUPABASE_UNVERIFIED` corresponda integralmente ao resultado P3.

Como os dois executores DEMO foram atestados separadamente, o G1 atesta
zero alteração dos outros nós e o P3 reportou somente esses dois nós
DEMO, a atribuição dos seis não-executores alcançáveis a `SOURCE` é uma
**dedução por exclusão controlada**, não uma leitura de credenciais nem uma
atestação de finalidade de negócio. Ela não funciona quando as contagens
ou a topologia de credenciais divergem: nesse caso bloqueia sem rascunho.
O G1 segue com `SETTINGS_DRIFT_REVIEW`, e a mudança não torna o canário
executável ou o fluxo oficial elegível ao cutover.

Validação offline ampliada: casos com uma ou duas credenciais pré-PUT,
uma terceira credencial alcançável ou desconectada, credencial inesperada
nos dois executores, presença prematura da nova credencial e workflow
sintético de **68 nós (60 alcançáveis, 8 desconectados, 11 PostgreSQL)**.
Tudo isso permanece estrutural, sem importar lógica contábil do legado.
