# Revisão física privada: G5 e P3 originais autenticados

**13/11/2026 — técnica executada na VPS, ainda sem qualquer aprovação financeira.**

A versão G5 selecionada no n8n contém **77 registros**: 18 regras, 40 aliases,
11 DRE e 8 tabelas. O snapshot físico P3 ORIGINAL foi preservado no SSH pelo
operador com `G5_P3_CUSTODY=PASS`: **137 colunas, 16 tabelas físicas em 2
schemas**, com SHA-256 exatamente igual ao digest autenticado dentro do G5.
Nenhuma SELECT financeira, alteração de banco, n8n, LLM ou contexto ocorreu.

## Resultado real da conciliação de identificadores

- **48 indícios de origem**: 40 aliases de coluna e 8 entradas de tabela.
- **0/8** schemas declarados pelo catálogo G5 têm identidade física exata no P3.
- Entre oito referências a tabelas: **seis nomes aparecem em mais de um schema**;
  dois têm apenas uma tabela de mesmo nome. Nome único não é equivalência.
- Entre 40 aliases: **32 nomes de coluna** têm uma única correspondência literal
  entre schemas de tabelas homônimas; **8 não têm nenhuma**. Nem as 32
  correspondências são aprovações financeiras nem os 8 ausentes são mapeados
  automaticamente.
- As 48 referências têm schema legado não presente na mesma tabela no P3;
  precisariam de justificativa de remapeamento, revisão e assinatura humana.

Essas estatísticas foram verificadas com o **pacote e snapshot originais**, sem
usar perguntas benchmark, golden answers, SQLs históricas ou valores contábeis.

## Artefatos de revisão (NUNCA publicar no GitHub ou usar em LLM)

Diretório privado root-only:
`/var/lib/agente-financeiro-mcp-admin/g5-financial-review-20261113/active-version-financial-review-private/`

- `confidential-financial-review.html`: os 77 registros financeiros de origem;
- `g5-p3-original-physical-worklist.json`: exatamente 48 referências de origem
  com hash, schema/tabela/coluna legados, todas as opções físicas por nome e
  tipo colunar P3, campos `selected_physical_binding=null`, aprovação FALSE;
- `g5-p3-original-physical-worklist.html`: exibição estática para conferência
  humana, com valores escapados, CSP sem scripts/rede, nenhuma decisão.

Todos têm permissão 0600; diretório 0700. O stdout só contém contagens e flags.
`scripts/operations/g5_p3_original_physical_worklist.py` exige os dois
arquivos privados, verifica SHA do G5 selado e do P3, valida fontes/indícios,
nunca seleciona tabela/coluna, e falha em adulteração, duplicidade ou permissões
inseguras. Não repetir a recuperação/descriptografia nem substituir arquivos.

## Correção necessária no validador de crosswalk

Na fonte real, os oito registros do catálogo guardam `schema_name/table_name`
no **registro de origem**, mas seus indícios P3 trazem `source_table_ref=null`.
O validador anterior exigia uma string nesse campo e, portanto, não poderia
aceitar nenhum crosswalk de 77 registros, mesmo revisado corretamente.

`g5_physical_source_evidence.py` agora recupera a identidade original pelo
hash do registro dentro do pacote G5 autenticado, verifica a consistência dos
indícios e distingue identidade original de destino físico aprovado. Para
mudança de schema, tabela ou coluna, exige em cada decisão
`physical_remap_evidence_sha256` (SHA-256 de justificativa de revisão
independente custodiada); o digest é vinculado à assinatura HMAC do crosswalk,
junto ao destino selecionado, fingerprint, version e digest P3. **A ferramenta
não gera justificativa, não decide significado financeiro e não assina.**

Testes sintéticos: dois tenants distintos, oito indícios do catálogo com
referência nula, colunas renomeadas, ausência/adulteração da prova, assinatura
alterada, tabela homônima, tipo incorreto, privacidade/imutabilidade de
artefatos. Uma coluna sem correspondência de nome só poderá receber destino
diferente após análise financeira, catálogo canônico aprovado e evidência
independente; nunca por heurística.

## Bloqueios efetivos

1. **77/77 significados financeiros UNRESOLVED**: revisão independente por
   especialista, classificação de regras e destinos por catálogo versionado.
2. **48/48 vínculos físicos não aprovados**: escolher e atestar schema, tabela,
   coluna quando aplicável, tipo, grão, chave, período e equivalência semântica.
3. Assinatura independente vinculada à proveniência G5/P3, tenant, versão e
   fingerprint; teste end-to-end de contexto aprovado (ainda inexistente).
4. Perguntas inéditas em dois contextos **reais**, Shadow auditável e paridade
   com n8n+Gemini. As 63 perguntas históricas são QC **posterior** apenas.
5. SELECT financeira read-only requer **autorização operacional separada**;
   cutover e merge seguem gates humanos. Nenhuma comparação de LLMs fase 3.

**Política preservada:** OFFICIAL=n8n+Gemini; SHADOW=n8n+LangGraph+Gemini;
`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.
