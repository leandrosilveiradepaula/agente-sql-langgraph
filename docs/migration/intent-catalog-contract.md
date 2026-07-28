# Contrato do catálogo semântico de intenções

## 1. Status

Este documento é uma extensão normativa de
`docs/migration/context-contract.md`.

Ele formaliza a estrutura semântica específica do catálogo de intenções
mencionada como evolução posterior no contrato principal.

Esta etapa define somente o contrato. Normalização, validação, motor de
resolução e carga de dados serão implementados em incrementos separados.

## 2. Objetivo

O catálogo semântico de intenções deverá permitir classificação
determinística e configurável sem:

- nomes fixos de intenções no Python;
- termos de negócio no Python;
- frases literais de benchmark como regra de produção;
- dependência do classificador legado do n8n;
- uso de SQL pronta para classificação;
- uso de catálogo físico completo no classificador;
- chamada a IA ou serviço externo.

## 3. Origem física

Nesta onda, não será criada uma nova tabela física.

As definições deverão ser armazenadas em registros versionados de:

`public.ai_ducklake_entity_aliases`

O adapter PostgreSQL atual já carrega os campos necessários:

- `entity_type`;
- `user_term`;
- `canonical_value`;
- `target_table`;
- `target_column`;
- `sql_filter_hint`;
- `business_rule`;
- `priority`.

Os filtros físicos existentes continuam válidos:

- `agent_version` igual à versão ativa;
- `is_active = TRUE`.

## 4. Identificação do registro

Uma definição semântica de intenção deverá possuir:

```text
entity_type = intent_definition
```

Mapeamento físico:

| Campo físico | Significado |
|---|---|
| `entity_type` | Deve ser `intent_definition` |
| `user_term` | Nome estável da definição |
| `canonical_value` | Nome da intenção já existente em `query_patterns` |
| `business_rule.intent_catalog` | Conteúdo declarativo da definição |
| `priority` | Prioridade determinística da definição |
| `target_table` | Deve ser nulo |
| `target_column` | Deve ser nulo |
| `sql_filter_hint.resolver` | Não deverá existir |

## 5. Projeção canônica

Os registros válidos deverão ser projetados em:

```text
intent_resolution.intent_catalog
```

Compatibilidade:

```text
nenhum intent_definition ativo
→ intent_resolution.intent_catalog = []
→ comportamento atual preservado
```

O catálogo derivado fará parte da forma canônica usada para o
fingerprint.

## 6. Estrutura de uma entrada

Cada item de `intent_resolution.intent_catalog` deverá conter:

```json
{
  "intent_name": "generic_intent",
  "definition_name": "generic_definition",
  "semantic_description": "Descrição semântica da intenção.",
  "rules": [],
  "priority": 1
}
```

A combinação deverá ser única por `intent_name`, desconsiderando
maiúsculas e minúsculas.

## 7. Estrutura física em business_rule

Formato esperado:

```json
{
  "intent_catalog": {
    "semantic_description": "Descrição semântica genérica.",
    "rules": [
      {
        "rule_name": "generic_required_rule",
        "effect": "require",
        "concepts": [
          {
            "concept_name": "first_concept",
            "terms": ["alpha", "alpha synonym"],
            "match_mode": "contains",
            "minimum_term_matches": 1
          },
          {
            "concept_name": "second_concept",
            "terms": ["beta"],
            "match_mode": "contains",
            "minimum_term_matches": 1
          }
        ],
        "minimum_concept_matches": 2,
        "score": null,
        "priority": 1
      }
    ]
  }
}
```

O exemplo acima é técnico e deliberadamente não contém termos de
negócio.

## 8. Conceitos

Cada conceito deverá conter:

- `concept_name`;
- `terms`;
- `normalized_terms`;
- `match_mode`;
- `minimum_term_matches`.

`terms` representa alternativas semânticas do mesmo conceito.

Não deverá conter perguntas completas de benchmark.

Os termos textuais deverão ser normalizados com a mesma função canônica
de busca já utilizada pelo projeto.

Padrões `regex` deverão preservar o conteúdo bruto.

Depois da normalização, termos semanticamente duplicados dentro do mesmo
conceito deverão ser rejeitados.

## 9. Regras compostas

Cada regra deverá conter:

- `rule_name`;
- `effect`;
- `concepts`;
- `minimum_concept_matches`;
- `score`;
- `priority`.

Efeitos permitidos:

- `positive_score`;
- `negative_score`;
- `require`;
- `exclude`.

`positive_score` adiciona score quando a regra é satisfeita.

`negative_score` subtrai score quando a regra é satisfeita.

`require` condiciona a aplicação da intenção.

`exclude` impede a aplicação da intenção quando satisfeita.

Score é obrigatório, finito e não negativo apenas para efeitos de
pontuação. Em `require` e `exclude`, deverá ser nulo ou ausente.

## 10. Isolamento

Um registro `intent_definition`:

