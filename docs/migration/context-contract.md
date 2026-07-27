# Contrato de Contexto Semântico

## 1. Identificação

- Projeto: Agente SQL Financeiro DuckLake
- Componente: LangGraph
- Onda: 1 — Contrato real de contexto
- Documento: Contrato canônico do snapshot semântico
- Versão documental: 1.0
- Status: especificação para implementação
- Branch: `feat/context-contract`
- Baseline anterior: `4ab4bf4`
- Data da especificação: 2026-07-23

---

## 2. Objetivo

Definir o contrato canônico de contexto que será utilizado pelo núcleo LangGraph do Agente SQL Financeiro.

O contrato deverá permitir que o grafo carregue, valide e consuma o contexto semântico versionado sem conhecer diretamente:

- PostgreSQL;
- Supabase;
- nomes de clientes;
- nomes de marcas;
- nomes de responsáveis;
- nomes de intenções específicas;
- tabelas específicas do cliente;
- frases do benchmark;
- formato interno do workflow n8n.

O contexto deverá ser carregado uma única vez por execução e preservado como snapshot imutável durante todo o processamento.

---

## 3. Escopo desta onda

Esta onda contempla:

1. documentar a estrutura atualmente retornada pelo n8n;
2. definir o modelo canônico do domínio Python;
3. definir a normalização entre banco e domínio;
4. definir as validações obrigatórias;
5. definir a política de falha;
6. definir os critérios de aceite;
7. preparar a futura implementação do adapter PostgreSQL.

Esta onda não contempla:

- classificação de intenção;
- chamada ao Gemini;
- geração de SQL;
- planejamento de query;
- integração real com PostgreSQL;
- alteração de tabelas do Supabase;
- alteração do workflow n8n;
- criação de novas intenções;
- criação de tabela de catálogo de intenções.

---

## 4. Fonte de verdade atual

O workflow TEST atual carrega o contexto através do node:

`Postgres - Buscar Contexto DuckLake`

A consulta utiliza atualmente a versão:

`v2.0-ducklake-query-generator-offline-poc-test-responsavel-cc`

Essa versão é utilizada para filtrar os cinco conjuntos semânticos:

1. regras;
2. entidades;
3. mapeamento DRE;
4. padrões SQL;
5. catálogo de tabelas.

O valor da versão está atualmente escrito na SQL do node n8n.

No LangGraph, a seleção da versão deverá ser uma configuração operacional externa e não um valor escrito em nodes do grafo.

---

## 5. Estrutura bruta retornada pelo n8n

A estrutura atual do snapshot é conceitualmente:

```json
{
  "semantic_agent_version": "versão",
  "semantic_context_source": "postgres_versioned_semantic_context",
  "regras": [],
  "entidades": [],
  "dre": [],
  "padroes": [],
  "catalogo": [],
  "context_counts": {
    "regras": 0,
    "entidades": 0,
    "dre": 0,
    "padroes": 0,
    "catalogo": 0
  }
}
```

Essa estrutura representa o contrato físico atual do workflow n8n.

Ela não será usada diretamente pelos nodes LangGraph.

---

## 6. Conjunto de regras

### 6.1 Origem

Tabela:

`public.ai_ducklake_agent_rules`

### 6.2 Filtros atuais

- `agent_version` igual à versão ativa;
- `is_active = TRUE`.

### 6.3 Campos carregados

- `rule_group`
- `rule_name`
- `rule_content`
- `applies_to_intents`
- `validation_hint`
- `severity`
- `priority`

### 6.4 Responsabilidades

Os registros podem representar:

- regras gerais do agente;
- regras financeiras;
- regras aplicáveis a determinadas intenções;
- orientações de validação;
- configurações técnicas de componentes.

### 6.5 Configurações de componentes

Alguns registros usam `rule_content` como objeto JSON e possuem uma propriedade semelhante a:

```json
{
  "component": "identificador_do_componente"
}
```

Esses registros deverão ser normalizados pelo adapter para uma coleção derivada chamada `component_configs`.

`component_configs` não é uma nova tabela nem um novo campo obrigatório no PostgreSQL. É uma projeção derivada das regras carregadas.

---

## 7. Conjunto de entidades

### 7.1 Origem

Tabela:

`public.ai_ducklake_entity_aliases`

### 7.2 Filtros atuais

