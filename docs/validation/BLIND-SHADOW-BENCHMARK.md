# Jornada 1 — Benchmark cego da inteligência SQL (sem refatorar n8n)

**Decisão do operador de 23/10/2026:** os 68 nós da inteligência n8n
existente são a baseline histórica, NÃO um alvo de modernização. O n8n
continua como orquestrador depois do cutover; será desligada apenas a
inteligência antiga, após provar equivalência funcional/financeira.

## Contrato das duas fases

**FASE A — PREPARE**, antes de geração. A baseline privada n8n pode
conter SQL e metadados de resultado, mas o artefato de perguntas
contém **apenas** `contract_version`, `suite` e itens
`{case_id, question}`. Os campos de baseline não são propagados ao
gerador, ao planner, ao resolver de intenção, a prompts, à seleção de
contexto ou ao reparador. O usuário aplica as perguntas pelo caminho
oficial/Shadow autorizado em outra etapa: esse utilitário NÃO faz requests.

**FASE B — EVALUATE**, somente DEPOIS de coletar evidências de execução
Shadow independentemente. Abre a baseline e um export privado de
`ShadowRunRecord` completo, valida seu fingerprint criptográfico e
executa em memória o **comparador SQL pós-geração existente**:
`CompareShadowSqlUseCase`. Não gera SQL, não acessa benchmark no leitor
semântico, não lê base financeira, não executa consultas e não chama
n8n/Gemini/SQL-InfoDive. Usa a mesma rotina de correlação, segurança
de identidade e de análise SQL do endpoint interno.

Nenhuma fase habilita `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION`. O processo
recusa flags de execução real/LLM ativa, mesmo sem possuir esses ports.

## Baseline histórica privada (formato mínimo)

Arquivo local que **não pode ser commitado**:

```json
{
  "contract_version": "1",
  "suite": "baseline-operador-v1",
  "cases": [
    {
      "case_id": "case-001",
      "question": "Pergunta histórica já executada pelo fluxo oficial",
      "agent_run_id": "id-correlacionado-da-run",
      "principal_id": "id-autenticado",
      "organization_id": "tenant-validado-opcional",
      "official_sql": "SQL oficial já persistida, apenas no arquivo privado",
      "official_intent": "intencao_registrada",
      "official_provider": "provedor-registrado",
      "official_model": "modelo-registrado",
      "official_context_fingerprint": "fingerprint-se-realmente-atestado"
    }
  ]
}
```

Campos opcionais: `agent_run_id`, `principal_id`,
`organization_id`, `official_sql`, `official_intent`,
`official_provider`, `official_model`, `official_context_fingerprint`.
Usar **identidades registradas**, nunca inventadas. Para pergunta nova,
`official_sql` pode ficar ausente: a ausência de baseline será
`sem_evidencia`, não aprovação de SQL.

Um export `evidence.json` usa formato
`{"contract_version":"1","records":[ShadowRunRecord, ...]}`. Esses
records podem conter perguntas, SQL, identidades e contexto privados,
portanto **não armazenar em `scripts/validation`, `semantic_context`
ou repositório compartilhado**. Obter export somente por caminho
operacional autorizado, sem imprimir credenciais; este runner não acessa
o banco para exportar evidência.

## Uso sem rede, sem pagar API, sem deploy

Em clone de trabalho autorizado, usar diretório `benchmark-private/`
(ignorado por Git), preferencialmente com permissões locais restritas:

```bash
python -m scripts.blind_shadow_benchmark prepare \
  --baseline benchmark-private/official-baseline.json \
  --output benchmark-private/questions-only.json

# Separadamente, submeter SOMENTE questions-only.json ao fluxo n8n/Shadow,
# quando esse caminho estiver autorizado; capturar depois os records assinados.

python -m scripts.blind_shadow_benchmark evaluate \
  --baseline benchmark-private/official-baseline.json \
  --manifest benchmark-private/questions-only.json \
  --evidence benchmark-private/shadow-records.json \
  --output benchmark-private/evaluation.json
```

Não há ativação automática, LLM paga, execução de SQL ou rede nesses
comandos. Arquivos de saída existentes nunca são sobrescritos; para
reavaliar, usar outro nome versionado. CLI imprime somente códigos de
status sanitizados; o relatório não devolve SQL, pergunta, nome de
tabela, coluna, literal, principal nem conteúdo bruto de erro.

**Status por caso**: `corresponde` (apenas SQL normalizada),
`diverge` (diferença estrutural/intent), `inconclusivo`
(correlação ambígua, query não analisável, fonte de provedor
incompatível, reparo sem aprovação), `sem_evidencia` (ausência de
record/correlação/SQL oficial). Cada caso carrega
`financial_result_status=nao_autorizado_executar`.
Nenhum resultado comprova paridade financeira. Diferentes SQLs
podem ser economicamente equivalentes, e SQLs idênticas podem
retornar resultados diferentes em snapshots diferentes. Comparação
de números exige outra etapa com credenciais read-only e autorização
separada.

## Critérios verificáveis

- Manifest de geração possui exatamente `case_id` e `question`
  por item; qualquer expectativa/SQL/resultado nele bloqueia avaliação.
- O manifesto deve casar **literalmente** com as perguntas da
  baseline privada congelada. Cases com identidades de runs, perguntas
  ou organizações inconsistentes não são considerados paritários.
- Mais de uma tentativa Generate para mesmo `agent_run_id` torna a
  avaliação inconclusiva até escolher formalmente a tentativa com
  evidência suficiente; não selecionar por melhor resultado.
- Evidências alteradas/sem fingerprint íntegro falham fechadas.
- Provedores/modelos são atribuídos somente por evidências registradas;
  jamais inferidos do default. SQL reparada exige reaprovação.
- Avaliar perguntas **históricas e inéditas independentes**. Separar
  `intent_status`, `provider_status`, `context_status`,
  `sql_verdict` e `financial_result_status`; não reduzir critérios
  nem escrever `if` por frase, DRE, marca ou cliente.
- Testar `python testar_blind_shadow_benchmark.py` ou
  `python scripts/check_all.py` offline, sem 63-case benchmark pago.

## O que falta para homologar

O runner prepara e avalia **evidências já existentes**. Não substitui
Jornada 2 (portabilidade em bancos/clientes), Jornada 3 (Shadow
Produto → n8n → LangGraph real com correlação) nem Jornada 4 (paridade
numérica autorizada). Não prova que o workflow legado de 68 nós está
publicado nem que foi substituído. A fonte oficial continua n8n+Gemini;
o novo caminho permanece Shadow com SQL real desligada.
