# SQL Repair Loop Contract

## Objetivo

Esta fase adiciona um loop controlado de reparo de SQL depois do
Engine Preflight. O reparo so e tentado quando o preflight retorna erro
SQL reparavel. O fluxo nao reinicia classificacao, planejamento, geracao
inicial nem carregamento de contexto.

Fluxo:

`generate_sql -> security_gate -> contract_gate -> engine_preflight`

Quando o preflight aprova, o grafo encerra em `processing`. Quando o
preflight rejeita com erro reparavel, o grafo chama `repair_sql`, valida a
SQL reparada estruturalmente e volta para `security_gate`. O ciclo repete
ate aprovacao, erro nao reparavel, limite de tentativas ou falha de
infraestrutura.

## Limites

O loop nao executa SQL de negocio, nao retorna dados, nao persiste historico
externo, nao altera PostgreSQL, nao usa `EXPLAIN ANALYZE`, nao altera n8n ou
PROD e nao cria integracao obrigatoria com fornecedor externo.

O reparo nao tenta corrigir falhas do Security Gate ou Contract Gate. Se uma
SQL reparada for rejeitada por qualquer um desses gates, o fluxo encerra
como `rejected` e nao chama novo reparo.

## Porta

`app/ports/sql_repairer.py` define `SqlRepairer.repair(request)`.

A porta recebe somente `SqlRepairRequest`. Ela nao recebe `GraphState`,
`ContextSnapshot`, repositorio de contexto, adapter de preflight, credenciais
ou dados do banco.

Nenhum provider real foi criado nesta fase. Como nao existe abstracao segura
preexistente para reparo live, a branch entrega apenas porta e fake local.

## Request

`SqlRepairRequest` contem:

- SQL atual com falha;
- fingerprint da SQL atual;
- tentativa atual e limite;
- contexto minimo derivado do `QueryPlan`;
- erro estruturado do Engine Preflight;
- historico resumido por fingerprints;
- instrucoes e restricoes de saida;
- fingerprint deterministico da propria request.

O request nao contem `GraphState` completo, `ContextSnapshot` completo,
credenciais, DSN, resultados de query, logs completos, catalogo de intencoes
ou sinais de classificacao.

## Result

`SqlRepairResult` contem status, SQL reparada quando aplicada, codigo de
erro quando houver, mensagem sanitizada, diagnostico, warnings e registro de
historico da tentativa.

Status:

- `repaired`: SQL estruturalmente valida foi aceita para nova passagem pelos
  gates;
- `rejected`: reparo desabilitado, limite atingido, falha nao reparavel ou
  resposta invalida do reparador;
- `infrastructure_error`: provider indisponivel, timeout ou excecao.

## Historico

Cada chamada efetiva ao reparador adiciona um registro append-only em
`repair_history`. O historico registra tentativa, estagio falho, categoria,
codigos sanitizados, fingerprints da SQL antes/depois, fingerprints de
request/response, provider sanitizado, duracao, erros e warnings.

O historico nao registra SQL integral. Campos legados `sql_before` e
`sql_after` permanecem no tipo antigo por compatibilidade, mas nao sao
preenchidos pela fase nova.

## Tentativas

`repair_attempts` inicia em 0. A primeira chamada usa `attempt = 1`.

O contador incrementa somente quando o reparador e efetivamente chamado.
`max_repair_attempts = 0` desabilita reparo. Quando o limite e atingido, o
provider nao e chamado novamente e o fluxo encerra com erro estruturado.

## Validacao Da Resposta

A resposta esperada do reparador contem exatamente uma SQL de leitura. A fase
reutiliza a validacao estrutural de geracao SQL para rejeitar vazio,
Markdown, texto explicativo, multiplos statements, comandos de escrita,
caracteres de controle, tamanho excessivo e SQL que nao inicia por
`SELECT` ou `WITH`.

A fase tambem rejeita SQL identica a atual ou repetida em tentativa anterior.
Depois de aceita estruturalmente, a SQL volta para Security Gate, Contract
Gate e Engine Preflight.

## Reset Dos Gates

Depois de reparo valido:

- `current_sql` recebe a SQL nova;
- `security_result`, `contract_result` e `engine_preflight_result` voltam a
  `not_run`;
- `failure_stage` e limpo;
- `final_status` permanece `processing`.

Nao sao limpos: `generated_sql`, `query_plan`, intent, contexto,
`repair_history`, `repair_attempts`, `request_id` e `run_id`.

## Seguranca

Erros e campos de provider sao sanitizados. SQL integral nao aparece em
diagnosticos, `AgentError` ou historico. O reparador pode receber a SQL
atual porque essa e a entrada minima para reparo, mas o resultado e o
historico usam fingerprints.

## Proxima Fase

A proxima fase pode criar um adapter real de reparo se existir provider
seguro, configuravel e injetado explicitamente. Essa integracao devera
respeitar o contrato acima e continuar sem execucao de SQL.
