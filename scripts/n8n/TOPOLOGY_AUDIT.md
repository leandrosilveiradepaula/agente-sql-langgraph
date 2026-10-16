## Diagnóstico de topologia n8n — somente leitura

Objetivo: entender a **estrutura do workflow financeiro oficial** antes de propor a ramificação Shadow. Este diagnóstico não altera o workflow oficial, não lê credenciais descriptografadas, não ativa rotas nem executa LLM ou SQL de negócio.

A CLI do n8n `export:workflow` exporta definições e pode incluir parâmetros internos sensíveis. Por isso, **não envie o JSON original** nem execute `n8n export:workflow --all` diretamente no terminal para copiar resultados. O runner mantém a exportação em diretório privado (modo 0700) **dentro do container n8n**, transforma a definição em topologia sanitizada e apaga os arquivos temporários no final.

Na VPS, após integrar o PR:

```bash
cd /docker/agente-sql-langgraph-repo
git pull --ff-only origin main
bash scripts/n8n/run_official_workflow_topology_audit.sh
```

A saída em modo INDEX mostra apenas o ID do workflow, indicação de ativo, impressão digital do nome, número de nós e categorias estruturais. Não são exibidos nomes de clientes, perguntas, SQL, URLs, textos, credenciais ou parâmetros.

Para detalhar **somente o ID escolhido** (copiado da URL do workflow no n8n ou do índice sanitizado):

```bash
N8N_AUDIT_WORKFLOW_ID='ID_DO_WORKFLOW' bash scripts/n8n/run_official_workflow_topology_audit.sh
```

Nesse modo a saída lista cada nó por índice numérico, categoria estrutural, habilitado/desabilitado e índices dos próximos nós. Compartilhar **somente essa saída sanitizada** é adequado; não compartilhar o export original nem variáveis de ambiente.

A exportação padrão pode corresponder ao rascunho atual, não necessariamente à versão publicada, dependendo da versão do n8n. O relatório indica explicitamente `PUBLISHED_VERSION_VERIFIED=false`. Antes de qualquer alteração no fluxo oficial, reconciliar topologia publicada, caminho de resposta, paralelismo, timeouts, credenciais S2S e política de não interferência. **Não fazer cutover nem adicionar chamadas de LLM sem decisão explícita.**
