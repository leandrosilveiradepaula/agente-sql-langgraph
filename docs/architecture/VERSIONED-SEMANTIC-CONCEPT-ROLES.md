# Conceitos portáteis por papéis estruturais — contrato de migração

## Problema confirmado

O resolvedor determinístico e o planejador reconheciam literalmente
`dimension_grouping` para proteger tokens e detectar agrupamento. Esse nome
representa um **conceito do catálogo de um cliente**, não uma propriedade
universal do produto. Sua presença no código impedia que outro cliente
configurasse um vocabulário distinto sem modificar Python.

## Solução

O mecanismo recebe um mapeamento versionado
`intent_resolution.config.concept_roles`. Cada chave é um papel **estrutural**
do planejador; os valores são nomes de conceitos válidos existentes no
catálogo de intenções do tenant:

```json
{
  "concept_roles": {
    "grouping": ["some_tenant_defined_concept"],
    "operation": ["another_tenant_concept"],
    "metric": ["a_third_tenant_concept"],
    "period": ["a_tenant_date_concept"]
  }
}
```

O valor é **ilustrativo e não deve ser copiado literalmente** para contextos
reais. O nome de conceito, os sinônimos, os termos, o idioma, as tabelas, as
colunas e os vínculos de métricas pertencem ao catálogo do cliente.

- Resolvedor: os conceitos configurados em `grouping` protegem tokens
  de agrupamento contra inferência indevida de outras métricas ou conceitos.
- Planejador: aceita evidência e termos apenas desses conceitos e resolve a
  dimensão nas entidades/tabelas físicas **autorizadas** do mesmo snapshot.
- Outros papéis estruturais: `operation`, `metric` e `period` selecionam
  evidência de conceitos do catálogo do mesmo tenant. Nenhum nome de
  conceito específico é embutido nas etapas de detecção semântica.
  Os tipos de *entidade* `analytical_operation` e `financial_metric`
  ainda são contratos de adaptação legados separados; sua revisão de
  portabilidade é um trabalho distinto, não deve ser confundida com
  a eliminação dos nomes de **conceitos** desta mudança.
- Validador: rejeita configuração malformada, duplicada ou que referencie
  conceitos inexistentes. Chamadas diretas ao resolvedor também falham fechado.
- Sem o campo opcional, não existe fallback implícito para o nome legado nem
  adivinhação de função com base em palavras-chave.
- Mantêm-se os mesmos mecanismos de validação de SQL e aprovação.
- A operação `grouping` é estrutural; não é uma intenção, métrica, DRE,
  unidade, conta, coluna, alias ou regra específica de cliente.

## Impacto e homologação

**A ausência do campo no contexto antigo altera a interpretação de
agrupamentos. Portanto, a branch não está pronta para cutover nem para merge
operacional sem planejar a atualização dos catálogos e verificar a paridade.**
O contrato é deliberadamente fail-closed: não há hardcode TRANSITIONAL
oculto no Python. Antes da aplicação, é necessário criar uma nova versão do
contexto semântico por tenant com os conceitos corretos e validar o
fingerprint. Sem mapear o conceito, o planejador não pode assumir uma dimensão.

Critérios para homologar:

1. Revisar e versionar os `concept_roles` de cada tenant; preservar a versão
   anterior para rollback.
2. Testar interpretação e planejamento com pelo menos dois contextos
   materialmente distintos (nomes, catálogos físicos, permissões), incluindo
   situações de conceito ausente, ambíguo ou sem vínculo físico.
3. Reexecutar o benchmark apenas em modo isolado com perguntas cegas e
   autorização específica; as respostas históricas e SQLs esperadas não
   podem entrar no gerador ou planejador.
4. Conferir qualidade e segurança; não baixar thresholds ou adicionar
   nomes próprios para aumentar pontuação.
