# P3 — Revisão versionada do mapeamento físico-semântico sem SQL financeira

## Problema comprovado no DEMO (30/10/2026)

A versão em uso `demo-finance-v9` possui 8 relações permitidas em
`demo_lakehouse`, enquanto o executor `finance_g1_readonly` possui
SELECT somente em 8 relações de `rivatti_demo_masked`. Todas as dez
versões cadastradas v1–v10 usam o esquema antigo. A fonte mascarada contém
67 colunas; todas as 8 relações têm PK, nenhuma tem FK declarada.

O catálogo antigo contém outras tabelas, chaves, datas, medidas, relações e
aliases. **Trocar apenas o nome do schema, renomear campos pelo nome parecido
ou importar o catálogo antigo não comprova significados contábeis.**

## Entrega

`scripts/operations/p3_semantic_mapping_review_readonly.py` transforma o
snapshot físico privado da auditoria P3 existente em um **formulário JSON
privado não executável**, separado do gerador e do benchmark. Todos os campos
de negócio inicialmente permanecem `null`.

Após revisão contábil explícita, o mesmo utilitário valida:

- identidade imutável de banco/schema/role, versão e fingerprint físico;
- inventário exato de tabelas/colunas/tipos, sem allowlist ampliada;
- identidade de tenant e nova versão semântica explícita;
- grain, PK/keys, métricas/agg/tipo, sinal e evidências;
- datas/referências, dimensões e relacionamentos de colunas com tipos
  compatíveis e cardinalidade expressamente declarada;
- fanout não autorizado, coleções de intents/aliases/regras, DRE opcional;
- atestação de privilégios SELECT e ausência de gravação com o P3 original.

**O resultado `structural_preview_only` não representa aprovação das
fórmulas financeiras ou autorização de publicação.** Nada é inserido no
contexto PostgreSQL. O preview físico é apenas entrada para uma futura
etapa de governaça, validação de significado contábil e migração autorizada.

## Uso na VPS após merge

O snapshot já está em disco e contém somente metadados. Não repetir n8n
audit, login, chamadas Gemini/SQL-InfoDive nem coleta de SQL financeira:

```bash
cd /docker/agente-sql-langgraph-repo || exit 1
git fetch -q origin && git checkout -q main && git pull --ff-only -q origin main || exit 1

.venv/bin/python -m scripts.operations.p3_semantic_mapping_review_readonly \
  --audit-dir /tmp/p3-source-audit.7DIc9fUP
```

Saída esperada da primeira execução:

```text
P3_MAPPING_REVIEW=PRIVATE_TEMPLATE_CREATED
P3_MAPPING_TABLES=8
P3_MAPPING_AUTHORIZED=false
P3_MAPPING_FINANCIAL_SQL_EXECUTED=false
P3_MAPPING_LLM_CALLS=0
```

O arquivo `p3-semantic-mapping-review.json` permanece proprietário em
`/tmp/p3-source-audit.7DIc9fUP`, no modo privado 0600. Não publicar no GitHub,
não colar seu conteúdo no chat. Não sobrescrever o draft: repetição bloqueia.

Após completar e revisar internamente o mapeamento, executar:

```bash
.venv/bin/python -m scripts.operations.p3_semantic_mapping_review_readonly \
  --audit-dir /tmp/p3-source-audit.7DIc9fUP \
  --review-file /tmp/p3-source-audit.7DIc9fUP/p3-semantic-mapping-review.json
```

`P3_MAPPING_REVIEW=BLOCKED` com códigos de erro é esperado até haver
documentação contábil/relacional e tenant reais. Não criar respostas sintéticas
para transformar bloqueios em PASS. Se a versão física mudar, criar um novo
snapshot e outra revisão devidamente autorizada: não reaproveitar prova antiga.

## Limites de aceitação

- **Shadow atual:** não trocar `SEMANTIC_AGENT_VERSION`, DSN, modelo/LLM,
  credenciais nem o fluxo publicado.
- **Motor:** não fazer if por cliente, lookup de pergunta nem copiar SQL,
  prompts, filtros de benchmark ou hardcodes do n8n.
