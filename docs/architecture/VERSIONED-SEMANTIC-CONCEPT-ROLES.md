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

## Gate de identidade semântica em tempo de planejamento (v1.4)

O scanner de catálogo identifica aliases ambíguos, mas a segurança exige
que o **próprio planejador** também recuse uma escolha errada:

- `PLANNING_METRIC_ALIAS_AMBIGUOUS`: um alias de métrica sem vínculo
  condicional que permita desambiguar o significado aponta para múltiplos
  `metric_ref` físicos. A prioridade não autoriza escolher uma medida.
- `PLANNING_OPERATION_ALIAS_AMBIGUOUS`: o mesmo alias representa
  configurações analíticas incompatíveis (direção, limite, cardinalidade ou
  operação), mesmo que uma delas tenha prioridade menor.
- Registros semanticamente equivalentes e duplicados podem ser deduplicados;
  conflitos reais de significado exigem nova versão do catálogo.
- Uma evidência de agrupamento de `best_candidate` de outra intenção é
  ignorada, igual aos mecanismos já aplicados às métricas e operações.

O contrato do planejador evolui para
`PLANNER_VERSION=v1.4.0-semantic-alias-integrity`, preservando evidência
do comportamento efetivamente testado e sem mudar o significado de nenhuma
empresa no código.

### Períodos nunca são comprovados por filtros alheios

Para interpretações opcionais por LLM, `semantic_plan_gate.py` exige
que cada alias de período identificado apareça em uma série temporal
cuja coluna de data esteja autorizada no catálogo, ou em um filtro cujo
`binding_ref` resolvido tenha **alvo físico em `date_columns`** do
mesmo catálogo e que preserve o alias citado. Um filtro de produto,
organização ou qualquer outra dimensão não prova período. Não há nome de
coluna de data fixo; dois tenants com estruturas diferentes passam pelo
mesmo mecanismo. Essa verificação é adicional às validações de SQL e
autorizações físicas existentes.

Regressões: testes de aliases ambíguos e equivalentes, isolamento de
intenções, datas não autorizadas, filtros sem relação temporal e dois
esquemas sintéticos materialmente distintos. Estas verificações não
certificam paridade numérica nem autorizam cutover.


## Isolamento da intenção escolhida e diagnóstico de causas

O planejador recusa `PLANNING_INTENT_EVIDENCE_MISMATCH` quando a evidência
de interpretação declara uma intenção diferente daquela selecionada. O
bloqueio ocorre **antes da projeção física** e vale para qualquer tenant,
mesmo que ambas as intenções possuam `query_pattern` válido. As evidências
sem intenção explícita continuam submetidas aos filtros de candidatos já
existentes; essa mudança não autoriza interpretações cruzadas.

A auditoria cega de migração agora retorna
`rejected_case_cause_counts`, com **classes puramente estruturais** para
os planos antes aceitos e agora rejeitados. Entre elas estão: aliases de
métricas sem resolução, metadados inválidos, requisitos de bindings ausentes,
predicados que impedem um binding, conflito de conceito métrico e
incompatibilidade de dimensão. Os valores são contados **uma vez por causa,
por pergunta rejeitada**, e podem se sobrepor: a soma das causas não equivale
ao número de perguntas distintas. Não são divulgados termos, filtros,
identificadores de tabelas, SQLs, nomes de métricas ou textos das perguntas.

Essa saída destina-se somente à avaliação **posterior** de planejamento:
não é um catálogo de respostas, não alimenta o interpretador/gerador e não
repara SQL automaticamente. Qualquer associação financeira ou novo sinônimo
deve ser comprovado na origem autorizada do tenant e publicado como nova
versão sem alterar o motor.

O contexto G5 anterior indicou seis termos de métricas sem alias físico
direto. A análise independente do catálogo mostrou que cinco não aparecem
como aliases de nenhuma entidade e um pertence a outra classe de entidade.
Isso é uma **lacuna de contexto**, não evidência suficiente para inventar
um significado contábil. A execução do relatório ampliado sobre o snapshot
privado ainda depende de acesso autorizado; não afirmar que esse
`rejected_case_cause_counts` já foi medido nas 63 perguntas.
## Fronteira física de autorização por tenant

A auditoria não deve certificar como completo um catálogo apenas porque
seus nomes de tabelas e colunas são fisicamente válidos. Em adição a
`table_catalog`, exige a allowlist `allowed_schemas` versionada do
tenant. Se ausente ou malformada, retorna `BLOCKED` antes de qualquer
inspeção física. Um alias `financial_metric` que aponta para schema fora
da allowlist é classificado como `metric_physical_binding_invalid`;
um `metric_binding` condicional nessas condições é classificado como
`metric_binding_schema_unauthorized` e não conta como rota válida de
métrica.

