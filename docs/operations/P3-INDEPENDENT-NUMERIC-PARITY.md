# P3 — comparação financeira independente, somente leitura, snapshot único

**Estado:** candidato file-only. O fluxo oficial n8n + Gemini continua intacto. O LangGraph Shadow continua com `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`; este avaliador NÃO pertence ao runtime do agente e NÃO executa por padrão.

## Problema resolvido

A comparação estrutural existente (`CompareShadowSqlUseCase`) não comprova equivalência de valores. Este avaliador compara uma SQL oficial e uma SQL Shadow **já geradas** sobre o mesmo snapshot PostgreSQL (`REPEATABLE READ READ ONLY`), sem que a baseline chegue ao gerador. Não há SQL pronta, lógica contábil ou mapeamento por cliente no código. As tabelas e funções permitidas são recebidas de política explícita, privada e versionada.

Executa somente após autorização **separada, concreta e humana** de leitura financeira; sem essa autorização, só valida estrutura/assinatura e imprime hashes. A autorização específica deve descrever banco/dataset/tenant, período e pergunta, SQLs imutáveis, tolerâncias contábeis (se houver), dados permitidos, papel exclusivo e plano de retenção/rollback. Um merge NÃO fornece essa autorização.

## Manifestos privados

Criar, fora do repositório e com permissão **0600**, dois arquivos JSON na VPS: política e par SQL. **Não publicar os arquivos nem enviar SQL/DSN/dados ao chat/GitHub.**

Política v1 (estrutura, não dados de cliente):

```json
{
  "contract_version": "1",
  "organization_id": "<uuid-autorizado>",
  "expected_database": "<database>",
  "expected_role": "<role-select-only>",
  "authorized_relations": ["<schema>.<tabela-autorizada>"],
  "authorized_functions": ["sum", "count"],
  "max_rows": 500,
  "max_result_bytes": 100000,
  "statement_timeout_ms": 10000,
  "lock_timeout_ms": 1000
}
```

Os limites acima são exemplos de formato, **não thresholds de homologação** e não autorizam qualquer execução. Definir limites reais no termo de autorização, antes de criar os manifestos.

Par v1:
- `contract_version`, `agent_run_id` UUID, `organization_id` UUID, `question_sha256`, `context_version`;
- `official` e `shadow` com `sql`, `sql_sha256`, `run_id`, `provider_key`, `model_key`, `config_version`, `question_sha256`;
- `shadow` também com `shadow_record_id`, `gates:{security,contract,preflight}` todos `approved`, `preflight_executed:false`, `requires_reapproval:false`, `real_sql_executed:false`.

Obter os dois SQLs de evidências existentes e autorizadas, não do benchmark. Gerar hashes SHA-256 localmente, sem imprimir conteúdo. O avaliador não confia em hashes desacompanhados da SQL: recomputa e compara.

## Operações

1. Sem conexão financeira: `python3 scripts/operations/p3_numeric_parity_readonly.py --policy /caminho/privado/policy.json --pair /caminho/privado/pair.json`. Esperado `P3_PREFLIGHT=PASS` e `isolated_readonly_evaluation_executed=false`. Falha bloqueia sem fazer SELECT.
2. **Somente após autorização explícita para SQL financeira e conferência humana dos arquivos/hashes:** fornecer `--execute-readonly`, os SHA-256 de política e par aprovados e `--approval-reference` registrado. Exige `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` no processo, TTY e confirmação literal `EXECUTE-P3-READONLY-COMPARISON`; `P3_READONLY_DSN` deve pertencer a um LOGIN **SELECT-only** e sem privilégios de superuser/create/replication/bypass RLS. Nunca usar DSN administrativa ou `SET ROLE`.
3. O SQL é checado pelo SQL Security Gate do próprio LangGraph, catálogo/funcões permitidos, referências com schema, statement único SELECT e sem curingas. A conexão inicia `REPEATABLE READ READ ONLY`, `statement_timeout`, `lock_timeout`, `search_path=pg_catalog`, valida identidade do role, database e ACL antes de SELECT.
4. Executa as duas SQLs na **mesma transação**; compara tipos de coluna e multiconjunto de hashes de linhas, independentemente da ordenação; nunca exporta linhas brutas. Limita linhas/bytes e faz ROLLBACK. Diferenças e resultados vazios não recebem aceite. Uma prova de igualdade exata em **um caso** não significa paridade financeira completa nem correção contábil.

**Limites conhecidos:** ainda não implementa política de tolerância monetária assinada, igualdade tolerante a diferenças de apresentação, múltiplos datasets, nem cobertura de períodos. O status `exact_numeric_case_match` significa apenas correspondência exata do caso, incluindo tipos e linhas. `financial_parity_proven` permanece false por construção. O contrato de aceitação de G3 completo será tratado separadamente com regras contábeis versionadas, amostra representativa e aprovação humana.

## Testes

`python3 -m unittest scripts.test_p3_numeric_parity_readonly -v` — sem DB ou LLM; cobre políticas, hashes, gates, SQL fora de catálogo, mutações, execução bloqueada, proteção de arquivos e comparação de linhas numéricas. CI deve permanecer verde antes de merge. Nenhum teste de CI acessa banco real.
