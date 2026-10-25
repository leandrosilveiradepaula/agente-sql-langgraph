# G1 — operação única de credencial PostgreSQL somente leitura

Este runbook é executado **somente na VPS autorizada**, depois da aprovação da PR. Ele não integra o runtime LangGraph e não altera o fluxo oficial por si só.

```bash
git pull --ff-only
python3 scripts/operations/g1_readonly_rollout.py --apply \
  --n8n-url https://<n8n-autorizado> --project-ref <referencia-do-projeto>
```

O programa pede a chave da API n8n e o DSN administrador em terminal sem eco, somente após preflight e a confirmação `APPLY-G1`. Nunca passe segredos por argumento, arquivo, Git ou chat. O DSN requer `sslmode=verify-full`. A senha é aleatória, fica apenas na memória e entra só na nova credencial privada n8n; o DDL usa verificador SCRAM calculado localmente, não a senha.

Antes de mutar, a ferramenta valida workflow publicado, 68 nós, versão homologada, webhook, referências dos dois nós, fingerprint, schema de credencial n8n, TLS, database, objetos permitidos, `PUBLIC`, funções `SECURITY DEFINER` e inexistência do papel. Depois de criar o papel, valida pelo pooler `current_user`, read-only, acesso SELECT e privilégios proibidos antes de mudar o n8n. Qualquer divergência falha fechada.

O snapshot privado fica em `~/.local/state/agente-sql-langgraph/` (`0700/0600`) e nunca deve ir para GitHub. A saída só tem `G1_ROLE`, `G1_N8N_BINDINGS` e `G1_ROLLBACK`.

## Verificação e rollback

```bash
python3 scripts/operations/g1_readonly_rollout.py --verify \
  --n8n-url https://<n8n-autorizado> --project-ref <referencia-do-projeto>

python3 scripts/operations/g1_readonly_rollout.py --rollback \
  --n8n-url https://<n8n-autorizado> --project-ref <referencia-do-projeto>
```

O rollback pede `ROLLBACK-G1`, compara o workflow vigente com o snapshot e restaura somente os dois bindings. Se houver concorrência, não faz PUT. Papel e credencial são preservados para revisão: não há `DROP` automático. Não toque em outros nós, `Postgres account`, Shadow, Gemini, migrations ou banco fora desta operação.

Sem acesso autorizado à VPS, n8n e Supabase, não execute modos mutáveis. A PR contém somente código, testes offline e rollback controlado; não comprova rollout nem execução G1 correlacionada.
