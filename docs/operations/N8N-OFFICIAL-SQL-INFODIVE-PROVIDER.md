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
