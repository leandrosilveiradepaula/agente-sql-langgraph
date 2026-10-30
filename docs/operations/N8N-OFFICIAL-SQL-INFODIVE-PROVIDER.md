# Troca de provedor do n8n oficial: Gemini -> SQL-InfoDive

Decisão recente do operador em 29/10/2026: não comprar novos créditos Gemini e usar a API privada SQL-InfoDive **também no n8n oficial**. Trata-se de mudança do **provedor da LLM**, não de um cutover do motor n8n para LangGraph. O n8n permanece como orquestrador.

## Verificação antes de qualquer publicação

No inventário histórico do n8n oficial, o fluxo possui 68 nós. A geração e o reparo de SQL usam *dois* nós HTTP Gemini, com corpo `contents[0].parts[0].text`, e dois consumidores Code que extraem `candidates[0].content.parts[0].text`. O protocolo privado OpenAI-compatible precisa de `messages[0].content` e devolve `choices[0].message.content`.

`scripts/n8n/official_sql_infodive_provider_candidate.py` faz apenas auditoria do workflow **armazenado** via CLI n8n, identifica os quatro IDs a partir do contrato de resposta, e opcionalmente prepara candidato **somente em memória**. Não exige chave da API n8n, não altera workflow, não faz chamadas LLM, não executa SQL, não grava export de workflow e não imprime segredos.

**Importante:** o export CLI da versão armazenada não atesta a versão **publicada**. O candidato não é um instalador. Quatro alterações são propostas: duas chamadas HTTP e os dois consumidores da resposta; nenhum ajuste de plano, métricas, aliases, SQL, conexões, configuração do workflow, credenciais PostgreSQL ou regras financeiras.

## Comando seguro: inventário sem credenciais novas

Após merge humano e CI:

```bash
cd /docker/agente-sql-langgraph-repo || exit 1
git fetch -q origin && git checkout -q main && git pull --ff-only -q origin main || exit 1
.venv/bin/python scripts/n8n/official_sql_infodive_provider_candidate.py \
  --n8n-container n8n-n8n-1 \
  --workflow-id 2E6mbYg8CEJhGhqs \
  --audit-only
```

A saída exibe somente fingerprint, contagem e IDs dos quatro nós. Se a estrutura publicada tiver mudado, falha fechado.

## Candidato de conversão sem publicar

Criar arquivo privado `/root/.local/share/agente-sql-langgraph/sql-infodive-official-provider.json` (diretório 0700, arquivo 0600), **não versionado**, com somente:

```json
{
  "url": "http://10.0.0.4:8080/api/chat/completions",
  "host": "chat.internal",
  "model": "MODELO_PRIVADO_VALIDADO",
  "max_tokens": 4096,
  "credential_type": "httpBearerAuth",
  "credential_id": "ID_DA_CREDENCIAL_N8N_EXISTENTE",
  "credential_name": "NOME_DA_CREDENCIAL_N8N_EXISTENTE"
}
```

O endereço IP acima é **ilustrativo**, não foi constatado no runtime. Substituir pelo endereço *real* já autorizado da API Infodive via WireGuard. O segredo deve existir apenas na credencial de **Bearer Auth** do n8n (ou tipo `httpHeaderAuth` quando esse for o contrato já autorizado). Não usar token/DSN/header Authorization no JSON nem na conversa. Sem proxy público, bypass TLS ou elevação de privilégio.

```bash
.venv/bin/python scripts/n8n/official_sql_infodive_provider_candidate.py \
  --n8n-container n8n-n8n-1 \
  --workflow-id 2E6mbYg8CEJhGhqs \
  --config /root/.local/share/agente-sql-langgraph/sql-infodive-official-provider.json
```

A ferramenta só anuncia `CANDIDATE_IN_MEMORY_ONLY`, com os fingerprints anterior/candidato e contagem exata de quatro alterações. **Não grava o patch e não atualiza o n8n**.

## Migração operacional (PR #205)

A atualização oficial **não é realizada pelo merge**. O utilitário `scripts/n8n/official_sql_infodive_provider_rollout.py` permite dry-run, aplicação e rollback com gates de revisão. O auditor da VPS confirmou em 30/10/2026: `activeVersionId == versionId`, `active=true`, 68 nós, e fingerprint armazenado `37725fe765f5f727838c7b5de31bbcf01c25b5deecdef338ead60917e4d70b6d`.

**O SQL-InfoDive disponível no Shadow não implica credencial correspondente no n8n.** Antes da migração, preparar uma credencial n8n com ID/nome/tipo conferidos no próprio n8n e armazenar o segredo no mecanismo de credenciais do serviço. A configuração local do candidato contém referências da credencial e endpoint privado, sem segredo.

