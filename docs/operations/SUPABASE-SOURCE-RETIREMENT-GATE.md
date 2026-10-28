# G5 — Consolidação Supabase: inventário comprovado e bloqueios para aposentar a origem

**Revisão 28/10/2026.** Este documento é um inventário READ-ONLY, não uma migração nem autorização para desativar bancos. Contrato de operação: `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.

## Identidades exatas

- Origem (candidata futura à aposentadoria): Supabase **Agente Financeiro**, `nywxpvzhlpqjtcafpdfe`.
- Destino (manter): Supabase **Demo**, `cenhadslwxgykqtuobgc`.
- Não confundir Supabase Demo com CRM ou Service Desk. A execução de `P3` transferiu **apenas 200 registros** de `public.langgraph_shadow_runs`; checksum ordenado em ambas origens: `5a2dd8dbe09c6f21b4fd8260e34dbced`.

## Evidências de diferenças reais (catálogo PostgreSQL; consultas sem dados brutos)

| Recurso | Origem | DEMO | Política de consolidação |
|---|---:|---:|---|
| Tabelas `public` | 47 | 10 | não duplicar esquema legado automaticamente |
| `ai_agent_users` | 10 | 1 | inventariar identidade, senha e autenticação antes de decisão; **não copiar hashes/sessões** |
| `ai_agent_sessions` | 112 | 9 | preservar ou exportar histórico autorizado; sessões ativas não são portáveis |
| `ai_agent_runs` | 238 | 42 | arquivamento/retention versionado com trilha, sem sobrescrever IDs |
| `langgraph_shadow_runs` | 200 | 200 | **migrado e checksum idêntico**; RLS do DEMO ativo |
| `ai_ducklake_agent_rules` | 318 (11 versões) | 110 (10 versões) | contextos diferentes: **não fazer merge de conhecimento** |
| `ai_ducklake_entity_aliases` | 738 | 605 | preservar versões legadas em arquivo isolado |
| `ai_ducklake_dre_mapping` | 121 | 130 | não fundir DRE/negócio |
| `ai_ducklake_sql_patterns` | 106 | 60 | exemplos e SQL legada são dados de avaliação, não prompt |
| `ai_ducklake_table_catalog` | 98 | 80 | destinos/dialetos diferentes, nunca copiar por nome |
| Contexto versionado | `public`, 11 versões `v2.0-ducklake-...` | `semantic_context`, 10 versões `demo-finance-v1..v10` | manter isolamento `SEMANTIC_AGENT_VERSION` |
| Warehouse | `public.gold_*` e `public.syn_gold_*` | `demo_lakehouse.gold_*` e `rivatti_demo_masked.gold_*` | schemas diferentes: não presumir compatibilidade contábil |

Os números são contagens observadas nas consultas, não estimativas do `pg_class.reltuples`.

## Produto: duas implantações Vercel e dois DATABASE_URL (valores **não lidos**)

Vercel confirmou projetos distintos:
- `agente-financeiro` (ID `prj_CcjDsXQDhREm6DYyrVtGPx29wq7U`): último Production READY consultado no commit `5f6d5113cd69ebcc4475a6f6046046051b8250ac`, branch `main`; variáveis `DATABASE_URL`, `N8N_GENERATE_SQL_WEBHOOK_URL`, `N8N_EXECUTE_WATSON_WEBHOOK_URL`, shadow e S2S presentes. **Destino efetivo do DATABASE_URL não identificado** (variável sigilosa, não decifrada).
- `agente-financeiro-demo` (ID `prj_jGIbRJIvuEPCIN1dQw92ZUST6jsU`): último Production READY consultado no commit `aa088f4426d42c94e79cd887ea6c16bb1200c09e`, branch `demo/grupo-horizonte`; `DATABASE_URL`, n8n e Shadow presentes; **destino efetivo não identificado**.

Código do Produto `Agente-Financeiro`: `lib/db.ts` consome `process.env.DATABASE_URL`; sessões e runs utilizam esse pool. A leitura das *chaves* da Vercel não demonstra a identidade da base. Portanto nenhuma exclusão pode ser autorizada antes de um atestado local, sem exibir o DSN.

## LangGraph: conexões separadas

`app/test_runtime/config.py` e `app/test_runtime/composition.py` confirmam:
- `LANGGRAPH_SHADOW_DATABASE_DSN`: histórico/evidências Shadow;
- `CONTEXT_POSTGRES_DSN`: cinco catálogos versionados; `POSTGRES_CONTEXT_SCHEMA` + `SEMANTIC_AGENT_VERSION`;
- possível `POSTGRES_DSN` no runtime geral, sujeito a inventário separado.

Não há prova atual dos **valores efetivos em contêineres da VPS**, nem autenticação com o novo login tenant-bound. A migração 002 só criou grupo NOLOGIN, políticas RLS e tabela de vínculo; sem login e sem organization_id validada. NÃO trocar DSN nem ligar flags por causa do inventário.

## n8n: bloqueio decisivo

O n8n oficial usa credencial PostgreSQL independente do Produto. O inventário legado tem 68 nós; houve tentativa de rebinding do workflow oficial, mas um diagnóstico anterior registrou drift na versão publicada. **Não inferir sucesso do PUT**. A auditoria viva da VPS/n8n precisa confirmar *published vs stored*, credenciais por ID e destino da conexão sem exibir senha ou host secreto. O caminho Shadow candidato `LwUsMRWi34D2ARWu1YzgV` não substitui o oficial.

Não desativar o Supabase antigo enquanto qualquer destino de n8n/Produto/LangGraph estiver `UNKNOWN` ou `SOURCE`.

## Inventário técnico seguro a executar na VPS (read-only)

Criar evidência de **somente fingerprints estáveis de destino**: cada processo de origem (Vercel Production/Preview, VPS LangGraph, credencial PostgreSQL n8n) deve indicar `SOURCE`, `DEMO`, `OTHER` ou `UNKNOWN`; nunca emitir `dsn`, usuário, senha, API key, cookies, host interno ou valores brutos de variáveis.

Critérios **obrigatórios** para declarar `READY_TO_RETIRE_SOURCE`:
1. Cada consumidor ativo conhecido e cada fluxo publicado n8n identificado com destino real e intenção funcional; nenhum `SOURCE`/`UNKNOWN`.
2. Preservação de registros antigos relevantes: export/backup privado, retenção e validação de restauração, incluindo históricos, benchmarks **fora** do gerador, contextos/versões e autenticação (sem copiar sessões/hashes cegamente).
3. `DEMO` com organização/membership autorizada, credential Shadow tenant-bound testada, separação de Generate/Repair/Execute Approved e isolamento provado.
4. Convergência operacional Produto + n8n + LangGraph confirmada em staging/canário. Continuidade da resposta oficial pelo n8n, SQL financeira Shadow desativada até autorização independente, plano de rollback testado.
5. Janela de observação e consentimento humano **específico** para aposentadoria/remoção. Desativação reversível primeiro, exclusão definitiva somente depois.

**Resultado de hoje: `RETIREMENT_GATE=BLOCKED`.** Motivos: dependências efetivas ainda não auditadas, histórico/semântica legados não arquivados, DSN sem cutover homologado, n8n published não reconciliado.

### Referências reais
- [PR LangGraph #181](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/pull/181): isolamento RLS.
- [PR LangGraph #182](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/pull/182): utilitário de login com gate.
- [PR Produto Demo #33](https://github.com/leandrosilveiradepaula/Agente-Financeiro/pull/33): tabelas de organização privadas.
- [Roadmap #155](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/issues/155): rastro operacional e decisões.

## G5 atualizado — dependências reais e preparação do arquivo da origem (28/10/2026)

Evidência da VPS fornecida pelo operador, duas execuções G5 coerentes:

- Workflow oficial armazenado: **68 nós, duas credenciais PostgreSQL**. A credencial SOURCE aparece em **9 nós não desabilitados**; a DEMO aparece em **2 nós**. Os dois bindings G1 são DEMO; não repetir PUT/recover.
- O Shadow n8n contém 7 nós e **zero credenciais PostgreSQL diretas**; porém o runtime LangGraph foi atestado com `LANGGRAPH_SHADOW_DATABASE_DSN=SOURCE`, `CONTEXT_POSTGRES_DSN=DEMO` e flag de execução SQL real desligada.
- O G5 não prova publicação sozinho. G1 atestou `activeVersionId` compatível, 2 vínculos G1 novos, zero drift nos nós, mas `settings.callerPolicy` adicionado ainda aparece como `SETTINGS_DRIFT_REVIEW` literal. A equivalência efetiva foi verificada em auditoria G1 separada, conforme issue #155. Não declarar `STRICT_PASS` textual.
- Consulta somente ao catálogo: `public.sql_generation_cache`, `public.ai_agent_data_source_config` e `public.ai_ducklake_agent_rules` existem na SOURCE e **não** no DEMO. O DEMO tem semântica versionada distinta em `semantic_context`. Rebinding indiscriminado dos 9 nós quebraria SQL e arriscaria contaminação de conhecimento entre clientes.
- O inventário de 68 nós (`docs/audits/n8n-official-68-node-externalization-ledger.md`) marca historicamente 6 nós PostgreSQL legados alcançáveis e 3 inalcançáveis, **sem atestar a topologia publicada atual**.

### Captura criptografada (gated, não ativada)

O utilitário `scripts/operations/g5_archive_supabase_source.py` tem três modos:

- `--plan`: apenas disponibilidade local de `pg_dump` e `gpg`, **sem conexão**.
- `--capture`: exige autorização **separada** do operador, TTY, confirmação `ARCHIVE-SOURCE-READONLY`, DSN admin SOURCE por `getpass`, identidade de projeto estrita e TLS `verify-full`. `pg_dump` executa com `default_transaction_read_only=on`; os bytes viajam em pipe diretamente ao `gpg` com destinatário OpenPGP de fingerprint completo, sem arquivo de dump plaintext. Guarda somente `.dump.gpg` e manifesto SHA-256 em diretório root-only 0700/0600.
- `--verify`: verifica integridade dos bytes **criptografados** e a estrutura do recibo; **não descriptografa nem atesta restauro**. O manifesto marca `restore_verified=false`.

Após merge da PR, testar **somente o planejamento**, sem expor credenciais:

~~~bash
cd /docker/agente-sql-langgraph-repo &&
git fetch -q origin && git checkout -q main && git pull --ff-only -q origin main &&
.venv/bin/python scripts/operations/g5_archive_supabase_source.py \
  --plan --source-project-ref nywxpvzhlpqjtcafpdfe
~~~

O `--capture` **não é autorizado pelo merge**. Antes dele, operador deve aprovar a exportação de dados históricos e definir custodiante, fingerprint de chave pública, espaço, destino externo seguro e retenção. O manifesto e o dump criptografado **nunca** vão para o GitHub/chat. Fazer ensaio de restauro em banco **isolado/descartável** e validar dados/roles, antes de considerar a origem removível. **Nunca restaurar diretamente no DEMO**, porque esquemas e tenants diferem. Um `pg_dump` lógico não captura objetos físicos do Storage, Edge Functions, segredos, credenciais, configurações de Auth e todas as roles; inventariar também esses recursos e sua custódia.

### P3 — identidade autorizada antes de criar login Shadow

O `p3_shadow_tenant_login.py` passa a exigir no preflight: `organization_id` como UUID canônico, organização ativa em `public.ai_agent_organizations` e pelo menos uma associação ativa em `public.ai_agent_user_organizations` com usuário ativo em `public.ai_agent_users`. É contrato **estrutural de identidade do Produto**, sem qualquer regra financeira. Um UUID arbitrário não pode criar role/binding de banco; o script não cria organizações, memberships, usuários, contexts ou privilégios automaticamente e não faz cutover de DSN.

**Prova viva 28/10:** DEMO tem **zero organizações e zero memberships**. Preflight P3 deve bloquear até uma organização real ser autorizada/cadastrada no Produto; não inferir tenant de registros históricos. Após isso, confirmar isolamento RLS e autenticação real com o login antes de qualquer mudança de `LANGGRAPH_SHADOW_DATABASE_DSN`. A mudança de DSN, a SQL financeira real e a exclusão da SOURCE ainda exigem gates humanos próprios.

## Gate automatizado sem contato com infraestrutura

`scripts/operations/check_supabase_retirement_gate.py` avalia apenas **atestações sanitizadas**. Cada registro de consumidor requer `consumer`, `destination` (`DEMO`, `OTHER`, `SOURCE`, `UNKNOWN`), `verified_at` (UTC), `probe_id` genérico e `evidence_sha` SHA-1 hexadecimal de 40 caracteres do recibo técnico (não senha/DSN). São obrigatórios os seis consumidores conhecidos: `product_primary`, `product_demo`, `n8n_official`, `n8n_shadow`, `langgraph_shadow_evidence`, `langgraph_semantic_context`.

A classificação `OTHER` admite um warehouse externo **desde que haja prova de independência do banco de origem**. `SOURCE` ou `UNKNOWN` bloqueiam a remoção. Outros campos como `dsn`, `url`, `password`, `host`, `token` são rejeitados por whitelist estrita. Os quatro booleanos de arquivo/restauração, rollback, observação e **aprovação explícita de aposentadoria** devem ser verdadeiros. A aprovação de migração, merge ou snapshot **não** satisfaz a aprovação de exclusão. A ferramenta não verifica autenticidade dos recibos; exige que a prova real seja coletada em operação separada e auditada.

```bash
python -m unittest scripts.test_supabase_retirement_gate -v
python scripts/operations/check_supabase_retirement_gate.py /caminho/privado/atestado-sanitizado.json
```

Não executar um arquivo de exemplo alegando ambiente liberado: um manifesto de CI pode passar estruturalmente, mas isso **não é evidência real da VPS/Vercel/n8n**. `READY` significa atestados declarados completos, não autorização independente para deletar o projeto. A deleção continua sempre manual.

## Auditoria operacional da VPS: classificação sem revelar DSNs

Após merge desta PR e sem modificar qualquer runtime:

```bash
cd /docker/agente-sql-langgraph-repo
git fetch origin
git checkout main
git pull --ff-only origin main

