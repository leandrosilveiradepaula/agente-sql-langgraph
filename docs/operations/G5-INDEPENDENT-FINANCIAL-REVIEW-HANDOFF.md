# G5/P3 — pacote privado pronto para revisão financeira independente

**Status operacional em 13/11/2026: preparação técnica concluída; homologação
contábil ainda NÃO iniciada/assinada.** Somente leitura de evidências originais;
nenhuma SQL financeira foi executada e nenhum contexto LangGraph foi ativado.

## Fonte efetivamente autenticada

- n8n publicado: 68 nós, 78 ligações, 41 Code; continuar a resposta oficial
  n8n + Gemini inalterada.
- Pacote G5 original: 77 registros (18 regras, 40 aliases, 11 DRE e 8 entradas
  de catálogo) recuperados localmente, versão SHA-256
  `7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485`.
- Snapshot P3 original: 137 colunas em 16 tabelas físicas, 2 schemas, com SHA
  conferido contra o pacote original autenticado.
- Reconciliação estrutural P3: **48 referências** (40 colunas, 8 tabelas);
  **32** aliases têm exatamente uma correspondência literal, **8** não têm
  correspondência literal; os oito schemas legados não têm equivalência física
  direta, seis nomes de tabela são homônimos entre schemas. **Nenhuma**
  correspondência nominal significa equivalência financeira.

## Pacote privado destinado ao revisor

Diretório root, 0700:

`/var/lib/agente-financeiro-mcp-admin/g5-financial-review-20261113/active-version-financial-review-private/`

Arquivos 0600 que já existem:

- `unapproved-source-packet.json`: original autenticado, valores confidenciais.
- `p3-physical-metadata-original.json`: bytes físicos autenticados.
- `confidential-financial-review.html`: 77 registros, legíveis apenas sob custódia.
- `g5-p3-original-physical-worklist.html`: 48 opções físicas, NÃO selecionadas.
- `g5-financial-review-worksheet-unapproved.json`: **77 classificações
  UNRESOLVED**, **48 decisões de vínculo com destino nulo**, opções físicas
  candidatas; sem nenhum contexto, assinatura ou autorização.
- `g5-remap-review-evidence-draft.json`: **48 justificativas nulas**, com
  origem e digest P3 G5 vinculados. Possui contrato explicitamente `DRAFT`
  para impossibilitar uso inadvertido como evidência aprovada.

Os dois últimos arquivos foram gerados pelo comando genérico
`scripts/operations/g5_financial_review_worksheet_offline.py`.
Ele só lê originais autenticados e draft financeiro original, verifica cobertura,
escreve 0600/0700, nunca preenche um significado ou escolhe um destino.

## Trabalho humano obrigatório para sair de PENDING

**Responsável financeiro que conhece o legado e seu destino:**

1. Revisar as 77 linhas originais no dossiê privado e classificar cada uma como
   **STRUCTURAL** (somente comportamento genérico de plataforma) ou **FORBIDDEN**
   no código (conhecimento de negócio migrado para catálogo versionado). Uma
   linha não pode ficar TRANSITIONAL/UNRESOLVED para homologação. Nas linhas
   de negócio, indicar objetos precisos do contexto canônico autorizado, por
   `collection/index`, SEM transformar exemplos/perguntas/SQL históricas em
   respostas, regras ou treinamento do planejador.
2. Em cada uma das 48 referências, escolher explicitamente `schema.tabela`
   e coluna física (nulo apenas para referência genuinamente de tabela), com
   tipo compatível com P3 e com catálogo **do tenant correto**. A presença de
   nome idêntico não substitui a escolha humana.
3. Para qualquer mudança de schema, tabela ou coluna, elaborar justificativa
   privada por vínculo, com fonte, destino e fundamento contábil. Não preencher
   somente uma string SHA-256 arbitrária.
4. Atribuir `tenant_id`, `semantic_agent_version`, catálogo e
   `context_fingerprint` de **contexto canônico efetivamente revisado**.
   Mapeamentos que não fazem sentido devem continuar BLOQUEADOS; não inventar
   tipos, sinais, contas, relação entre tabelas ou fórmula financeira.

**Autoridade independente do autor das propostas:**

5. Conferir os 77 destinos, 48 vínculos físicos, justificativas efetivamente
   lidas, versão G5/P3, contexto/fingerprint e separação de tenant.
   O contrato `g5-physical-remap-review-evidence-v1` exige um documento
   **preenchido** com dados vinculados à origem, autora e revisor distintos,
   fonte/destino exatos e texto de justificativa não vazio. O
   `physical_remap_evidence_sha256` de cada decisão deve ser o SHA-256 do
   JSON canônico dessa linha real; um hash sem o respectivo documento privado
   é REJEITADO.
6. A assinatura HMAC independente inclui os digests de todas as decisões,
   conteúdo das justificativas, SHA do snapshot P3 e fingerprint G5/contexto.
   A chave de verificação deve ficar segregada do autor do mapeamento.
   Identidade textual por si só não prova segregação de funções; preservar
   controle organizacional e logs de aprovação.

**Verificação técnica, SEM ativação nem SQL:**

A CLI `scripts/operations/g5_financial_crosswalk_review_cli.py` aceita
`--p3-metadata-file` e `--physical-remap-evidence-file` privados, além do
pacote/G5, inventário do n8n, revisão 77, contexto aprovado, recibo assinado e
chave privada do verificador. Ela deve produzir somente
`G5_FINANCIAL_MAPPING_CANDIDATE_NOT_ACTIVATED` após todos os gates, nunca
`context_activated=true` ou execução. A presença do workbook **não**
autoriza esta chamada com dados falsos; sem especialista real, manter
`G5_PHYSICAL_DECISIONS_INCOMPLETE`.

## Próximas provas de produto

Depois da validação financeira independente: perguntas inéditas em pelo menos
dois tenants realmente distintos e execução Shadow auditável em paralelo ao
n8n+Gemini oficial. Comparar interpretação, período, filtro, SQL e resultados
quando houver autorização read-only de menor privilégio **separada**.
Usar as 63 perguntas históricas exclusivamente como avaliação posterior.
Somente aprovação humana explícita permite merge, migração, release ou cutover;
n8n permanece orquestrador. Comparar SQL-InfoDive somente após Fase 2.

**Restrições vigentes:** OFFICIAL=n8n+Gemini,
SHADOW=n8n+LangGraph+Gemini,
`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.
