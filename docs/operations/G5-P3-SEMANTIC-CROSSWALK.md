# G5 -> P3: revisao offline de conhecimento historico por versao

## Evidencia real anterior (operador, 30/10/2026)

- `G5_CONTEXT_RESULT=PASS`
- `G5_CONTEXT_SEALED_VERSIONS=11`
- `G5_CONTEXT_SEALED_ROWS=1275`
- `G5_CONTEXT_EVALUATION_ROWS_EXCLUDED=106`
- `G5_CONTEXT_APPROVED=false`
- `G5_CONTEXT_SQL_EXECUTED=false`

Esse passo preservou o conteudo historico, mas **nao converteu nenhum contexto para o LangGraph nem validou significados contabeis**. Todos os pacotes sao privados na VPS. A SOURCE continua INACTIVE, e nao aposentada.

## Objetivo da nova ponte

`scripts/operations/g5_p3_semantic_crosswalk_offline.py` une os pacotes cifrados G5 com o inventario fisico P3 ja autorizado para leitura. Para **cada versao antiga individual**, constroi um rascunho `p3-semantic-mapping-review-v1` de todas as tabelas autorizadas e associa evidencias por hash do registro historico. Toda associacao por nomes de tabelas e colunas e **sintatica**, nunca uma afirmacao de equivalencia financeira.

Implementacao generica, sem if por cliente, sem tabela ou coluna de negocio codificada. O esquema autorizado e carregado da politica P3 existente. O mecanismo utiliza a revisao fisica ja presente, e nao consulta dados financeiros.

Validacoes no passo offline:

1. P3: identidade de banco, role, versao, grants, fingerprint e inventario. Role com privilegios de escrita ou sem escopo SELECT autorizado bloqueia.
2. G5: manifesto `ENCRYPTED_NOT_APPROVED`, formato fechado, versoes sem duplicidade, cada arquivo 0600, SHA256 de ciphertext e plaintext, descriptografia GPG sem eco.
3. Conteudo: somente as quatro colecoes de regras, DRE, aliases e catalogo fisico; nenhum padrao SQL historico no rascunho.
4. Mapeamento: nome fisico exatamente autorizado, mesmo nome em outro esquema, coluna presente/ausente, ou falta de vinculo; nada e selecionado como correto pelo score.
5. Producao: nenhum tenant, versao candidata, prompt, pergunta benchmark, SQL, operacao n8n, LLM ou ALTER/INSERT de banco; execucao financeira sempre false.

Cada rascunho e um JSON cifrado GPG AES256 (`crosswalk-<version-sha256>.json.gpg`). O manifesto local separado registra versoes, hashes, totais e categorias de divergencia, **nao os textos financeiros, nomes de contas ou SQL**. Os rascunhos sao `NOT_APPROVED_NOT_IMPORTABLE`. Nada deles alimenta resolver/planner/generator.

## Execucao exclusiva na VPS, apos merge humano desta PR

Usar o repositorio real atualizado na VPS. Nenhum download no Windows, recaptura de SOURCE, restore, n8n PUT ou migracao de banco:

```bash
cd /docker/agente-sql-langgraph-repo || exit 1
git fetch -q origin && git checkout -q main && git pull --ff-only -q origin main || exit 1
umask 077
.venv/bin/python -m scripts.operations.g5_p3_semantic_crosswalk_offline \
  --g5-manifest /root/.local/share/agente-sql-langgraph/semantic-recovery/g5-private-source-review-v1/manifest.json \
  --audit-dir /tmp/p3-source-audit.7DIc9fUP
```

O programa pede **uma vez** a senha G5 original no terminal local, sem eco. Compartilhar somente linhas `G5_CROSSWALK_*`. A pasta de saida e somente local e privada:

`/root/.local/share/agente-sql-langgraph/semantic-recovery/g5-p3-crosswalk-unapproved-v1/`

Execucao repetida falha se a pasta ja existir: nao substituir, remover nem vazar artefatos privados para contornar bloqueio. O codigo nao utiliza rede ou APIs pagas.

## Aceite e passos para gerar SQL

Essa entrega fecha somente a **ponte tecnica para revisao financeira de verdade**. Ainda exige revisao da correspondencia de cada metrica/sinal/periocidade, chaves/grain, relacoes/fanout, DRE, escopo de tenant e aceite contábil independente. A seguir, o aprovador deve alimentar uma revisao P3 versionada; `p3_semantic_context_candidate.py` e o gate separado que exige evidencias e assinatura independentes. Um mapeamento com campos desconhecidos falha fechado.

Somente depois de uma versao semantica aprovada e segura podera ocorrer geracao SQL real **generate-only**, sem execucao financeira e com o workflow Shadow correlacionado; paridade e cutover requerem provas e autorizacoes distintas. Ainda nao mudar `SEMANTIC_AGENT_VERSION`, nem copiar catalogos G5 para `semantic_context`.

As politicas permanecem `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.