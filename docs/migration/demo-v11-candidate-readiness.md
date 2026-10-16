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
usa `configured_metric_source_date` com dois bindings explícitos para a
métrica `amount` (um por fonte): o orçamento usa `competencia`, enquanto o
realizado também propõe `competencia` como referência de competência contábil
para DRE e comparação com orçamento. A origem v10 confirma que as duas fontes
declaram essa coluna; o realizado também declara `data_lancamento`. Nenhuma
escolha é feita pela quantidade de datas: ambas as associações vêm do
manifesto semântico versionado, e a cópia em PostgreSQL verifica que cada
métrica possui exatamente um binding temporal autorizado.

**Limite de interpretação:** a configuração não transforma `data_lancamento`
em sinônimo de `competencia`, nem prova a semântica contábil por consultar o
catálogo. Uma pergunta explicitamente sobre data de lançamento precisa de
seleção de referência temporal própria (ainda não demonstrada); não é lícito
responder como se fosse competência. A cobertura de planejamento temporal,
incluindo eventual consulta comparativa multiorigem, precisa de evidência de
generalização independente antes de qualquer promoção.

**Gates de aprovação separados:** confirmar a definição financeira com
responsável pelo dado, verificar o esquema físico e contratos de filtros/DRE,
testar perguntas novas e equivalentes sem golden SQL no gerador, e revisar
evidências Shadow. Não aplicar ou ativar a candidata somente porque o
pré-validador retorna `metadata_checks_passed`.

O CI inclui cenários de rejeição para data não autorizada em uma fonte,
binding declarado sem métrica, métrica adicional sem binding explícito,
fonte ambígua, clonagem com payload alterado e reexecução da mesma versão.
Todos os registros usados são sintéticos.

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

A integração sintética também carrega v10/v11 pelo **mesmo leitor
`PostgresContextRepository` do LangGraph**, com uma credencial efêmera
restrita a `USAGE` de schema e `SELECT` nas cinco coleções semânticas.
O CI verifica explicitamente a ausência de `INSERT`, `UPDATE` e `DELETE`
nesse papel. Os snapshots normalizados são comparados contra o manifesto
versionado de paridade da v11. Uma alteração silenciosa em metadado da regra
nova e outra em uma entidade clonada são induzidas apenas no banco descartável
e devem resultar em bloqueio. O teste não utiliza benchmark, credenciais da
VPS, base financeira real, provedor LLM nem execução SQL financeira.

## Prévia da v11 em memória, antes de qualquer migração

O arquivo `scripts/preview_semantic_candidate_readonly.py` faz um ensaio
com **somente a versão de origem disponível no PostgreSQL**. Lê a v10 com
credencial SELECT-only, constrói uma v11 hipotética inteiramente em memória,
e adiciona exclusivamente os registros completos autorizados pelo manifesto
versionado. Em seguida calcula novo fingerprint, exige paridade exata com a
origem e executa as validações estruturais e de prontidão temporal.

```bash
LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false \
  python -m scripts.preview_semantic_candidate_readonly \
  --policy semantic_context/candidate_parity_demo_finance_v11.json \
  --expected-source-fingerprint <fingerprint-previamente-auditado>
```

O argumento `--expected-source-fingerprint` é recomendado para impedir a
continuação após mudanças não revisadas na origem. O código recusa colisões
com regras ou componentes já existentes: não substitui metadados herdados
silenciosamente. Os relatórios contêm somente versões, fingerprints,
contagens e códigos de diagnóstico; não imprimem nomes de clientes, regras
integrais, DSN ou respostas financeiras.

O ensaio **não cria a versão no PostgreSQL**. Se houver bindings temporais
sem data explicitamente configurada, retorna `blocked` com códigos para
auditoria. Um eventual `metadata_checks_passed` significa apenas que os
metadados verificados em memória passaram: não autoriza promover, executar
SQL ou dispensar validações financeiras independentes.

A workflow PostgreSQL descartável compara o fingerprint dessa prévia contra
o fingerprint da v11 realmente criada pela migração de teste. Isso assegura
que o ensaio reproduz o comportamento do normalizador e da cópia transacional,
sem acessar a base financeira real.

## Executar diagnóstico na VPS sem redeploy

O executor `scripts/run_shadow_semantic_candidate_preflight.sh` lê um
**manifesto versionado** do repositório e usa o ambiente do container Shadow
existente, sem imprimir DSN nem reiniciar serviços. Ele verifica
`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`, exige checkout na `main`, copia
somente código rastreado pelo commit para um diretório isolado em `/tmp`
e remove os arquivos transitórios ao encerrar. O código usado no diagnóstico
é aquele do commit exibido, não necessariamente o do serviço em execução;
**o serviço em execução permanece intacto**.

Depois de atualizar a `main` do checkout da VPS, execute:

```bash
bash scripts/run_shadow_semantic_candidate_preflight.sh \
  semantic_context/candidate_parity_demo_finance_v11.json
```

Para repetir o diagnóstico com bloqueio de alterações da v10, informe como
segundo argumento o fingerprint da origem aprovado na primeira coleta.
Um fingerprint diferente interrompe a leitura. O resultado é um JSON
sanitizado com versões, fingerprints, quantidades e códigos de inconsistência.
Não cole nem registre valores de variáveis de ambiente, arquivos `.env` ou
respostas brutas de provedores.

O primeiro ensaio pode retornar `blocked` em vez de `metadata_checks_passed`:
isso é evidência de metadados incompletos, **não** autorização para reduzir
threshold, escolher automaticamente datas ou executar a migração. Tratar
`candidate_readiness_blocking_codes` e
`candidate_structural_error_codes` como itens para revisão semântica. Sem
acesso ao container/DSN correto ou sem permissões de leitura, o diagnóstico
falha fechado e não tenta outras credenciais ou acessos.

## Auditoria de paridade entre snapshots (somente leitura)

O arquivo versionado `semantic_context/candidate_parity_demo_finance_v11.json`
declara a versão de origem, a candidata e **somente** as novas regras de
metadados permitidas, incluindo o registro completo esperado (conteúdo,
intenções aplicáveis, prioridade, severidade e demais metadados). A regra
adicional também é comparada integralmente; autorizar seu nome não autoriza
alterações arbitrárias no conteúdo. O motor genérico
`scripts/audit_semantic_candidate_parity_readonly.py` carrega ambas as versões
pelo leitor SELECT-only de contexto e verifica:

- versões e fingerprints observados;
- integridade estrutural dos dois snapshots;
- igualdade de todo o conteúdo normalizado de regras, entidades, DRE, padrões
  e catálogo, isolando apenas a(s) regra(s) nova(s) cujo registro completo coincide com a política declarada;
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
