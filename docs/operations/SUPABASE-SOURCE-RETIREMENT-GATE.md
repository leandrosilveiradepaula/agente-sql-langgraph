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

## 28/10/2026 — Extensão indisponível: diagnóstico real e preflight multicliente

**Evidência do segundo ensaio autorizado na VPS**, após a PR #190 mergeada e diagnóstico sanitizado:

~~~text
G5_REHEARSAL_MODE=RESTORE
G5_IMAGE_CACHED=YES
G5_REHEARSAL_RESULT=BLOCKED
G5_REHEARSAL_ERROR=ISOLATED_RESTORE_SQL_FAILED
G5_RESTORE_FAILURE_CATEGORY=EXTENSION_UNAVAILABLE
G5_RESTORE_TEST=NOT_VERIFIED
~~~

**Comprovado:** pelo menos uma instrução relacionada a extensão não pôde ser restaurada no contêiner `postgres:17` padrão. Isso não torna o backup inválido. **Não comprovado:** qual extensão específica e se há outras incompatibilidades posteriores. O contêiner foi removido conforme o gate de limpeza; o backup e os Supabases permanecem intactos.

Foi executada **somente uma consulta de catálogo SELECT**, fora do benchmark, no PostgreSQL da SOURCE `nywxpvzhlpqjtcafpdfe`: `pg_catalog.pg_extension` + `pg_catalog.pg_available_extensions`. Extensões efetivamente instaladas, com versões:

| Extensão SOURCE | Versão | Esquema |
|---|---|---|
| `pg_stat_statements` | `1.11` | `extensions` |
| `pgcrypto` | `1.3` | `extensions` |
| `plpgsql` | `1.0` | `pg_catalog` |
| `supabase_vault` | `0.3.1` | `vault` |
| `uuid-ossp` | `1.1` | `extensions` |

**Hipótese prioritária:** `supabase_vault` não vem na imagem oficial comunitária `postgres:17`. Isso só se tornará um gap comprovado quando as extensões que o **arquivo** realmente contém forem comparadas com os arquivos `.control` instalados no contêiner de destino. A SOURCE pode ter uma extensão instalada mas não incluída no dump `pg_dump` por configurações de esquema/objeto; por isso a lista de catálogo não substitui a leitura do arquivo.

### Novo preflight seguro, sem tentar outra restauração

A auditoria genérica `scripts/operations/g5_extension_compatibility_readonly.py` executa quatro mecanismos, sem conhecer cliente/esquema de negócio: (1) verifica SHA, manifesto e arquivos root-only já gerados; (2) confirma que cada imagem PostgreSQL 17 permitida está **previamente no cache** e fixa seu SHA; (3) em contêiner efêmero com `--network=none`, `--read-only`, usuário sem privilégio, sem binds, sem dados nem banco, enumera exclusivamente nomes de `*.control` da imagem, sem usar DSN ou senha; (4) solicita uma única vez a senha do backup na VPS e usa o pipeline GPG → `pg_restore --list` já homologado, retendo apenas identificadores sintaticamente seguros de extensões (nunca o resto do TOC).

O relatório compara os dois conjuntos dinamicamente, imprime `G5_IMAGE_N_MISSING` apenas com os nomes das extensões ausentes, e mantém **`G5_RESTORE_TEST=NOT_PERFORMED`**. Mesmo `FILES_PRESENT_NOT_RESTORE_PROOF` confirma somente a presença de arquivos de controle. Não atesta versão binária, dependências de bibliotecas, execução segura, papel superuser, chave Vault, restauração ou paridade. Erros ou metadados estranhos falham com códigos fixos, sem imprimir SQL/tabelas/DSNs/segredos.

**Supabase PostgreSQL 17 para futura comparação:** as instruções públicas atuais de self-hosting demonstram a tag `supabase/postgres:17.6.1.136`. Essa imagem é **candidata**, não substituta aprovada do `postgres:17`. A auditoria não faz `docker pull` automaticamente nem altera a imagem de restauração. Se a imagem candidata não estiver no cache, retorna `POSTGRES17_IMAGE_NOT_CACHED`, antes de solicitar senha. Documentação oficial: `https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore`, `https://supabase.com/docs/guides/database/vault`, `https://supabase.com/docs/guides/self-hosting/custom-postgres-extensions`.

**Comando inicial para comparar com a imagem comunitária já existente**, somente depois de PR aprovada/mergeada na main:

~~~bash
cd /docker/agente-sql-langgraph-repo || exit 1
git fetch -q origin && git checkout -q main && git pull --ff-only -q origin main || exit 1
PATH="/usr/lib/postgresql/17/bin:$PATH" \
.venv/bin/python scripts/operations/g5_extension_compatibility_readonly.py \
  --source-project-ref nywxpvzhlpqjtcafpdfe \
  --manifest /root/.local/share/agente-sql-langgraph/source-archives/source-nywxpvzhlpqjtcafpdfe-20261028T145054Z-1557baa82308af9b.dump.gpg.manifest.json \
  --image-ref postgres:17
~~~

Futuramente, depois de autorizar/baixar a imagem Supabase específica e confirmar seu digest e escopo, executar a mesma auditoria com duas opções `--image-ref`, para comparar ambas **com uma única senha**. Não executar `--restore` por causa de um resultado de preflight; antes será necessário validar runtime da nova imagem, porta/volumes/UID, extensions e aprovação específica. Não baixar imagem pela aplicação nem abrir conexão externa do contêiner.

**Atenção especial ao Vault:** o root key de criptografia não está no dump; não copiar, revelar ou alterar chave entre projetos por implicação. O processo atual de exportação `pg_dump --no-owner --no-acl` tampouco comprova recuperação de roles, Auth, Storage, Edge e outros componentes gerenciados. Não aposentar SOURCE enquanto persistirem dependências n8n/Shadow/Produto e gates não homologados.

---

## 28/10/2026 — Primeiro ensaio G5 de restauração isolada: SQL bloqueada

**Evidência real na VPS do operador**, após a PR #189 e `--plan` PASS, imagem Docker PostgreSQL 17 já em cache, confirmação digitada `RESTORE-G5-ISOLATED` e senha local do backup:

~~~text
G5_REHEARSAL_MODE=RESTORE
G5_IMAGE_CACHED=YES
G5_REHEARSAL_RESULT=BLOCKED
G5_REHEARSAL_ERROR=ISOLATED_RESTORE_SQL_FAILED
G5_RESTORE_TEST=NOT_VERIFIED
~~~

**Conclusão correta:** o comando `docker exec pg_restore --single-transaction --exit-on-error` terminou com código não-zero. O script original descartava stderr para não revelar SQL, tabelas, senhas, usuários e funções, portanto **a causa exata da falha não ficou observável**. Ausência de extensões, roles, privilégios ou recursos no PostgreSQL comunitário são hipóteses e NÃO diagnósticos comprovados. O código só devolve essa classe de erro quando a limpeza do contêiner foi verificada; se não fosse, teria retornado `ISOLATED_CLEANUP_UNVERIFIED`. SOURCE, DEMO, n8n, credenciais e LLM não foram alterados; o backup cifrado não foi sobrescrito. O ensaio falhou e **NÃO** representa restore efetivo.

### Correção segura de observabilidade, sem omitir SQL/objetos

O utilitário G5 recebe captura do stderr do `pg_restore` **somente em memória**, com thread que drena o pipe concorrente (evita travamento de buffer). A thread **NUNCA** imprime, transmite, armazena, ecoa ou inclui stderr bruto nas exceções. Apenas o primeiro **código estrutural fixo** de erro pode atravessar a fronteira, por exemplo `EXTENSION_UNAVAILABLE`, `EXTENSION_LIBRARY_UNAVAILABLE`, `ROLE_MISSING`, `OBJECT_DEPENDENCY_MISSING`, `PERMISSION_DENIED`, `OBJECT_CONFLICT`, `RESOURCE_LIMIT`, `SERVER_SETTING_UNSUPPORTED`, `ARCHIVE_INVALID`, `SQL_SYNTAX_UNSUPPORTED` ou `UNCLASSIFIED`. Todos esses nomes são genéricos; não há nomes de negócio ou mapeamentos de cliente. Falhas desconhecidas permanecem `UNCLASSIFIED`; não transformar hipótese em fato.

