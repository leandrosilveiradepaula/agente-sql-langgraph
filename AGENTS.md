# AGENTS.md

## Arquitetura

O LangGraph local carrega um `ContextSnapshot` canonico, resolve uma unica
intencao, constroi um `QueryPlan` deterministico e gera SQL por um
`SqlGenerator` injetado. Depois, o Security Gate valida read-only e
autorizacao estrutural, e o Contract Gate valida aderencia ao `QueryPlan`.
O Engine Preflight valida planejamento do motor por porta injetada, sem
executar a consulta de negocio.
Quando aprovado, a execucao controlada usa somente `current_sql` e uma
`SqlExecutionRequest` minima enviada a um `SqlExecutor` explicitamente
injetado.
Depois da execucao aprovada, o resultado e apenas normalizado e serializado:
nao interpretar, arredondar, inferir moeda, percentual ou data. `Decimal` nao
vira float; erros nao carregam celulas; serializacao deve ser JSON-safe,
deterministica e sem logs do payload completo.
Preflight live so pode ser habilitado com capability comprovada do motor real;
execucao normal, `LIMIT 0` e `EXPLAIN ANALYZE` nunca podem ser usados como
preflight.
Se o preflight rejeitar uma SQL com erro reparavel, o grafo pode chamar um
SqlRepairer injetado e reenviar a SQL reparada para Security Gate, Contract
Gate e Engine Preflight.
O planner usa somente o snapshot versionado ja validado; geracao e gates
consomem somente o `QueryPlan` e a SQL corrente.
Toda saida terminal do grafo passa por finalizacao local: `RunRecord`,
persistencia obrigatoria, auditoria obrigatoria e observabilidade best-effort.
Depois da finalizacao, toda execucao terminal deve produzir uma
`ApplicationResponse` publica, deterministica e segura. Mensagens publicas sao
canonicas; erros brutos de provider nao atravessam. `data` so existe em
success finalizado com persistencia e auditoria aprovadas. Falha de
persistencia/auditoria e fail-closed; observabilidade degradada preserva o
outcome original. Nao duplicar payload, e JSON canonico deve ser produzido
somente sob demanda.
Toda execucao externa futura deve passar pelo application service. Endpoints
nao invocam o grafo diretamente. O service sempre retorna `ApplicationResponse`,
request invalida nao chama o grafo, exception de runtime e fail-closed, e
`GraphState` nunca e retornado.

## Principios permanentes do Agente Financeiro

- A arquitetura e hibrida: n8n permanece responsavel por orquestracao operacional,
  webhooks, integracoes e etapas deterministicas; LangGraph fica com semantica,
  classificacao, selecao de contexto, planejamento, geracao/validacao de SQL,
  repair como proposta e evidence/governanca. Nao migrar tarefas para LangGraph
  apenas porque ele existe.
- Nunca implementar pergunta -> SQL, frase -> resposta ou benchmark -> comportamento.
  Perguntas, SQLs historicas e golden answers servem apenas para avaliacao e
  documentacao, nunca para geracao.
- Migrar comportamento, nao hardcode. Classificar conhecimento encontrado como:
  `STRUCTURAL` (motor/plataforma), `TRANSITIONAL` (divida herdada) ou `FORBIDDEN`
  (regra de negocio, tabela/coluna cliente-especifica, DRE, marca, conta, centro
  de custo, alias, intencao especifica, excecao, SQL pronta, pergunta/resposta ou
  threshold de caso). Nenhum `FORBIDDEN` entra em codigo novo.
- O codigo conhece o PROCESSO; conhecimento de negocio deve vir de contexto/configuracao
  versionada e auditavel. Preferir fontes como regras, aliases, mappings, patterns
  e catalogo semantico versionados.
- `business_question_examples` sao apenas sinais semanticos auxiliares; nunca lookup.
- Campos de benchmark (`tabelas_obrigatorias`, `filtros_obrigatorios`,
  `deve_conter_sql`, `nao_deve_conter_sql`, `criterio_semantico`, SQL esperada,
  resposta esperada, golden answer) nunca podem chegar ao generator/prompt.
- Antes de aceitar uma mudanca, validar se ela melhora capacidade geral ou apenas
  um caso. Nunca reduzir threshold, criar `if` por frase ou SQL especial para benchmark.
- `SEMANTIC_AGENT_VERSION` deve permitir trocar regras, aliases, mappings, patterns
  e catalogo preferencialmente sem alterar Python/TypeScript.
- Durante shadow: OFFICIAL = n8n, SHADOW = LangGraph, `real_sql_execution=false` e
  nenhum cutover implicito.
- Generate, Repair e Execute sao etapas distintas. SQL alterada perde aprovacao,
  exige `requires_reapproval=true` e nunca e executada silenciosamente.
- Preservar observabilidade e correlation metadata; nunca expor secrets, DSN,
  Authorization, cookies, API keys ou raw provider responses desnecessarias.
- Nunca afirmar que arquivo, codigo, SQL, log ou configuracao foi revisado sem
  realmente acessar o conteudo.
- Testar generalizacao com perguntas novas e equivalentes semanticamente, nao apenas
  benchmark conhecido.

