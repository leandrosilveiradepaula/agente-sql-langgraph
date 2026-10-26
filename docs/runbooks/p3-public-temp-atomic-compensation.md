# P3 — Remediação reversível de TEMPORARY e prova financeira read-only

**Estado em 26/10/2026:** P1 e P2 PASS com geração SQL real Gemini. Isto
é um procedimento **candidato**, não autorização para executar SQL financeira,
alterar banco, mudar credenciais n8n ou fazer cutover. A operação automática
`g1_public_temp_preserve_roles.py` foi criada devido a bloqueio real observado
no catálogo PostgreSQL: `PUBLIC TEMPORARY=true` no database DEMO.

## Solução mínima para o bloqueio identificado

PostgreSQL concede `TEMPORARY` a `PUBLIC`, incluindo novas roles NOINHERIT.
Não é possível negar TEMP apenas à nova role enquanto esse grant persistir.
Também não basta configurar `default_transaction_read_only=on` (configurável
pela própria sessão). Não afrouxar os gates do rollout G1 existente.

**Proposta atômica:** numa ÚNICA transação PostgreSQL:

1. Capturar identidades/privilegios efetivos de **todas as roles atuais**
   (LOGIN e NOLOGIN), ACL atual do database, e garantir que
   `finance_g1_readonly` ainda não existe (nome configurável no JSON G1).
2. Remover somente `TEMPORARY` do grantee `PUBLIC` no database definido
   em `g1_readonly_rollout.json`, sem remover `CONNECT` de ninguém.
3. Conceder `TEMPORARY` explicitamente **somente às roles existentes que
   perderam esse direito** por causa da remoção de PUBLIC.
4. Verificar, *antes do COMMIT*, que todas as roles anteriores mantiveram
   exatamente os mesmos privilégios efetivos de `TEMPORARY`, `CONNECT` e
   `CREATE`, que nenhuma role apareceu/desapareceu e que a ACL só mudou
   nesses grants. Qualquer divergência **desfaz toda a transação**.
5. Salvar snapshot privado local `0600`, com status passível de verificação,
   para rollback antes da criação da role dedicada. Não divulgar snapshot,
   grant recipients, credenciais nem DSN.

**Limitação explícita:** o padrão de TEMP para **novas** roles (criadas
no futuro) muda. Provisionadores de novos serviços deverão conceder TEMP
explicitamente *se a aplicação realmente necessitar*. A medida preserva as
roles já existentes, mas não prova que futuros serviços não dependem do grant
padrão. Aprovação humana específica para essa modificação global continua
obrigatória. Não há transação distribuída entre banco e n8n.

## 1. Plano SOMENTE LEITURA (ainda sem qualquer alteração)

Na VPS autorizada:

```bash
cd /docker/agente-sql-langgraph-repo
git fetch origin && git checkout main && git pull --ff-only origin main
export PGSSLROOTCERT=/root/.local/share/agente-sql-langgraph/supabase-ca.crt
.venv/bin/python scripts/operations/g1_public_temp_preserve_roles.py \
  --project-ref cenhadslwxgykqtuobgc
```

Informe o DSN admin apenas pelo prompt `getpass`, com
`sslmode=verify-full`. Saída esperada:
`P3_ACL_PLAN=REVIEW_REQUIRED`,
`P3_ACL_MUTATION=FALSE`, total de roles, proteção existente.
O comando não toca em n8n, executor ou tabelas financeiras.

## 2. ALTERAÇÃO GLOBAL (SOMENTE MEDIANTE AUTORIZAÇÃO ESPECÍFICA)

Após revisar o plano/impacto e receber autorização explícita para a
compensação transacional da ACL global:

```bash
.venv/bin/python scripts/operations/g1_public_temp_preserve_roles.py \
  --project-ref cenhadslwxgykqtuobgc --apply
```

A ferramenta exige o texto `APPLY-P3-ACL` no terminal e escreve apenas
o snapshot privado em `~/.local/state/agente-sql-langgraph/`.
Se houver erro, falha fechada; reconcilie snapshot e catálogo antes de
repetir. Não remover snapshots sem reconciliação.

```bash
.venv/bin/python scripts/operations/g1_public_temp_preserve_roles.py \
  --project-ref cenhadslwxgykqtuobgc --verify
```

**Rollback global:** só possível pela ferramenta enquanto a role G1 e
quaisquer outras novas roles não existirem, e sem deriva de privilégios:

```bash
.venv/bin/python scripts/operations/g1_public_temp_preserve_roles.py \
  --project-ref cenhadslwxgykqtuobgc --rollback
```

Se a role G1 já existir, **não** restaurar `PUBLIC TEMPORARY` enquanto
a credencial read-only estiver ativa; primeiro restaurar os dois bindings
n8n com o rollback G1 existente, desativar/remover a role/credencial
por processo especificamente autorizado, revalidar o catálogo e só então
reavaliar rollback global. A ferramenta rejeita essa condição.

## 3. G1 já existente: apenas depois da mudança global e verificação

Usar o runbook [G1 read-only](g1-readonly-single-step-operator.md) e o
`scripts/operations/g1_readonly_rollout.py --dry-run`. A ferramenta já
existente confirma schema, allowlist, TLS, roles e workflow oficial
publicado de 68 nós antes de modificar qualquer coisa. Após autorização
separada para `--apply`, provisiona a role e troca **somente dois**
bindings PostgreSQL no workflow oficial, com snapshot e rollback.
Nenhum outro nó/credencial é alterado. O reader é exclusivo da execução,
não do contexto semântico.

## 4. Aceite numérico de P3 — prova ainda NÃO executada

Depois de instalar e verificar o reader, com **autorização separada para
execução SQL real exclusivamente SELECT**, comparar:

- SQL aprovada pelo LangGraph na P2, identificada pelo
  `agent_run_id=41d54ee0-b730-41ec-ba69-836d862b1780`,
  `shadow_record_id=shadow-07d311c493efb7383fe0f5e0fc133997`;
  **recuperá-la somente no ambiente privado**, jamais incluí-la em GitHub,
  prompt ou benchmark.
- SQL gerada pelo agente oficial n8n+Gemini para a **mesma pergunta**,
  mesmo recorte/contexto/snapshot de dados; baseline só para avaliação,
  não para informar a geração LangGraph.
- Executar ambas com o mesmo executor estritamente read-only, transação
  `READ ONLY`, limites de tempo/linhas, identidade e allowlist verificadas.
  Reportar contagens, fingerprints, equivalência/ divergência sem divulgar
  resultados financeiros brutos. Exigir um procedimento de aprovação para
  qualquer SQL reparada e registrar autorização e evidência de cada run.

**Não reativar SQL real no Shadow atual** (`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`).
P3 não autoriza cutover, migração, hardcode nem reduzir gates.

## Referências

- [Supabase: custom role inherits privileges granted to PUBLIC](https://supabase.com/kb/troubleshooting/custom-role-inherits-privileges-that-were-not-explicitly-granted).
- [PostgreSQL: privilégios por tipo de objeto](https://www.postgresql.org/docs/17/ddl-priv.html).
- [Roadmap de evidências #155](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/issues/155).
