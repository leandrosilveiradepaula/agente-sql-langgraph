# Run Persistence, Audit And Observability Contract

## Objetivo

Toda execucao terminal do grafo passa a construir um `RunRecord` antes de
encerrar. O encerramento local segue:

`build_run_record -> persist_run -> record_audit -> emit_observability -> END`.

O contrato cobre `success`, `rejected` e `infrastructure_error`.

## Escopo

Esta fase adiciona somente contratos de dominio, portas explicitas, fakes
locais, nos de grafo, roteamento, testes e documentacao. Nao ha adapter live,
rede, banco, SQL real, PostgreSQL, Watson, n8n ou PROD.

## RunRecord

`RunRecord` e um registro estruturado e imutavel por copia independente. Ele
preserva `request_id`, `run_id`, outcome original, `failure_stage`, estagio
anterior, lineage, metricas, erros, warnings, registros seguros de estagio e,
quando existir e couber no limite, o `SerializedQueryResult` validado.

O registro nao inclui `GraphState` completo, `ContextSnapshot` completo,
`QueryPlan` integral, SQL integral, prompts, stack traces, credenciais,
headers, cookies, DSN ou payload duplicado.

## original_outcome E finalization_status

`original_outcome` representa o resultado do fluxo de negocio antes da
finalizacao:

- `approved` vira `success`;
- `rejected` e `invalid_request` viram `rejected`;
- `infrastructure_error` permanece `infrastructure_error`.

`finalization_status` representa apenas a pipeline final:
`record_built`, `persisted`, `audited`, `observed`,
`persistence_failed`, `audit_failed`, `record_failed` ou
`observability_degraded`.

Persistencia e auditoria bem-sucedidas nao sobrescrevem o motivo original de
rejeicao. Falhas de persistencia ou auditoria encerram como
`infrastructure_error`.

## Lineage E Payload

Lineage usa fingerprints e status seguros: contexto, plano, SQL gerada e
corrente por fingerprint, gates, preflight, execucao, normalizacao,
serializacao e historico resumido de reparo. Historico de reparo nao guarda
SQL, apenas fingerprints e classificacoes.

O payload persistivel e somente o `SerializedQueryResult` ja validado. Ele nao
duplica `canonical_json`; `canonical_json` permanece sob demanda no contrato de
serializacao. Se `max_persisted_payload_bytes` for excedido, a construcao do
`RunRecord` falha de forma estruturada e o resultado original permanece no
estado.

## Limites

`RunFinalizationLimits` define limites explicitos para payload, estagios,
erros, warnings, codigos de auditoria, atributos de observabilidade,
comprimento de atributo e nomes de provider. Valores zero, negativos ou
excessivos sao rejeitados.

`receive_question` inicializa limites explicitos em `options`; os nos finais
consomem esses limites do estado.

## Fingerprints E Idempotencia

Fingerprints usam JSON canonico deterministico e nao incluem o proprio
fingerprint. Mudancas em outcome, lineage, status dos gates, reparos,
resultado serializado, erros, warnings e metricas relevantes alteram o
fingerprint.

Persistencia usa chave deterministica baseada em `run_id`, fingerprint do
`RunRecord` e versao do contrato. Auditoria usa chave deterministica baseada
no mesmo lineage. Mesma chave e mesmo fingerprint sao idempotentes; mesma
chave com fingerprint diferente e conflito. Nao ha sobrescrita silenciosa.

## Portas E Fakes

Portas explicitas:

- `RunRepository.save(PersistRunRequest) -> PersistRunResult`;
- `AuditSink.write(AuditEvent) -> AuditResult`;
- `ObservabilitySink.emit(ObservabilityEvent) -> ObservabilityResult`.

As portas nao recebem `GraphState`, `ContextSnapshot`, SQL, credenciais ou
providers de SQL. Fakes locais ficam em memoria, capturam requests/eventos por
copia independente, suportam respostas e excecoes configuraveis, idempotencia
e conflito. Fakes nunca sao defaults no bootstrap.

## Auditoria

`AuditEvent` e menor que `RunRecord`. Ele registra identificadores, outcome,
status final, failure stage, intent minima, contexto, fingerprints principais,
tentativas de reparo, row count, codigos de erro/warning e `record_id` da
persistencia. Ele nao contem SQL, linhas, celulas, resultado serializado,
`QueryPlan`, prompts ou corpo de provider.

## Observabilidade

`ObservabilityEvent` nao contem payload de resultado nem SQL. Metricas usam
labels de baixa cardinalidade (`outcome` e `finalization_status`). IDs de
request/run, pergunta, SQL, fingerprints completos de SQL, tabelas, colunas,
mensagens de erro e usuarios arbitrarios nao sao labels de metrica.

Falha de observabilidade e best-effort: adiciona warning estruturado, marca
`observability_degraded` e nao remove resultado, persistencia ou auditoria.

## Falhas

- Falha ao construir `RunRecord`: encerra em `infrastructure_error` sem ciclo.
- Falha de persistencia: nao chama auditoria; emite observabilidade tecnica se
  seguro; encerra em `infrastructure_error`.
- Falha de auditoria: preserva persistencia, emite observabilidade tecnica e
  encerra em `infrastructure_error`.
- Falha de observabilidade: marca degraded e encerra sem retry.

Nao ha retry nesta fase e nenhum caminho volta para fases de negocio.

## Bootstrap

`create_graph` e `create_postgres_context_graph` exigem explicitamente:
`context_repository`, `sql_generator`, `engine_preflight`, `sql_repairer`,
`sql_executor`, `run_repository`, `audit_sink` e `observability_sink`.

## Proximos Passos

Adapters live de persistencia, auditoria e observabilidade devem ser criados
em fases separadas, com validacao propria, sem substituir os fakes como
defaults e sem ampliar o escopo desta fase.
