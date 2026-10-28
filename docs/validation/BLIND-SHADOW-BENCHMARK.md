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
  --output benchmark-private/questions-only.json \
  --receipt-output benchmark-private/freeze-receipt.json

# Separadamente, submeter SOMENTE questions-only.json ao fluxo n8n/Shadow,
# quando esse caminho estiver autorizado; capturar depois os records assinados.

python -m scripts.blind_shadow_benchmark evaluate \
  --baseline benchmark-private/official-baseline.json \
  --manifest benchmark-private/questions-only.json \
  --evidence benchmark-private/shadow-records.json \
  --receipt benchmark-private/freeze-receipt.json \
  --output benchmark-private/evaluation.json
```

Não há ativação automática, LLM paga, execução de SQL ou rede nesses
comandos. Arquivos de saída existentes nunca são sobrescritos; para
reavaliar, usar outro nome versionado. CLI imprime somente códigos de
status sanitizados; o relatório não devolve SQL, pergunta, nome de
tabela, coluna, literal, principal nem conteúdo bruto de erro.

**Congelamento reforçado:** o `prepare` gera um segundo arquivo privado (`freeze-receipt.json`) com fingerprints da baseline e do manifesto, sem SQL ou respostas. O `evaluate` exige esse recibo e falha se qualquer campo da baseline for alterado. Manter o recibo em custódia separada **antes da geração**; recibo produzido no mesmo computador **não comprova data de congelamento nem autenticidade da fonte**. O relatório registra essas duas ressalvas e não as converte automaticamente em PASS. Arquivos privados de entrada (baseline, recibo, evidência) precisam de permissões POSIX 0600, e todos os outputs são criados sem overwrite (0600 no POSIX). Nunca subir baseline, evidências ou recibo privado ao GitHub. Runs oficiais duplicadas entre casos e registros Shadow fora da lista de runs autorizadas bloqueiam a avaliação inteira.\n\n**Status por caso**: `corresponde` (apenas SQL normalizada **com identidade de tenant, provedor/modelo, fingerprint de contexto e intenção atestados**),
`diverge` (diferença estrutural/intent), `inconclusivo`
(correlação ambígua, query não analisável, fonte/modelo/contexto/intenção\nnão atestados ou incompatíveis, reparo sem aprovação), `sem_evidencia` (ausência de
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

## Auditoria de disponibilidade de baseline na DEMO — 28/10/2026\n\nConsulta exclusivamente agregada à `public.ai_agent_runs` da DEMO ativa, sem retornar perguntas, SQL, usuários, metadados brutos ou dados financeiros: **42 registros**, **39** com SQL gerada, **42** com pergunta, `run_id` e `user_id`, **0** com `organization_id`, **0** com par `llm_provider`/`llm_model` nos campos próprios. Fonte `interface`, executor `postgres_demo`: 38 registros, todos com SQL gerada e intenção; outros três `interface` sem executor e uma tentativa `shadow_p2_generate_only` (esta sem SQL no campo gerado). Histórico de 04/09/2026 a 26/10/2026. **Nenhuma dessas 42 linhas constitui por si só uma baseline Gemini+Gemini homogênea e versionada**; não presumir provedor pelo nome do fluxo, tenant pelo ambiente ou paridade por SQL textual. A SOURCE antiga encontra-se temporariamente pausada para liberar a quota do CRM.\n\n**J1 gate honesto:** instrumento e controles offline passam por CI, mas a Jornada 1 **não estará homologada** até congelamento anterior à geração, origem/provedor validado, perguntas inéditas independentes e execução Shadow autenticada. Não executar 63 perguntas sem autorização; nunca injetar SQL histórica no gerador.\n\n## O que falta para homologar

O runner prepara e avalia **evidências já existentes**. Não substitui
Jornada 2 (portabilidade em bancos/clientes), Jornada 3 (Shadow
Produto → n8n → LangGraph real com correlação) nem Jornada 4 (paridade
numérica autorizada). Não prova que o workflow legado de 68 nós está
publicado nem que foi substituído. A fonte oficial continua n8n+Gemini;
o novo caminho permanece Shadow com SQL real desligada.


## Fronteira de SQL catalogada x SQL gerada (G3)

`ai_ducklake_sql_patterns.sql_pattern`, `notes` de padrões e
`QueryPlan.sql_pattern_metadata` podem carregar SQL histórica ou
pré-escrita; permanecem no **planejador/evidência** para auditoria, mas
não atravessam o contrato LLM de Generate/Repair. O padrão enviado ao
provedor contém somente intenção, nome, prioridade e referências de
tabelas/regras autorizadas. `generation_context.pattern_metadata`
mantém exclusivamente `pattern_name`. As regras, dimensões, métricas,
filtros e joins continuam vindo do catálogo semântico versionado, sem
resposta pronta codificada no novo motor.

Os testes injetam SQL e markers de respostas históricas nesses três
campos e verificam tanto os payloads quanto os prompts Gemini, sem
mutação do QueryPlan e com fingerprints independentes de SQL pré-escrita.
Isso protege essas rotas conhecidas, não certifica todos os textos
livres de regras externas: catálogos continuam exigindo governança
contra exemplos/expectativas de benchmark incorporados indevidamente.