.venv/bin/python scripts/operations/audit_supabase_runtime_dependencies_readonly.py \
  --source-project-ref nywxpvzhlpqjtcafpdfe \
  --demo-project-ref cenhadslwxgykqtuobgc \
  --shadow-container agente-sql-langgraph-shadow-test-langgraph-shadow-test-1 \
  --official-workflow-id 2E6mbYg8CEJhGhqs \
  --inspect-n8n-credentials
```

A inspeção usa `docker inspect` do **contêiner Shadow realmente em execução**, distingue `LANGGRAPH_SHADOW_DATABASE_DSN` e `CONTEXT_POSTGRES_DSN`, verifica que `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false` e classifica host/usuário do projeto Supabase em `SOURCE`, `DEMO`, `OTHER_SUPABASE_UNVERIFIED` ou `UNKNOWN`.

Para n8n **2.4.8**, o script detecta um único contêiner `n8nio/n8n` ou aceita `--n8n-container` explícito, exporta em memória o workflow informado e extrai **somente IDs das credenciais PostgreSQL referenciadas**. A opção `--inspect-n8n-credentials` exige terminal local interativo e confirmação literal `AUDIT-N8N-LOCAL`: então consulta **apenas** essas credenciais pelo comando CLI `n8n export:credentials --id=... --decrypted`, capturando stdout/stderr em memória sem imprimi-los ou criar arquivos. A extração temporária inclui material sensível em RAM: executar **apenas localmente na VPS confiável**, nunca enviar saída bruta do comando n8n a chats, arquivos, CI ou sistemas de logging. Sem essa opção, não ocorre decriptação e o resultado n8n é `NOT_AUDITED`. Não se solicita API key, token ou senha ao operador.

**Limite importante:** `n8n export:workflow` em n8n 2.4.8 lê o workflow armazenado e **não prova** a versão publicada/efetivamente executada. Mesmo uma classificação `DEMO` depende de reconciliação G1 com `scripts/operations/g1_post_put_audit_readonly.py`, da verificação de aprovações e dos demais consumidores. Uma conexão de outro host/proxy recebe `UNKNOWN`, não é automaticamente declarada livre do banco antigo. O veredito de aposentadoria continua bloqueado.

Compartilhar somente linhas com prefixo `SUPABASE_`. O script nunca imprime DSNs, host, usuário, senha, IDs de credenciais, perguntas, SQL nem payloads financeiros; não grava arquivos nem executa SQL. Não é necessária nova credencial ou migração para executar essa auditoria.


### Diagnóstico de descoberta Docker (28/10/2026)

Na primeira execução real na VPS, a auditoria retornou
`SUPABASE_DEPENDENCY_ERROR=N8N_CONTAINER_MISSING_OR_AMBIGUOUS`.
A causa identificada no código foi a busca excessivamente restritiva pela
imagem `n8nio/n8n`: ela não incluía nomes qualificados com registry como
`docker.n8n.io/n8nio/n8n:2.4.8`. O detector agora reaproveita a expressão
já validada em `scripts/operations/g1_partial_reconcile_readonly.py`,
obtém `docker ps --format '{{.Names}} {{.Image}}'` e continua exigindo
**exatamente um** contêiner. O retorno anterior ocorreu antes da leitura
de credenciais n8n e não alterou banco nem configuração.

Após merge da correção, basta repetir o comando de auditoria VPS acima,
sem token nem DSN. Se houver *mais de uma* instância n8n em execução,
selecionar a instância **comprovadamente oficial** usando
`--n8n-container NOME_VALIDADO`; não escolher arbitrariamente, não
desativar outra instância e não contornar a conferência de versão.