- deverá continuar preservado em `entities`;
- deverá gerar uma entrada em `intent_resolution.intent_catalog`;
- não deverá gerar item em `intent_resolution.signals`;
- não deverá gerar item na projeção legada `aliases`;
- não deverá criar uma nova intenção;
- não deverá ser interpretado como filtro físico.

Registros existentes que não sejam `intent_definition` manterão o
comportamento atual nesta onda.

## 11. Validações obrigatórias

O validator deverá rejeitar:

- definição sem `user_term` ou `canonical_value`;
- intenção inexistente;
- definição duplicada;
- `business_rule.intent_catalog` inválido;
- descrição vazia;
- regras vazias;
- regras duplicadas;
- conceitos vazios ou duplicados;
- termos vazios ou duplicados após normalização;
- modo, efeito, score ou prioridades inválidos;
- mínimos fora do intervalo;
- tabela ou coluna física preenchida;
- `sql_filter_hint.resolver` presente.

## 12. Ordenação determinística

Catálogo:

1. `priority`;
2. `intent_name`;
3. `definition_name`.

Regras:

1. `priority`;
2. `rule_name`.

Conceitos:

1. `concept_name`.

Termos normalizados serão ordenados deterministicamente.

## 13. Relação com business_question_examples

`business_question_examples` permanece fora do classificador.

Ele continuará restrito a documentação, revisão humana, curadoria,
fixtures, testes funcionais e avaliação de cobertura.

Nenhum exemplo será copiado automaticamente para o catálogo.

## 14. Relação com sinais existentes

`intent_resolution.signals` continuará existindo.

O motor futuro agregará, de forma determinística:

```text
sinais simples
+
regras compostas do intent_catalog
→ candidatos
```

A política de agregação é definida na seção 16 deste documento.

## 15. Neutralidade

O Python conhecerá somente estruturas técnicas, modos e efeitos.

Não conhecerá cliente, versão específica, intenção real, domínio,
benchmark, tabelas de negócio ou métricas específicas.

## 16. Política determinística de agregação

O motor deverá avaliar primeiro os sinais simples e depois todas as
entradas normalizadas de `intent_resolution.intent_catalog`.

Para cada conceito:

- cada termo será avaliado pelo `match_mode` configurado;
- um conceito será satisfeito quando `matched_term_count` atingir
  `minimum_term_matches`;
- termos distintos serão contabilizados separadamente;
- nenhum fallback por tokens será aplicado implicitamente aos conceitos.

Para cada regra:

- uma regra será satisfeita quando `matched_concept_count` atingir
  `minimum_concept_matches`;
- `positive_score` adicionará seu score ao candidato;
- `negative_score` subtrairá seu score do candidato;
- todas as regras `require` de uma intenção deverão ser satisfeitas;
- qualquer regra `exclude` satisfeita bloqueará a intenção.

A intenção bloqueada por `require` ou `exclude` não participará do
ranking nem do cálculo de ambiguidade, mesmo que possua score acumulado
por sinais ou regras de pontuação.

Uma regra de pontuação poderá criar um candidato mesmo quando não houver
sinal simples correspondente. Regras `require` e `exclude`, isoladamente,
não criarão candidato com score.

A prioridade efetiva do candidato será o menor valor configurado entre
as evidências que efetivamente contribuíram ou restringiram a intenção.
Uma regra de pontuação não satisfeita não poderá alterar a prioridade de
um candidato existente.

O ranking será determinado por:

1. maior score final;
2. menor prioridade efetiva;
3. nome da intenção em ordem estável, para desempate técnico.

A aplicação continuará dependente de `minimum_score` e
`ambiguity_margin` da configuração versionada do resolvedor.

O resultado deverá preservar diagnóstico completo das entradas,
conceitos, termos e regras avaliados, inclusive regras não satisfeitas e
intenções bloqueadas. O catálogo ausente será tratado como lista vazia,
sem alterar a resolução baseada apenas em sinais.

## 17. Integração com o grafo

`load_context` deverá validar o snapshot completo antes de disponibilizar
`context.intent_resolution` para o classificador.

`classify_intent` deverá encaminhar ao motor a projeção completa, incluindo:

- `config`;
- `signals`;
- `intent_catalog`.

O resultado integral de `resolve_intent` deverá ser preservado em
`GraphState.intent_resolution_result`, incluindo o diagnóstico do catálogo.

Depois da classificação:

- resolução aplicada seguirá com `final_status = processing`;
- rejeição semântica encerrará com `final_status = rejected`;
- falha de contrato ou erro inesperado seguirá para
  `finalize_infrastructure_error`;
- o erro original e `failure_stage = classify_intent` deverão ser
  preservados pelo finalizador.

O catálogo ausente deverá manter o fluxo anterior baseado somente em sinais.

## 18. Incrementos

```text
7D.1 contrato e tipos
7D.2 normalização, isolamento e validação
7D.3 motor determinístico
7D.4 integração e regressões
7D.5 carga curada e teste real
```
