# G5 — Revisão completa para candidatura não ativada

**Marco 13/11/2026:** a passagem de planilha financeira preenchida para revisão
estruturada verificável está implementada, sem suprimir a aprovação contábil.

## O que já existe na VPS e NÃO deve ser reconstruído

- G5 original recuperado e criptograficamente verificado: **77 registros**;
- snapshot P3 original SHA-pinned: **137 metadados**, 16 tabelas, 2 schemas;
- referências físicas: **48**; 32 aliases com correspondência literal única
  de coluna, oito aliases sem correspondência literal, seis nomes de tabela
  ambíguos entre schemas; nenhuma dessas semelhanças é equivalência contábil;
- arquivos de entrada do revisor, **0600 root** sob diretório 0700:
  `g5-financial-review-worksheet-unapproved.json` (77 linhas UNRESOLVED e 48
  destinos nulos) e `g5-remap-review-evidence-draft.json` (48 justificativas
  em branco). Os originais permanecem intocados.

**Não transportar esses arquivos em repositórios GitHub nem enviá-los para LLMs.**
Os 63 casos históricos n8n são exclusivamente avaliação posterior.

## Etapa humana imprescindível (não automatizar)

A pessoa com conhecimento da contabilidade original revisa, em área privada,
as 77 linhas do dossiê `confidential-financial-review.html` e seleciona
individualmente STRUCTURAL (somente processo genérico) ou FORBIDDEN no
**código** (conteúdo de negócio que deve existir apenas no catálogo por
tenant/versão). Para cada regra de negócio, indica destinos exatos em
`collection/index` de um contexto canônico **revisado e aprovado
separadamente**, sem copiar SQL, benchmark nem golden answers.

Também escolhe schema.tabela e coluna em cada um dos 48 vínculos físicos,
valida tipos, grão, períodos, relações e sinais quando pertinentes e registra
a fundamentação financeira para mudanças de schema/tabela/coluna.
Não presumir que 32 colunas nominalmente semelhantes tenham significado igual.

O revisor e o autor das propostas devem ser pessoas/autoridades distintas.
A segregação organizacional é um controle humano, não é provada apenas por
textos `prepared_by` e `reviewer_id`. Todos os arquivos revisados precisam
permanecer privados sob menor privilégio.

## Compilador sem aprovação automática

`scripts/operations/g5_compile_completed_review_offline.py` aceita
somente:

1. **Cópia revisada** de `g5-financial-review-worksheet-unapproved.json`
   com os 77 destinos e 48 vínculos preenchidos explicitamente;
2. **Cópia revisada** de `g5-remap-review-evidence-draft.json` com
   justificativas materiais, identidades e destinos correspondentes;
3. Contexto canônico do tenant versionado com
   `source_approval_status="APPROVED"`, padrões exclusivamente estruturais,
   sem SQL histórica, e fingerprint exato;
4. G5 e P3 **originais** SHA-pinned, sem alterar seus bytes.

Exemplo de invocação a partir do checkout da PR #233 na VPS, **somente depois
que especialistas preencherem e revisarem** os arquivos, usando caminhos
absolutos privados:

```bash
python -m scripts.operations.g5_compile_completed_review_offline \
  --manifest /CAMINHO-PRIVADO/manifest.json \
  --source-version-sha256 SHA256-G5-ORIGINAL \
  --packet-file /CAMINHO-PRIVADO/unapproved-source-packet.json \
  --p3-file /CAMINHO-PRIVADO/p3-physical-metadata-original.json \
  --completed-workbook-file /CAMINHO-PRIVADO/worksheet-revisada.json \
  --completed-remap-file /CAMINHO-PRIVADO/remaps-revisados.json \
  --approved-context-file /CAMINHO-PRIVADO/contexto-aprovado.json \
  --output-review-file /CAMINHO-PRIVADO/review-unsigned.json \
  --output-remap-evidence-file /CAMINHO-PRIVADO/remap-evidence-unsigned.json
```

O compilador verifica cobertura 77/48 e identidade por SHA de cada fonte,
fidelidade de campos legados, todas as opções P3, unicidade, classificações
sem pendências, destinos válidos no catálogo, tenant, fingerprint, tipo físico,
justificativas reais e relação autora/revisor. Ele **calcula** digests de
justificativas efetivas, não aceita hashes arbitrários de entrada. O artefato
que produz possui `accounting_approved=false`,
`ready_for_generation=false` e **NENHUMA assinatura, SQL ou ativação**.

Se o preenchimento estiver incompleto, alterado, for de outro tenant ou
tiver evidência de remapeamento inválida, retorna
`G5_REVIEW_CANDIDATE=BLOCKED` sem criar artefatos de saída.
Na ausência de renomeações, o documento de remapeamento não é necessário.

## Assinatura externa e verificação final

Somente uma autoridade financeira realmente independente poderá assinar
a revisão depois de verificar os documentos, significados, proveniência,
catálogo, fingerprint e 48 decisões. A assinatura do contrato
`g5-independent-financial-approval-v1` permanece fora do compilador.
A CLI `g5_financial_crosswalk_review_cli.py` compara essa assinatura
independente ao contexto e aos arquivos de origem e, **no máximo**, retorna
`G5_FINANCIAL_MAPPING_CANDIDATE_NOT_ACTIVATED`. Não habilita consulta.

Os testes com dois tenants **sintéticos** demonstram o encadeamento completo,
inclusive uma matriz de 77 registros e 48 referências, com assinatura de
TESTE separada e resposta explicitamente **não ativada**. Não constituem
homologação de cliente real.

Depois dessa etapa: perguntas inéditas em pelo menos dois contextos **reais**
materialmente diferentes e Shadow auditável com n8n+Gemini oficial.
Comparação financeira numérica requer autorização adicional SELECT-only;
merge/cutover humano controlado somente após provas de paridade.

**Estados atuais:** OFFICIAL=n8n+Gemini; SHADOW=n8n+LangGraph+Gemini;
`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. Nenhum banco, serviço ou
contexto produtivo foi alterado.
