# P3 — Provisionamento controlado da identidade Shadow por organização

Status: **preparado, não aplicado**. A migration 002 no DEMO foi aplicada e validada separadamente (Supabase version `20261028012939`). Esta etapa **não autoriza** alterar o DSN do LangGraph, n8n, execução SQL financeira, cutover, regras contextuais, nem associar evidências históricas sem `organization_id` a uma organização.

## Pré-condições

- Confirmar a organização de destino através da autorização do Produto, nunca inferir de perguntas, benchmark, nome do projeto Supabase ou do histórico (197 das 200 evidências antigas estão sem `organization_id`).
- Validar que a role `langgraph_shadow` é NOLOGIN e as quatro políticas RLS da migration 002 estão instaladas e sem drift.
- Conectar como administrador apenas ao projeto PostgreSQL DEMO correspondente ao `--project-ref`; `sslmode=verify-full` e CA confiável obrigatórios.
- Usar o CLI apenas na VPS, com permissão root para armazenar a conexão da nova role em diretório privado `0700`, arquivo `0600`.

## Comando de inspeção sem alterações

```bash
cd /docker/agente-sql-langgraph-repo
git fetch origin
git checkout main
git pull --ff-only origin main

.venv/bin/python scripts/operations/p3_shadow_tenant_login.py \
  --project-ref cenhadslwxgykqtuobgc \
  --organization-id ORGANIZATION_ID_AUTORIZADO
```

O programa solicita **somente no terminal da VPS** o DSN admin DEMO com entrada oculta; nunca enviar credenciais ou saída bruta de erros PostgreSQL ao ChatGPT. O comando acima não cria role nem binding.

## Gate separado: criação da credencial

Depois de autorização explícita para uma organização **identificada e aprovada**, usar o mesmo comando acrescentando `--apply`. O programa exige confirmação literal `CREATE-SHADOW-LOGIN` e então:

1. Cria o LOGIN exclusivo com senha aleatória SCRAM e privilégios herdados da role `langgraph_shadow`, sem `SET ROLE`, `CREATE`, `DELETE` ou direitos administrativos.
2. Registra o vínculo no catálogo privado `langgraph_internal.shadow_role_tenants` sem modificar registros históricos.
3. Testa login real, uma leitura exclusiva da organização, INSERT e UPDATE de registro sintético e rejeição de INSERT de outra organização; todos os dados de teste são revertidos com rollback.
4. Preserva o DSN no caminho privado exibido como `P3_SECRET_PATH`. Nenhuma troca de ambiente é efetuada.
5. Confere novamente o checksum das 200 evidências.

Se o login for criado mas um teste posterior falhar, a saída marca `P3_ROLE_STATE=CREATED_REQUIRES_RECONCILIATION`: **não repetir `--apply` e não fazer DROP automático**. Corrigir/reconciliar após inspeção e autorização.

## Verificação posterior (sem mudança de DSN)

```bash
.venv/bin/python scripts/operations/p3_shadow_tenant_login.py \
  --project-ref cenhadslwxgykqtuobgc \
  --organization-id ORGANIZATION_ID_AUTORIZADO --verify
```

Somente depois de `P3_SHADOW_LOGIN_VERIFY=PASS`, ausência de drift e teste correlacionado Produto/n8n/Shadow, pedir autorização independente de mudança de `LANGGRAPH_SHADOW_DATABASE_DSN`, com rollback controlado. `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` continua obrigatório.

**Provas já existentes:** PR #181 (política tenant-bound), `scripts/validation/test_shadow_tenant_rls_postgres.py` executado em PostgreSQL descartável, e migração de evidências 200/200 com checksum `5a2dd8dbe09c6f21b4fd8260e34dbced`. Este runbook não declara teste de login real no DEMO antes de executá-lo.