5. Preservar `OFFICIAL=n8n`, `SHADOW=LangGraph` e
   `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.

Esta PR é apenas código/testes/documentação. Não altera banco, n8n, produção,
catálogo ativo, permissões ou credenciais. Não implica aprovação de merge.


## Preflight de migração, somente leitura

A implementação de `app/domain/semantic_role_migration.py` prepara em memória
uma **nova versão candidata**, sempre a partir do catálogo bruto completo.
O chamador deve fornecer `expected_source_fingerprint` e o mapa de papéis
**escolhido e revisado fora do benchmark**, não inferido automaticamente pelo
código. O preflight confirma:

- a impressão digital exata do contexto de origem;
- a existência de uma regra única e válida de configuração do resolvedor;
- a validade do novo catálogo e a integridade das referências de papéis;
- a imutabilidade das demais coleções, regras, tabelas, políticas e aliases;
- a alteração da versão e do fingerprint da candidata;
- a comparação de decisões de intenção e projeções de planejamento, usando
  somente perguntas (sem golden answer, SQL histórica ou SQL executada).

O relatório contém apenas contagens de transições e categorias de vínculos
incompletos. Os dados de cada pergunta, SQL e exemplos históricos não são
devolvidos. Uma alteração de intenção ou plano resulta em `REVIEW_REQUIRED`.
Mesmo `NO_DETECTED_DRIFT` **não autoriza ativação**, paridade financeira ou
cutover. A migração é proibida sem novo snapshot e aprovação humana.

### Evidência diagnóstica G5 (não homologação)

Em ensaio privado offline, com 63 perguntas históricas usadas somente como
avaliação posterior e um **mapeamento de papéis provisório**, o preflight
confirmou o fingerprint de origem e encontrou:

- intenções alteradas: 0;
- planos alterados: 25;
- planos antes aceitos: 26; candidatos aceitos: 17;
- transições `planned → rejected`: 9, todas por
  `PLANNING_ANALYTICAL_BINDING_INCOMPLETE`;
- projeções aceitas mas alteradas: 16.

O resultado é `REVIEW_REQUIRED`. O teste não usou SQL histórica, não
chamou LLM, não executou SQL financeira e não ativou configuração. A causa
exata de cada vínculo e a correção de negócio devem ser determinadas pelo
catálogo autorizado, não por perguntas→SQL nem por thresholds artificiais.


### Diagnóstico ampliado e decisão de segurança

A auditoria isolada do contexto privado detectou um descompasso **do catálogo
versionado**, não apenas uma exceção de código: o snapshot possui 17 aliases
de operações analíticas, quatro entidades de métricas financeiras e dois
bindings explícitos de métricas. Isso não autoriza inferir a relação entre
eles; tais relações exigem validação do domínio de cada empresa.

O preflight da candidata conta, de modo agregado, operações sem operandos
comprovados: 9 operações de comparação e 3 operações de ranking contidas nos
9 casos que passaram de planejados a rejeitados. Não são 12 casos distintos.
**Nenhuma das nove comparações tem métricas vinculadas suficientes para
satisfazer a cardinalidade configurada.** Portanto, a rejeição
`PLANNING_ANALYTICAL_BINDING_INCOMPLETE` deve continuar ativa. Também
há 16 planos aceitos cuja projeção difere, e devem ser revisados.

O planejador passou a ignorar `best_candidate` que não corresponda à
intenção selecionada e a validar os operandos explicitamente vinculados.
Não foi ampliada a aprovação de comparações sem métricas. A exigência de
operando obrigatório em rankings historicamente sem operando é um contrato
separado e versionado, não uma alteração implícita na migração de papéis.

**Não se pode declarar estes problemas resolvidos somente por CI verde.**
Para remover o bloqueio, é necessário obter mapeamentos de métricas/
operações/dimensões autorizados para o tenant, versionar o catálogo candidato,
repetir o preflight e comprovar que os 9 casos têm operandos completos,
sem inventar métricas. Se novas operações forem legítimas, o planejamento
pode mudar, mas requer revisão explícita; o benchmark nunca determina
quais vínculos contábeis devem ser configurados.


### Integridade de papéis: capacidades e exclusividade

O mecanismo admite somente os papéis estruturais implementados pelo
planejador: `grouping`, `operation`, `metric` e `period`. Uma chave de
papel inexistente não pode ser ignorada silenciosamente: toda solicitação
com papel não suportado falha com `concept_role_unsupported`.

Um mesmo conceito de catálogo também não pode receber dois papéis diferentes
na mesma versão (`concept_role_overlap`). Essa regra protege contra
contabilizar a mesma evidência conceitual simultaneamente como operação e
métrica, por exemplo. Vários conceitos distintos **podem** representar
um mesmo papel estrutural, se existirem no catálogo do tenant. Não há nomes
de negócio pré-configurados no código.

Esses gates foram validados por testes e no snapshot privado em memória.
O diagnóstico anterior de migração permanece `REVIEW_REQUIRED`:
não são autorizados reparos automáticos de métricas ou alterações de produção.


## Gate de integridade de interpretação na saída do planejamento

`app/domain/semantic_plan_gate.py` valida **somente** os casos cuja
classificação utilizou o interpretador opcional (`semantic_interpretation_selected`).
Ele extrai os aliases declarados na evidência, resolve seu papel por
`intent_resolution.config.concept_roles` e exige que permaneçam nas
projeções físicas já autorizadas (`planned_metrics`,
`analytical_operations`, `detected_dimensions`). Referências temporais
exigem evidência de projeção temporal ou filtros e não devem ganhar datas
inferidas. O código aceita os formatos de evidência do resolvedor legado
(`semantic_signal`) e do interpretador (`semantic_signals`) sem descartar
nenhum deles.

Quando a interpretação não tem papel utilizável ou o plano perde algum
binding, `build_plan` retorna `PLANNING_SEMANTIC_BINDING_INCOMPLETE`,
sem SQL e com o nome estrutural do papel ausente, jamais dados do cliente.
Não afeta a validação de perguntas atendidas pelo classificador
determinístico.

Esta proteção é complementar, não substitui a checagem da cardinalidade
e das relações entre operações e métricas. Os mapeamentos contábeis ainda
precisam ser definidos pelo contexto autorizado de cada tenant.


## Auditoria de completude do catálogo — independente do benchmark

`app/domain/semantic_catalog_audit.py` inventaria em memória os metadados
estruturais de operações, aliases de métricas e bindings físicos. Usa os
validadores do planejador e a tabela de colunas autorizadas; não usa perguntas,
SQLs históricas, métricas específicas, dados financeiros nem dependências de
rede. Os relatórios contêm apenas contagens agregadas e códigos de erro.

A falta de `metric_binding` explícito é **indicador de revisão, não prova
automática de erro**: alguns catálogos utilizam aliases diretos de métricas.
O auditor não exige DRE, IMD ou número fixo de métricas, e não considera cada
operação uma relação contábil necessariamente incompleta. Ambiguidade entre
aliases ou alvos físicos inválidos exige revisão. Mesmo
`INVENTORY_COMPLETE` nunca significa paridade financeira ou aprovação de
ativação.

O resultado integra o preflight de migração e é avaliado **em paralelo** à
comparação cega das projeções de plano. É possível ter inventário consistente,
mas perguntas cujo planejamento muda por associação semântica insuficiente.

No snapshot privado G5 desta etapa: 17 aliases de operações válidos, quatro
aliases de métricas válidos representando **um único conceito contábil**, dois
bindings explícitos do mesmo conceito, nenhuma inconsistência estrutural
detectada pelo inventário. O status do inventário foi
`INVENTORY_COMPLETE`, enquanto o preflight de 63 perguntas **permanece
`REVIEW_REQUIRED`** por 9 rejeições e 16 mudanças de plano. Isso confirma
que completude estática e equivalência funcional são gates diferentes.

## Integridade de proveniência e isolamento da auditoria

A auditoria de catálogo agora falha fechado se o snapshot não possui versão
não vazia ou fingerprint hexadecimal bem formado. Esses campos são pré-condição
para a auditoria; a correspondência efetiva do fingerprint com a origem é
verificada separadamente no preflight de migração. O auditor não presume que
um formato válido, isoladamente, prova autenticidade.

Aliases compartilhados entre uma operação e uma métrica geram
`cross_role_alias_ambiguous`: não se aplica desempate automático nem regra
específica de cliente. Classes personalizadas de entidades são agregadas
como `other`, sem divulgação dos nomes de domínio no relatório.

Testes novos cobrem perda de versão, fingerprint inválido, alias com múltiplas
funções e proteção de metadados particulares. A auditoria permanece
somente leitura, sem benchmark, geração SQL, chamadas LLM ou aprovação de
ativação.

## Cobertura física do vocabulário semântico e viabilidade de bindings

O catálogo versionado é a única fonte de nomes e significados de métricas.
Um termo que o classificador reconhece para o papel estrutural `metric`
não deve ser presumido uma métrica física. A auditoria cruza os termos dos
conceitos declarados nas regras de intenção (`require` e `positive_score`)
com os aliases físicos já validados pelo planejador.

Os relatórios retornam somente **contagens agregadas**, por papel
`metric` e `operation`: `catalog_alias_terms`,
`physically_resolved_terms` e `unbound_alias_terms`. Uma lacuna sinaliza
`semantic_fallback_binding_review_required=true`, **sem fabricar uma
associação contábil**. A ação correta é revisar cada alias na origem
autorizada e publicar novo catálogo versionado, não criar um `if` por
pergunta nem inserir uma SQL histórica no gerador.

A nova `semantic_binding_feasibility.py` avalia apenas a viabilidade
*teórica* das combinações de bindings declarados, respeitando
cardinalidades, condições `when_present`/`when_absent`, conceito comum
quando exigido e referências físicas distintas. A busca tem limite
estrutural; quando não é possível provar o resultado dentro do orçamento
retorna `indeterminate`, nunca `impossible` por aproximação. Rotas
alternativas de métricas diretas não são consideradas impossíveis só por
não haver `metric_binding`.

O planejador também compara identificadores de conceitos de forma
case-insensitive nos predicados; condições contraditórias com diferenças
de caixa são recusadas e predicados equivalentes produzem referências
consistentes. Nenhum valor financeiro ou coluna foi configurado pelo código.

### Evidência diagnóstica privada (não autorização de migração)

No snapshot G5 verificado por fingerprint, o preflight em memória mediu
dez termos semânticos de métricas, dos quais **quatro** têm alias físico
diretamente correspondente e **seis** não têm; operações: **16/16** termos
com correspondência. As dez declarações de operação de comparação
possuem uma combinação de bindings teoricamente viável. Isso não prova
que todas as perguntas fornecem as condições necessárias.

Na avaliação separada das 63 perguntas, continuaram **nove**
`planned → rejected` (`PLANNING_ANALYTICAL_BINDING_INCOMPLETE`) e
**16** projeções aceitas alteradas; nenhuma decisão de intenção mudou.
A diferença entre cobertura lexical, viabilidade dos bindings e
equivalência por pergunta é intencional: são gates independentes.

Sem chamadas de LLM, execução financeira, leitura da SQL histórica,
ativação de catálogo ou mudança na operação oficial.

