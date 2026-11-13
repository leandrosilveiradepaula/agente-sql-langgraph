## ATUALIZAÇÃO 13/11/2026 — Fonte G5 + metadados P3 verificados; decisões financeiras pendentes

O P3 original (137 metadados/16 tabelas/2 schemas) foi finalmente recuperado com SHA conferido ao pacote G5 de 77 registros. Seções históricas abaixo que afirmam que P3 ainda não foi encontrado estão superadas. O cruzamento técnico autenticado de 48 indícios revelou 32 aliases com uma correspondência literal de nome físico, 8 aliases sem e seis tabelas homônimas em dois schemas. O catálogo G5 declara 8/8 schemas ausentes fisicamente no P3. Os artefatos privados `g5-p3-original-physical-worklist.json/.html` (0600) registram TODAS as opções, nunca uma escolha; há também dossiê HTML privado com os 77 textos originais.

O verificador foi corrigido para os 8 indícios `source_table_ref=null` provenientes do catálogo original e para remapeamento de schema/tabela/coluna autenticado: uma alteração só pode ser validada com `physical_remap_evidence_sha256` da análise financeira independente, anexado à decisão e à assinatura HMAC do aprovador junto aos hashes P3/contexto/fonte. Ainda faltam 48 decisões físicas e 77 aprovações de significado; o gate real retorna `G5_PHYSICAL_DECISIONS_INCOMPLETE` conforme esperado. Consulte `docs/operations/G5-P3-ORIGINAL-PHYSICAL-WORKLIST.md`. Nenhuma aprovação contábil foi simulada, nem SQL financeira real, importação ou cutover.

---

## 13/11/2026 — Revisão material disponível e requisito adicional de identidade P3

**Dossiê real criado** em `/var/lib/agente-financeiro-mcp-admin/g5-financial-review-20261113/active-version-financial-review-private/confidential-financial-review.html` (0600, owner root; diretório 0700). HTML estático, sem scripts/rede, com valores originais escapados, cada SHA de fonte, campos de origem, estado PENDING e indícios físicos ainda não aprovados. Não transferir por GitHub nem usar em LLM. Seu conteúdo é *confidencial*; só especialista financeiro autorizado deve lê-lo no ambiente controlado. Já existem 77 registros íntegros: não executar a recuperação novamente.

**Diferença crítica:** 40/40 aliases têm referência consistente ao catálogo LEGADO (8 tabelas), mas nos indícios do snapshot físico P3 há 46 referências `AMBIGUOUS_TABLE_NAME` (40 aliases + 6 tabelas) e 40 `COLUMN_UNRESOLVED`; as duas tabelas restantes são `TABLE_NAME_ONLY`, não atestação. Nenhum desses nomes pode ser promovido como verdadeiro só por similaridade de string. O P3 físico ORIGINAL, cujo SHA está em `packet.origin.p3_snapshot_sha256`, ainda precisa de disponibilização custodiada como arquivo 0600; não foi encontrado no conjunto privado consultado. O gate real `G5_P3_ORIGINAL_METADATA_REQUIRED` é esperado até isso.

**Novo contrato genérico de promoção somente de CANDIDATO:** `g5_physical_source_evidence.py` recebe o P3 completo (JSON original; `physical` de [schema,table,column,type]; `sql_executed=false`, `llm_calls=0`) sem acessar dados financeiros, valida seu SHA contra a origem G5 e exige `review.physical_binding_decisions` para todo indício. Cada entrada deve conter precisamente `collection`, `source_row_sha256`, `qualified_table` (schema.table) e `target_column` (nulo para referências apenas à tabela). A escolha só é válida se o schema/tabela/coluna realmente ocorrerem no P3 e corresponderem ao catálogo canônico aprovado inclusive no tipo físico, respeitando caixa do identificador entre aspas. Escolher arbitrariamente entre tabelas homônimas, alterar tipo/coluna, misturar versões, retirar registros ou fornecer P3 sem digest original é BLOQUEADO. A CLI `g5_financial_crosswalk_review_cli.py` recebe `--p3-metadata-file` como caminho privado, exigido quando a fonte traz indícios, e o recibo HMAC de aprovação independente precisa incluir `p3_snapshot_sha256`, `physical_binding_decisions_sha256` e `physical_binding_rows` entre seus claims autenticados. Revisão de significado financeiro dos 77 registros e assinatura do aprovador ainda não existem; não construir recibo fictício.

O dossier foi validado sobre o pacote original real, com 77/77 linhas, 48 indícios, 46 ambiguidades de tabela e 40 de coluna; as duas suítes novas incluem 15 testes sintéticos de dois contextos distintos e adulterações. Nenhuma SQL financeira foi executada ou foi concedido acesso a LLM/contexto. Não afirmar paridade ou preparação para merge/cutover.

---

# G5 para catálogo canônico: revisão financeira individual


## Atualização verificada após recuperação no terminal da VPS — 13/11/2026

O operador completou a descriptografia sem ecoar a passphrase. O pacote ORIGINAL foi validado no SHA-256 selado, com **77/77 linhas** e segregação das 106 SQL históricas. O recuperador tinha uma falha: salvava o JSON com separadores/espaços diferentes, produzindo um SHA incompatível com a verificação de `verify_private_review`. O arquivo privado foi restaurado ao byte stream original e `verify_decrypted_packet` passou sobre esse arquivo. A PR #233 foi corrigida para persistir `content` original, e um teste de entrada real sintética (dois schemas) exige bytes idênticos e rejeita a reserialização. O pacote não precisa ser decifrado novamente para revisão offline.

