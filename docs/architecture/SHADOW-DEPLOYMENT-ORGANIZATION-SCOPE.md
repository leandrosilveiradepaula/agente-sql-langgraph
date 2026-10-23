# Shadow TEST — organização vinculada à implantação (opt-in)

**Problema real:** o runtime Shadow já recebia `principal.organization_id`
no contrato v1, mas não confrontava esse identificador com a organização
cujo contexto/DSN foi implantado. O adapter PostgreSQL usa configuração
de fonte por processo; ele não aplica RBAC por `user_profile`.

## Proteção implementada

`LANGGRAPH_EXPECTED_ORGANIZATION_ID` é uma configuração opcional
**estrutural por implantação**. Quando fornecida, o runtime exige uma
igualdade exata (case-sensitive) com `principal.organization_id`
tanto em Generate quanto em Execute Approved Shadow, **antes de qualquer
leitura de contexto, chamada de LLM, repair, preflight ou persistência
de evidência**.

A configuração é validada no startup; valores vazios, não identificadores,
SQL, URLs e valores acima de 128 caracteres falham com erro sanitizado.
Rejeições de organização ausente/diferente retornam
`INTERNAL_ORGANIZATION_SCOPE_MISMATCH` e não persistem payload não
autorizado. O caminho Execute Approved não devolve a SQL fornecida
nesses casos. A opção não muda `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.

**Compatibilidade:** sem a nova variável, a API mantém seu comportamento
legado. Isso preserva o Shadow de demonstração, **mas não é garantia de
isolamento multi-tenant**.

## Pré-condição para uso em tenants reais

Não habilitar a variável em produção/Shadow atual enquanto Produto/n8n
não obtiverem `organization_id` de identidade/autorização confiável e
o transmitirem pelo canal S2S. No estado atual da Demo, a sessão envia
somente `id`, `email` e `profile`; ativar este guard agora bloquearia
todas as chamadas Shadow. A string não pode vir da pergunta, do modelo,
da resposta oficial, de um cookie editável ou do benchmark.

Para cada implantação por tenant, a origem de dados, o DSN, a versão do
contexto, o segredo S2S e o banco de evidências também precisam estar
isolados e revisados. Uma correspondência de `organization_id` não
autentica um usuário: Produto conserva autenticação, permissões e
ownership; o token S2S e o isolamento de banco continuam mandatórios.
Não usar essa validação como pretexto para compartilhar DSNs/segredos
entre organizações.

## Evidência offline

`testar_shadow_test_runtime.py` instancia dois runtimes com IDs de
organização distintos e os mesmos componentes. As tentativas cruzadas
ou sem organização são rejeitadas antes de gerador, preflight e
persistência. Chamadas de organização correspondente continuam
utilizando gerador/preflight fakes sem SQL financeiro. Isso demonstra
o gate por deployment, **não** a portabilidade semântica completa, o
enforcement de roles, a configuração de tenant na interface ou a
equivalência n8n↔LangGraph no ambiente real.

Nenhum n8n, Vercel, banco, tenant ativo, LLM paga, contexto versionado
ou cutover foi alterado pelo PR.


## Fechamento do caminho de leitura/comparação (candidato offline 2026-10-23)

O escopo por deployment precisa proteger **toda** a superfície Shadow,
não apenas Generate e Execute Approved. A configuração já existente
`LANGGRAPH_EXPECTED_ORGANIZATION_ID` passa também para:

- `GET /v1/internal/shadow-runs/{shadow_record_id}` (safe view);
- `GET /v1/internal/shadow-runs/{shadow_record_id}/visualization`;
- `GET /v1/internal/agent-runs/{agent_run_id}/shadow-runs`;
- `POST /v1/internal/sql-agent/compare-shadow-sql` (avaliação posterior).

Nos dois endpoints individuais, evidência com organização diferente ou
ausente retorna **404 indistinguível de não encontrada**, sem renderizar
dados. A listagem inclui apenas evidência pertencente ao escopo configurado,
mesmo quando IDs de runs colidem entre organizações. Comparação recebe
a restrição ainda **antes de consultar** o repositório; uma identidade
da organização correta não autoriza evidência armazenada com principal
divergente.

O repositório PostgreSQL usa adicionalmente um filtro **SELECT parametrizado**
por `principal ->> 'organization_id'`, aplicado no banco antes da
desserialização. O nome da organização jamais é interpolado na SQL.
Consultas antigas sem escopo continuam compatíveis, mas **não atestam
segregação multicliente**. O servidor S2S continua protegendo as rotas.

Validação sintética offline: `python testar_shadow_read_organization_scope.py`
(verificações de duas organizações, mesmo `agent_run_id`, operações de
leitura, comparação, ASGI e SQL parametrizada). Também integrado a
`python scripts/check_all.py`.

**Limites:** a proteção não cria memberships, RLS, DSN separado, política
do Produto, implantação física isolada ou paridade de SQL/resultados.
Sem `LANGGRAPH_EXPECTED_ORGANIZATION_ID` explicitamente configurado,
o comportamento legado mantém-se, inclusive leitura não filtrada. O
candidato não ativa flags, não muda banco/n8n, não executa SQL de negócio,
não consulta a LLM e não autoriza publicação/cutover.


## Defesa adicional na persistência (G4, candidato offline 2026-10-23)

Mesmo após autenticação S2S e gate de organização no caso de uso, a
camada PostgreSQL precisa defender suas próprias mutações:

- `create` em deployment vinculado recusa qualquer principal sem
  `organization_id` igual ao escopo server-side, **antes da conexão**;
- `update_evidence` valida o principal enviado **e** condiciona o UPDATE
  ao `principal ->> 'organization_id'` **já persistido** na linha;
- `finalize` não recebe principal no contrato; o UPDATE valida o
  `organization_id` da linha no WHERE e retorna `not_found` se ela
  não pertencer ao deployment;
- sem escopo configurado, mantém o comportamento anterior. Este modo
  legado **não é segregação multicliente**.

Todas as condições SQL são estruturais e parametrizadas; os valores não
entram na string SQL. Uma tentativa fora do escopo não revela o tenant
esperado nem qualquer SQL armazenada. Essa defesa não altera tabelas,
RLS, migrations, credenciais, privilégios, o fluxo oficial n8n ou o
controle humano de ativação. O teste `testar_shadow_evidence_persistence.py`
comprova as quatro operações em modo vinculado/legado e que UPDATE sem
linha elegível devolve `not_found`. Não substitui prova de isolamento
em banco real com policies e conexões por tenant.
