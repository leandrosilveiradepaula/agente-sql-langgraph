# Gateway MCP da VPS — capacidades G5 (escopo fixo)

Esta atualização **não** cria outro túnel, aplicação, workflow n8n nem nova chave.
Amplia apenas o MCP já instalado (`agente-mcp` + broker root via socket Unix
`/run/agente-financeiro-mcp/operations.sock`). Os originais são copiados para
backup privado e o instalador realiza rollback se os serviços não voltarem.

## Ferramentas novas

| MCP | Operação permitida |
|---|---|
| `sync_approved_langgraph_main(expected_sha)` | Atualização somente fast-forward da branch `main` do repositório fixo, **apenas** se o SHA informado corresponde exatamente ao remoto; sem checkout de outra branch, sem shell, sem deploy |
| `g5_benchmark_preflight()` | Valida checksum SHA256 do backup G5 e imagem PostgreSQL 17 local, sem descriptografar |
| `g5_benchmark_recover_once()` | Uma recuperação das **duas tabelas legadas de avaliação** em PostgreSQL descartável, sem rede; exige senha colocada localmente em arquivo root-only de uso único |
| `g5_benchmark_recovery_status()` | Retorna apenas contagens e condições dos quatro arquivos privados, nunca conteúdo SQL, respostas ou senha |

Operações anteriores de diagnóstico continuam. O importador de evidence-read
já existente **não é substituído**. O gateway não recebe shell root genérico,
comando SQL, DSN, chave ou parâmetros de filesystem livres, aprovação automática
de query reparada, publicação n8n ou cutover.

## Passo único de instalação (após PR merge e CI aprovado)

Execute **no SSH da VPS** (a `main` precisa estar limpa):

```bash
cd /docker/agente-sql-langgraph-repo && \
  git fetch -q origin && git checkout -q main && git pull --ff-only -q origin main && \
  bash deploy/vps-mcp-g5/install_mcp_g5_once.sh
```

Não é necessário baixar ZIP ou configurar outro tunnel ID. O instalador exige
que os dois componentes atuais e a unidade systemd correspondam exatamente à
versão já homologada; se houver drift, bloqueia sem modificar.

A saída exigida inclui:

```text
G5_MCP_INSTALL=PASS
G5_MCP_BROKER=PASS
G5_MCP_TUNNEL=PASS
ARBITRARY_SHELL=DENIED
FINANCIAL_SQL_EXECUTION=DENIED
```

Atualize a lista de ferramentas do plugin `Agente Financeiro VPS` em
**Configurações → Plugins → Agente Financeiro VPS → Atualizar ferramentas**.
A atualização no app pode exigir uma nova conversa para refletir as ações.

## Como recuperar o G5 sem entregar a senha ao ChatGPT

O ChatGPT deve chamar primeiro `sync_approved_langgraph_main` (caso o checkout
não esteja na versão desejada), depois `g5_benchmark_preflight`. Só quando
`status=pass` o operador deve provisionar a senha **uma vez** no terminal VPS:

```bash
( umask 077; \
  read -r -s -p 'Senha local do backup G5: ' G5_PASS; printf '\n'; \
  printf '%s' "$G5_PASS" > /run/agente-financeiro-mcp/g5-benchmark-passphrase.once; \
  unset G5_PASS; \
  chown root:root /run/agente-financeiro-mcp/g5-benchmark-passphrase.once; \
  chmod 600 /run/agente-financeiro-mcp/g5-benchmark-passphrase.once; \
  echo 'ONE_SHOT_SECRET_READY=YES' )
```

O arquivo está em `/run` (tmpfs), com `0600` root, e nunca é exposto ao usuário
`agente-mcp`, ao ChatGPT, ao túnel, ao GitHub ou a argumentos/env/logs de
subprocessos. O broker o lê e o **exclui antes da descriptografia**, mesmo se a
validação falhar. Uma falha de senha exige repetir somente este passo.

Depois, o ChatGPT chama `g5_benchmark_recover_once()` e
`g5_benchmark_recovery_status()`. Os resultados históricos e a SQL oficial
ficam somente em `/root/.local/share/agente-sql-langgraph/benchmark-private/`
com arquivos `0600` e diretórios `0700`. O retorno MCP inclui contagens e
status, não dados. O mecanismo original continua proibindo SQL financeira e
chamadas à LLM durante a recuperação.

## Condições de segurança e limites

