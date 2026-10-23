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

## Vincular o conteúdo aprovado do catálogo ao runtime — Jornada 2

Além de `SEMANTIC_AGENT_VERSION` e do schema físico do leitor, o operador
pode configurar o SHA-256 canônico do snapshot semântico por deployment:

```text
SEMANTIC_CONTEXT_EXPECTED_FINGERPRINT=<sha256-minúsculo-validado>
```

A variável é **opcional/desativada por padrão** para não alterar deployments
legados sem decisão operacional. Quando definida, o leitor PostgreSQL
normaliza o snapshot inteiro e compara seu fingerprint com o hash
exatamente aprovado. **Mudança de regras/aliases/métricas/tabelas/filtros
sob a mesma versão será rejeitada antes da classificação, do planner, da
geração de SQL e de seu repair.** Não há fallback para outra versão,
tenant ou resposta de benchmark. Erro público genérico não revela
hash real/esperado, regras, conexão ou SQL.

Valores ausentes preservam o comportamento anterior; valores presentes
inválidos, vazios, com maiúsculas, espaços ou tamanho incorreto bloqueiam
o bootstrap. A mesma configuração funciona no runtime Shadow
`CONTEXT_POSTGRES_DSN` e no runtime geral `POSTGRES_DSN`. O fingerprint
do contexto não é um segredo, **não** substitui autenticação,
tenant-binding, privilégios do leitor ou controle de versão. A pinagem
correta deve ser registrada *após* conferir o conteúdo e origem do
catálogo, não inferida de uma saída da LLM.

O teste `python testar_shadow_context_portability_e2e.py` exercita
o mesmo código HTTP/S2S → leitura do catálogo → resolução/planner →
validação da SQL usando **provedores offline injetados** e dois contextos
sintéticos com estruturas e nomes diferentes. Um dos contextos usa
`CONTEXT_CATALOG_TABLES_JSON` para ler metadados de tabelas com outros
nomes e `dre=null`. A suíte verifica:

- Configuração e fingerprints diferentes para ambientes independentes.
- Mudança de metadados **mantendo a versão** causando rejeição segura
  antes da geração.
- Organização divergente recusada antes até do SELECT de metadados.
- Pergunta que faz sentido apenas no outro catálogo sem inferência
  entre clientes ou SQL default.
- SQL analisada/gated no fluxo real, mas produzida por stub de teste;
  **isto NÃO comprova qualidade do gerador LLM, portabilidade financeira
  real nem SQL executada no warehouse.**

Para G4, continuam necessárias segregação física ou política de DSN
e autenticação por organização, prova no runtime implantado e
consulta financeira read-only separadamente autorizada. Não aplicar
configuração, migração nem alterar n8n por esta PR.