### Dry-run sem n8n API key

```bash
cd /docker/agente-sql-langgraph-repo
.venv/bin/python scripts/n8n/official_sql_infodive_provider_rollout.py \
  --n8n-container n8n-n8n-1 \
  --workflow-id 2E6mbYg8CEJhGhqs \
  --expected-stored-sha 37725fe765f5f727838c7b5de31bbcf01c25b5deecdef338ead60917e4d70b6d \
  --config /root/.local/share/agente-sql-langgraph/sql-infodive-official-provider.json
```

É operação somente leitura, não exige API key, não modifica n8n, não chama LLM nem executa SQL.

### Apply (operação separada, sujeita a autorização explícita)

Criar anteriormente diretório privado com `mkdir -m 700 -p /root/.local/state/agente-sql-langgraph/llm-provider-rollout`. Depois de validar canário isolado e obter autorização operacional, o comando dry-run acima recebe:

```text
--apply
--n8n-url https://n8n.srv1319424.hstgr.cloud
--private-backup-dir /root/.local/state/agente-sql-langgraph/llm-provider-rollout
```

O modo apply solicita confirmação local `APPLY-INFODIVE` e chave API n8n sem eco. Ele verifica identidade/versão publicada por API e CLI, fingerprint, metadados da credencial privada, conectividade TCP desde o container n8n, formato do PUT, snapshot privado `0600` e edição concorrente; só então tenta alteração dos quatro nós. Não altera PostgreSQL nem switches de execução LangGraph.

O PUT pode salvar sem publicar a nova revisão no n8n 2.4.8. **Nesse caso a ferramenta falha fechada:** não interpretar sucesso do PUT como efetiva substituição do Gemini, nem publicar automaticamente por uma segunda rota. Verificar via UI e reconciliar com o snapshot sob aprovação.

### Rollback

Usar `--rollback` (sem `--apply`) com os mesmos `--workflow-id`, `--expected-stored-sha`, `--n8n-url` e `--private-backup-dir`; não exige `--config`. A restauração só tenta PUT se os arquivos `0600` (backup e receipt) existirem, o fingerprint atual corresponder exatamente à revisão aplicada e o operador digitar `ROLLBACK-INFODIVE`. Falhas após PUT podem não gerar receipt: esse caso exige reconciliação manual antes de novas escritas, preservando a evidência local. Restaurar Gemini estruturalmente não restaura créditos de geração.

### Comprovação necessária

O fluxo oficial ainda pode alcançar SQL financeira. Portanto, não realizar execução end-to-end no webhook oficial enquanto a nova geração não estiver isoladamente homologada e a aprovação/escopo read-only não estiver comprovada. A mudança de provedor não autoriza execução financeira nem cutover n8n→LangGraph. O benchmark legado é somente avaliador, não contexto do gerador.

## Antes do cutover do provedor — gates separados

1. Validar versão **publicada** do fluxo oficial e compatibilidade da API n8n 2.4.8 (não tratar export CLI isolado como published).
2. Atestar autenticação da credencial privada e rede n8n -> API Infodive **fora de qualquer caminho para executor PostgreSQL**, com chamada segura, aprovação de custo e nenhum segredo em log.
3. Testar Generate e Repair com o novo formato; verificar SQL/gates em ambiente isolado com `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`, sem perguntas benchmark ou respostas legadas no gerador.
4. Preparar *backup* privado 0600 da versão publicada, diff com identidade/revisão e rollback autorizado. Não usar `import:workflow` para sobrescrever o oficial ativo — em n8n 2.4.8 isso pode desativá-lo.
5. Só então publicar mediante autorização explícita da **troca operacional de provedor**, preservar n8n oficial e correlacionar evidências com o Shadow usando **SQL-InfoDive nos dois caminhos**.

**Atenção:** o legado possui um caminho até execução SQL financeira. Uma LLM diferente pode produzir SQL distinta; aprovação de provedor não autoriza executar consultas financeiras novas nem reduzir os gates. Portabilidade e paridade numérica continuam exigindo reconciliação do catálogo físico/role em PR #202 e autorização SELECT-only independente.

## Provas disponíveis

- 13 testes Python de protótipo local: PASS (fora do CI, sem VPS).
- Testes reimplementados na PR para CI offline; seu resultado precisa ser consultado na PR.
- Nenhuma gravação no n8n oficial, banco, credenciais, Shadow, Vercel ou produção foi realizada nesta entrega.
