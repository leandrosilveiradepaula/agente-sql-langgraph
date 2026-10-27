
## G1 parcialmente criado: reconciliação de um POST n8n ambíguo (27/10/2026)

**Caso real confirmado:** o --apply retornou G1_ROLE=CREATED,
G1_N8N_BINDINGS=NOT_APPLIED, G1_ROLLBACK=ROLE_RETAINED_FOR_REVIEW
e ERROR=n8n API indisponivel ou resposta inesperada.
O código da chamada indica falha no POST /api/v1/credentials **antes**
da confirmação da identidade da credencial. A role foi persistida, mas
não sabemos se a credencial chegou a ser gravada no n8n. A senha gerada
pelo processo original não deve ser inferida nem recuperada de logs.

**Jamais repetir --apply neste estado.** Não executar --verify nem
--rollback sem o snapshot aplicável. Não fazer PUT dos dois nós,
não remover a role, não alterar senhas ou credenciais por tentativa.

Após merge humano da correção, executar somente o inventário abaixo
na VPS, dentro do checkout sincronizado:

~~~bash
cd /docker/agente-sql-langgraph-repo
git fetch -q origin && git checkout -q main && git pull --ff-only -q origin main
.venv/bin/python scripts/operations/g1_partial_reconcile_readonly.py \
  --n8n-url https://n8n.srv1319424.hstgr.cloud
~~~

O script exige **n8n 2.4.8** e lê o workflow oficial com a chave de API
digitada sem eco. Faz ainda uma única exportação de credenciais **cifradas**
por CLI dentro do contêiner (n8n export:credentials --all), captura a
saída somente na memória do processo Python, extrai a **contagem** de
credenciais Postgres com prefixo de nome controlado pelo rollout e descarta
todos os dados, inclusive cifras. **Nunca** utilizar --decrypted,
redirecionar o JSON bruto a disco, imprimir/exportar tokens ou arquivos
com segredos. Se a leitura do CLI falhar ou houver formato desconhecido,
o inventário falha fechado, sem inferir ausência de credencial.

Verificações emitidas sem segredos:

- G1_RECONCILE_MODE=READ_ONLY
- G1_CREDENTIAL_MATCHES=0|1|N (contagem da instância; não garante que
  a credencial esteja correta ou utilizável pelo workflow)
- G1_N8N_BINDINGS=OLD_BINDINGS_CONFIRMED
- G1_WORKFLOW_FINGERPRINT=prefixo_SHA256
- G1_SNAPSHOT=ABSENT
- G1_RECOVERY=... — decisão de **não aplicar** automaticamente

Qualquer correspondência exige análise de credencial órfã, autoria e
usabilidade pelo projeto n8n antes de ligação. Mesmo com
G1_CREDENTIAL_MATCHES=0 não se autoriza repetir o POST com role já existente:
o segredo original não é recuperável; projetar recuperação com rotação
controlada, confirmação de ausência/duplicação, snapshot e rollback humano.
A recuperação mutável é gate posterior ao inventário, não parte dele.

A correção no transporte da API passa a preservar **somente o código HTTP**
(por exemplo, HTTP_STATUS_403), sem corpo, cabeçalhos, URL ou segredo.
Ela não altera a requisição nem esclarece retrospectivamente o status
HTTP da tentativa que já falhou.


> **P3/G1 — estado real em 26/10/2026:** a compensação de
> `PUBLIC TEMPORARY` foi **aplicada e verificada** no Supabase financeiro
> DEMO, com 35 roles preservadas e 32 compensadas. O preflight G1 passou.
> O primeiro `--apply` confirmado foi revertido ao detectar um privilégio
> de modificação; auditoria catalogal real comprovou um único caso:
> **`pg_catalog.pg_settings` — view de configuração de sessão com `UPDATE`
> recebido de `PUBLIC`**. A role G1 e seu snapshot não existem, e não
> houve rebind n8n. Não repetir `--apply` com o código antigo.
>
> O gate corrigido diferencia exclusivamente o `UPDATE` **intrínseco**
> concedido por `PUBLIC` à view de sistema (equivalente a `SET` na sessão);
> qualquer outro DML, inclusive em outros objetos de `pg_catalog`, ou
> grants diretos adicionais para a role, continua proibido. Prova obrigatória
> em PostgreSQL descartável, sem uso de Supabase/LLM. A permissão nativa de
> ajuste da sessão **não equivale a credencial fisicamente incapaz de
> executar UPDATE**: execução financeira requer, separadamente, SQL SELECT
> aprovada, limites, allowlist e transação `READ ONLY` configurada pelo
> executor. Esta PR não autoriza execução de SQL financeira ou cutover.
>
> Após CI verde, merge humano e sincronização da VPS, reconfirmar
> `--dry-run` antes de reexecutar o G1 já autorizado. Se houver falha após
> criação de role, **não** repetir `--apply`: reconciliar role, credencial,
> bindings e snapshot privado. A remediação global anterior tem runbook
> [p3-public-temp-atomic-compensation.md](p3-public-temp-atomic-compensation.md).
>
> Referência PostgreSQL 17:
> [52.24 `pg_settings`](https://www.postgresql.org/docs/17/view-pg-settings.html).

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

### Inventário de impacto read-only antes de qualquer mudança global

O utilitário de plataforma `scripts/operations/g1_public_acl_impact_audit.py`
opera **somente com SELECTs em catálogos PostgreSQL** e define
`SET TRANSACTION READ ONLY` antes de lê-los. Solicita o DSN administrativo
sem eco, valida identidade do projeto, exige `sslmode=verify-full` e não
utiliza credenciais n8n, Gemini, tabelas financeiras ou benchmark. Emite
**apenas contagens e flags**, sem nomes de roles, objetos ou segredos.

```bash
cd /docker/agente-sql-langgraph-repo
export PGSSLROOTCERT=/root/.local/share/agente-sql-langgraph/supabase-ca.crt
.venv/bin/python scripts/operations/g1_public_acl_impact_audit.py \
  --project-ref cenhadslwxgykqtuobgc
```

No caso DEMO, compartilhe somente as linhas `G1_*`. O relatório cobre:
`PUBLIC` no banco (`CONNECT`, `TEMPORARY`, `CREATE`), número de
destinatários explícitos de `TEMPORARY`, quantidade de roles com login
e acesso ao database, sessões ativas, schemas não-sistêmicos com
`PUBLIC USAGE`, relações com `PUBLIC SELECT`/DML, sequences,
funções `SECURITY DEFINER` executáveis por `PUBLIC` e presença da
role alvo. Os grupos são **genéricos e multicliente**, não codificam
tabelas ou regras de negócio.

**Limitação essencial:** contagens e grants do catálogo **não provam**
que um workload precisa ou não criar tabelas temporárias, nem demonstram
a segurança efetiva de uma role futura. A saída sempre será
`G1_AUDIT_RESULT=REVIEW_REQUIRED`; não constitui aprovação automática
de `REVOKE`, `GRANT`, G1 ou cutover. O inventário de dependências dos
serviços e o plano de rollback deverão ser concluídos antes de decidir
entre mudança de ACL global ou separação do banco/serviço de leitura.
Se existirem grants de extensão não revogáveis pelo administrador do
Supabase, não criar exceções nos gates para contorná-los.

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
