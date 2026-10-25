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


## Notas obrigatórias da revisão de segurança

- A origem dos parâmetros não secretos da nova conexão é o DSN administrativo digitado privadamente na VPS, que precisa apontar para o pooler Supavisor do projeto DEMO correto, com `sslmode=verify-full`. A API pública do n8n não expõe `data` da credencial antiga; o programa não tenta recuperá-lo.
- O nome de usuário criado no n8n é `finance_g1_readonly.<project-ref>`; o papel PostgreSQL permanece `finance_g1_readonly`. A conexão da role nova é testada antes de alterar qualquer vínculo n8n.
- O n8n real deve ser exatamente versão 2.4.8, comprovada pelo CLI do contêiner Docker. O payload `PUT` contém apenas campos públicos editáveis; `meta`, `pinData` e settings retidas pelo servidor nunca são reenviadas.
- O banco pode conceder `TEMPORARY` e outros privilégios a `PUBLIC` por padrão. Se o preflight detectar privilégios incompatíveis com o contrato SELECT-only, **ele deve interromper a operação sem revogar grants globais e sem alterar terceiros**. Isso será reportado como bloqueio, não como sucesso.
- A criação do papel e os grants ocorrem em uma transação. Se uma etapa posterior falhar, o status deixa explícito que a role e/ou a credencial podem existir sem estar vinculadas; nenhuma conta é excluída automaticamente.
- `--verify` consulta novamente grants efetivos e configurações da role pelo DSN administrativo. Não recupera a senha da role armazenada no n8n. `--rollback` retorna somente os dois nós à credencial original, sempre depois de confirmar que não houve drift nos outros 66.
- O snapshot privado pode conter configuração sensível que já existia no workflow legado; nunca o publique em Git, issue, log ou mensagem. Se houver erro depois da tentativa de PUT, verifique a identidade publicada antes de tentar repetir o comando.

**Critério de homologação:** CI verde não prova rollout real. Manter Shadow desativado e execução SQL Shadow bloqueada até receber confirmação explícita dos gates G1.
