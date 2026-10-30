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

## Ponte candidata para o contrato do motor

Após uma aprovação contábil verificável, a etapa offline
`scripts.operations.p3_semantic_context_candidate.build_candidate` recebe a
revisão privada e uma seção `semantic_context` completa no formato bruto já
consumido por `normalize_context_snapshot`. Ela não completa aliases,
métricas, sinais, períodos, joins, DRE ou regras a partir de nomes físicos.

O adaptador exige, além do fingerprint físico atual:

- `status=APPROVED` e `accounting_approval.status=APPROVED`;
- identidade de organização e proveniência já presentes na revisão;
- catálogo com o conjunto exato de tabelas, colunas e tipos do P3;
- um contrato semântico integral que passe por
  `normalize_context_snapshot` e `validate_context_snapshot`.

Qualquer ausência, ambiguidade, drift físico ou tentativa de ativação retorna
um código estável, incluindo `NEEDS_BUSINESS_APPROVAL`,
`CANDIDATE_CATALOG_PHYSICAL_MISMATCH` ou `CONTEXT_CONTRACT_INVALID`.
O resultado contém `CANDIDATE_READY_NOT_ACTIVATED`; não persiste contexto,
não executa SQL, não chama LLM e não modifica `SEMANTIC_AGENT_VERSION`.

O DEMO atual continua em `NEEDS_BUSINESS_APPROVAL`: o formulário P3 contém
somente metadados físicos, sem definição homologada de métrica, sinal,
agregação, período, relacionamento, granularidade, tenant ou DRE. Portanto,
ele não pode ser promovido usando esta ponte.

`testar_p3_semantic_context_candidate.py` prova offline, em dois esquemas
sintéticos materialmente distintos, que uma revisão externamente aprovada
passa pelo contrato real de contexto, e percorre pergunta inédita → resolução
→ planejamento → gerador fake → Security Gate → Contract Gate. A SQL do fake
é apenas pré-condição técnica de gate; não é resposta de benchmark, não é
enviada a provider e não há execução financeira. O mesmo teste cobre rejeição
de revisão sem aprovação e coluna fora do inventário físico.
