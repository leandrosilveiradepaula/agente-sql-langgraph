# Private n8n Shadow evidence read relay — inactive candidate

Supplies an authenticated Product -> n8n -> private LangGraph read-only
channel without exposing LangGraph directly to public internet.
Separate from both the 68-node official workflow and the seven-node Shadow generator.

## Contract

- POST /webhook/langgraph-shadow-evidence-v1, protected with a dedicated n8n Header Auth
  credential named X-Agent-Shadow-Evidence-Token. Its secret must be NEW and
  not reused from generation's previously exposed Webhook credential.
- Request: contract_version=1, request_id, operation=list|detail|visualization,
  with agent_run_id and integer limit 1..50 for list, shadow_record_id for detail/visualization.
- Inbound arbitrary target_path, URL, SQL, question or other keys are rejected.
- Only n8n -> LangGraph uses Authorization: Bearer and the existing separate S2S token.
- Only safe run IDs, status, dates, flags, bounded numeric graph metadata
  and graph topology are forwarded. The canonical LangGraph step kind
  (`step_type`) is projected into the UI-supported `metadata.kind` field;
  canonical edge kinds (`edge_type`: normal, conditional, repair, terminal)
  are projected into the UI-supported `label` field. Both are restricted
  to structural values to prevent raw SQL, prompts or arbitrary labels from
  passing through a privileged endpoint. Date fields must be ISO-8601
  with timezone; event/status/step fields are validated, not blindly copied.
  Canonical `persistence_failure` and `has_unknown_evidence` flags generate
  only bounded, predefined warning codes; no raw diagnostic text is forwarded. Canonical LangGraph `final_status`,
  `sequence`, and UTC timestamps with `+00:00` are normalized to Product
  `status`, `order`, and compatible timestamps. Repair/reapproval flags
  come from canonical visualization flags, and list responses cannot exceed
  the requested limit. No SQL, prompts, raw responses, diagnostics or secrets.
- Product MUST enforce its own session, profile and run ownership before calling
  this privileged backend-only relay. The relay cannot authenticate individual tenants.

## Safety / deployment

Template is INACTIVE and without credentials, pinned data or execution-history
persistence. The generated workflow must use a private destination and GET-only
LangGraph endpoint. No global n8n $env access is required.

Run: python3 testar_n8n_shadow_evidence_read_workflow.py
Render privately: python3 scripts/n8n/render_shadow_evidence_read_workflow.py
  --internal-base-url http://YOUR_PRIVATE_DOCKER_SERVICE:8000
  --output /tmp/YOUR_NEW_UNIQUE_PRIVATE_FILE.json

Import, credential setup, publication, Vercel environment configuration and
connection testing require separate explicit operator approval. Do not alter
the official n8n or the existing Shadow generation workflow.

An HTTP 200 safe read response confirms retrieval only; it does not prove SQL
parity, LLM provider equivalence or financial results.

## Auditoria de bindings do relay importado (read-only)

**Somente após uma importação separadamente autorizada**, ainda **inativa**,
com o Webhook Header Auth exclusivo salvo e com o HTTP Header Auth do
LangGraph associado ao nó `Read LangGraph Evidence`, conferir o ID real
do NOVO workflow (nunca usar o ID de produção nem do Shadow de sete nós).
Executar no host Docker autorizado, sem informar tokens:

```bash
cd /docker/agente-sql-langgraph-repo
bash scripts/n8n/audit_shadow_evidence_read_bindings_readonly.sh \
  --workflow-id ID_REAL_DO_WORKFLOW_NOVO
```

A auditoria usa `n8n export:workflow --id` na versão *draft* (não publica,
não ativa e não usa o workflow oficial). Guarda o JSON bruto apenas em
arquivos temporários restritos no host e no contêiner e os remove antes
de declarar sucesso. Não expõe conteúdo de nós, URLs internas, IDs/nome de
credenciais nem segredos.

Um resultado `EVIDENCE_READ_BINDINGS=PASS` comprova apenas: cinco nós,
configuração igual ao template revisado, caminho `GET` privado e
estático, nenhuma expressão `$env` necessária, armazenamento de execuções
desabilitado, dois IDs de credenciais Header Auth **distintos**, topologia
sem deriva e workflow inativo. Os testes offline exercitam erros de
bind, injeção de URL, métodos não-GET, alterações de código e opções de
execução perigosas. A ferramenta aceita IDs de nós gerados pelo n8n 2.x
e a omissão do método GET padrão na exportação.

Um PASS **não comprova** valores corretos das credenciais, conexão
n8n→LangGraph, existência dos endpoints na imagem implantada, autorização
multi-tenant nem leitura real de evidências. Essas verificações exigem
suas etapas operacionais e autorizações próprias. Não rodar chamadas
reais, alterar variáveis Vercel ou publicar o workflow em resposta a uma
falha da auditoria.
