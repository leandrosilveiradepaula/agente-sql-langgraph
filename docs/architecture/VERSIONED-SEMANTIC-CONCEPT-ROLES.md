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
