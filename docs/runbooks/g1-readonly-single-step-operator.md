# G1 — operação única de credencial PostgreSQL somente leitura

Este runbook é executado **somente na VPS autorizada**, depois da aprovação da PR. Ele não integra o runtime LangGraph e não altera o fluxo oficial por si só.

```bash
git pull --ff-only
export PGSSLROOTCERT=/root/.local/share/agente-sql-langgraph/supabase-ca.crt
.venv/bin/python scripts/operations/g1_readonly_rollout.py --dry-run \
  --n8n-url https://<n8n-autorizado> --project-ref <referencia-do-projeto>
```

**Não iniciar com `--apply`.** Somente depois de todos os gates, da
remediação autorizada de privilégios globais (se necessária) e da
revisão de rollback, executar:

```bash
.venv/bin/python scripts/operations/g1_readonly_rollout.py --apply \
  --n8n-url https://<n8n-autorizado> --project-ref <referencia-do-projeto>
```

O programa pede a chave da API n8n e o DSN administrador em terminal sem eco; qualquer mutação depende da confirmação `APPLY-G1`. Nunca passe segredos por argumento, arquivo, Git ou chat. O DSN requer `sslmode=verify-full`. A senha é aleatória, fica apenas na memória e entra só na nova credencial privada n8n; o DDL usa verificador SCRAM calculado localmente, não a senha.

Antes de mutar, a ferramenta valida workflow publicado, 68 nós, versão homologada, webhook, referências dos dois nós, fingerprint, schema de credencial n8n, TLS, database, objetos permitidos, `PUBLIC`, funções `SECURITY DEFINER` e inexistência do papel. Depois de criar o papel, valida pelo pooler `current_user`, read-only, acesso SELECT e privilégios proibidos antes de mudar o n8n. Qualquer divergência falha fechada.

O snapshot privado fica em `~/.local/state/agente-sql-langgraph/` (`0700/0600`) e nunca deve ir para GitHub. A saída só tem `G1_ROLE`, `G1_N8N_BINDINGS` e `G1_ROLLBACK`.

## Preflight real: privilégio TEMPORARY herdado de PUBLIC (25/10/2026)

**Evidência operacional na VPS:** o preflight da PR #171 retornou
`G1_N8N_BINDINGS=PREFLIGHT:0eee554daf77` e `G1_ROLE=NOT_APPLIED`
após conexão TLS verificada com a CA do Supabase. A verificação adicional,
executada no **banco real** antes de qualquer alteração, confirmou
`G1_PUBLIC_TEMPORARY=TRUE`, `G1_PUBLIC_DATABASE_CREATE=FALSE`,
`G1_PUBLIC_ACL_CHECK=PASS`.

