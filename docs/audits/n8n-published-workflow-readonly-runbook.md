# Reconciliação da versão publicada do n8n — procedimento somente leitura

**Objetivo:** fechar a lacuna de G2 entre a exportação histórica `v2.2.31` no GitHub e o workflow **publicado** no n8n autorizado da VPS. Isto **não ativa o Shadow**, não prova paridade financeira e não autoriza cutover.

## Situação comprovada versus desconhecida

O repositório `leandrosilveiradepaula/Agente-Financeiro` contém uma exportação congelada em julho de 2026, com 75 nós, incluindo 13 nós com hardcodes de negócio comprovados na exportação histórica. Consulte `docs/audits/n8n-legacy-workflow-v2.2.31-inventory.md`.

O produto `Agente-Financeiro` possui código que chama n8n e despacha eventos LangGraph Shadow **por `after()` quando `LANGGRAPH_SHADOW_ENABLED=true`**. No repositório, o valor padrão da variável é `false`; isso **não informa o valor implantado**. O n8n ativo, a versão publicada, o despacho real, Gemini no Shadow e as respostas numéricas equivalentes **não foram comprovados por esses arquivos**.

## Referência oficial para a exportação

A documentação atual do n8n diferencia versão **published** de rascunho. O Server CLI `n8n export:workflow --id=... --published` exporta a versão publicada; o comando sem esse parâmetro pode exportar um rascunho e portanto não serve como atestado do caminho oficial. Documentação: https://docs.n8n.io/hosting/cli-commands/ .

**Requisitos:** operação por pessoa autorizada no host que contém a instalação n8n, acesso ao Docker e Python 3, workflow ID da versão pública escolhido pelo operador. A própria CLI Server tem acesso direto ao banco n8n e pode ignorar os controles de usuários; portanto o uso fica **restrito a operador autorizado**, mesmo sendo exportação read-only. Nenhum n8n API key é necessário nesse método.

## Procedimento manual na VPS, sem executar workflow

1. Atualizar a cópia do repositório LangGraph para um commit que já tenha a PR de atestado mergeada:

```bash
cd /docker/agente-sql-langgraph-repo || exit 1
git fetch -q origin &&
git checkout -q main &&
git pull --ff-only origin main
```

2. Identificar os nomes dos contêineres **sem exibir variáveis nem credenciais**:

```bash
docker ps --format '{{.Names}} {{.Image}}' | grep -i n8n
```

3. Executar o atestado com o container/ID **efetivamente publicado**. O ID `0dXXQGtb4i18-YEqVSTWY` aparece na exportação histórica, **mas deve ser validado contra a instância atual** e **não é um default do script**:

```bash
bash scripts/audit_n8n_published_workflow_readonly.sh \
  --container CONTAINER_N8N_CONFIRMADO \
  --workflow-id ID_PUBLICADO_CONFIRMADO \
  > /tmp/n8n-published-summary.json
```

Se houver um arquivo histórico disponível localmente **fora do Git/sem publicá-lo**, acrescente `--compare-to /caminho/privado/workflow-historico.json`; o relatório terá `unchanged/changed/added/removed` por nó, usando hashes de identidade, sem imprimir SQL, prompts ou valores de configuração. O script usa nomes `node-001`, `node-002` etc. deliberadamente, pois nomes livres dos nós também podem conter secrets. O hash do workflow não revela seu conteúdo.

O script falha fechado quando a CLI não suporta `--published`, quando o ID exportado difere do solicitado, quando há múltiplos workflows, quando não consegue limpar o arquivo temporário do contêiner ou quando a estrutura do JSON é inválida. **Não contornar uma falha exportando o rascunho.** A execução de coleta pode criar e remover arquivos efêmeros privados em `/tmp` no contêiner e no host; não altera workflows nem executa SQL financeiro ou faz chamadas LLM. A exportação **lê o armazenamento interno do próprio n8n** e por isso exige operador autorizado. Não faça a coleta caso isso não seja permitido na política operacional local.

4. Encaminhar **apenas o JSON sanitizado**. Não enviar o JSON exportado pelo n8n, `docker inspect` completo, `.env`, headers, logs completos, credenciais, prompts ou SQLs.

## Como interpretar

- `published_export_selected=true` significa que o script invocou **`--published`**, mas ainda é necessário provar que o webhook do produto usa exatamente esse workflow.
- `official_webhook_route_verified=false` não muda até comprovar configuração/roteamento real.
- `node_identity_sha256` e `parameters_sha256` identificam o nó e seus parâmetros sem expor valores.
- `runtime_configuration_sha256` detecta mudanças também de tipo/versão, credenciais referenciadas e demais configurações operacionais. `topology_changed` alerta para conexões diferentes mesmo quando nenhum nó mudou; `workflow_id_matches_baseline` distingue identidades de workflow. Esses sinais são conservadores e **não** classificam regras de negócio por si.
- Não afirmar que as regras são iguais só porque `changed=0`: consultar também `topology_changed`, IDs e demais diferenças de export.
- `workflow_export_sha256` divergente pode refletir metadados, configurações e alterações reais. Não tratar hash diferente como regressão sem revisar diferenças de nós.
- Números de casos semânticos v16/v17/v18 são apenas diagnóstico; não comprovam equivalência SQL nem resultado financeiro.

## Próximos gates, sem operações não autorizadas

A) Confirmar exatamente qual fluxo n8n a rota oficial `/api/generate-sql` alcança (por configuração do deployment e execução correlacionada; não usar URLs hardcoded como prova).

B) Com o inventário da versão publicada em mãos, revisar regras `MIXED_TO_VERIFY`, identificar `FORBIDDEN`, fonte contábil e seu destino em contexto versionado. Nenhum literal de esquema/cliente no motor LangGraph.

**Lacuna de integração encontrada em código:** em `Agente-Financeiro/app/api/generate-sql/route.ts` o disparo Shadow via `after()` só ocorre no caminho que alcança o retorno final normal; respostas antecipadas de erro, bloqueio por política e webhook não-2xx não programam esse dispatch. Além disso, o disparo parte do BFF, não do workflow n8n. Isso **não** demonstra integração orquestrada n8n → LangGraph; G1 precisa cobrir também divergências/falhas antes de qualquer cutover.

C) Capturar pares de evidências `agent_run_id` do mesmo pedido, um do n8n+Gemini oficial e outro do n8n+LangGraph+Gemini Shadow. O produto já grava SQL e status oficiais, e o serviço LangGraph grava Shadow separadamente; ainda falta um comparador de evidência consolidado e comprovação de ativação/execução real.

D) Somente após autorização separada de SQL read-only e menor privilégio, validar resultados numéricos. Não ativar contexto, modificar workflows n8n, rodar benchmark formal nem realizar cutover implicitamente.

**Responsabilidade:** operador n8n escolhe instância/ID, sem delegar credenciais. O agente SQL pode analisar o relatório sanitizado e preparar externalização via PR sem tocar no runtime.