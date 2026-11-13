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
