# Fallback semântico portátil — proposta isolada, desligada por padrão

## Motivação e limite da evidência

O replay histórico G5 recuperou 63 perguntas e suas SQLs oficiais. O primeiro
lote SQL-InfoDive foi interrompido após 19 respostas `rejected`: 17
`INTENT_RESOLUTION_MINIMUM_SCORE_NOT_REACHED`, 1
`INTENT_RESOLUTION_AMBIGUOUS` e 1 `SQL_GENERATION_PLAN_INVALID`.
Nenhuma das 19 produziu SQL, e o modelo não foi acionado na maioria dos casos.
A execução financeira permanece proibida. Em um ensaio **offline** de
classificação das 63 perguntas, a configuração vigente classificou 26,
rejeitou 29 por pontuação e marcou 8 como ambíguas. Este ensaio não prova
que novos resultados terão a mesma distribuição.

## Implementação independente de empresa

O código continua a conhecer apenas os contratos: interpretar a pergunta,
identificar intenção conceitual, conferir proveniência e validar vínculos
físicos. Todas as intenções, descrições, conceitos, aliases, métricas,
dimensões, relacionamentos, tabelas, filtros e políticas pertencem ao
snapshot semântico versionado por tenant. Nenhum exemplo histórico, SQL
esperada, métrica ou filtro do benchmark entra no prompt.

O componente opcional `semantic_intent_fallback` pode ser declarado em uma
regra de configuração versionada. Exemplo **estrutural**, não autorização
de aplicar essa regra ou copiar para nenhum banco:

```json
{
  "component": "semantic_intent_fallback",
  "enabled": false,
  "applied_confidence": 0.75
}
```

`enabled=false` é o padrão efetivo: sem regra ou com regra desabilitada,
permanece o classificador determinístico atual, sem chamadas adicionais ao
provedor. Quando autorizado e habilitado para um contexto aprovado:

1. Executar normalmente `resolve_intent`.
2. Somente se a causa for `minimum_score_not_reached`, projetar para o
   interpretador a pergunta, a identidade/fingerprint do contexto e **apenas**
   intenções existentes, descrições e léxico de conceitos do catálogo.
   O processo não projeta tabelas físicas, SQL, resultados oficiais ou
   linhas de benchmark.
3. Usar o interpretador injetado (porta de provedor, sem regras de negócio).
   A implementação atual integra o cliente privado OpenAI-compatible já
   configurado no Shadow, sem trocar modelos nem alterar o serviço ativo.
4. Validar JSON de resposta com esquema exato, intenção autorizada, fingerprint
   do contexto, conceitos catalogados, frases presentes na pergunta, grupos
   de conceitos obrigatórios e proibição de spans com conceitos conflitantes.
   Resposta ambígua/ausente/inválida ou intenção explicitamente excluída
   permanece rejeitada.
5. Encaminhar a intenção e **evidência conceitual**, jamais SQL, para o
   planejador original, preservando os gates de métricas, filtros, joins,
   temporalidade, SQL security, contrato, preflight e aprovação.
6. Registrar estado da interpretação, provedor/modelo e uso de tokens de
   forma sanitizada; jamais incluir resposta bruta do modelo, credenciais ou
   chaves de autenticação nas evidências.

Uma classificação determinística **ambígua** nunca chama o fallback para
desempatar silenciosamente. O modelo não aumenta thresholds, não inventa
intents e não fornece mapeamentos contábeis sem contexto. A
`applied_confidence` é uma política versionada, **não** probabilidade
estatística calculada pela LLM.

## Governança, portabilidade e testes

O contrato do componente é idêntico para múltiplos clientes. As fixtures
sintéticas de regressão exercitam dois contextos independentes, com nomes de
intenções, operações e esquemas físicos diferentes. Isso comprova o
desacoplamento da transformação isolada, **não** a portabilidade operacional
entre dois tenants reais nem paridade numérica.

A interpretação reutiliza a porta neutra `SemanticIntentInterpreter`.
A branch inclui adaptadores offline-testados para **OpenAI-compatible** e
**Gemini**, ambos baseados nos clientes já existentes; nenhum modelo ou
provider adicional é ativado por default. Uma seleção explícita só é
aceita quando `provider_key`, `model_key` e `config_version` coincidem
integralmente com a identidade do interpretador configurado; sem coincidência
o fallback rejeita e não chama provedor externo. Os adaptadores não provam
disponibilidade real da LLM e a portabilidade entre múltiplos tenants reais
ainda precisa de homologação.

