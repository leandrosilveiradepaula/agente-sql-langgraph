# Configuração portável de fontes de contexto semântico (candidata)

**Escopo:** somente Shadow TEST, modo de geração/validação. Este contrato não altera
automaticamente n8n, banco, perfil, produção, credenciais, contexto ativo nem
`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.

## Problema real

O carregador PostgreSQL original selecionava cinco relações
`ai_ducklake_*` de um único schema, incluindo mapeamento DRE obrigatório
na consulta. Isso impedia a leitura do catálogo de um cliente cuja fonte
de contexto tivesse outros nomes ou nenhum conjunto DRE, ainda que o motor
de planejamento fosse dirigido por contexto.

## Configuração adicionada

`POSTGRES_CONTEXT_SCHEMA` continua definindo o **schema do catálogo**
(isolado do schema físico de dados do cliente). `SEMANTIC_AGENT_VERSION`
continua selecionando a versão do conhecimento. A variável opcional
`CONTEXT_CATALOG_TABLES_JSON` mapeia os cinco papéis estruturais de
metadados para nomes simples de relações nesse schema.

Exemplo **sintético e desativado**, que não representa tabelas da VPS:

```json
{
  "rules": "context_rules",
  "entities": "context_entities",
  "dre": null,
  "patterns": "context_patterns",
  "catalog": "context_tables"
}
```

`"dre": null` remove a dependência da relação DRE e produz uma
coleção semântica vazia, **não um mapeamento de contabilidade inventado**.
Se DRE for relevante e seu mapeamento estiver ausente, a pergunta que o
exija deve falhar com segurança, nunca receber fórmula implícita.

Se a variável não estiver presente, o comportamento SQL anterior é
preservado integralmente (mesmas cinco relações e parâmetros).
Chaves inesperadas, expressões SQL, nomes qualificados, `null` em
coleções obrigatórias e valores malformados são recusados antes de
construir o runtime. O `agent_version` continua sendo parâmetro SQL;
nenhum parâmetro é originado da pergunta ou do benchmark.

As fontes fornecem o contrato **canônico de colunas dos metadados**
atualmente conhecido pelo adapter. Caso o novo cliente armazene essas
colunas de outra forma, criar um adapter externo autorizado ou views
read-only por tenant para projetá-las; não acrescentar ramificações
de cliente ou fórmulas financeiras no LangGraph.

## Segurança / não conclusões

- A configuração deve ser aplicada **por tenant e por deploy**. O
  contexto nunca obtém credenciais, tabela ou versão da linguagem natural.
- Exigir banco/DSN separados da persistência de Shadow, menor privilégio,
  SELECT somente nas fontes autorizadas e versionamento por tenant.
- `user_profile` permanece no contrato de chamada, mas o loader legado
  não aplica RBAC no PostgreSQL; isso precisa de verificação independente
  da fronteira de autorização e do isolamento antes da homologação.
- Testes offline exercitam dois contextos fisicamente distintos, DRE
  ausente, nomes configurados e tentativas de injeção. Isso prova somente
  a flexibilidade do **adapter**, não paridade semântica, SQL ou financeira
  real entre clientes.
- Não modificar `SEMANTIC_AGENT_VERSION`, runtime n8n, banco, políticas,
  produção ou SQL executor ao revisar este PR.
