## RESULTADO CONFIRMADO — original recuperado em 13/11/2026

O operador executou o wrapper local no SSH; **G5_P3_CUSTODY=PASS**, 137 registros físicos P3 vinculados ao SHA da versão G5 ativa (77 registros semânticos). O arquivo P3 original agora existe em `/var/lib/agente-financeiro-mcp-admin/g5-financial-review-20261113/active-version-financial-review-private/p3-physical-metadata-original.json` como 0600/root. O bloqueio de custódia P3 deste documento já foi resolvido; os passos de recuperação abaixo ficam como referência histórica, **não executar novamente**.

Foi gerada matriz física privada de 48 referências em `g5-p3-original-physical-worklist.json` e `.html` (mesmo diretório 0700). Resultado: 32/40 nomes de coluna com um candidato literal, 8 sem nome correspondente, 6 nomes de tabela multi-schema, 8/8 schemas G5 ausentes fisicamente; nenhuma aprovação. Ver contrato `G5-P3-ORIGINAL-PHYSICAL-WORKLIST.md`. Gates pendentes são avaliação contábil 77/77, 48 decisões físicas assinadas, tenant/version/fingerprint aprovado e paridade. Nenhuma SQL financeira foi executada.

---

# Preservação do snapshot físico P3 original — sem importação financeira

**Estado: pendente de arquivo P3 original; nenhuma migração ou SQL financeira.**

A origem G5 publicada no n8n foi recuperada com 77 registros (18 regras,
40 aliases, 11 DRE, 8 catálogos). O `origin.p3_snapshot_sha256` existente no
pacote original coincide **exatamente** com os hashes P3 registrados em cinco
evidências locais independentes de armazenamento: pacote G5, inventário
semântico, lineage, hints de identificadores e manifesto cifrado do crosswalk
G5/P3. Isso comprova coerência da referência histórica, não demonstra que
um arquivo P3 íntegro esteja disponível hoje.

Um scan limitado às áreas autorizadas do serviço MCP e à árvore de projetos
verificou 1.535 arquivos candidatos sem encontrar o **arquivo de bytes
originais** com esse digest. O serviço MCP usa `PrivateTmp=yes`, portanto
sua visualização de `/tmp` é diferente do `/tmp` do terminal SSH do
operador. O caminho histórico gerado pelo auditor de 29/10/2026 era
`/tmp/p3-source-audit.7DIc9fUP/physical-metadata.json` — sua existência
atual no namespace SSH ainda não foi confirmada.

## Recuperação segura do artefato já capturado

O comando de custódia usa
`scripts/operations/g5_preserve_p3_custody_offline.py`; somente aceita um
arquivo P3 **existente**. Não executa coleta nova, SQL, n8n, LLM, restauração,
escrita de banco ou migração. Exige arquivos 0600 e diretórios 0700, confirma
o SHA original contra o G5 verificado, valida forma/escopo de metadados P3 e
salva os **mesmos bytes** em diretório 0700, arquivo exclusivo 0600. Nenhum
conteúdo financeiro ou identidade sensível vai para stdout ou GitHub.

Na sessão SSH root do operador, após o checkout deste commit estar presente
em diretório privado, executar apenas o `run-p3-original-custody.sh`
preparado no diretório persistente de administração. Este wrapper referencia
o caminho histórico e usa o SHA do pacote G5, sem expor o conteúdo. Retornos:

- `G5_P3_CUSTODY=PASS`: bytes originais preservados, metadados somente; NÃO
  significa significado contábil aprovado nem contexto ativado.
- `G5_P3_CUSTODY=BLOCKED`: arquivo ausente, diferente do SHA original,
  permissão insegura ou forma diferente do contrato. Não criar snapshot
  aproximado, não preencher manualmente nem inferir tabela/coluna.

## Gates posteriores que continuam obrigatórios

Após autenticar o arquivo P3 original, comparar fisicamente as 48 referências
(40 aliases + 8 catálogos): 46 aparecem como AMBIGUOUS_TABLE_NAME, 40 colunas
como COLUMN_UNRESOLVED. O verificador exige decisões explícitas e assinadas
para schema/tabela/coluna, tipos verificados e cobertura total dos 77
registros com homologação contábil independente. O pacote original NÃO é
entrada do planner/LLM, benchmark nem SQL real.

OFFICIAL=n8n+Gemini; SHADOW=n8n+LangGraph+Gemini;
`LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. Merge, produção, autorização
financeira, mudança de contexto ou cutover permanecem humanos.
