# Live Engine Preflight Adapter

## Descoberta

Esta fase investigou o repositorio antes de implementar qualquer integracao
live. Foram verificados codigo, docs, configuracao, scripts live, adapters,
ports e variaveis de ambiente.

Evidencias encontradas:

- `requirements.txt` contem somente `langgraph` e `psycopg`.
- `app/adapters/postgres/context_repository.py` acessa PostgreSQL apenas para
  carregar o contexto semantico versionado.
- Scripts `*_postgres_*_live.py` fazem diagnosticos e manutencao do contexto
  PostgreSQL, incluindo consultas de contexto e `SELECT 1` de conectividade.
- `docs/migration/intent-resolution-engine.md` descreve a migracao do agente
  SQL DuckLake para LangGraph.
- `docs/migration/engine-preflight-contract.md` ja registrava que nao havia
  adapter real seguro para planejamento sem execucao.
- Nao foi encontrado SDK DuckDB/DuckLake, endpoint Watson/Orchestrate,
  ferramenta `execute_sql`, dry-run, parse, plan, webhook ou contrato n8n
  congelado capaz de validar SQL sem executar consulta de negocio.

Decisao objetiva: D. Nao existe integracao live suficiente para criar um
adapter real seguro. PostgreSQL existe como armazenamento do contexto, mas nao
foi tratado como motor final da SQL de negocio.

## Resultado

Esta branch nao cria adapter live real. Ela cria infraestrutura configuravel de
capability e falha fechada quando nao ha capacidade segura comprovada.

Arquivos principais:

- `app/config/engine_preflight_runtime.py`
- `app/adapters/engine_preflight/capability_unavailable.py`
- `testar_engine_preflight_capability_integration.py`
- `testar_engine_preflight_live.py`

## Configuracao

Variaveis suportadas para diagnostico:

- `ENGINE_PREFLIGHT_PROVIDER_TYPE`
- `ENGINE_PREFLIGHT_CAPABILITY_MODE`
- `ENGINE_PREFLIGHT_DIALECT`
- `ENGINE_PREFLIGHT_ENDPOINT`
- `ENGINE_PREFLIGHT_AUTH_MODE`
- `ENGINE_PREFLIGHT_OPERATION`
- `ENGINE_PREFLIGHT_TIMEOUT_SECONDS`
- `ENGINE_PREFLIGHT_SSL_VERIFY`

Credenciais nao sao versionadas. Quando um auth mode diferente de `none` for
diagnosticado manualmente, o script live solicita segredo por entrada oculta e
nao armazena nem imprime o valor.

## Capabilities

O diagnostico declara:

- `supports_parse`
- `supports_plan`
- `supports_explain`
- `supports_explain_analyze = False`
- `executes_query = False`
- `returns_rows = False`
- `supports_sqlstate`
- `supports_error_position`
- `supports_related_object`
- `supported_dialects`

Mesmo quando um modo seguro e declarado, `adapter_available = False` enquanto
nao existir provider real implementado e validado. O erro canonico e
`ENGINE_PREFLIGHT_CAPABILITY_UNAVAILABLE`.

## Provider Diagnostico

`CapabilityUnavailableEnginePreflight` implementa a porta `EnginePreflight`,
mas nao e adapter live real. Ele recebe somente `EnginePreflightRequest`,
nao recebe `GraphState`, nao recebe `ContextSnapshot`, nao abre rede, nao abre
banco e nao executa SQL. O resultado normalizado fica como erro de
infraestrutura, com:

- `failure_category = capability_unavailable`
- `repairable = false`
- `statement_planned = false`
- `executed = false`
- `rows_returned = 0`

## Bootstrap

`create_engine_preflight_from_runtime_config(config)` e uma factory explicita
para o provider diagnostico fail-closed. Ela nao e usada automaticamente por
`create_postgres_context_graph`; o grafo continua exigindo injecao explicita de
`engine_preflight`.

## Testes

`testar_engine_preflight_capability_integration.py` roda sem rede, sem banco,
sem SQL e sem `EXPLAIN`. Ele cobre configuracao, capability indisponivel,
factory explicita, sanitizacao, imutabilidade, determinismo e prova de
`executed = false` / `rows_returned = 0`.

`testar_engine_preflight_live.py` e manual e nao entra em `scripts/check_all.py`.
Ele nao recebe SQL e nao chama provider externo; apenas imprime diagnostico
sanitizado da configuracao/capability.

## Proibicoes Mantidas

- Nao executar consulta de negocio.
- Nao usar `EXPLAIN ANALYZE`.
- Nao usar `LIMIT 0`.
- Nao usar execucao normal como preflight.
- Nao criar objetos persistentes ou temporarios no motor.
- Nao retornar linhas.
- Nao reescrever SQL.
- Nao imprimir DSN, token, senha, host, usuario, request body, response body ou
  SQL integral.
- Nao alterar workflows n8n, PROD ou scripts live existentes.

## Limitacoes

O bloqueio tecnico permanece: falta uma capacidade comprovadamente segura no
motor final. O proximo passo e obter contrato oficial de parse/plan/dry-run ou
EXPLAIN sem ANALYZE do motor real, com autenticacao, endpoint/tool ID e
garantia documentada de `executes_query = false`.