**Sem regressão de gate:** para retorno não-zero do PostgreSQL, permanece `G5_REHEARSAL_RESULT=BLOCKED`, `G5_REHEARSAL_ERROR=ISOLATED_RESTORE_SQL_FAILED`, `G5_RESTORE_TEST=NOT_VERIFIED`. Adiciona-se somente `G5_RESTORE_FAILURE_CATEGORY=<CATEGORIA_FIXA>`. O contêiner continua descartável sem rede, portas ou volumes, com transação única, `--exit-on-error`, identidade sem privilégio, nenhuma escrita no Supabase, limpeza verificada, senha via FD anônimo e **nenhuma autorização para contornar falhas**.

Depois do merge humano e CI verde da correção, o operador poderá fazer **uma tentativa diagnóstica autorizada do mesmo ensaio isolado** usando o comando original `--restore` com confirmação local e senha fora do chat, sem modificar parâmetros nem repetir o download da imagem. Fornecer ao assistente **somente as linhas `G5_`**, nunca stderr bruto do PostgreSQL, tabelas/SQL/DSN/senha. Essa classificação depende do próximo ensaio; não temos a mensagem do ensaio anterior.

**Proibido** ocultar ou excluir extensões, funções, tabelas, triggers ou erros para obter PASS. Se o erro depender de objetos Supabase gerenciados, será necessário um contrato de recuperação compatível e governado, sem tratar PostgreSQL comunitário como equivalente a Supabase. O banco SOURCE continua INELEGÍVEL à aposentadoria; cópia cifrada fora da VPS e restauração integral permanecem pendentes.

---

## G5 — Inspeção real concluída e restauração isolada preparada (28/10/2026)

**Comprovado na VPS pelo operador, após merge da PR #188:** o arquivo criptografado já gerado com manifesto privado `source-nywxpvzhlpqjtcafpdfe-20261028T145054Z-1557baa82308af9b.dump.gpg.manifest.json` foi inspecionado sem contato com DB. Resultado: `G5_ARCHIVE_DECRYPTION=PASS`, `G5_PG_RESTORE_TOC=PASS`, `G5_PG_RESTORE_TOC_ENTRIES=811`, `G5_DECRYPTED_ARCHIVE_BYTES=25905751`, `G5_RESTORE_TEST=NOT_PERFORMED`. Foi uma leitura integral da stream GPG, não execução dos 811 itens; banco SOURCE/DEMO intocados.

### Novo contrato de ensaio de restauração (ainda não executado)

`scripts/operations/g5_restore_isolated_rehearsal.py` prepara um **ensaio real e explicitamente autorizado**, importando a stream descriptografada em uma instância PostgreSQL 17 **temporária, dentro de Docker local**. O código não tem acesso a DSNs/credenciais de SOURCE ou DEMO, não altera n8n e não faz cutover. Ele **não é ativado pelo merge** e tem novo gate humano `RESTORE-G5-ISOLATED`.

**Segurança estrutural, fail closed:**
- `--plan`: valida SHA-256/manifesto root-only, verifica socket Docker local e que a imagem oficial PostgreSQL 17 **já está no cache**; retorna código de readiness sem iniciar contêiner, sem pedir senha e sem conectar banco. Não faz `docker pull` automático.
- `--restore`: apenas depois de aprovação específica, solicita no terminal confirmação literal e senha já custodiada pelo operador. É executado com root local porque o socket Docker tem privilégios; o contêiner roda sob UID 999:999 e tem `--network=none`, sem portas publicadas, `--cap-drop=ALL`, `--security-opt=no-new-privileges`, filesystem raiz read-only, PGDATA/socket/tmp em `tmpfs`, limites de CPU/memória/processos e **nenhum mount do host, volume persistente, credencial, senha ou DSN**. O comando verifica via `docker inspect` todas essas condições antes da importação e fixa o identificador SHA256 da imagem.
- Fluxo: `gpg --decrypt` (senha via FD anônimo) → pipe somente em memória → `docker exec -i ... pg_restore -d postgres --single-transaction --exit-on-error --no-owner --no-acl` em conexão local dentro do contêiner. **Não restaura no Supabase.** stderr de ambos é descartado (jamais enviar SQL/nomes/valores para chat/CI). Erro em qualquer item interrompe, retorna `ISOLATED_RESTORE_SQL_FAILED`; não há regras de omissão ou desativação casuística de validação.
- Se todas as instruções forem importadas com código zero, consulta apenas agregação de quantidade de tabelas do catálogo na instância descartável; em seguida força exclusão do contêiner, valida a limpeza e **só então** reporta `G5_RESTORE_TEST=PASS`. Não publica resultados financeiros.
- O arquivo real e manifesto permanecem na VPS; nenhuma cópia plaintext é gravada. A restrição `--log-driver=none` desativa logs Docker do contêiner, e o cliente não imprime SQL, DSN, nomes de tabela ou dados da importação.
- Pode falhar no PostgreSQL padrão, principalmente se o backup exigir extensões/roles gerenciadas do Supabase, tipos ou serviços ausentes. **Nesse caso deve continuar bloqueado**: sucesso parcial nunca equivale a restauração certificada. Mesmo `PASS` em PostgreSQL padrão prova apenas restauração lógica nesse contêiner, não recuperação de Auth/Storage/Edge Functions/roles/ACL nem paridade financeira.

