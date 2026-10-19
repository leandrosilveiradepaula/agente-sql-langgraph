# Demo Finance v17 — termo negado, não conceito inteiro

**Status:** candidata virtual não promovida. Execução SQL real desativada no Shadow.
n8n permanece oficial; o LangGraph não altera respostas oficiais.

## Evidência antes da mudança

Validação read-only v15 × v16 enviada pela VPS:

| Suite | v15 | v16 |
|---|---:|---:|
| Independentes v12 | 11/12 | 11/12 |
| Temporais v11 | 10/12 | 10/12 |
| Operações v13 | 18/20 | 18/20 |
| Temporais v14 | 14/14 | 14/14 |
| Flexões v15 | 22/26 | 25/26 |
| Negação/temporal v16 | 10/32 | 26/32 |
| **Total** | **85/116** | **104/116** |

A avaliação encontrou **zero regressões observadas** nesse conjunto, mas
12 verificações ainda falharam. A maior parte ficou abaixo do score mínimo
porque a pergunta não deu evidência suficiente de métrica. Reduzir score ou
injetar uma resposta conhecida não é solução aceitável.

## Falhas de capacidade geral

**Negação de conceitos compartilhados:** a v16 suprimia inteiramente um
conceito quando um de seus termos aparecia negado. Se dois operadores
distintos compartilham o mesmo conceito (por exemplo, ordenação versus
comparação), negar um deles podia ocultar o outro mesmo estando afirmado.

**Granularidade anual:** a cobertura temporal de `year` incluía
`anual`, `anuais` e `por ano`, mas não o plural genérico `anos`.

## Mudanças estruturais

- A negação léxica fica vinculada a cada **termo** e só o suprime quando não
  há outra ocorrência afirmativa independente do mesmo termo.
- O resolvedor conserva a regra de `semantic_defaults`: conceitos com
  todos os termos negados não podem reaparecer por defaults.
- A operação de overlay `extend_negation_scope_concepts` amplia a lista de
  conceitos autorizados **apenas após** a criação explícita e versionada da
  política. Rejeita termos repetidos, nomes ausentes ou alteração arbitrária.
- A v17 reutiliza integralmente o overlay v16 e acrescenta, no contexto,
  o termo anual plural e a cobertura de operações analíticas negativas.
- Nenhum threshold, esquema, padrão SQL, métrica financeira, DRE, tabela,
  credencial, conexão, intenção ou frase de cliente entra no Python.

## Limitações intencionais

O componente continua conservador: não tenta inferir metricas a partir de
poucos indícios, nem faz interpretação livre de negação distante. Mantém
falhas explícitas quando não existe evidência semântica suficiente. Não
declara 100% de cobertura do domínio ou capacidade de execução financeira.

As 30 contraprovas independentes da v17 testam operações afirmadas e negadas
na mesma solicitação, palavras de ano, agrupamentos não temporais, séries
temporais, ranking e guardrails de referência de data. Suas expectativas
são usadas **somente depois** da classificação e do planejamento.

## Gates para aceitação

1. CI offline completo, sem chamadas LLM/SQL real/benchmark formal.
2. Merge humano do código, se CI estiver aprovado.
3. Comparação virtual v16 × v17 na VPS usando o comparador read-only, nas
   seis suítes históricas mais a nova suíte v17. Conferir **cada regressão**,
   não somente total de aprovados.
4. Rejeitar qualquer regressão semanticamente perigosa, principalmente
   operações concorrentes com negação, e manter v17 não ativada até
   decisão explícita.
