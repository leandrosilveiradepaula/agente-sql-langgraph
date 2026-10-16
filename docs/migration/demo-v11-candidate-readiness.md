# Pré-verificação somente leitura para contexto candidato

O utilitário `scripts/preflight_semantic_candidate_readonly.py` inspeciona apenas
o contexto semântico versionado carregado do PostgreSQL pelo leitor de contexto.
Não faz consulta à base financeira, não chama LLM, não executa SQL financeiro,
não importa benchmark e não persiste alterações.

Para uso operacional, a credencial de contexto existente deve continuar com
permissões apenas de leitura e `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.

Exemplo no ambiente existente (sem imprimir DSN):

```bash
LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false python -m scripts.preflight_semantic_candidate_readonly \
  --version demo-finance-v10 \
  --simulate-temporal-strategy unique_metric_source_catalog_date
```

`--simulate-temporal-strategy` avalia uma hipótese operacional **sem modificar**
o snapshot, banco, SQL ou versão ativa. Uma data ambígua produz
`TEMPORAL_DATE_AMBIGUOUS`; a ferramenta nunca escolhe uma data automaticamente.
Para verificar a configuração já persistida da candidata, execute sem o
argumento de simulação. O parâmetro opcional `--expected-fingerprint` bloqueia
resultados em caso de mudança inesperada do contexto.

`checks_passed` significa **somente consistência dos metadados verificados**.
Não comprova a existência física de tabelas/colunas, fórmula financeira, joins
completos, correção contábil, segurança de execução ou prontidão para ativação.
`activation_authorized=false` é fixo. Erros estruturais e ambiguidades
bloqueiam o relatório. As contagens ajudam a reconhecer contextos incompletos,
não substituem a auditoria física e semântica.

## Gates antes de criar ou promover demo-finance-v11

1. Auditar versão e fingerprint do ambiente, sem mudar `SEMANTIC_AGENT_VERSION`.
2. Confirmar fisicamente as colunas e caminhos de join com uma operação de
   inventário **somente leitura**, feita pela credencial autorizada.
3. Identificar, em contexto versionado, o significado contábil de cada
   métrica, filtro obrigatório e coluna de competência/data de lançamento.
4. Quando houver múltiplas datas por fonte, usar
   `configured_metric_source_date` e `date_bindings` explícitos e auditados
   em vez de `unique_metric_source_catalog_date`.
5. Criar uma versão candidata imutável, validá-la com perguntas novas sem
   injetar expectativas de avaliação no agente e sem execução SQL real.
6. A aplicação de migração, a promoção de contexto e qualquer modificação
   no workflow n8n oficial permanecem ações separadas.

O arquivo `scripts/migrations/021_prepare_demo_finance_context_v11.sql`
usa `configured_metric_source_date` e inclui somente o binding temporal
versionado cuja origem foi documentada. As fontes sem binding temporal explícito
continuam bloqueadas para séries temporais. Não aplicar nem ativar a candidata
sem revisão das regras financeiras, da origem física e da evidência.

A workflow `v11-disposable-postgres.yml` executa a migração contra PostgreSQL
local descartável com metadados e dados inteiramente sintéticos. Verifica
sucesso, rejeição de reexecução e rollback em cenários adversos, além da
preservação de um destino já existente. O gate de integridade compara os
registros clonados em ambas as direções com `EXCEPT ALL`, excluindo apenas o
identificador de versão e a regra temporal adicional. Assim, uma cópia que
altera campos sem mudar a contagem também é rejeitada. O teste de integração
induz essa corrupção sintética e confirma o rollback.
 O teste **não comprova** a integridade
do PostgreSQL financeiro real, dos joins ou das regras contábeis.

## Auditoria de paridade entre snapshots (somente leitura)

O arquivo versionado `semantic_context/candidate_parity_demo_finance_v11.json`
declara a versão de origem, a candidata e **somente** as novas regras de
metadados permitidas. O motor genérico
`scripts/audit_semantic_candidate_parity_readonly.py` carrega ambas as versões
pelo leitor SELECT-only de contexto e verifica:

- versões e fingerprints observados;
- integridade estrutural dos dois snapshots;
- igualdade de todo o conteúdo normalizado de regras, entidades, DRE, padrões
  e catálogo, ignorando apenas a(s) regra(s) nova(s) explicitamente declarada(s);
- ausência de alterações silenciosas mesmo com contagens iguais.

Para executar **apenas depois** que uma candidata isolada tenha sido
persistida e estiver disponível para leitura (não a promove):

```bash
LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false python -m scripts.audit_semantic_candidate_parity_readonly \
  --policy semantic_context/candidate_parity_demo_finance_v11.json
```

A verificação exige a credencial `CONTEXT_POSTGRES_DSN` restrita a SELECT.
É possível fornecer `--expected-source-fingerprint` para impedir a validação
se a origem mudar desde a aprovação. Os resultados não imprimem DSN, SQL de
negócio, regras individuais ou dados financeiros; incluem versões,
fingerprints e apenas códigos/resumos de diferenças.

`parity_match` não significa autorização de ativação: o código mantém
`activation_authorized=false`, `financial_validation_complete=false` e
`real_sql_execution=false`. O inventário físico, as fórmulas financeiras e
as perguntas inéditas são gates independentes. Na ausência de uma v11
persistida ou de credenciais somente leitura, o comando falha fechado,
sem tentar criar tabelas, executar migração, alternar runtime ou acessar benchmark.

O n8n continua OFFICIAL e o LangGraph continua SHADOW.