### Comando de plano, após CI e merge da implementação

~~~bash
cd /docker/agente-sql-langgraph-repo || exit 1
git fetch -q origin && git checkout -q main && git pull --ff-only -q origin main || exit 1
.venv/bin/python scripts/operations/g5_restore_isolated_rehearsal.py \
  --plan \
  --source-project-ref nywxpvzhlpqjtcafpdfe \
  --manifest /root/.local/share/agente-sql-langgraph/source-archives/source-nywxpvzhlpqjtcafpdfe-20261028T145054Z-1557baa82308af9b.dump.gpg.manifest.json
~~~

O plano **não pede senha** e pode devolver `POSTGRES17_IMAGE_NOT_CACHED`. Nesse caso o operador deve decidir se autoriza obter a imagem oficial após conferência de versão/digest; o script não baixa imagem sozinho. **Não executar `--restore` sem autorização específica posterior à leitura dos riscos.** O simples `--plan` e qualquer resultado de CI não significam que o teste real de restauração tenha ocorrido.

### Cópia externa ainda obrigatória

Copiar `.dump.gpg` e `.manifest.json` através de SFTP privado para repositório de backups fora da VPS, verificar hash SHA-256 na cópia e manter a senha em custódia separada. **Ainda não há prova dessa cópia.** O snapshot lógico `pg_dump --no-owner --no-acl` não substitui exportação integral de grants, roles, objetos Storage, Auth e configurações Supabase. O fechamento do G5 exige comprovante de restauração isolada **e** inventário de componentes não cobertos. Nunca aposentar SOURCE antes de comprovar consumidores independentes, rollback, isolamento e aprovação humana própria.

---

## 28/10/2026 — backup SOURCE capturado e etapa de leitura de recuperação

**Evidência operacional na VPS fornecida pelo operador:** após a correção da PR #187 e autorização expressa para exportação read-only, o G5 concluiu a captura da origem `nywxpvzhlpqjtcafpdfe`. Resultado **real**: `G5_ARCHIVE_RESULT=ENCRYPTED_CAPTURED`, `G5_ARCHIVE_INTEGRITY=ENCRYPTED_DIGEST_PASS`, `G5_ARCHIVE_RESTORE=NOT_VERIFIED`. Manifesto privado (NÃO enviar arquivo ao GitHub):

`/root/.local/share/agente-sql-langgraph/source-archives/source-nywxpvzhlpqjtcafpdfe-20261028T145054Z-1557baa82308af9b.dump.gpg.manifest.json`

**Isso prova apenas:** a captura criptografada retornou sucesso e o SHA-256 cifrado bateu com o recibo. **Não prova:** que a senha recupera os dados, que `pg_restore` reconhece o arquivo, que houve restore real, que roles/ACL, Storage/Edge/Auth/secrets estejam recuperáveis, que os consumidores saíram da SOURCE ou que a SOURCE possa ser apagada. Não alterar `restore_verified=false` no manifesto original.

### Leitura da cópia criptografada, sem restauração ou acesso a banco

`scripts/operations/g5_inspect_encrypted_source.py` adiciona etapa **somente leitura e local**, sem qualquer DSN nem conexão PostgreSQL. Primeiro verifica o SHA-256, projeto e manifesto root-only. Solicita a senha fora do eco de terminal, descriptografa via GPG a partir do arquivo já existente e envia o fluxo por **pipes anônimos** ao `pg_restore --list` (cliente major >=17) para contar itens do TOC, sem listar nomes de objetos nem gravar dump plaintext. Consome todo o fluxo GPG para verificar conclusão da decriptação, mesmo se o `pg_restore -l` parar após o TOC. GPG e pg_restore são chamados sem credenciais PG e sem `--dbname`; todas as mensagens stderr são suprimidas e não logadas. Executar depois de merge humano e CI verde:

