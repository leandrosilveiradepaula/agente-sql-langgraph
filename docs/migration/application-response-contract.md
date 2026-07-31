# Application Response Contract

## Objetivo

Esta fase adiciona um contrato de resposta da aplicacao independente de HTTP,
framework, banco, UI e provider externo. A resposta projeta o estado final do
grafo em um objeto deterministico, seguro e JSON-safe para uso futuro por API,
interface, SDK, CLI, testes de integracao e jobs internos.

Nao ha endpoint HTTP, servidor, autenticacao, rede, SQL live, persistencia
adicional, cache, streaming, download, paginacao live ou resumo por IA nesta
fase.

## Status externo

`ApplicationResponse.status` e publico e estavel:

- `success`
- `rejected`
- `infrastructure_error`

Ele nao e o mesmo campo que `original_outcome` nem que o estado operacional de
finalizacao.

## Original outcome

`original_outcome` preserva o resultado original do processamento:

- `success`
- `rejected`
- `infrastructure_error`

A construcao da resposta nunca transforma `rejected` ou `infrastructure_error`
em sucesso.

## Finalization

`finalization.status` representa a finalizacao operacional:

- `completed`
- `persistence_failed`
- `audit_failed`
- `observability_degraded`
- `record_failed`
- `incomplete`

Esse campo inclui apenas flags e IDs seguros de persistencia/auditoria. Nao
inclui `RunRecord`, eventos integrais, diagnosticos internos ou payloads.

## Persistencia e auditoria obrigatorias

Persistencia e auditoria sao fail-closed. Quando `original_outcome=success`,
mas persistencia ou auditoria falham, a resposta publica fica:

- `status=infrastructure_error`
- `data=None`
- `metadata.original_outcome=success`
- `finalization.status=persistence_failed`, `audit_failed` ou `incomplete`

Assim, dados validados nao sao entregues como sucesso completo quando uma etapa
operacional obrigatoria falhou.

## Observabilidade degradada

Falha de observabilidade nao altera `original_outcome`. Quando persistencia e
auditoria estao completas, observabilidade degradada preserva:

- `status=success`
- `data` presente
- warning publico `OBSERVABILITY_DEGRADED`
- `finalization.status=observability_degraded`

## Data

`data` so existe quando todos os itens abaixo sao verdadeiros:

- `original_outcome=success`
- execucao, normalizacao e serializacao estao em `success`
- persistencia esta `persisted` ou `already_persisted`
- auditoria esta `written` ou `already_written`
- finalizacao esta `completed` ou `observability_degraded`
- limites da resposta foram respeitados

`data.result` e uma projecao segura do `SerializedQueryResult`: contem uma
unica representacao com colunas, linhas e fingerprint do resultado. Nao inclui
`canonical_json`, lineage integral, SQL, QueryPlan ou ContextSnapshot.

## Metadata

`metadata` contem somente informacao util ao consumidor:

- versao de contexto
- intencao minima
- contagens de linhas e colunas
- bytes do resultado
- truncamento
- tentativas de reparo
- duracao total quando disponivel
- flags de persistencia, auditoria e observabilidade
- provider logico sanitizado
- versoes de contrato
- lineage minimo

Fingerprints ficam em `metadata.lineage`, nao espalhados pelos campos comuns.

## Lineage

O lineage publico pode incluir fingerprints de contexto, plano, SQL atual,
preflight, execucao, normalizacao, serializacao, RunRecord, persistencia e
auditoria. Ele nunca inclui SQL integral, IDs secretos, corpo de provider,
headers ou dados de credencial.

## Erros

`errors` contem codigo canonico, categoria, stage, mensagem publica segura e
indicacao de retry. Mensagens brutas de provider, SQL, payloads, stack traces,
DSN, host, headers, tokens e valores de celula nao atravessam o contrato.

Erros sao deduplicados de forma deterministica. Erros originais permanecem antes
de erros de finalizacao obrigatoria.

## Warnings

`warnings` contem codigo, categoria, stage e mensagem publica curta. O caso
principal desta fase e `OBSERVABILITY_DEGRADED`.

## Mensagens publicas

Mensagens principais sao canonicas:

- sucesso: `Consulta processada com sucesso.`
- rejeicao: `A solicitacao nao pode ser processada.`
- infraestrutura: `O processamento nao pode ser concluido.`

## Paginacao

Nao existe paginacao live nesta fase. A resposta declara explicitamente:

- `mode=none`
- `has_more=False`
- `next_cursor=None`
- `total_rows` apenas quando comprovado
- `returned_rows` calculado a partir das linhas retornadas

## Limites

`ApplicationResponseLimits` define limites positivos para bytes totais,
erros, warnings, mensagens, lineage, linhas, colunas e metadata. Excesso de
resposta vira falha estruturada:

- `status=infrastructure_error`
- `data=None`
- erro `APPLICATION_RESPONSE_LIMIT_EXCEEDED`

Dados nao sao truncados silenciosamente.

## Canonicalizacao e fingerprint

`to_canonical_application_response_json(...)` produz JSON canonico sob demanda,
com chaves ordenadas, UTF-8 e `allow_nan=False`. O JSON canonico nao e armazenado
como segunda copia dentro da resposta.

`response_fingerprint` e calculado sem incluir a si proprio, evitando ciclo.
Mudancas relevantes de status, data ou erro alteram o fingerprint.

## Resposta minima

Falha interna na construcao gera uma resposta minima fail-closed:

- `status=infrastructure_error`
- `code=APPLICATION_RESPONSE_BUILD_FAILED`
- `data=None`
- sem payload, SQL, RunRecord integral ou mensagem bruta da excecao

## Roteamento

Todo caminho terminal passa por:

`build_run_record -> persist_run -> record_audit -> emit_observability -> build_application_response -> END`

Falhas de RunRecord, persistencia, auditoria ou observabilidade tambem convergem
para `build_application_response -> END`, sem ciclo, sem repetir sinks e sem
voltar a fases de negocio.

## Seguranca

`ApplicationResponse` nunca inclui SQL integral, pergunta integral, prompt,
ContextSnapshot, QueryPlan, GraphState, intent_catalog, token, API key,
Authorization, cookie, DSN, host interno, usuario de banco, headers, stack
trace, provider body, AuditEvent integral ou ObservabilityEvent integral.

Valores legitimos dentro de `data` nao sao sanitizados, pois representam o
resultado validado.

## Proximos passos

Etapas futuras podem criar adaptadores HTTP, SDK, CLI, UI, paginacao live ou
formatadores de apresentacao consumindo este contrato, sem alterar o dominio
puro desta fase.
