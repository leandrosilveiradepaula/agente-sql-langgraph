# G1 — reconciliar workflow Shadow publicado no n8n 2.4.8

**Estado observado na VPS (23/10/2026)**: o candidato de sete nós
`LwUsMRWi34D2ARWu1YzgV` está ativo, com versão publicada idêntica
à atual, mas diverge do contrato mais recente em três Code nodes e na
URL da leitura de evidências. O método GET omitido é serialização
normal do n8n 2.x: não será reescrito.

A análise do histórico mostrou mudanças estruturais após a primeira
importação: propagação de organization_id, seleção de LLM, falha HTTP 503,
versão do contrato de evidências e GET com filtro pelo run_id exato.
Nada disso é regra de negócio nem SQL financeira hardcoded.

**Nunca usar n8n CLI import:workflow para sobrescrever o candidato ativo**.
No n8n 2.4.8 o import sempre desativa o workflow, gera outro versionId e
não publica automaticamente. A API Pública, ao contrário, implementa
PUT /api/v1/workflows/{id} e republica workflows já publicados.
Fontes verificadas:
- https://github.com/n8n-io/n8n/blob/n8n%402.4.8/packages/cli/src/services/import.service.ts
- https://github.com/n8n-io/n8n/blob/n8n%402.4.8/packages/cli/src/public-api/v1/handlers/workflows/spec/paths/workflows.id.yml

## Modo 1: revisão somente leitura (padrão)

**Opção preferida no n8n 2.4.8: SEM criar API key nova.**
O auditor já existente exporta o JSON para diretórios privados,
consulta o reconciliador offline e apaga o arquivo antes de imprimir
apenas o relatório sanitizado:

```bash
cd /docker/agente-sql-langgraph-repo
bash scripts/n8n/audit_parallel_shadow_bindings_readonly.sh \
  --workflow-id LwUsMRWi34D2ARWu1YzgV --upgrade-plan
```

Este comando funciona mesmo enquanto a auditoria de vínculos
anterior reporta \`SHADOW_NODE_CONFIGURATION_DRIFT\`: valida a
cópia corrigida EM MEMÓRIA, sem confundir o candidato real com um PASS.
Nenhum webhook, token, LLM, SQL, publish ou import é executado.

**Alternativa** com API HTTPS já disponibilizada e credencial com escopo
de leitura, provisionada localmente (não neste chat):

```bash
cd /docker/agente-sql-langgraph-repo
# Carregue N8N_API_KEY de um secret store local; NUNCA imprima seu valor.
python3 scripts/n8n/reconcile_parallel_shadow_candidate.py \
  --n8n-base-url "https://SEU-ENDERECO-N8N" \
  --workflow-id LwUsMRWi34D2ARWu1YzgV
```

O recibo retorna somente SHA-256 da snapshot, nomes de nós alterados e
revisões históricas conhecidas. Não imprime URLs internas, JS, tokens,
nomes/IDs de credenciais ou o export bruto. Se um Code node é diferente
de todas as revisões históricas conhecidas ou se a URL de leitura não
corresponde ao formato antigo conhecido, **falha fechado**. Também exige
mesmo versionId/activeVersionId, sete nós, credenciais segregadas, URLs
internas privadas, topologia e flags seguras após a correção em memória.

## Modo 2: aplicação somente após autorização explícita

A aplicação modifica o workflow **ativo**, portanto requer aprovação
operacional separada. Não execute o comando abaixo até autorização
expressa e snapshot atual PASS. A versão de n8n deve continuar 2.4.8;
o valor do hash vem do dry-run imediatamente anterior.

```bash
# Crie um diretório PRIVADO (700), antes da operação.
umask 077
mkdir -m 700 -p /root/n8n-shadow-private-backups
# N8N_API_KEY deve continuar disponível somente via secret store local.
N8N_CANDIDATE_UPDATE_APPROVED=true \
python3 scripts/n8n/reconcile_parallel_shadow_candidate.py \
  --n8n-base-url "https://SEU-ENDERECO-N8N" \
  --workflow-id LwUsMRWi34D2ARWu1YzgV \
  --apply \
  --expected-sha256 "SHA256_EXATO_DO_DRY_RUN" \
  --backup-dir /root/n8n-shadow-private-backups
```

O aplicativo lê o estado novamente antes de fazer o PUT, grava backup
privado com permissão 0600, envia somente os campos aceitos pelo schema
da API e verifica versão republicada e contrato após salvar. Não altera
o workflow oficial de 68 nós, não toca em credenciais, migrations,
provedores LLM ou banco financeiro.

**ATENÇÃO:** o PUT pode afetar imediatamente o endpoint ativo. A API
pública do n8n não fornece If-Match atômico; o script detecta alterações
entre leituras mas não pode eliminar uma corrida durante a requisição.
Se a verificação pós-PUT falhar, ele **não sobrescreve automaticamente**
uma edição concorrente: retorna `POST_APPLY_VERIFY_FAILED_BACKUP_REQUIRED`
e preserva o backup para recuperação humana controlada. Por isso,
executar apenas em janela autorizada e sem outros editores do candidato.

**Pré-condição adicional:** atualizar o LangGraph Shadow TEST para
versão homologada com rollback antes do PUT; o runtime da VPS ainda
reportou LANGGRAPH_COMMIT 136da341... quando o código principal já tinha
avançado. A revisão de alterações do n8n não substitui G1 real.