~~~bash
cd /docker/agente-sql-langgraph-repo || exit 1
git fetch -q origin && git checkout -q main && git pull --ff-only -q origin main || exit 1
PATH="/usr/lib/postgresql/17/bin:$PATH" \
  .venv/bin/python scripts/operations/g5_inspect_encrypted_source.py \
  --source-project-ref nywxpvzhlpqjtcafpdfe \
  --manifest /root/.local/share/agente-sql-langgraph/source-archives/source-nywxpvzhlpqjtcafpdfe-20261028T145054Z-1557baa82308af9b.dump.gpg.manifest.json
~~~

Solicita **somente a senha do backup**, guardada pelo operador (não o DSN). Saída esperada: `G5_ARCHIVE_DECRYPTION=PASS`, `G5_PG_RESTORE_TOC=PASS`, contagem agregada e `G5_RESTORE_TEST=NOT_PERFORMED`. Não executar `pg_restore -d`, `gpg --output` para plaintext ou `docker run` com a cópia real por implicação. O ensaio efetivo de restauração de dados financeiros históricos em PostgreSQL descartável, isolado, precisa de autorização operacional própria, condições de segurança, revisão de funções/triggers `SECURITY DEFINER` do backup e confirmação de não conexão ao DEMO/SOURCE.

### Cópia externa, custódia e limites do G5

A captura ainda está somente na VPS: **fazer cópia cifrada externa usando canal SFTP seguro** (por exemplo WinSCP) de ambos o `.dump.gpg` e o `.dump.gpg.manifest.json` para armazenamento privado separado da VPS, e verificar SHA-256 da cópia. Senha de backup em gerenciador de segredos **fora da VPS** e recuperação custodiada separadamente. Não copiar dump descriptografado nem colocar os arquivos no repositório, n8n, Vercel, Supabase Storage público, CI, chat ou logs. Esta etapa ainda não atesta que a cópia externa foi feita.

A archive `pg_dump --no-owner --no-acl` não contém todos os metadados, roles e grants do projeto Supabase e não inclui outros componentes externos; uma prova TOC é **necessária, porém insuficiente** para desligar SOURCE. Portabilidade e hardcodes dos nove nós PostgreSQL legados n8n e migração da persistência LangGraph/Produto continuam gates independentes, sem SQL financeira executada.

---

## Incidente G5 — primeira exportação autorizada bloqueada (28/10/2026)

O operador autorizou explicitamente a **exportação somente leitura** da SOURCE `nywxpvzhlpqjtcafpdfe`, não a importação nem a exclusão. Na VPS, depois da PR #186 mergeada, o comando `--capture` chegou à solicitação de senha local do backup e DSN SOURCE; terminou com:

~~~text
G5_ARCHIVE_MODE=CAPTURE
G5_ARCHIVE_RESULT=BLOCKED
G5_ARCHIVE_ERROR=ENCRYPTED_DUMP_FAILED
G5_ARCHIVE_RESTORE=NOT_VERIFIED
~~~

O cliente SSH também encerrou a sessão depois da falha; isso **não é evidência** de queda do PostgreSQL. Consulta independente somente a metadados no SOURCE confirmou que o banco seguia respondendo, versão do servidor `17.6`. O script anterior descartava stderr bruto de `pg_dump` e GPG por segurança e misturava ambos os códigos de saída, impossibilitando atribuir causa retrospectivamente. **Não presumir senha errada, TLS, bloqueio de grants ou falha GPG.** Não houve resultado `ENCRYPTED_CAPTURED`, manifesto atestado ou teste de recuperação.

A correção G5 limita o diagnóstico a **códigos fixos sem detalhes sensíveis** derivados de stderr consumido somente em memória: autenticação SOURCE, TLS, cliente incompatível, pool esgotado, DNS, rede, permissões, lock, consulta, falha genérica de `pg_dump` e falha GPG. **Nenhuma linha bruta de stderr**, URL, tabela, usuário, SQL, host, senha ou dado financeiro pode ser impressa ou gravada. Se não for possível classificar, o resultado permanece genérico e seguro.