- `agent_version` igual à versão ativa;
- `is_active = TRUE`.

### 7.3 Campos carregados

- `entity_type`
- `user_term`
- `canonical_value`
- `target_table`
- `target_column`
- `sql_filter_hint`
- `business_rule`
- `priority`

### 7.4 Responsabilidades

Os registros podem representar:

- aliases e sinônimos;
- valores canônicos;
- filtros físicos;
- associação com tabela e coluna;
- regras de negócio;
- sinais configuráveis de intenção.

### 7.5 Incompatibilidade com o contrato Python atual

O contrato Python atual usa:

```python
aliases: dict[str, str]
```

Esse formato é insuficiente porque elimina:

- `entity_type`;
- `target_table`;
- `target_column`;
- `sql_filter_hint`;
- `business_rule`;
- `priority`;
- metadados de resolução de intenção.

No novo contrato, entidades deverão ser representadas como uma lista de objetos estruturados.

### 7.6 Sinais de resolução de intenção

Alguns registros possuem dentro de `sql_filter_hint` uma estrutura semelhante a:

```json
{
  "resolver": {
    "match_mode": "contains",
    "polarity": "positive",
    "score": 100
  }
}
```

Esses sinais deverão ser normalizados em uma coleção derivada chamada `intent_resolution.signals`.

Essa coleção será derivada dos registros de entidades e não constitui, nesta fase, uma nova tabela física.

Os modos técnicos suportados pelo contrato são:

- `exact`
- `contains`
- `starts_with`
- `ends_with`
- `all_tokens`
- `any_token`
- `regex`

As polaridades suportadas são `positive` e `negative`.

Para modos textuais, o padrão será normalizado com case folding, remoção de acentos, substituição de pontuação por espaços e compactação de espaços. Para `regex`, o padrão bruto será preservado porque sua pontuação e seus metacaracteres fazem parte da expressão.

---

## 8. Mapeamento DRE

### 8.1 Origem

Tabela:

`public.ai_ducklake_dre_mapping`

### 8.2 Filtros atuais

- `agent_version` igual à versão ativa;
- `is_active = TRUE`.

### 8.3 Campos carregados

- `dre_code`
- `nivel_1_bi`
- `business_description`
- `sign_convention`
- `category`
- `is_revenue`
- `is_deduction`
- `is_cost`
- `is_opex`
- `is_financial_result`
- `sql_filter_hint`
- `sort_order`

### 8.4 Responsabilidades

O mapeamento DRE deverá continuar sendo a fonte para:

- classificação dos grupos DRE;
- convenção de sinais;
- identificação de receitas;
- identificação de deduções;
- identificação de custos;
- identificação de OPEX;
- identificação de resultado financeiro;
- filtros e ordenação DRE.

Nenhuma dessas classificações deverá ser escrita diretamente no código Python.

---

## 9. Padrões SQL

### 9.1 Origem

Tabela:

`public.ai_ducklake_sql_patterns`

### 9.2 Filtros atuais

- `agent_version` igual à versão ativa;
- `is_active = TRUE`.

### 9.3 Campos carregados

- `intent_name`
- `pattern_name`
- `business_question_examples`
- `required_tables`
- `required_rules`
- `sql_pattern`
- `notes`
- `priority`

### 9.4 Responsabilidades atuais

Os padrões são utilizados para:

- listar intenções disponíveis;
- associar padrões a intenções;
- definir tabelas requeridas;
- definir regras requeridas;
- orientar o planejamento;
- orientar a geração SQL;
- orientar a validação contratual.

### 9.5 Regra para exemplos de perguntas

`business_question_examples` poderá ser utilizado para:

- documentação;
- revisão humana;
- curadoria;
- geração de fixtures;
- testes funcionais.

`business_question_examples` não deverá ser utilizado como entrada do router semântico de intenção.

Uma frase de benchmark não poderá se tornar regra literal de classificação.

### 9.6 Regra para SQL textual

`sql_pattern` poderá permanecer temporariamente no snapshot para compatibilidade e referência.

Ele não será considerado o contrato canônico de planejamento.

A evolução futura deverá transformar padrões SQL em contratos declarativos de query.

---

## 10. Catálogo de tabelas

### 10.1 Origem

Tabela:

`public.ai_ducklake_table_catalog`

### 10.2 Filtros atuais