- **Segurança:** `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` preservado;
  nenhuma execução financeira, migração, corte ou mudança de permissões.
- **Gates ainda pendentes:** `SETTINGS_DRIFT_REVIEW`, persistência Shadow
  SOURCE, tenant binding, aprovação contábil, paridade Gemini/Gemini,
  portabilidade efetiva, rollback e cutover humano.
- **Testes:** duas estruturas sintéticas de clientes diferentes, colunas
  inválidas, cardinalidade, datas, métricas, fonte/tenant, integridade do
  fingerprint e ausência de autorização operacional.

Este documento especifica revisão de metadados; **não** afirma que a nova
versão esteja pronta para ser carregada no planner.

## Ponte candidata ao contexto — provas independentes

A ponte `p3_semantic_context_candidate.py` exige duas provas distintas. Um
JSON com `status=APPROVED` ou fingerprint recalculado da própria revisão não
comprova homologação. Nada é ativado ou executado.

**Prova física:** o CLI reconstrói a baseline por meio do snapshot P3 privado
`physical-metadata.json`, da política existente e das validações de escopo da
role, sem nova conexão, leitura financeira ou alteração de banco. A revisão
precisa coincidir em banco, schema, role, versão, tabelas, colunas e tipos; o
mapeamento também passa pelo `check_review` do P3 (grão, PK, métricas,
sinais, datas, joins, cardinalidade e bloqueio de fanout).

**Prova contábil:** recibo externo de autoridade autorizada, autenticado por
HMAC-SHA256 e vinculado ao SHA-256 da revisão integral, ao fingerprint físico,
tenant, versão, revisor, data e referência de evidência. O segredo verificador
é independente do autor do mapeamento, com mínimo de 32 bytes. A PR não
implementa emissor de recibos, não provisiona segredo operacional e não
estabelece autorização contábil. Não criar atestações sintéticas para DEMO.

O formato privado do recibo é um objeto com `claims` contendo exatamente
`contract, decision, review_sha256, physical_fingerprint, organization_id,
candidate_version, reviewer_id, approved_at, evidence_ref` e com
`hmac_sha256` calculado sobre a serialização JSON compacta, ASCII e com
chaves ordenadas de `claims`. O contrato deve ser
`p3-accounting-approval-v1`. O segredo não pode ser compartilhado pelo
mesmo agente que cria a revisão.

Somente após aprovação real, o operador poderá fornecer os dois arquivos
privados modo 0600 e a variável de ambiente
`P3_APPROVAL_HMAC_VERIFY_KEY_HEX` por meio de mecanismo secreto adequado,
sem expô-la em histórico de shell, logs ou chat. A execução de validação
offline é:

```bash
cd /docker/agente-sql-langgraph-repo || exit 1
.venv/bin/python -m scripts.operations.p3_semantic_context_candidate \
  --audit-dir /tmp/p3-source-audit.7DIc9fUP \
  --review-file /caminho/privado/revisao-aprovada.json \
  --approval-file /caminho/privado/recibo-de-aprovacao.json
```

Sem prova independente o candidato falha fechado com
`P3_INDEPENDENT_EVIDENCE_REQUIRED`, `P3_INDEPENDENT_APPROVAL_REQUIRED`,
`P3_APPROVAL_SIGNATURE_INVALID`, `P3_APPROVAL_SCOPE_MISMATCH` ou
`P3_SEMANTIC_REVIEW_INCOMPLETE`, entre outros. Com provas válidas:
`CANDIDATE_READY_NOT_ACTIVATED` e fingerprints de candidato, origem,
aprovação e tenant; não persiste, publica ou executa SQL.

A DEMO real permanece em `NEEDS_BUSINESS_APPROVAL`. Os testes usam somente
segredo e contextos sintéticos: dois tenants e esquemas materialmente distintos,
um com DRE opcional e outro sem, perguntas inéditas, drift, versão, tenant,
fanout, recusa semântica, fake SQL e Security/Contract Gates. Isso não prova
paridade financeira. `OFFICIAL=n8n`, `SHADOW=LangGraph` e
`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` permanecem.