### Gates antes de qualquer ativação

- Revisar a regra por tenant e versionar o snapshot e seu fingerprint.
- Confirmar qual interpretação foi usada no runtime e o modelo efetivo.
- Comprovar testes completos, incluindo classificação, planejamento,
  ambiguidades e cenários sem DRE, com pelo menos dois contextos materiais.
- Autorizar e limitar custos e requisições do provedor em etapa separada.
- Não conectar respostas históricas ao gerador, nem executar SQL financeira
  para tentar melhorar pontuação.
- Manter `OFFICIAL=n8n`, `SHADOW=LangGraph` e
  `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` até gate humano de cutover.

A branch e a PR desta proposta não habilitam configuração, não executam
migrações, não alteram n8n, não fazem deploy e não habilitam SQL.

## Contrato semantic-intent-v2 — trecho do usuário versus alias autorizado

O interpretador não pode enviar diretamente um sinônimo novo ao planejador.
A resposta deve conter um vínculo com **três campos**: nome do conceito
existente no catálogo, `question_span` literalmente presente na pergunta
e `catalog_term` pertencente ao léxico versionado desse mesmo conceito.

O validador verifica o termo contra `concept_lexicon` e preserva separadamente
a citação do usuário. Na projeção para o planejador, somente o alias validado
é empregado na resolução das entidades/métricas. São recusados termos
inventados, conceitos inexistentes, citações fora da pergunta, fingerprints
diferentes e spans conflitantes.

A PR #231 acrescenta o gate complementar de **integridade pós-planejamento**:
uma interpretação por LLM não pode passar como `planned` se os aliases
prometidos não aparecem nas operações, métricas ou dimensões realmente
projetadas e autorizadas. O gate usa os papéis versionados do tenant,
não nomenclaturas de clientes. Os caminhos determinísticos continuam
independentes dessa verificação específica.

Um teste integrado, sem rede, demonstra a passagem de um sinônimo
inédito para um alias autorizado e sua vinculação física; os testes de
segurança demonstram rejeição quando há alias inventado ou vínculo perdido.
A prova não demonstra ainda qualidade no benchmark ou equivalência
financeira, que exigem seus próprios gates.

## Grounding físico antes da chamada ao modelo (sem vínculo inventado)

Quando a configuração versionada declara os papéis estruturais `metric`
ou `operation`, o projetor do contexto apresentado à LLM só mantém os
aliases do léxico de intenções que correspondem a entidades de métrica/
operação efetivamente autorizadas no catálogo do próprio tenant. A
verificação reutiliza os validadores físicos do planejador e exige
que o alvo de métrica pertença ao `table_catalog` **e** a um schema da
allowlist `allowed_schemas` do tenant. Recusa também conceitos com papéis
sobrepostos. Nenhuma tabela, coluna ou SQL é enviada ao modelo.

Aliases de métricas com destinos físicos diferentes ou de operações com
significados incompatíveis **não são oferecidos**. Registros equivalentes
continuam utilizáveis. Um conceito obrigatório sem alias comprovado
torna aquela intenção indisponível; as demais intenções válidas permanecem
selecionáveis. Se nenhuma intenção subsistir, o fallback recusa a solicitação
**antes de consumir tokens**. Isso não altera os thresholds existentes nem
cria respostas tabeladas.

O uso de um alias fisicamente válido **não garante que seus bindings
condicionais sejam aplicáveis** à pergunta. A cardinalidade, filtros,
períodos, joins e permissões continuam sujeitos aos gates posteriores.
Sinônimos ausentes ou semanticamente incertos devem ser confirmados e
versionados pelo domínio financeiro do cliente, nunca associados pelo
benchmark ou por suposição da LLM.

Os testes usam dois contextos sintéticos de esquemas e métricas diferentes,
intenção parcialmente indisponível, alias ambíguo e falta de coluna física.
São verificações offline, sem SQL financeira, rede ou chamada real ao modelo.