Uma inspeção estruturada PRIVADA localizou 40 aliases com tabela sem schema, todos vinculáveis univocamente às **8** definições de tabela pelo nome legado; as 40 colunas de destino ocorrem nas listas de metadados do catálogo. Foi criado `unapproved-physical-lineage-candidates.json` com ligações registro-origem -> registro-tabela -> coluna física candidata, sob 0600/0700, explicitamente não aprovado. **Essa confirmação estrutural não comprova que os campos existam fisicamente com tipos corretos na base original inativa, nem seus significados, regras, sinais, joins ou resultados.** Todos os 77 registros continuam `UNRESOLVED` em `financial-crosswalk-review-draft.json`; nenhum destino canônico foi chancelado e nenhum recibo de especialista independente foi fornecido. O caminho `G5_FINANCIAL_MAPPING_CANDIDATE_NOT_ACTIVATED` ainda não foi atingido. Não importar o candidato como contexto, não usar como prompt e não executar SQL financeira.

---

## Fonte e estado real — 13/11/2026

A versão selecionada pelo n8n publicado (source-version SHA-256
7f36f6619fe64b5d537bb4a84b5e148347e3b594a7e9f129ed9b55e9f6ac6485)
foi reconciliada com o manifesto G5 privado. A integridade de seu ciphertext
foi confirmada na VPS: 77 registros em quatro coleções (18 regras,
40 aliases, 11 mapeamentos DRE, 8 entradas de catálogo). O conjunto de 11
versões cifradas permanece guardado, com 1.275 registros de contexto. As
SQL patterns históricas estão excluídas do corpus de geração.

**O significado contábil dos 77 registros ainda não foi homologado.**
Não existe contexto financeiro G5 aprovado nem importado. Nenhuma SQL de
cliente foi executada. Este contrato implementa a passagem obrigatória
de origem para revisão e aprovação, não a dispensa.

## Caminho operacional

1. O script scripts/operations/g5_targeted_financial_review_offline.py
   continua exigindo TTY e passphrase exclusivamente local. Confirma
   contrato do manifesto, versão e digest criptográfico antes de decifrar.
   Rejeita symlink do manifesto. Em diretório privado 0700, cria arquivos
   0600: unapproved-source-packet.json, sanitized-review-evidence.json e
   **financial-crosswalk-review-draft.json**.
2. O draft lista cada source_row_sha256 e coleção originais, sem valores
   contábeis nem SQL. Todos começam UNRESOLVED, sem destinos ou aprovação.
   Um especialista revisa privadamente cada registro real e o classifica
   STRUCTURAL ou FORBIDDEN. Para FORBIDDEN, deve indicar objetos exatos do
   catálogo canônico por collection/index. TRANSITIONAL e UNRESOLVED
   impedem qualquer conclusão.
3. O catálogo canônico precisa declarar tenant_id, versão, fingerprint
   verificado e padrões exclusivamente estruturais. Nenhuma semântica
   contábil pode ser inferida pelo programa.
4. A autoridade financeira independente deve emitir um recibo autenticado
   vinculando decisão, tenant, versão semântica, revisor, fingerprint,
   versão original, hash do plaintext e hash de todos os registros revisados.
   O verificador é HMAC-SHA256 do SHA-256 do JSON canônico de claims.
   A chave não deve ficar acessível ao autor do mapeamento.
   **O isolamento da autoridade é um controle externo e não é demonstrado
   apenas pela assinatura ou por um arquivo.**
5. O script scripts/operations/g5_financial_crosswalk_review_cli.py exige
   também --n8n-binding-evidence com o inventário privado fonte-vinculado
   da versão publicada. A versão selecionada do n8n, o manifest e seus
   row_counts precisam ser IDENTICOS; fontes de versões diferentes são
   rejeitadas. Valida tudo offline em modo somente leitura:
   ciphertext/seal, versão, 100% dos
   registros, destinos válidos, tenant, fingerprint, assinatura e arquivos
   privados (0600, diretório 0700). Retorna exclusivamente
   G5_FINANCIAL_MAPPING_CANDIDATE_NOT_ACTIVATED ou BLOCKED.
   Não ativa o catálogo, não muda banco, não autoriza execução nem cutover.

## Falhas bloqueantes

- Linha original ausente, duplicada ou inventada;
- classificação TRANSITIONAL/UNRESOLVED ou regra financeira sem destino;
- destino inexistente no contexto versionado;
- versão selecionada no n8n diferente da versão do pacote G5;
- versão, tenant, contexto ou pacote criptográfico divergente;
- SQL/benchmark no snapshot canônico;
- recibo de aprovação inexistente, alterado ou não autenticado;
- arquivo privado com permissão ampla ou symlink.

O resultado CANDIDATE_NOT_ACTIVATED não é aprovação operacional. Os
testes usam fontes e contextos sintéticos materialmente distintos, incluindo
77 linhas de exemplo; não carregam nem aprovam 77 linhas reais G5.

## Critérios ainda abertos

A conclusão real do Bloco 1 depende de revisão contábil dos 77 registros
da versão ativa e dos registros relevantes das outras versões; vinculação
das regras aprovadas às capacidades do LangGraph; e prova de paridade
funcional e financeira sem injetar golden answers. Validação numérica
read-only exige autorização separada. SOURCE não é reativado.
OFFICIAL=n8n, SHADOW=LangGraph, LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false.