Esses checks utilizam apenas schema/tabela/coluna fornecidos pelo próprio
tenant, sem nomes conhecidos de empresas nem semântica contábil no motor.
Relatórios públicos permanecem agregados, sem revelar nomes físicos.
Testes com dois esquemas independentes e com destinos de outro schema
confirmam que a auditoria não permite uma migração baseada em metadados
de fora da autorização declarada. Isso é diagnóstico estático, não
substitui RBAC, RLS, SQL Gate ou testes de isolamento entre tenants reais.
## Planejamento v1.5 — autorização de schema em runtime e métricas explícitas

A etapa de planejamento verifica a allowlist `allowed_schemas` do tenant
**também em runtime**, antes da geração SQL, em ambos os caminhos:
`financial_metric` (alias direto) e `metric_binding` (condicional).
A existência de tabela e coluna em `table_catalog` **não implica
autorização**. Um alias físico inválido não pode introduzir um
`metric_concept` para posterior inferência por binding condicional.
Essa proteção vale para qualquer tenant, sem condições por empresa.

A versão `PLANNER_VERSION=v1.5.0-tenant-metric-gate` acrescenta
`PLANNING_METRIC_BINDING_INCOMPLETE`. O novo caminho de interpretação
por LLM (`semantic_interpretation_selected`) falha fechado quando
a pergunta tem métrica explícita sem vínculo, com vínculo parcialmente
resolvido, com metadados inválidos ou com condições de binding
incompletas. O gate é independente da cardinalidade de operações:
não pode haver `planned` apenas por o motor ter reconhecido
a operação quando a métrica não foi vinculada.

**Compatibilidade transitória documentada:** os resolvedores determinísticos
legados ainda podem produzir planos com termos de métrica lexicalmente
reconhecidos, porém sem alias físico conhecido. Isso evita alterar a
resposta oficial do n8n durante Shadow, **não certifica** esses planos como
financeiramente corretos e deve ser externalizado/retirado apenas após
paridade e ativação controlada por tenant. Metadados físicos comprovadamente
inválidos, inclusive schemas não autorizados, são rejeitados mesmo nesse
caminho legado. Não se alteram expectativas históricas do benchmark nem se
criam mapeamentos para fazê-lo passar.

A regressão valida planos completos, metadados inválidos, aliases físicos
de outro schema, bindings condicionais fora da allowlist, impedimento de
inferência a partir de alias inválido, métrica parcialmente resolvida pela
LLM e comportamento determinístico legado. Também testa dois contextos
materialmente distintos, sem acesso a dados financeiros.


## Defesa estrutural em runtime: escopo físico do tenant — 11/11/2026

O planejador v1.6.0 (`PLANNER_VERSION=v1.6.0-tenant-physical-scope`)
estabelece a fronteira de autorização **antes da geração de SQL**, em todos
os caminhos de planejamento, inclusive no resolvedor determinístico legado:

- `allowed_schemas` deve existir, ser uma lista não vazia de nomes válidos
  e não pode conter valores nulos ou malformados; caso contrário,
  `PLANNING_SCHEMA_SCOPE_INVALID`.
- Todas as tabelas efetivamente selecionadas para o plano — inclusive
  introduzidas por regras, entidades, métricas ou agrupamentos — precisam
  pertencer ao escopo ativo do tenant. Tabela fisicamente existente em
  catálogo não é autorização de leitura: `PLANNING_TABLE_SCHEMA_UNAUTHORIZED`.
  Nenhuma tabela é silenciosamente omitida para fazer uma pergunta passar.
- Toda dimensão projetada precisa apontar para tabela selecionada e coluna
  presente em `table_catalog.columns`. A presença apenas em `key_columns`
  ou o texto de um alias não comprova a existência física da coluna:
  `PLANNING_DIMENSION_TARGET_INVALID`.
- Casos cobertos com dois esquemas e nomenclaturas sintéticas diferentes,
  dimensões migradas para schema estrangeiro, alias para coluna inexistente,
  ausência de escopo e metadata de chave contraditória.
- O gate não atribui significado financeiro a nenhuma coluna; conceitos e
  vínculos contábeis seguem exigindo autorização e versão do tenant. Não há
  conexão com banco, alteração do n8n, provider, SQL financeira executada
  ou ativação do contexto.

Observação: o erro de uma métrica fora do schema autorizado agora pode ser
classificado prioritariamente como `PLANNING_TABLE_SCHEMA_UNAUTHORIZED`,
em vez de `PLANNING_METRIC_BINDING_INCOMPLETE`. Ambos impedem a geração e
a execução, mas o primeiro evidencia o bloqueio anterior do escopo físico.
É uma alteração versionada e deve ser avaliada na paridade Shadow; jamais
reinterprete códigos históricos de benchmark para mascarar diferenças.

Esses testes sintéticos demonstram controle de acesso ao planejamento, não
certificação multicliente real, equivalência financeira ou autorização de
cutover. `OFFICIAL=n8n`, `SHADOW=LangGraph` e
`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` permanecem inalterados.