- `agent_version` igual à versão ativa;
- `is_allowed = TRUE`.

### 10.3 Campos carregados

- `table_name`
- `schema_name`
- `table_type`
- `description`
- `grain`
- `primary_key`
- `key_columns`
- `metric_columns`
- `date_columns`
- `join_rules`
- `ai_hint`
- `priority`

### 10.4 Responsabilidades

O catálogo deverá ser a fonte física principal para:

- tabelas autorizadas;
- schemas autorizados;
- descrição das tabelas;
- grão;
- chave primária;
- chaves de associação;
- métricas;
- colunas de data;
- regras de join;
- orientações técnicas.

O antigo `Code - Schema Real Watson` não será portado para Python.

Informações físicas necessárias e ausentes no catálogo deverão ser adicionadas ao contexto versionado, e não duplicadas no código.

---

## 11. Modelo em três camadas

O contexto será dividido conceitualmente em três camadas.

### 11.1 Camada 1 — Registro físico

Representa exatamente o formato retornado pelo PostgreSQL.

Exemplos:

- `semantic_agent_version`
- `semantic_context_source`
- `regras`
- `entidades`
- `dre`
- `padroes`
- `catalogo`
- `context_counts`

Essa camada pertence ao adapter PostgreSQL.

### 11.2 Camada 2 — Snapshot canônico

Representa o domínio Python utilizado pelo grafo.

Estrutura conceitual:

```json
{
  "version": "versão semântica",
  "source": "origem",
  "fingerprint": "hash do snapshot",
  "counts": {
    "rules": 0,
    "entities": 0,
    "dre_mappings": 0,
    "query_patterns": 0,
    "table_catalog": 0
  },
  "rules": [],
  "entities": [],
  "dre_mappings": [],
  "query_patterns": [],
  "table_catalog": [],
  "allowed_schemas": [],
  "component_configs": {},
  "intent_resolution": {
    "config": {},
    "signals": []
  }
}
```

### 11.3 Camada 3 — Projeções por estágio

Cada estágio do grafo deverá receber apenas a parte necessária do snapshot.

Exemplos:

- `IntentContextProjection`
- `EntityContextProjection`
- `PlanningContextProjection`
- `GenerationContextProjection`
- `ValidationContextProjection`

Os nodes não deverão receber o snapshot inteiro quando apenas uma projeção menor for necessária.

---

## 12. Campos canônicos propostos

### 12.1 Identificação

- `version`
- `source`
- `fingerprint`

### 12.2 Contagens

- `counts.rules`
- `counts.entities`
- `counts.dre_mappings`
- `counts.query_patterns`
- `counts.table_catalog`

### 12.3 Coleções principais

- `rules`
- `entities`
- `dre_mappings`
- `query_patterns`
- `table_catalog`

### 12.4 Coleções derivadas

- `allowed_schemas`
- `component_configs`
- `intent_resolution.config`
- `intent_resolution.signals`

As coleções derivadas serão produzidas pelo adapter ou por um normalizador de contexto.

Elas não representam novos dados de negócio.

---

## 13. Regras de normalização

O adapter deverá executar as seguintes normalizações.

### 13.1 Listas

Quando uma coleção vier como:

- lista JSON;
- string contendo JSON;
- valor nulo;

o adapter deverá convertê-la para uma lista Python válida ou produzir erro estruturado quando o valor não puder ser interpretado com segurança.

### 13.2 Objetos JSON

Campos como:

- `rule_content`
- `sql_filter_hint`
- `join_rules`
- `required_tables`
- `required_rules`
- `business_question_examples`

poderão chegar como objetos JSON, listas ou strings serializadas.

O adapter deverá preservar o conteúdo original e produzir uma forma normalizada quando aplicável.

### 13.3 Ordenação determinística

As coleções deverão possuir ordenação estável.

Ordem recomendada:

```text
rules:
priority, rule_group, rule_name

entities:
priority, entity_type, user_term

dre_mappings:
sort_order, dre_code

query_patterns:
priority, intent_name, pattern_name

table_catalog:
priority, schema_name, table_name
```

### 13.4 Schemas autorizados

`allowed_schemas` deverá ser derivado dos valores únicos e não vazios de:

`table_catalog[].schema_name`

### 13.5 Configurações de componentes

Objetos válidos encontrados em `rule_content` que contenham uma identificação de componente deverão ser projetados em:

`component_configs[component_name]`

O registro original deverá continuar preservado em `rules`.

### 13.6 Configuração do resolvedor

A configuração do resolvedor de intenção deverá ser derivada de uma configuração de componente apropriada e projetada em:

`intent_resolution.config`

O contrato operacional atual contém:

- `component`
- `minimum_score`
- `ambiguity_margin`
- `applied_confidence`
- `fallback_to_previous_intent`
- `token_fallback` opcional

Os campos numéricos e booleanos deverão ser normalizados sem definir valores padrão escondidos no código. A ausência ou invalidade de um campo obrigatório deverá ser detectada pelo validator.

`token_fallback`, quando presente, poderá conter:

- `enabled`
- `apply_to_polarities`
- `apply_to_match_modes`
- `ignored_tokens`
- `minimum_pattern_tokens`
- `minimum_matched_tokens`
- `minimum_pattern_coverage`
- `maximum_unmatched_pattern_tokens`
- `allow_prefix_equivalence`
- `minimum_prefix_length`
- `minimum_prefix_ratio`

Listas que funcionem semanticamente como conjuntos deverão ser normalizadas de forma determinística. Nenhum token ignorado, limiar ou equivalência poderá ser criado no Python.

### 13.7 Sinais do resolvedor

Registros de entidade que contenham uma configuração válida em:

`sql_filter_hint.resolver`

deverão gerar sinais normalizados em:

`intent_resolution.signals`

O registro original deverá continuar preservado em `entities`.

### 13.8 Fingerprint

O snapshot deverá receber um fingerprint determinístico calculado a partir da forma canônica normalizada.

O fingerprint não deverá depender de:

- ordem acidental de objetos JSON;
- timestamps locais;
- IDs da execução;
- usuário;
- pergunta;
- ambiente virtual.

O fingerprint deverá mudar quando o conteúdo semântico mudar.

---

## 14. Validações obrigatórias

### 14.1 Identificação

O snapshot será inválido quando:

- `version` estiver vazio;
- `source` estiver vazio;
- `fingerprint` estiver vazio após a normalização.

### 14.2 Formato das coleções

Os seguintes campos deverão ser listas:

- `rules`
- `entities`
- `dre_mappings`
- `query_patterns`
- `table_catalog`

### 14.3 Catálogo mínimo

`table_catalog` deverá possuir pelo menos uma tabela autorizada.

Cada tabela deverá possuir:

- `table_name`
- `schema_name`

A combinação `schema_name + table_name` deverá ser única.

### 14.4 Padrões mínimos

`query_patterns` deverá possuir pelo menos um padrão ativo.

Cada padrão deverá possuir:

- `intent_name`
- `pattern_name`

A combinação `intent_name + pattern_name` deverá ser única dentro do snapshot.

### 14.5 Tabelas requeridas

Toda tabela referenciada em `query_patterns[].required_tables` deverá existir no catálogo autorizado.

### 14.6 Regras requeridas

Toda regra referenciada em `query_patterns[].required_rules` deverá existir no conjunto de regras normalizado.

A forma exata de identificação da regra deverá ser definida antes da implementação do validator.

### 14.7 Configuração do resolvedor

`intent_resolution.config` deverá ser um objeto e deverá identificar `component = intent_resolver`.

Os campos abaixo são obrigatórios:

- `minimum_score`: número finito e não negativo;
- `ambiguity_margin`: número finito e não negativo;
- `applied_confidence`: número entre 0 e 1;
- `fallback_to_previous_intent`: booleano.

A presença do campo de compatibilidade `fallback_to_previous_intent` não obriga o LangGraph a implementar um classificador legado. O uso operacional desse campo será definido no estágio de classificação.

Quando `token_fallback.enabled = true`:

- `apply_to_polarities` deverá ser uma lista não vazia contendo somente polaridades suportadas;
- `apply_to_match_modes` deverá ser uma lista não vazia contendo somente modos suportados;
- `ignored_tokens` deverá ser uma lista de textos, podendo ser vazia;
- `minimum_pattern_tokens`, `minimum_matched_tokens` e `minimum_prefix_length` deverão ser inteiros positivos;
- `maximum_unmatched_pattern_tokens` deverá ser inteiro não negativo;
- `minimum_pattern_coverage` e `minimum_prefix_ratio` deverão estar entre 0 e 1;
- `allow_prefix_equivalence` deverá ser booleano.

