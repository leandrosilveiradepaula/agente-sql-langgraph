# G3 — prova de pré-execução de SQL aprovada (não executora)

Workflow isolado:
\`scripts/n8n/candidate_approved_sql_shadow_witness_v1.workflow.json\`.

Fluxo: Produto autenticado / ledger de solicitação já aprovado
→ webhook n8n protegido com \`headerAuth\`
→ validação estrutural de identidades UUID, digest, correlação
→ LangGraph \`POST /v1/internal/sql-agent/execute-approved-shadow\`
→ pré-validação de segurança/contrato/preflight, sem execução de SQL financeira
→ recibo sanitizado (sem approved_sql ou proposta de repair)
→ Produto registra evidência e estado.

A execução real continua **proibida**: o workflow tem zero nós de banco
ou execução, zero alteração de status no fluxo oficial e é publicado
como **inativo**. O endpoint LangGraph de shadow não executa SQL
financeira; pode propor **repair**, que invalida a aprovação original
e obriga nova geração e nova decisão humana.

A chamada interna usa \`httpHeaderAuth\` separado da autenticação
\`headerAuth\` do webhook do n8n. Configurar URL privada e credenciais
**fora do repositório**, sem upload de segredos. 
O envelope exige \`agent_run_id\`, \`approved_sql\`, tenant, principal,
UUID da solicitação, \`approval_binding_sha256\` e \`request_id\`.
Não aceita SQL de fonte browser: o Produto deve ler a SQL de um ledger
imutável vinculado ao tenant e aprovação humana.

A resposta retorna \`status\`, \`run_id\`, \`response_fingerprint\`,
gates resumidos, \`requires_reapproval\`, \`real_sql_executed=false\`.
O workflow nunca propaga \`approved_sql_original\`, reparo SQL ou
respostas financeiras ao browser. Recusa HTTP divergente, falta de
proveniência, divergência de agente e gates inválidos. Rejeições
22x são resultado de validação, **não** autorização para executar.

**Ativação pendente:** nenhuma importação ou ativação n8n nesta PR.
Primeiro validar a PR do Produto que fornece leitura autenticada
do ledger e persistência de recibo, configurar caminho privado e
identidades reais com aprovação do operador, e homologar sem
custo desnecessário. Se repair requisitar LLM paga, solicitar
autorização antes de disparar. O fluxo oficial de 68 nós permanece
intacto e \`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false\`.