- `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.
- `repo_sync` usa `git fetch` em `origin/main` validado contra a URL exata do
  repositório, confere SHA e ancestralidade e faz apenas fast-forward, sem hooks.
- `benchmark_recover` exige que o recuperador original ainda seja um descendente
  do merge aprovado e tenha o **Git blob SHA imutável** revisado. Mudanças
  naquele script causam bloqueio até nova revisão explícita.
- O serviço usa `ProtectSystem=strict` com escrita somente no checkout conhecido,
  no diretório privado de resultados e em `/run` para locks/segredo de uso único.
  `ProtectHome=read-only` permite ler o arquivo G5 original, mas não gravar
  em outros diretórios de `/root`. Docker sem volumes e sem rede é validado
  pelo recuperador G5 existente.
- Operações podem ser negadas pela própria plataforma ChatGPT mesmo quando o
  broker as permite; isso não deve ser contornado.
- O `--plan` **não prova a presença das 63 linhas**. Somente `--recover` com
  cópia íntegra e execução histórica completa poderá fazê-lo. O benchmark
  oficial segue como avaliação posterior, fora do prompt gerador.
- Backup anterior mantido em
  `/opt/agente-financeiro-mcp/backup-before-g5-mcp/` para rollback controlado;
  não eliminar esse diretório sem revisão operacional.

## Administrator-enabled MCP — one-time upgrade

The operator authorized broad VPS administration from ChatGPT so day-to-day
work does not require copy/pasting SSH commands. This extends the **existing**
tunnel and Unix-socket broker; no second tunnel, agent or third-party host.

After the PR containing this feature is reviewed and merged, the current MCP
**cannot bootstrap itself** because its previously installed source only
recognizes a fixed command allowlist. The bridge must be upgraded **once**
from an authorized VPS console, using the tracked main checkout:

\`\`\`bash
cd /docker/agente-sql-langgraph-repo &&
git fetch -q origin main &&
git merge --ff-only origin/main &&
bash deploy/vps-mcp-g5/upgrade_vps_admin_once.sh
\`\`\`

This is not a recurring workflow. It preserves unrelated local untracked
files, verifies the currently installed MCP gateway and broker blob identities,
backs up the originals, installs only the broker + gateway + admin module +
service-unit upgrade, restarts the existing broker and tunnel, probes both
short commands and a durable \`systemd-run\` job, and rolls back on failure.

Then refresh the **Agente Financeiro VPS** plugin tools in ChatGPT. These four
new tools should appear:

| Tool | Purpose |
|---|---|
| \`vps_exec(argv, cwd, timeout_seconds, show_output)\` | Execute a named absolute-path binary with a bounded runtime (maximum 120 seconds), sanitised tail output and command hash |
| \`vps_start_job(argv, cwd, timeout_seconds)\` | Launch longer operations through transient systemd units, up to 4 hours, with a root-private durable job ID |
| \`vps_job_status(job_id, show_output)\` | Retrieve completion code and bounded output, including after MCP reconnect |
| \`vps_cancel_job(job_id)\` | Stop a specific running job, preserving its audit receipt |

The plugin exposes **administrative privilege on the VPS**. Use only in the
operator-owned project and never share this connection with another tenant.
Its root broker verifies the local \`agente-mcp\` UID over \`SO_PEERCRED\`;
command argv and output are **not included in the audit log**, which records
only digests, timestamps and exit codes. Output is redacted and bounded, but
arbitrary command output is not guaranteed secret-free, so commands that
print tokens, DSNs, cookies or private SQL must not be requested. Job
records and output are root-only under
\`/var/lib/agente-financeiro-mcp-admin\`.

The administrative privilege is **not** an implicit authorization to do
production cutover, destructive SQL, schema/credential migration, expanded
cloud cost, security-policy change or deployment. Such actions still require
the corresponding explicit operator gate. The main financial engine safety
flag remains \`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false\` until separately
approved, and \`OFFICIAL=n8n\` is unchanged.

After upgrade, ChatGPT should use \`vps_exec\` to refresh \`main\` without
deleting the untracked \`p3_migrate_shadow_evidence.py\`, verify the exact
tenant/provider/model for the LangGraph SQL-InfoDive replay and run the
offline preflight. Only with explicit private-model call authorization
should it invoke the 63-case benchmark as a persistent job. Never rerun
the 63 historic official n8n/Gemini calls.
