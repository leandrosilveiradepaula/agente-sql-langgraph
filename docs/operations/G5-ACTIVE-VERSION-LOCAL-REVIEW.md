# Desbloqueio local, por versão, do contexto financeiro oficial G5


## Resultado operacional confirmado — 13/11/2026

O operador já executou `G5_TARGETED_REVIEW=PASS` para a versão ativa 7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485, recuperando 77 registros. O diretório de saída real e persistente é `/var/lib/agente-financeiro-mcp-admin/g5-financial-review-20261113/active-version-financial-review-private`. O antigo caminho `/tmp/legacy-n8n-g5-inventory-20261111` era **PrivateTmp do serviço MCP** e não é visível no SSH do operador; o comando em /tmp abaixo está registrado apenas como procedimento histórico e NÃO deve ser repetido. O pacote privado foi reparado para preservar exatamente o SHA-256 plaintext original, e o recuperador atualizado para salvar os bytes GPG sem reserializar. Revisão contábil: PENDING, 77/77 registros ainda UNRESOLVED. A candidata privada de linhagem técnica dos 40 aliases com as 8 tabelas não é contexto autorizado. Sem nova senha necessária, sem SQL real, sem ativação.

---

**Objetivo:** remover a dependência do Bloco 1 com uma única interação humana no terminal da VPS. Este procedimento **não usa a senha no ChatGPT, GitHub, linha de comando, variáveis de ambiente nem logs** e não ativa qualquer contexto no n8n/LangGraph. Não há execução de SQL financeira. O pacote fica marcado como evidência NÃO APROVADA para a posterior revisão contábil.

## Por que apenas este pacote?

Os cinco SELECTs do nó 5 do workflow n8n publicado fixam um mesmo agent_version. O SHA-256 dessa versão é:

~~~text
7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485
~~~

Esse hash coincide com apenas um dos 11 pacotes cifrados G5 (índice 10/11): **18 regras + 40 aliases + 11 mapeamentos DRE + 8 registros de catálogo**, total 77 registros. A coleção de padrões SQL históricos ficou excluída desse pacote. As 10 versões restantes continuam preservadas para revisão histórica/portabilidade, sem misturar os dados de diferentes versões.

## Única ação que exige terminal interativo local

Usar uma sessão SSH com usuário autorizado na VPS. Antes de executar, conferir que o checkout temporário ainda contém o código revisado na PR #233; o caminho abaixo corresponde ao checkout isolado de auditoria e **não** atualiza o n8n oficial ou a main.

~~~bash
cd /tmp/agente-financeiro-full-migration-audit-20261111
/docker/agente-sql-langgraph-repo/.venv/bin/python \
  scripts/operations/g5_targeted_financial_review_offline.py \
  --manifest /root/.local/share/agente-sql-langgraph/semantic-recovery/g5-private-source-review-v1/manifest.json \
  --version-sha256 7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485 \
  --output-dir /tmp/legacy-n8n-g5-inventory-20261111/active-version-financial-review-private
~~~

O script solicita a senha somente pelo TTY local, sem eco. Usa GPG com descritor anônimo, confere os hashes do ciphertext e plaintext, versão e contagem de registros e exclui importação, prompt/LLM e SQL financeira. Após êxito, cria dois arquivos **0600 em diretório 0700**: unapproved-source-packet.json (conteúdo privado sensível, não compartilhar) e sanitized-review-evidence.json (contagens, nomes de campos e hashes, não valores financeiros). O pacote não é aprovado nem ativado. O script falha se o destino já existir ou se rodar sem TTY. O preflight não interativo com o arquivo real retornou BLOCKED conforme esperado; a senha ainda não foi utilizada nesta execução.

## Próxima etapa técnica depois do desbloqueio

Inspecionar **somente na VPS privada** as 18 regras, 40 aliases, 11 DRE e 8 registros de catálogo, separar definições estruturais de negócios específicos e correlacioná-las ao código dos nós 6/7/8/22/23/54. Confirmar fórmula, fonte, sinal, grão, filtros, join e período com responsável financeiro; mapeamentos desconhecidos devem ser bloqueados. Só então construir contexto versionado autorizado, interpretar pergunta inédita no LangGraph e gerar/validar SQL sem execução financeira.

**Segurança:** nunca copiar o arquivo unapproved-source-packet.json para um repositório público ou chat; não usar perguntas/respostas/SQL do benchmark como conhecimento do gerador. Merge, ativação, migração e cutover continuam sujeitos a aprovação humana.
