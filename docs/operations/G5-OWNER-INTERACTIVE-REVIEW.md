# Bloco 1 — Revisão G5/P3 pelo operador responsável

**Estado:** artefato de revisão privado pronto para utilização; não substitui
revisão financeira nem homologação final. O operador do projeto pode
conduzir pessoalmente as decisões financeiras. Não é necessário procurar
um novo responsável nem delegar a responsabilidade integral do produto.
Há, porém, separação obrigatória entre **preparação técnica** de propostas e
**ato explícito de aprovação humana**, assinaturas/evidências e execução SQL.

## Já recuperado (não repetir)
- n8n publicado: 68 nós, 41 Code; OFFICIAL=n8n+Gemini.
- Fonte G5 original: **77** regras/aliases/mapeamentos/catalogos, protegidos 0600.
- P3 original: **137** colunas em 16 tabelas, 2 schemas, SHA autenticado.
- 48 referências físicas: 40 alias + 8 tabelas. Sem aprovação por semelhança.
- 63 benchmarks históricos: apenas avaliação, **nunca entrada ao gerador**.

## Programa privado TTY, recuperável e sem rede

`scripts/operations/g5_owner_review_tui.py` foi criado para o responsável
revisar diretamente na VPS e registrar decisões sem editar JSON manualmente.
Use o wrapper root-only instalado na VPS:

```bash
bash /var/lib/agente-financeiro-mcp-admin/g5-financial-review-20261113/run-owner-review.sh
```

Se desejar apenas contagens, sem exibir qualquer dado financeiro:

```bash
bash /var/lib/agente-financeiro-mcp-admin/g5-financial-review-20261113/run-owner-review.sh status
```

O programa só abre os valores originais no **terminal local /dev/tty** e
nunca os encaminha ao stdout do broker MCP, ChatGPT, GitHub, log, LLM, prompt
ou benchmark. Usa somente os bytes G5/P3 selados e valida seu SHA exato
antes de permitir uma escolha. Modificações são salvas após **cada decisão**
com arquivo privado 0600 sob diretório 0700 e retomadas na próxima execução.
Rejeita saída sem TTY, fontes trocadas, identificadores alterados, dados
duplicados, permissões amplas, symlinks e alterações em flags de aprovação.

### Comandos no menu privado

- `f`: próximo registro financeiro pendente. Exibe texto original
  autenticado no seu terminal. Escolha **S** para mecanismo STRUCTURAL
  (plataforma/processo) ou **B** para informação de negócio que deve morar
  **apenas no catálogo versionado**, não em Python/TypeScript.
- Ao escolher **B**, informe os destinos canônicos efetivamente revisados
  no formato `collection:index`, separados por vírgulas. Se não existe
  catálogo validado, deixe vazio: permanece **pendência**, não invente.
- `p`: próximo vínculo físico P3. A interface exibe TODAS as tabelas e
  colunas disponíveis no P3 original, sem escolher nenhuma. O operador
  seleciona schema/tabela e coluna; se diferem da origem, precisa registrar
  justificativa contábil material. A semelhança literal não prova equivalência.
- `f 12` ou `p 20`: revisar ou corrigir um item específico.
- `i`: registrar identificadores reais de tenant, versão, origem técnica
  da proposta (`prepared_by`), responsável revisor (`reviewer_id`) e
  fingerprint do contexto canônico **realmente aprovado**. Eles não podem
  ser inventados. A autoria técnica e aprovação financeira têm papéis
  distintos: o próprio titular do projeto pode ser a autoridade humana.
- `s`: ver apenas quantidades revisadas/pendentes.
- `e`: **exportação UNSIGNED** dos dois arquivos revisados SOMENTE quando
  as 77 classificações têm destino ou são STRUCTURAL, os 48 vínculos
  foram selecionados, e identidade/fingerprint estão preenchidos. Não
  ativa contexto, não assina nada e não executa SQL.
- `q`: encerra sem perder as decisões já gravadas.

Arquivos persistentes da VPS, **não enviar aqui**:

`/var/lib/agente-financeiro-mcp-admin/g5-financial-review-20261113/active-version-financial-review-private/`

- `g5-owner-review-progress.json`: estado não aprovado, retomável, 0600.
- `g5-owner-completed-worksheet-unsigned.json`: exportação somente explícita.
- `g5-owner-completed-remap-unsigned.json`: razões físicas exportadas.

O código exige que `accounting_approved=false`,
`financial_sql_executed=false`, `context_activated=false` e
`benchmark_used=false` permaneçam inalterados. Não oferece a opção
de marcar aprovação contábil, assinar ou executar SQL.

## Após concluir as escolhas

`g5_compile_completed_review_offline.py` usa as duas exportações,
o contexto canônico tenant/version/fingerprint já aprovado e os G5/P3
originais. Revalida todas as linhas, destinos, tipos, grãos e razões de
mudança, e produz apenas candidatura `UNSIGNED` para exame.
`g5_financial_crosswalk_review_cli.py` verifica **assinatura humana
externa e separada da geração**; só pode retornar
`G5_FINANCIAL_MAPPING_CANDIDATE_NOT_ACTIVATED`.

O responsável pode conduzir as revisões e ser autoridade de aprovação,
mas a assinatura não é gerada pelo motor que propõe o mapeamento nem
substituída por identidade textual. Preservar trilha e ato explícito de
aprovação; se o mesmo agente ou a mesma pessoa for tanto autor final das
decisões quanto seu auditor, **não declarar revisão independente**.
Esta separação é operacional, não um convite a inventar outro aprovador.

O Bloco 1 requer ainda a integração Shadow auditável, perguntas inéditas em
pelo menos dois contextos **reais** distintos e paridade com o n8n+Gemini.
Qualquer SELECT financeira real precisa de autorização operacional
separada, com menor privilégio. Nenhuma migração, merge, produção ou cutover
foi autorizada implicitamente.

**Política:** OFFICIAL=n8n+Gemini; SHADOW=n8n+LangGraph+Gemini;
`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.
