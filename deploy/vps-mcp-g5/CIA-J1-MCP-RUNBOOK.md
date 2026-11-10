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

## Upgrade consolidado pronto para homologação (sem execução na VPS)

O script `upgrade_cia_j1_readonly_once.sh` é uma operação root one-shot de deploy, não uma ferramenta do MCP. Ele faz preflight dos hashes Git dos componentes instalados do broker/túnel, aceita apenas as revisões G5 anterior ou atual do módulo `benchmark_ops.py`, usa fontes fixadas no merge `26b9b8fa9b3f5a027fb82199c8bc77dc7f83734e` e valida SHA Git blob antes de qualquer substituição. Faz backup privado, instala apenas `mcp_server.py`, `operations_broker.py`, `crypto_j1_readonly.py`, reinicia broker/túnel e exige provas do socket e da readiness; rollback automático se falhar. O módulo financeiro nunca é sobrescrito. `upgrade_g5_diagnostics_once.sh` também aceita o novo hash do broker para preservar a evolução paralela sem resetar checkout.

**Gate adicional real:** o ChatGPT conectado hoje não dispõe de nenhuma ação para executar um instalador root no host; o MCP expõe somente operações finitas G5/financeiras. Portanto esse script **NÃO FOI EXECUTADO**, mesmo que a PR passe e seja mesclada. Implantar sem operador ou sem uma action de rollout previamente autorizada é impossível com este conector, não uma falha de teste. A ampliação das ferramentas do plugin exige atualizar/recarregar o catálogo após restart do túnel.

**Operação futura sob gate de autorização para ampliar acesso**: em SSH root no servidor correto, apenas com hashes compatíveis e ambiente não perturbado, verificar que a PR de upgrade foi integrada com CI verde, obter o script de `deploy/vps-mcp-g5/upgrade_cia_j1_readonly_once.sh` a partir do SHA conferido do merge e executá-lo uma única vez. Não baixar/rodar branch móvel, não executar código da PR aberta e não modificar o timer CIA. Não solicitar esse comando a quem está no celular agora.

### Escopo de prova
- Tests e CI = software preparado, sem comprovação VPS.
- Upgrade PASS + refresh ChatGPT = capabilities realmente expostas.
- `cia_j1_rest_journal_summary.status=pass` **e** `cia_j1_rest_sqlite_audit.status=pass` = prova da janela finita 24 rodadas N=2.
- O timer não foi projetado como serviço 24/7 infinito, e nenhuma etapa libera ordens, sinal ou Top50.

O operador consegue reverter o bridge apenas por restauração dos arquivos do backup root-only caso seja necessário; o script faz rollback automático em falhas ocorridas durante sua execução.
