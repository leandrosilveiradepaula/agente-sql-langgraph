# Motor determinístico de resolução de intenção

## 1. Escopo

Este documento define o motor puro criado na Fase 7B da migração do
Agente SQL Financeiro DuckLake para LangGraph.

O motor recebe somente:

- a pergunta;
- `intent_resolution.config`;
- `intent_resolution.signals`.

Ele não acessa banco de dados, não chama modelos de linguagem, não gera
SQL e não conhece nomes de intenções ou termos de negócio.

## 2. API

```python
resolve_intent(
    question: str,
    intent_resolution: IntentResolutionContext,
) -> IntentResolutionResult
```

A função é pura e não modifica os objetos recebidos.

## 3. Normalização

A pergunta é normalizada com o mesmo contrato usado para os padrões não
regex:

- decomposição Unicode;
- remoção de acentos;
- `casefold`;
- substituição de pontuação por espaços;
- redução de espaços consecutivos.

Padrões `regex` permanecem brutos, conforme o contrato do normalizador.

## 4. Correspondência direta

Modos técnicos suportados:

- `exact`;
- `contains`;
- `starts_with`;
- `ends_with`;
- `all_tokens`;
- `any_token`;
- `regex`.

Uma expressão regular inválida não interrompe a execução. O sinal apenas
não corresponde.

## 5. Pontuação

Para cada intenção candidata:

```text
score final = soma dos sinais positivos - soma dos sinais negativos
```

O menor valor de `priority` entre os sinais correspondentes é mantido em
`best_priority` e usado como desempate quando as pontuações são iguais.

## 6. Decisão

A intenção é aplicada somente quando:

```text
best_candidate.score >= minimum_score
```

E, quando existir segundo candidato:

```text
best_candidate.score - second_candidate.score >= ambiguity_margin
```

A confiança retornada é `applied_confidence`, exclusivamente quando a
intenção é aplicada.

## 7. Fallback por cobertura de tokens

O fallback só é executado quando:

- `token_fallback.enabled` é verdadeiro;
- a polaridade do sinal está em `apply_to_polarities`;
- o modo do sinal está em `apply_to_match_modes`;
- a correspondência direta falhou.

Todos os limiares, tokens ignorados e regras de equivalência por prefixo
são recebidos do contexto versionado. O Python não define valores de
negócio ou listas ocultas.

## 8. Ausência de classificador legado

O campo `fallback_to_previous_intent` é preservado no snapshot para
compatibilidade com a origem n8n. O motor LangGraph não recebe uma
intenção anterior e não recria o classificador hardcoded.

Quando a pontuação mínima não é atingida ou os candidatos são ambíguos:

```text
intent = null
intent_confidence = null
```

## 9. Resultado

O resultado inclui:

- decisão aplicada ou não;
- motivo da decisão;
- intenção e confiança;
- pergunta normalizada;
- melhor e segundo candidatos;
- lista completa de candidatos;
- sinais correspondentes;
- diagnóstico do fallback por tokens;
- configuração usada;
- versão do motor.

## 10. Não objetivos desta fase

Esta fase não:

- altera o grafo;
- substitui `mark_ready_for_intent`;
- escreve `intent` no `GraphState`;
- chama Gemini;
- cria fallback semântico por IA;
- compara resultados com o n8n;
- gera ou executa SQL.