O `--capture` passa ainda a fazer `--verify` do SHA-256 cifrado automaticamente antes de anunciar sucesso. Isso evita `tee`, `mktemp` e `set -Eeuo pipefail` envolvendo a captura no SSH. Em caso de falha, o arquivo parcial é removido pelo script; a remoção efetiva na VPS ainda precisa ser inspecionada antes de nova captura.

**Após merge da correção e CI verde, executar uma única captura autorizada diretamente no terminal interativo**, com controle humano da senha/DSN; não enviar dados confidenciais ao chat:

~~~bash
cd /docker/agente-sql-langgraph-repo || exit 1
git fetch -q origin && git checkout -q main && git pull --ff-only -q origin main || exit 1
export PATH="/usr/lib/postgresql/17/bin:$PATH"
export PGSSLROOTCERT="/root/.local/share/agente-sql-langgraph/supabase-ca.crt"
test -r "$PGSSLROOTCERT" || exit 2
.venv/bin/python scripts/operations/g5_archive_supabase_source.py \
  --capture --source-project-ref nywxpvzhlpqjtcafpdfe
~~~

Prompt local: confirmação literal `ARCHIVE-SOURCE-READONLY`, mesma senha longa de backup (digitada duas vezes, sem eco) e DSN admin da SOURCE com TLS `verify-full` (sem eco). Nunca usar a string de exemplo `[YOUR-PASSWORD]`: substituir pela senha real com URL encoding para caracteres reservados, **sem enviá-la ao chat**. Usar senha guardada fora da VPS em gerenciador de senhas. O comando não altera SOURCE/DEMO, n8n, roles ou runtime, mas lê dados para o arquivo criptografado; a autorização concedida se limita a esta exportação.

**Sucesso esperado:** `G5_ARCHIVE_RESULT=ENCRYPTED_CAPTURED` e `G5_ARCHIVE_INTEGRITY=ENCRYPTED_DIGEST_PASS`, com `G5_ARCHIVE_RESTORE=NOT_VERIFIED`. Digest cifrado **não** prova restauração. O arquivo deve ser copiado com segurança para custódia externa e ensaiado em PostgreSQL separado e descartável antes da aposentadoria. O banco SOURCE continua necessário para consumidores ativos (n8n e Shadow).

---

## G5 atualizado — dependências reais e preparação do arquivo da origem (28/10/2026)

Evidência da VPS fornecida pelo operador, duas execuções G5 coerentes:

- Workflow oficial armazenado: **68 nós, duas credenciais PostgreSQL**. A credencial SOURCE aparece em **9 nós não desabilitados**; a DEMO aparece em **2 nós**. Os dois bindings G1 são DEMO; não repetir PUT/recover.
- O Shadow n8n contém 7 nós e **zero credenciais PostgreSQL diretas**; porém o runtime LangGraph foi atestado com `LANGGRAPH_SHADOW_DATABASE_DSN=SOURCE`, `CONTEXT_POSTGRES_DSN=DEMO` e flag de execução SQL real desligada.
- O G5 não prova publicação sozinho. G1 atestou `activeVersionId` compatível, 2 vínculos G1 novos, zero drift nos nós, mas `settings.callerPolicy` adicionado ainda aparece como `SETTINGS_DRIFT_REVIEW` literal. A equivalência efetiva foi verificada em auditoria G1 separada, conforme issue #155. Não declarar `STRICT_PASS` textual.
- Consulta somente ao catálogo: `public.sql_generation_cache`, `public.ai_agent_data_source_config` e `public.ai_ducklake_agent_rules` existem na SOURCE e **não** no DEMO. O DEMO tem semântica versionada distinta em `semantic_context`. Rebinding indiscriminado dos 9 nós quebraria SQL e arriscaria contaminação de conhecimento entre clientes.
- O inventário de 68 nós (`docs/audits/n8n-official-68-node-externalization-ledger.md`) marca historicamente 6 nós PostgreSQL legados alcançáveis e 3 inalcançáveis, **sem atestar a topologia publicada atual**.

### Caminho simplificado G5: backup criptografado com senha, sem chave GPG

A pedido do operador (28/10/2026), o script G5 suporta também **criptografia simétrica OpenPGP com senha forte**, sem Kleopatra, sem gerar par de chaves e sem importar arquivo público. Isso **não substitui** a proteção do histórico nem muda a política de consentimento.

