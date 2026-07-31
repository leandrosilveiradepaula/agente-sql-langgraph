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

## Testes

A suite local deve usar dados genericos. Scripts live ficam separados e so
podem ser usados em leitura quando necessario. `scripts/check_all.py` e a
regressao consolidada esperada antes de commit.
Testes locais de preflight usam fake injetado e nao acessam motor real.
Testes locais de reparo usam fake injetado, sem rede, sem banco e sem
execucao de SQL.
Testes locais de execucao usam fake injetado e nao executam SQL real.
Script live de preflight fica fora de `scripts/check_all.py` e nao deve ser
executado automaticamente.
