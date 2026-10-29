# G3 — geração SQL candidata, somente para revisão humana

Este novo workflow não substitui o fluxo oficial de 68 nós nem o Shadow
assíncrono de sete nós. É uma rota **separada, inativa**:

Produto (servidor autenticado) → n8n (header auth) → LangGraph
`POST /v1/internal/sql-agent/generate` → SQL validada para revisão.

Contrato: POST `/webhook/langgraph-candidate-generate-v1`, envelope v1
`agent_run_id`, `question`, `principal`, `correlation_metadata` e
`llm_selection` opcionais autorizados. O LangGraph gera SQL dinâmica
usando o contexto versionado, executa os gates e devolve a SQL **somente
quando** `status=success`, HTTP 200, preflight approved e
`preflight.executed=false`. Resposta inclui `requires_human_approval=true`.
Não há query executora nem nó PostgreSQL no candidato.

## Limites do contrato

- `requires_human_approval` é uma indicação de bloqueio, **não** uma
  aprovação persistida nem autorização para executar. Esta entrega ainda não
  cria o mecanismo de aprovação/executor.
- Não enviar a SQL como “aprovada” ao `execute-approved-shadow`:
  essa rota é exclusivamente testemunha de uma aprovação que já ocorreu
  fora do Shadow e nunca executa SQL.
- Sem SQL hardcoded, sem decisão de negócio no n8n, sem benchmark no prompt.
  Não ativar o candidato nem usar LLM paga sem aprovação da janela.
- Candidato isolado requer uma credencial Webhook Header Auth exclusiva e
  uma credencial HTTP Header Auth S2S para LangGraph. A identidade do tenant
  origina-se no Produto, não no n8n.
- Execuções n8n não armazenam body, SQL ou resposta no histórico de sucesso,
  erro ou manual. A persistência de evidência LangGraph segue a política
  de menor privilégio e deve ser apontada para banco ativo homologado.
- Um resultado técnico positivo não prova correção financeira ou paridade.

## Preparação reversível, sem alterar n8n

1. `python testar_n8n_candidate_generate_review.py`
2. `python scripts/n8n/render_candidate_generate_review.py --check-template`
3. Após autorização de importação inativa e identificação do DNS Docker interno:
   `python scripts/n8n/render_candidate_generate_review.py --internal-base-url 'http://langgraph-internal:8000' --output /tmp/candidate-private.json`.
4. Importar **como novo workflow inativo**, conferir roteamento e credenciais
   separadas. Render não importa/publica/ativa nada e cria arquivo 0600
   sem sobrescrever.
5. Ativação, chamada Gemini real, contexto/tenant e conexão do Produto
   dependem de aprovação operacional própria.
6. Para reversão, manter flag do Produto desativada e o workflow inativo.
   Não alterar nem remover o n8n oficial.

`OFFICIAL=n8n+Gemini`, `SHADOW=LangGraph`,
`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.