Quando `token_fallback.enabled = false`, o objeto mínimo `{"enabled": false}` será válido.

### 14.8 Sinais de intenção

Todo sinal normalizado do resolvedor deverá apontar para uma intenção existente entre os padrões ativos. Nenhum sinal poderá criar uma intenção nova.

Cada sinal deverá possuir:

- `raw_pattern` e `normalized_pattern` não vazios;
- `match_mode` pertencente ao contrato técnico;
- `polarity` igual a `positive` ou `negative`;
- `score` numérico, finito e não negativo;
- `priority` numérica, finita e não negativa quando informada.

Para `match_mode = regex`, `normalized_pattern` deverá preservar o padrão bruto.

### 14.9 Prioridades

Valores de prioridade, quando informados, deverão ser numéricos e não booleanos.

### 14.10 Contagens

As contagens informadas pelo banco deverão ser comparadas com o tamanho das coleções normalizadas.

Divergência de contagem deverá gerar erro ou warning conforme a causa.

A política inicial recomendada é:

- divergência causada por transformação segura: warning;
- divergência causada por perda ou conteúdo inválido: error.

### 14.11 Duplicidades

Duplicidades idênticas poderão ser normalizadas de forma controlada.

Duplicidades com a mesma chave e conteúdo incompatível deverão invalidar o snapshot.

---

## 15. Política de falha

Falhas no carregamento ou validação do contexto deverão resultar em:

```text
final_status = infrastructure_error
failure_stage = load_context ou validate_context
```

Não será permitido:

- continuar com catálogo vazio;
- continuar sem padrões;
- ignorar intenção inexistente;
- usar contexto parcial silenciosamente;
- recorrer a tabelas escritas no código;
- usar uma versão padrão escondida no node;
- continuar com uma configuração do resolvedor inválida.

Erros deverão seguir o formato comum `AgentError`.

---

## 16. Seleção da versão

O grafo não deverá escolher diretamente a versão semântica.

A versão será resolvida através de configuração operacional.

Possíveis fontes futuras:

1. variável de ambiente;
2. arquivo de configuração da aplicação;
3. tabela de versão ativa;
4. referência explícita recebida pela API de TEST.

A implementação deverá permitir uma versão explícita para benchmark.

O valor não deverá ser espalhado em nodes ou serviços.

---

## 17. Imutabilidade

O mesmo snapshot deverá ser utilizado durante toda a execução.

Depois de carregado:

- não será recarregado no meio do grafo;
- não será alterado por nodes;
- não receberá regras criadas durante a execução;
- não será complementado por hardcodes;
- terá versão e fingerprint registrados no resultado.

A política recomendada para a base semântica é:

```text
versões ativadas são imutáveis
+
cada execução registra o fingerprint real
```

---

## 18. Segurança

O snapshot não deverá conter:

- senha do PostgreSQL;
- connection string;
- tokens;
- chave Gemini;
- token IAM;
- headers;
- cookies;
- credenciais do usuário;
- stack trace de infraestrutura.

O adapter deverá retornar somente dados semânticos autorizados.

---

## 19. Relação com o usuário

O `user_profile` poderá ser utilizado futuramente para filtrar regras ou tabelas permitidas.

Ele não será utilizado como:

- versão do contexto;
- identificação do cliente;
- identificação do ambiente;
- chave do snapshot.

O LangGraph recebe usuário já autenticado pelo backend.

---

## 20. Relação com classificação de intenção

O contrato de contexto deverá fornecer ao classificador:

- intenções permitidas;
- configurações do resolvedor;
- sinais configuráveis;
- descrições semânticas futuras;
- regras de desambiguação futuras.

O classificador não deverá receber:

- `business_question_examples`;
- SQL pronta do padrão;
- resultado esperado do benchmark;
- intenção legada como verdade;
- catálogo físico completo.

A estrutura semântica específica do catálogo de intenções será definida em uma onda posterior.

---

## 21. Relação com o planner

O planner deverá receber uma projeção contendo:

- padrão selecionado;
- regras aplicáveis;
- tabelas necessárias;
- colunas relevantes;
- joins autorizados;
- entidades resolvidas;
- mapeamento DRE relevante.

O planner não deverá precisar pesquisar novamente o snapshot inteiro.