## Protocolo Codex

O Codex deve tratar este repositorio como fonte de verdade operacional.
Antes de qualquer implementacao, ler este `AGENTS.md` e
`docs/codex/CURRENT_TASK.md` quando existir.

Para cada tarefa:
1. confirmar HEAD/branch e working tree antes de editar;
2. respeitar estritamente o escopo de `CURRENT_TASK.md`;
3. nao alterar arquivos ou subsistemas fora do escopo sem necessidade comprovada;
4. executar os testes novos e a regressao relevante indicada;
5. executar `python scripts/check_all.py` antes de commit quando a tarefa exigir
   regressao consolidada;
6. produzir inventario de hardcodes `STRUCTURAL / TRANSITIONAL / FORBIDDEN`;
7. nunca introduzir `FORBIDDEN` em codigo de producao;
8. registrar no resultado: arquivos alterados, diff resumido, testes, riscos e
   `git status`;
9. somente fazer commit quando `CURRENT_TASK.md` autorizar explicitamente;
10. nunca fazer deploy, alterar Supabase, n8n, PROD ou servico externo sem autorizacao
    explicita na tarefa corrente.

`docs/codex/CURRENT_TASK.md` e o control plane da tarefa corrente. Ele nao deve
conter secrets nem golden answers de benchmark. Ao concluir uma tarefa, nao inventar
a proxima: aguardar que a tarefa corrente seja atualizada.

## Comandos principais

- `python -m compileall app`
- `python testar_intent_resolver.py`
- `python testar_classify_intent.py`
- `python testar_planner.py`
- `python testar_build_plan.py`
- `python testar_sql_generation.py`
- `python testar_sql_execution.py`
- `python testar_engine_preflight.py`
- `python testar_sql_repair.py`
- `python testar_sql_analysis.py`
- `python testar_sql_security.py`
- `python testar_security_gate.py`
- `python testar_sql_contract.py`
- `python testar_contract_gate.py`
- `python testar_engine_preflight_node.py`
- `python testar_execute_sql.py`
- `python testar_repair_sql.py`
- `python testar_generate_sql.py`
- `python testar_run_record.py`
- `python testar_application_response.py`
- `python testar_build_application_response.py`
- `python testar_grafo_base.py`
- `python scripts/check_all.py`

## Restricoes

Nao modificar workflows n8n, nao tocar PROD e nao executar scripts live com
escrita. Gemini, Watson, Supabase e outros servicos externos nao fazem parte do
planner.

## Hardcodes

Nao colocar termos de negocio, nomes reais de clientes, fabricantes, tabelas,
colunas ou exemplos de benchmark em regras Python. Decisoes devem vir do
`ContextSnapshot` e, depois do planejamento, do `QueryPlan`. Gates nao releem
o snapshot completo, nao executam SQL e nao corrigem SQL automaticamente.
Preflight tambem nao rele o snapshot completo, nao chama o gerador novamente,
nao executa SQL, nao usa `EXPLAIN ANALYZE` e deve sanitizar erros. O loop de
reparo so inicia depois de preflight reparavel, nao recarrega contexto, nao
reexecuta geracao inicial, respeita limite obrigatorio e registra historico
sem SQL integral. SQL reparada volta aos gates antes de novo preflight.
Provider live e sempre explicitamente injetado; nao ha provider global, fake
como fallback de producao ou credenciais versionadas. Na ausencia de capability
segura comprovada, use apenas diagnostico fail-closed.
Execucao SQL controlada tambem exige executor explicitamente injetado, nao
recebe GraphState nem ContextSnapshot, nao altera SQL e nao pode ser alcancada
sem Security Gate, Contract Gate e Engine Preflight aprovados.
ApplicationResponse nao cria endpoint nesta fase, nao executa SQL, nao chama
sinks, nao expoe SQL integral, pergunta integral, QueryPlan, ContextSnapshot,
GraphState, prompts, headers, tokens, DSN, RunRecord integral ou eventos
integrais.
Application service tambem nao cria endpoint HTTP, nao loga pergunta, SQL ou
payload, nao chama adapters/sinks diretamente e nao implementa retry automatico.
HTTP entry adapter chama `Authenticator` e `Authorizer` explicitamente
injetados antes de `SqlAgentApplicationService`; endpoints nunca invocam o
grafo diretamente. Identidade HTTP nunca vem do body: `user` em JSON publico
e proibido, e `ApplicationRequest.user` deriva somente do principal
autenticado. Authorization, credenciais, principal, roles e scopes nunca devem
ser logados ou retornados. Auth falha fechada, deny por padrao, sem usuario
anonimo, sem role de negocio hardcoded e sem provider real nos testes. O
adapter nao inicia servidor em `check_all.py` e nenhum endpoint expoe
`GraphState`.
ASGI adapter traduz somente protocolo para o `SqlAgentHttpHandler`: nao chama
grafo, application service, authenticator ou authorizer diretamente. Nao
armazenar scope, body, headers, eventos ou tokens em estado global; nao logar
eventos, headers ou body; nao iniciar servidor em `check_all.py`; nao adicionar
Uvicorn/Hypercorn nesta fase. `http.disconnect` nao chama o handler. Depois de
`http.response.start`, nao enviar segunda resposta.
Watson Flow nesta fase existe apenas como contratos offline e adapters
explicitamente injetados. O payload Watson contem somente `sql_query`; nunca
enviar `limit` sem mudanca formal de contrato. `approved_sql` e
`sql_transport` sao conceitos diferentes: compactar apenas uma copia de
transporte, sem truncar, sem persistir e sem substituir a SQL original. Token
IAM e value object sensivel e nao pode ser serializado, logado ou retornado.
Raw output do Flow nao atravessa a fronteira do adapter. Cada adapter faz uma
tentativa; retry deve ser decorator ou orquestracao explicita. Falhas de IAM,
provider, timeout, rate limit, autenticacao, resposta invalida ou ambigua nunca
acionam repair. `check_all.py` nunca acessa rede, socket, Watson ou IBM Cloud.
O dry-run do probe Watson nao exige secret, nao acessa `SecretValueProvider`,
nao cria adapters live e nao acessa rede. Somente live mode pode consultar API
key, sempre depois de validar arquivo SQL, compactacao, payload, configuracao
nao sensivel e confirmacao TEST. A composition root Watson TEST aceita somente
`DeploymentEnvironment.TEST`, rejeita PROD/production/prd/live, nao infere TEST
pela URL e nao altera o bootstrap padrao offline. Operacao Windows deve
documentar comandos CMD quando o usuario pedir fluxo operacional; nunca usar
`setx` para secrets. Probe live continua manual, sem retry automatico.

