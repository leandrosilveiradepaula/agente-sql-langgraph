# Atualização pontual do diagnóstico G5 — sem modificar checkout

## Motivo e limite

A PR #220 foi incorporada à `main` em
`f3edfba09b687d088a2a4b35dcdc3a66f63bae54`, com Windows/Linux PASS
([run 42852375456](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/actions/runs/42852375456)).
O MCP instalado segue na revisão anterior e devolve
`g5_benchmark_preflight = blocked/command_failed` e
`g5_benchmark_recovery_status = blocked/recovery_snapshot_missing_or_ambiguous`.

O Git do servidor está sujo (`repo_not_clean`); **não limpar, resetar, trocar
branch ou perder evidências locais**. `sync_approved_langgraph_main` não
realiza deploy para `/opt/agente-financeiro-mcp`, mesmo com checkout limpo.
O instalador G5 original é one-shot e **não deve ser repetido**.

O novo utilitário `upgrade_g5_diagnostics_once.sh` atualiza **somente**
`/opt/agente-financeiro-mcp/benchmark_ops.py`, diretamente da revisão
GitHub imutável do merge #220. O Git do servidor é usado apenas para calcular
hashes de arquivos; seu checkout não é acessado nem modificado.

## Verificações e rollback

- Exige root, broker/túnel ativos e binários instalados.
- Verifica Git blob SHA do broker, unidade systemd e módulo pré-atualização.
- Baixa apenas o módulo revisado, do **commit imutável** `f3edfba...`,
  com TLS e conferência exata do Git blob SHA antes de instalar.
- Preserva o módulo anterior num backup dedicado root-only.
- Reinicia somente o serviço `agente-financeiro-mcp-ops.service`,
  **não** o túnel, n8n, Docker, LangGraph, Produto ou Supabase.
- Exige prova no socket Unix como usuário `agente-mcp` com os comandos
  `benchmark_plan` e `benchmark_status`; bloqueia a antiga classificação
  genérica `command_failed` e verifica que o túnel segue ativo.
- Se a instalação ou prova falhar, restaura a cópia anterior e reinicia
  novamente o broker. O backup é retido para auditoria.

O utilitário **não está executado na VPS** e precisa de implantação autorizada
do próprio utilitário antes de ser invocado; o MCP atual não possui uma
capacidade para copiar/instalar/reiniciar o broker e não se deve ampliar o
escopo por meio de n8n, imports ou comandos shell arbitrários.

## Após a implantação

O ChatGPT chama `g5_benchmark_preflight()` e
`g5_benchmark_recovery_status()` via MCP, esperando falha específica segura,
ou `pass`. Só após preflight `pass` a recuperação das 63 perguntas poderá
ser analisada. O segredo do backup cifrado permanece exclusivamente na VPS,
nunca no ChatGPT ou Github.

Sem ativar SQL financeira, LLM, banco, n8n oficial, cutover ou migrações.
A atualização não prova que o arquivo G5 contenha 63 casos.