---

## 22. Relação com os validadores

O Security Gate deverá utilizar o catálogo para validar:

- schemas;
- tabelas;
- objetos autorizados.

O Contract Gate deverá utilizar o plano e os padrões para validar:

- tabelas requeridas;
- filtros;
- métricas;
- dimensões;
- aliases;
- fórmulas;
- construções proibidas.

Nenhum dos gates deverá possuir uma lista paralela de tabelas escrita no código.

---

## 23. Diferenças em relação ao ContextSnapshot atual

O contrato atual possui:

- `version`
- `versions`
- `allowed_schemas`
- `tables`
- `rules`
- `aliases`
- `dre_mappings`
- `sql_patterns`

As alterações conceituais necessárias são:

```text
aliases: dict
→
entities: list

tables simplificadas
→
table_catalog estruturado

sql_patterns
→
query_patterns

ausência de source
→
source obrigatório

ausência de fingerprint
→
fingerprint obrigatório

ausência de counts
→
counts normalizados

configurações escondidas nas regras
→
component_configs derivado

sinais escondidos nas entidades
→
intent_resolution derivado
```

O campo `versions` atual não corresponde diretamente ao snapshot retornado pelo n8n.

Ele não deverá ser mantido apenas para preencher versões fictícias.

Poderá ser removido ou redefinido quando houver fontes reais para versões internas independentes.

---

## 24. Não objetivos

Não faz parte desta especificação:

- criar hardcode para a versão atual;
- criar nomes fixos de intenções no Python;
- criar aliases específicos no Python;
- transformar cada pergunta em um padrão;
- copiar o classificador JavaScript;
- copiar o `Schema Real Watson`;
- criar templates SQL por benchmark;
- alterar regras financeiras;
- criar novas tabelas no Supabase;
- definir o prompt Gemini;
- implementar preflight Watson.

---

## 25. Critérios de aceite da implementação

A implementação futura desta especificação será considerada concluída quando:

```text
[ ] O domínio representa todos os campos relevantes do snapshot real.
[ ] Entidades não são reduzidas a dict[str, str].
[ ] O catálogo preserva grão, chaves, métricas, datas e joins.
[ ] A versão não está escrita em nodes do grafo.
[ ] O snapshot possui fingerprint determinístico.
[ ] allowed_schemas é derivado do catálogo.
[ ] Configurações de componentes são normalizadas.
[ ] Sinais de intenção são normalizados.
[ ] Sinais só apontam para intenções ativas.
[ ] required_tables são validadas contra o catálogo.
[ ] required_rules são validadas contra as regras.
[ ] Snapshot inválido produz infrastructure_error.
[ ] Nenhum fallback hardcoded é utilizado.
[ ] Os testes atuais continuam aprovados.
[ ] Novos testes unitários do contexto estão aprovados.
```

---

## 26. Sequência de implementação após aprovação

A implementação deverá ocorrer nesta ordem:

1. atualizar os tipos do domínio em `app/domain/context.py`;
2. criar um normalizador de snapshot;
3. criar um validador de snapshot;
4. atualizar o fake de contexto dos testes;
5. atualizar `load_context`;
6. criar testes de normalização;
7. criar testes de validação;
8. integrar o validator ao grafo;
9. executar toda a baseline;
10. criar commit exclusivo do contrato de contexto.

O adapter PostgreSQL real será implementado somente depois que o contrato e os testes locais estiverem estáveis.

---

## 27. Decisões ainda abertas

As seguintes decisões exigem inspeção adicional ou spike técnico:

1. tipo físico real de cada campo JSONB;
2. formato real de `required_tables`;
3. formato real de `required_rules`;
4. formato real de `join_rules`;
5. identificação canônica de uma regra;
6. política exata para duplicidades idênticas;
7. algoritmo final do fingerprint;
8. fonte operacional da versão ativa;
9. necessidade de versões internas por conjunto;
10. necessidade futura de catálogo próprio de intenções.

Nenhuma dessas decisões autoriza hardcode temporário no código.

---

## 28. Registro de aprovação

Este documento deverá ser revisado antes da alteração de `app/domain/context.py`.

Após aprovação, a implementação ocorrerá em pequenos incrementos, sempre com:

- arquivo completo;
- teste correspondente;
- compilação;
- execução da baseline;
- inspeção do diff;
- commit isolado.
