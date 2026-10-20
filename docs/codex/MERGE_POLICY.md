> **Decisão operativa de 2026-10-19 — gate humano neste projeto:**
> a política de delegação antiga abaixo permanece como histórico de microetapas.
> Para Agente Financeiro, **não fazer auto-merge** de PRs sem autorização
> explícita do operador. CI verde não permite cutover, deploy, migrations,
> atualização de n8n, acesso adicional ou execução SQL real. Preparar PR,
> revisar diff/CI e solicitar merge humano. Regras gerais do Factory não
> sobrepõem este gate. Consulte `AGENTS.md` e
> `docs/architecture/PORTABILITY-AND-CUTOVER-CONTRACT.md`.

---

# MERGE_POLICY

## Regra atual: merge humano obrigatório

O assistente pode inspecionar GitHub, criar branch/PR, rodar CI, corrigir
arquivos e preparar a revisão. **Não executar o merge sem autorização
explícita nesta tarefa.** A autorização para merge não inclui deploy,
alteração de n8n, cutover, banco, credenciais nem privilégios.

## Autoridade de merge — delegação histórica (não vigente)

O usuario delega ao ChatGPT/revisor tecnico a decisao operacional de merge das microetapas deste projeto.

O ChatGPT pode aprovar e executar merge sem solicitar nova confirmacao a cada PR somente quando todos os gates abaixo forem satisfeitos:

1. o PR remoto existe e o HEAD remoto foi confirmado;
2. o diff foi revisado no GitHub e esta dentro do escopo definido em `docs/codex/CURRENT_TASK.md`;
3. nao ha hardcode `FORBIDDEN` novo e qualquer `TRANSITIONAL` esta explicitamente identificado;
4. os testes exigidos pela tarefa passaram;
5. os checks obrigatorios do GitHub passaram;
6. nao ha conflito de merge;
7. nao ha mudanca implicita de arquitetura, privilegios ou escopo;
8. nenhuma alteracao inclui deploy, Supabase, n8n, Watson, PROD, credenciais ou ambiente externo sem autorizacao explicita separada.

Se qualquer gate falhar, o merge deve ser bloqueado e a correcao deve ser solicitada antes de nova avaliacao.

## Limite da delegacao historica

Esta delegacao vale para merge de codigo no repositorio. Ela nao autoriza deploy, cutover, alteracao de Supabase, n8n, Watson, PROD, credenciais, permissoes ou qualquer execucao externa. Essas acoes continuam exigindo autorizacao explicita e separada.

## Principio

O usuario nao deve atuar como ponte operacional entre ChatGPT, Codex e GitHub. O revisor tecnico deve consultar diretamente o GitHub, avaliar qualidade, decidir merge conforme os gates acima e registrar a evidencia correspondente.