- Modo simples: `--capture` sem `--recipient-fingerprint` pede confirmação literal `ARCHIVE-SOURCE-READONLY`, senha de backup gerada em gerenciador de senhas (mínimo 32 caracteres imprimíveis ASCII, máximo 256, sem espaços, duas entradas sem eco) e DSN administrativo da SOURCE (sem eco). A senha do backup **não é** a senha da base de dados e **nunca** deve ser escrita em chat, logs, scripts, argumentos de shell, variável ambiente ou no arquivo de manifesto.
- Criptografia: `pg_dump` com transação read-only envia os bytes diretamente para `gpg --symmetric` com AES256, S2K SHA512 iterado e passagem da senha por **file descriptor anônimo**, sem texto puro em arquivo intermediário. A senha não é cacheada pelo GPG. O manifesto indica `pg_dump_custom_openpgp_symmetric` e `restore_verified=false` até um ensaio real de restauração independente.
- **Recuperação exige guardar a senha no gerenciador de senhas fora da VPS** e uma segunda cópia de recuperação controlada. Se a senha for perdida, o backup criptografado não poderá ser restaurado; se a VPS for comprometida antes de copiar o arquivo para um local seguro, a proteção pode ser comprometida. Retirar a cópia criptografada da VPS e testar decriptação/restauração em instância isolada antes de qualquer aposentadoria.
- O modo antigo com `--recipient-fingerprint <FPR>` continua suportado para quem prefere chave pública GPG e custódia externa da chave privada.
- O script mantém gates separados: merge de PR **não** autoriza `--capture`, e `--verify` só testa integridade de arquivo criptografado, **não restauração**.

**Depois do merge da implementação**, o operador pode verificar requisitos sem acessar a SOURCE:

~~~bash
cd /docker/agente-sql-langgraph-repo &&
git fetch -q origin && git checkout -q main && git pull --ff-only -q origin main &&
PATH="/usr/lib/postgresql/17/bin:$PATH" .venv/bin/python \
  scripts/operations/g5_archive_supabase_source.py \
  --plan --source-project-ref nywxpvzhlpqjtcafpdfe
~~~

A captura real só poderá ser orientada/executada após autorização específica de leitura/exportação dos dados legados, com proteção de credenciais e destino externo seguro. **Não** executar `--capture` apenas por causa deste documento.

### Captura criptografada (gated, não ativada)

O utilitário `scripts/operations/g5_archive_supabase_source.py` tem três modos:

- `--plan`: disponibilidade de `gpg` e de `pg_dump` major 17 ou superior, **sem conexão**.
- `--capture`: exige autorização **separada** do operador, TTY, confirmação `ARCHIVE-SOURCE-READONLY`, DSN admin SOURCE por `getpass`, identidade de projeto estrita e TLS `verify-full`. `pg_dump` executa com `default_transaction_read_only=on`; os bytes viajam em pipe diretamente ao `gpg` protegido por senha forte digitada localmente (padrão), ou por destinatário OpenPGP quando `--recipient-fingerprint` é especificado; nunca há arquivo de dump em texto puro. Guarda somente `.dump.gpg` e manifesto SHA-256 em diretório root-only 0700/0600.
- `--verify`: verifica integridade dos bytes **criptografados** e a estrutura do recibo; **não descriptografa nem atesta restauro**. O manifesto marca `restore_verified=false`.

Após merge da PR, testar **somente o planejamento**, sem expor credenciais:

~~~bash
cd /docker/agente-sql-langgraph-repo &&
git fetch -q origin && git checkout -q main && git pull --ff-only -q origin main &&
PATH="/usr/lib/postgresql/17/bin:$PATH" .venv/bin/python \
  scripts/operations/g5_archive_supabase_source.py \
  --plan --source-project-ref nywxpvzhlpqjtcafpdfe
~~~

O `--capture` **não é autorizado pelo merge**. Antes dele, operador deve aprovar a exportação de dados históricos e definir custódia externa da senha forte (ou da chave privada, no modo alternativo), espaço, destino externo seguro e retenção. O manifesto e o dump criptografado **nunca** vão para o GitHub/chat. Fazer ensaio de restauro em banco **isolado/descartável** e validar dados/roles, antes de considerar a origem removível. **Nunca restaurar diretamente no DEMO**, porque esquemas e tenants diferem. Um `pg_dump` lógico não captura objetos físicos do Storage, Edge Functions, segredos, credenciais, configurações de Auth e todas as roles; inventariar também esses recursos e sua custódia.

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
