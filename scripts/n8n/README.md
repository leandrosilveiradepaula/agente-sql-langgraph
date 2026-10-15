# Isolated n8n → LangGraph Shadow correlation proof

This directory contains a **manual, inactive test workflow** for n8n. Its purpose is to prove that a call originated from an actual n8n workflow can be correlated with a persisted LangGraph Shadow record.

## What this does

1. Manual Trigger creates a fresh synthetic `agent_run_id` associated with the n8n execution.
2. HTTP Request calls `/v1/internal/sql-agent/generate` with an **empty question**.
3. A Code node requires HTTP 422, `INTERNAL_GENERATE_QUESTION_REQUIRED`, no SQL and a `run_id`. Failure terminates the isolated workflow.
4. The second HTTP Request reads `/v1/internal/agent-runs/{agent_run_id}/shadow-runs`.
5. A final Code node requires **exactly one** `generate/rejected` Shadow record with the same identifiers and emits only the correlation identifiers/status.

The empty question is deliberate: the request is rejected before calling any LLM. The only expected database write is an explicitly synthetic, rejected Shadow evidence record. Neither the official n8n workflow nor any business data is modified, and no SQL is executed.

## Preconditions and security gate

- Shadow is healthy and `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.
- n8n can resolve the Shadow Docker address used by the two HTTP Request nodes. Adjust **only the infrastructure hostname** in this isolated test workflow if needed.
- An n8n administrator provisions a **Header Auth** credential **inside n8n's encrypted credential store**: header name `Authorization`, header value `Bearer <Shadow S2S token>`. Never paste that value into the workflow JSON, GitHub, ChatGPT or execution logs. Use an isolated credential with the minimum required scope; avoid exporting credential data.
- Import `shadow_correlation_manual_test.workflow.json` as a **new workflow** through the n8n UI only after explicit authorization to write a new workflow to that instance. It must remain **inactive**. Do not import into, activate, edit, or replace the official finance workflow.
- Link the same secure Header Auth credential to **both** HTTP Request nodes. The intentionally credential-less JSON file should not be executable successfully until this is done.
- Trigger the imported workflow **manually once**. Do not configure a webhook, schedule, or auto-trigger.

The final node must report `result=PASS` with matching IDs; the PR/CI validates only the exported workflow structure, **not** this runtime result. A `401`, `422` mismatch or missing evidence must be investigated; never bypass the security gate or broaden permissions just to make the test pass.

## Cleanup

The isolated workflow can be deleted from the n8n UI by an authorized administrator, independently from the production workflows. The synthetic rejected Shadow evidence remains available for audit under its correlation identifiers; no DELETE is issued.

## Scope

This artifact does **not** prove a production n8n execution has invoked LangGraph, does not enable cutover, and does not modify `SEMANTIC_AGENT_VERSION` or Shadow's LLM selection. It is a separate, controlled integration fixture.


## Audit read-only do workflow oficial (sem cutover)

A prova manual n8n → LangGraph terminou em PASS. Antes de criar qualquer
ramificação no workflow financeiro oficial, é preciso inspecionar **a versão
real exportada da instância n8n**, já que o workflow de teste não mostra onde
entra a pergunta no fluxo financeiro publicado.

Execute na VPS, a partir do checkout deste repositório:

```bash
cd /docker/agente-sql-langgraph-repo
bash scripts/run_n8n_workflow_audit_readonly.sh \
  --match "financeiro" --match "ducklake" --match "sql"
```

A ferramenta executa somente `n8n export:workflow --all` para um arquivo
temporário privado (permissões restritas), copia o arquivo para uma área
temporária privada na VPS e imprime **apenas** nomes sanitizados, IDs, status
e topologia. Não exporta credenciais, não envia parâmetros, código,
SQL, URLs, webhooks, DSNs ou segredos ao ChatGPT/GitHub. Apaga os dois
arquivos brutos ao sair, incluindo em caso de erro.

Caso encontre vários workflows, execute novamente **somente** para selecionar
o ID que corresponde ao workflow publicado:

```bash
bash scripts/run_n8n_workflow_audit_readonly.sh --workflow-id "ID_DO_WORKFLOW"
```

A saída inclui tipos de nós, arestas e flags de revisão de lógica inline.
`review=true` significa apenas **possível hardcode ou comportamento a
revisar**; não demonstra regra FORBIDDEN. As classes STRUCTURAL,
TRANSITIONAL e FORBIDDEN exigem evidência do conteúdo antes de classificação
final. O inventário não transfere conhecimento de negócio ao código novo.

**Limites e gates:** o export contém a versão de workflow da base acessada
pela CLI; confirme pela UI qual workflow e versão estão efetivamente
publicados antes de planejar a inserção. O inventário estrutural não prova
comportamento nem faz deploy. Nenhum workflow oficial é importado, editado,
publicado, despublicado ou executado. A eventual integração deverá ser
assíncrona, isolada e não bloquear/substituir a resposta oficial; n8n continua
OFFICIAL e LangGraph permanece SHADOW com real_sql_execution=false.