**Consequência:** o `--apply` da versão anterior seria bloqueado depois de
tentar criar a role, porque `assert_role_effective_permissions` rejeita
`TEMPORARY`. A partir desta correção, o `--dry-run` e o `--apply`
rejeitam `PUBLIC TEMPORARY`/**CREATE** **antes de CREATE ROLE e antes de
POST/PUT de credenciais/workflows n8n**. Se aparecer
`ERROR=PUBLIC tem TEMPORARY; bloquear G1 antes de criar role`,
**não execute `--apply`**. O snapshot e os vínculos originais permanecem
inalterados. O preflight não cria uma role simulada: a verificação de outros
privilégios efetivos continua sendo necessária após a criação.

O PostgreSQL concede privilégios de `PUBLIC` a **todas** as roles, inclusive
roles `NOINHERIT` criadas no futuro. `REVOKE TEMPORARY ... FROM finance_g1_readonly`
**não elimina** o grant de `PUBLIC`. Configurar
`default_transaction_read_only=on` tampouco remove esse privilégio.
A referência oficial explica o risco:
[Supabase — custom role inherits privileges that were not explicitly granted](https://supabase.com/docs/guides/troubleshooting/custom-role-inherits-privileges-that-were-not-explicitly-granted-ddaa1c).

**Possível remediação de privilégios (NÃO AUTORIZADA por este runbook):**
`REVOKE TEMPORARY ON DATABASE postgres FROM PUBLIC` alteraria a
configuração **de todo o banco Supabase**, não apenas do agente. Antes de
considerá-la, inventariar as roles de conexão e workloads que dependem de
tabelas temporárias, grants explícitos alternativos, dependências do Supabase,
plano de restauração e impacto sobre outros serviços. Uma transação com
grants compensatórios para roles justificadas pode ser proposta **somente após
aprovação específica da alteração global**; não executar automaticamente,
não revogar permissões de terceiros e não enfraquecer gates para passar no teste.
Outra arquitetura de isolamento exige desenho, autorização e homologação
próprios. ACL catalogal mostra **permissões**, não comprova o uso real
de tabelas temporárias pelos serviços.

### Reexecutar diagnóstico seguro após uma remediação autorizada

1. Preservar o arquivo CA oficial em caminho privado da VPS. Para
   `sslmode=verify-full`, usar `export PGSSLROOTCERT=/root/.local/share/agente-sql-langgraph/supabase-ca.crt`
   na sessão do operador; não desabilitar TLS ou verificação de hostname.
2. Usar o Python isolado `.venv/bin/python` com `psycopg[binary]==3.3.4`.
3. Executar **apenas** `--dry-run` com a mesma origem n8n, projeto e DSN
   via `getpass`. Verificar a versão publicada e o novo fingerprint.
4. Prosseguir ao `--apply` apenas se os gates forem positivos **e**
   os requisitos de autorização/rollback de G1 permanecerem atendidos.

## Verificação e rollback

```bash
.venv/bin/python scripts/operations/g1_readonly_rollout.py --verify \
  --n8n-url https://<n8n-autorizado> --project-ref <referencia-do-projeto>

.venv/bin/python scripts/operations/g1_readonly_rollout.py --rollback \
  --n8n-url https://<n8n-autorizado> --project-ref <referencia-do-projeto>
```

O rollback pede `ROLLBACK-G1`, compara o workflow vigente com o snapshot e restaura somente os dois bindings. Se houver concorrência, não faz PUT. Papel e credencial são preservados para revisão: não há `DROP` automático. Não toque em outros nós, `Postgres account`, Shadow, Gemini, migrations ou banco fora desta operação.

Sem acesso autorizado à VPS, n8n e Supabase, não execute modos mutáveis. A PR contém somente código, testes offline e rollback controlado; não comprova rollout nem execução G1 correlacionada.


## Correção n8n 2.4.8 — API de credenciais

A versão **exata** `n8n@2.4.8` tem `POST /api/v1/credentials` e
`GET /api/v1/credentials/schema/postgres`, mas **não** oferece
`GET /api/v1/credentials` nem `GET /api/v1/credentials/{id}`.
O procedimento valida a identidade antiga nos dois nós da versão publicada,
confirma `id`/`name`/`type` na resposta ao **POST** da nova credencial e
verifica os novos vínculos pelo **GET do workflow publicado** depois do PUT.
Não lê nem tenta descriptografar credenciais existentes.

O campo nativo de segurança TLS do Postgres no n8n 2.4.8 é
`allowUnauthorizedCerts=false` (e `ssl=require`), **não**
`ignoreSSLIssues`. A configuração do rollout fixa o nome físico correto.
Se o schema de credencial retornado pelo n8n divergir, o procedimento
**interrompe antes de criar a role ou alterar o fluxo**.

A criação da credencial pelo endpoint público vincula a credencial ao projeto
pessoal do usuário dono da chave API. Se a credencial não puder ser utilizada
pelo projeto do workflow, a publicação/validação deve falhar sem declarar o
rollout concluído; não contornar por alteração de permissões de terceiros.
A equivalência financeira G1 permanece bloqueada até uma validação
operacional do executor real.

## Notas obrigatórias da revisão de segurança

- A origem dos parâmetros não secretos da nova conexão é o DSN administrativo digitado privadamente na VPS, que precisa apontar para o pooler Supavisor do projeto DEMO correto, com `sslmode=verify-full`. A API pública do n8n não expõe `data` da credencial antiga; o programa não tenta recuperá-lo.
- O nome de usuário criado no n8n é `finance_g1_readonly.<project-ref>`; o papel PostgreSQL permanece `finance_g1_readonly`. A conexão da role nova é testada antes de alterar qualquer vínculo n8n.
- O n8n real deve ser exatamente versão 2.4.8, comprovada pelo CLI do contêiner Docker. O payload `PUT` contém apenas campos públicos editáveis; `meta`, `pinData` e settings retidas pelo servidor nunca são reenviadas.
- O banco pode conceder `TEMPORARY` e outros privilégios a `PUBLIC` por padrão. Se o preflight detectar privilégios incompatíveis com o contrato SELECT-only, **ele deve interromper a operação sem revogar grants globais e sem alterar terceiros**. Isso será reportado como bloqueio, não como sucesso.
- A criação do papel e os grants ocorrem em uma transação. Se uma etapa posterior falhar, o status deixa explícito que a role e/ou a credencial podem existir sem estar vinculadas; nenhuma conta é excluída automaticamente.
- `--verify` consulta novamente grants efetivos e configurações da role pelo DSN administrativo. Não recupera a senha da role armazenada no n8n. `--rollback` retorna somente os dois nós à credencial original, sempre depois de confirmar que não houve drift nos outros 66.
- O snapshot privado pode conter configuração sensível que já existia no workflow legado; nunca o publique em Git, issue, log ou mensagem. Se houver erro depois da tentativa de PUT, verifique a identidade publicada antes de tentar repetir o comando.

**Critério de homologação:** CI verde não prova rollout real. Manter Shadow desativado e execução SQL Shadow bloqueada até receber confirmação explícita dos gates G1.