## Testes

A suite local deve usar dados genericos. Scripts live ficam separados e so
podem ser usados em leitura quando necessario. `scripts/check_all.py` e a
regressao consolidada esperada antes de commit.
Testes locais de preflight usam fake injetado e nao acessam motor real.
Persistencia e auditoria devem ser idempotentes, falhar fechadas e nunca
registrar SQL integral ou valores em auditoria/telemetria. Observabilidade pode
degradar sem apagar resultado persistido, mas nao usa IDs de alta cardinalidade
como labels. Fakes de persistencia, auditoria e observabilidade nunca sao
defaults e nenhum adapter live entra no `check_all.py`.
Testes locais de reparo usam fake injetado, sem rede, sem banco e sem
execucao de SQL.
Testes locais de execucao usam fake injetado e nao executam SQL real.
Script live de preflight fica fora de `scripts/check_all.py` e nao deve ser
executado automaticamente.
Testes de auth usam fakes injetados, sem token real, rede, servidor, socket ou
provider live.
Testes ASGI usam harness em memoria, sem TestClient que abra socket, sem rede,
sem servidor e sem framework externo.
Testes Watson Flow usam FakeIamTokenProvider e FakeWatsonFlowClient injetados,
sem token real, sem API key, sem rede, sem servidor, sem SQL e sem provider
live.
Adapters Watson live nunca sao defaults. Nenhum import ou factory pode acessar
secret, IAM, Watson, rede, socket, servidor ou PostgreSQL. API key vem somente
de `SecretValueProvider` e nunca entra em request de dominio; `Authorization`
sempre e header sensivel materializado apenas no transporte. `check_all.py`
permanece offline. O script manual Watson exige confirmacao explicita para
rede, nao imprime body IAM/Flow, token, API key ou Authorization, nao segue
redirect, nao aceita TLS inseguro, nao usa proxy env e nao implementa retry
interno.
Testes de composition root Watson TEST usam FakeSecretValueProvider e
FakeHttpTransport. A composition root pode construir objetos live, mas isso
nao pode consultar secret, IAM, Watson, env, rede, socket, servidor,
PostgreSQL ou executar SQL. O runner offline pode simular IAM e Flow com fakes
e pode entrar no `check_all.py`; probe live nunca entra no `check_all.py`.
CI e `check_all.py` sao offline. `scripts/check_clean_room.py` e executado
separadamente para evitar recursao; quando ele chama `check_all.py`, o ambiente
clean-room desabilita `pip check`. O network guard e obrigatorio para testes
criticos e deve bloquear rede real apenas no subprocesso protegido. O launcher
CMD nao armazena secrets, nao usa `setx`, nao faz retry, nao limpa variaveis da
sessao CMD pai quando usa `setlocal` e deve recomendar a limpeza manual
`set "IBM_CLOUD_API_KEY="`. O launcher prefere
`.venv\Scripts\python.exe`; se a venv nao existir, pode usar um `python.exe`
valido no PATH, como no CI com `actions/setup-python`. Ele nunca cria venv,
nunca instala dependencias, nunca chama pip e falha antes de qualquer operacao
quando nao ha Python valido. Em maquina operacional, recomenda-se usar a
`.venv`; usar PATH nao implica isolamento de dependencias. Probe live e sempre
uma tentativa unica, fora do CI, sem cache, retry, backoff ou probe automatico.
Failure rehearsal usa somente fakes. Workspace hygiene e dependency checker sao
obrigatorios e operam offline, sem apagar arquivos e sem consultar PyPI.
