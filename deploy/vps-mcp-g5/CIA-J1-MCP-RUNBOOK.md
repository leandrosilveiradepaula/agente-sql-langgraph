# CIA/J1 — extensão controlada MCP de auditoria somente leitura

## Estado e dependência

Contrato preparado sob [Crypto Intelligence Agent #532](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/532). **Uma PR e CI não atualizam o gateway em execução.** O MCP atual do agente financeiro já opera por túnel e broker Unix, mas não possui ações para o coletor CIA. Não substituir instalação existente nem executar o instalador G5 novamente: este tem checksums fixos e rollback para versão anterior e pode interferir na PR financeira #221, que permanece independente.

Este pacote adiciona três operações *sem parâmetros*:
- `cia_j1_rest_timer_status` — consulta `systemctl show` em nomes fixos; enum/contagem, sem stdout bruto.
- `cia_j1_rest_journal_summary` — janela exata 2026-11-09 19:00 a 2026-11-10 18:30 UTC, 24 linhas JSON de pesquisa, sem símbolos ou logs brutos.
- `cia_j1_rest_sqlite_audit` — abre exclusivamente `/home/cia-probe/agent/j1-rest-m3-20261109/canary/j1-rest-hourly-research.sqlite` em `mode=ro`, `query_only=ON`; confirma 100 candles, 26 publicações, cursores, continuidade e digest por vela sem retornar preços/símbolos.

Separação de papéis: o endpoint MCP aceita apenas operações codificadas; broker root consulta somente arquivos/unidades fixas. **Não recebe caminho, SQL, shell, símbolos, datas, credentials, URLs ou comandos arbitrários.** Não há coleta, escrita, troca do SHA CIA, ordem ou alteração do timer. O code review deve checar que o novo módulo no gateway é root-owned e imutável pelo writer `cia-probe`; o SQLite de pesquisa permanece owner-only.

## Gates antes de instalação (NÃO executar nesta PR)

1. Resolver ou compatibilizar a [PR financeira #221](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/pull/221). Checar revisão de `/opt/agente-financeiro-mcp/{mcp_server.py,operations_broker.py,benchmark_ops.py}`, daemon, socket e SELinux/systemd; **não sobrescrever drift**, hashes pinados ou trabalhos financeiros.
2. CI offline Linux do novo contrato deve PASS no SHA exato. Revisar diferenças e ausência de mutações, bypass de quotas, acesso não autorizado e vazamento de dados.
3. Criar um upgrade *separado*, com backups root-only, checagem SHA dos arquivos realmente instalados, instalação de `crypto_j1_readonly.py` como root `0644`, broker/mcp compatibilizados e rollback automático; parar se o checkout atual estiver sujo. Conferir permissão root para ler o DB 0600 e para `journalctl/systemctl show`; assegurar que a exposição dos resultados não inclui dados financeiros ou de negociação.
4. Solicitar/autenticar gate de implantação da extensão de permissões e reinício de componentes do gateway. A solicitação do usuário neste chat autoriza estudar e implementar o código seguro; **não prova que a ampliação já foi aplicada**.
5. Atualizar catálogo de ferramentas do plugin no ChatGPT; somente após observar os três nomes, chamá-los e conferir resultados. `status=pass` em journal **e** SQLite comprova 24 janelas da amostra N=2, não Top50 crypto-only, 24/7 infinito ou execução comercial.

## Resultados e rollback

Se qualquer operação falhar, retornar somente `status=blocked` e código estático de falha; nunca mostrar traceback, payload Bybit, preços, símbolo, logs, caminho ou SQL. Em caso de falha de rollout, recuperar os três arquivos do backup root-only e reiniciar apenas broker/túnel para manter acesso financeiro existente. Nunca executar `git reset --hard`, desabilitar segurança SQL ou reiniciar coletores CIA para diagnosticar o MCP.

Nesta entrega: **nenhum acesso novo ao SQLite foi instalado na VPS; auditoria final J1 permanece pendente.**
