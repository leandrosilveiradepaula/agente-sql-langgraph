# Reconciliação de literais JavaScript do workflow n8n publicado — 12/11/2026

**Resultado confirmado por sintaxe:** o corpus de 41 nós Code do workflow publicado, idêntico ao baseline por SHA de corpo, possui **3.698 ocorrências de literais string e template** quando analisado pelo parser JavaScript Acorn 8.15.0. O censo anterior indicava 3.403, mas utilizava outra contagem. A diferença **+295 não pode ser ocultada nem somada às categorias antigas**. Foi conferido separadamente o crosswalk dos 68 nós e 78 arestas.

## Contagem nova e evidências

- **3.698/3.698** ocorrências sintáticas com posição inicial, linha, coluna, tipo e candidatura de classificação, sem valores nem hashes dos próprios valores publicados.
- **1.719** ocorrências com conteúdo estático de até 10 caracteres, **1.979** acima de 10. Essa separação AST NÃO é comparável diretamente aos 1.416/1.987 do heurístico antigo, por diferenças de tokenização, escape e template interpolado.
- **18 dos 41 nós** apresentam diferença de contagem entre métodos. A diferença líquida é +295; o maior desvio individual é o nó 23 (+219). Não inferir que todo desvio seja uma regra financeira.
- **Triagem automática nova, não homologação:** 1.732 candidatos FORBIDDEN, 371 TRANSITIONAL, 830 STRUCTURAL, 765 INDETERMINADOS. Nenhuma das classificações constitui aprovação do significado contábil de G5, nem identificação de fórmula financeira completa.
- A evidência imutável está em legacy-n8n-ast-all-literals-20261112.json.gz: código vinculado por SHA-256, posições e classes. Nenhum prompt, valor de string, token, corpo JS ou SQL do legado é publicado. O vocabulário de risco é isolado em legacy-n8n-review-signal-policy-v1.json como auditoria somente, nunca conhecimento do gerador.

## Reconciliação detalhada por nó Code

| Nó | Censo histórico | AST JavaScript | Diferença | Curtos AST | Longos AST | F cand. | T cand. | S cand. | U cand. |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 58 | 57 | -1 | 37 | 20 | 0 | 0 | 57 | 0 |
| 3 | 2 | 2 | +0 | 0 | 2 | 0 | 0 | 2 | 0 |
| 6 | 256 | 261 | +5 | 99 | 162 | 158 | 0 | 0 | 103 |
| 7 | 34 | 39 | +5 | 26 | 13 | 13 | 0 | 26 | 0 |
| 8 | 13 | 13 | +0 | 5 | 8 | 2 | 0 | 0 | 11 |
| 9 | 28 | 28 | +0 | 14 | 14 | 1 | 0 | 27 | 0 |
| 11 | 161 | 150 | -11 | 84 | 66 | 41 | 0 | 0 | 109 |
| 12 | 155 | 155 | +0 | 73 | 82 | 21 | 0 | 134 | 0 |
| 13 | 73 | 72 | -1 | 27 | 45 | 1 | 0 | 71 | 0 |
| 15 | 206 | 207 | +1 | 88 | 119 | 69 | 138 | 0 | 0 |
| 17 | 18 | 8 | -10 | 6 | 2 | 0 | 8 | 0 | 0 |
| 19 | 233 | 235 | +2 | 130 | 105 | 77 | 158 | 0 | 0 |
| 20 | 7 | 16 | +9 | 8 | 8 | 0 | 16 | 0 | 0 |
| 22 | 726 | 730 | +4 | 243 | 487 | 538 | 0 | 0 | 192 |
| 23 | 24 | 243 | +219 | 95 | 148 | 158 | 0 | 0 | 85 |
| 24 | 204 | 204 | +0 | 72 | 132 | 91 | 0 | 113 | 0 |
| 26 | 14 | 14 | +0 | 6 | 8 | 0 | 0 | 14 | 0 |
| 28 | 137 | 138 | +1 | 77 | 61 | 10 | 0 | 128 | 0 |
| 30 | 24 | 24 | +0 | 8 | 16 | 3 | 0 | 21 | 0 |
| 31 | 5 | 5 | +0 | 3 | 2 | 0 | 0 | 5 | 0 |
| 32 | 495 | 566 | +71 | 314 | 252 | 400 | 0 | 0 | 166 |
| 33 | 6 | 6 | +0 | 2 | 4 | 0 | 0 | 6 | 0 |
| 34 | 17 | 17 | +0 | 10 | 7 | 1 | 0 | 16 | 0 |
| 38 | 7 | 7 | +0 | 3 | 4 | 0 | 0 | 7 | 0 |
| 39 | 3 | 3 | +0 | 0 | 3 | 0 | 0 | 3 | 0 |
| 40 | 2 | 2 | +0 | 0 | 2 | 0 | 0 | 2 | 0 |
| 43 | 3 | 3 | +0 | 0 | 3 | 0 | 0 | 3 | 0 |
| 44 | 13 | 13 | +0 | 7 | 6 | 0 | 0 | 13 | 0 |
| 47 | 3 | 3 | +0 | 0 | 3 | 0 | 0 | 3 | 0 |
| 50 | 4 | 4 | +0 | 0 | 4 | 0 | 0 | 4 | 0 |
| 52 | 21 | 21 | +0 | 18 | 3 | 0 | 0 | 21 | 0 |
| 53 | 15 | 15 | +0 | 8 | 7 | 0 | 15 | 0 | 0 |
| 54 | 241 | 246 | +5 | 154 | 92 | 147 | 0 | 0 | 99 |
| 55 | 48 | 47 | -1 | 25 | 22 | 0 | 0 | 47 | 0 |
| 57 | 28 | 28 | +0 | 17 | 11 | 0 | 0 | 28 | 0 |
| 59 | 25 | 22 | -3 | 14 | 8 | 0 | 0 | 22 | 0 |
| 60 | 21 | 19 | -2 | 11 | 8 | 0 | 0 | 19 | 0 |
| 61 | 25 | 25 | +0 | 12 | 13 | 1 | 0 | 24 | 0 |
| 64 | 34 | 36 | +2 | 16 | 20 | 0 | 36 | 0 | 0 |
| 65 | 10 | 10 | +0 | 4 | 6 | 0 | 0 | 10 | 0 |
| 68 | 4 | 4 | +0 | 3 | 1 | 0 | 0 | 4 | 0 |

## Prova de origem sem execução

O auditor scripts/operations/legacy_js_ast_literal_audit.cjs foi executado numa cópia descartável da imagem n8n, sem rede, com parser Acorn instalado no próprio ambiente. Todos os corpos Code foram comparados com o checksum do inventário privado e o workflow foi validado previamente com o crosswalk 68/78. O auditor apenas faz parse da AST; NÃO avalia nem executa JavaScript dos nós, consultas, respostas, Gemini ou benchmark.

A ferramenta só retorna posições, ordinal, checksum do nó, comprimento em classe (curto/longo) e candidato a categoria. A política de classificação está em um JSON versionado de auditoria e nunca é exposta ao planejador ou LLM.

O teste CI testar_legacy_ast_literal_evidence.py rejeita mudanças nas contagens, posições, hashes de corpo, proveniência, classificações não reconhecidas e marcadores falsos de aprovação. A reexecução com fonte publicada exige acesso separado ao arquivo privado do workflow; CI não contém nem exige a cópia em claro.

## O que significa conclusão neste ponto

A localização sintática e a triagem **preliminar** de strings/templates dos 41 Code foram completadas com o parser independente, inclusive as ocorrências curtas antes agregadas. Não é correto afirmar que os 3.403 literais antigos foram todos classificados no mesmo esquema, nem que 3.698 regras de negócio existem. A revisão individual de efeito e a validação contábil G5 permanecem abertas; G5 cifrado não foi decodificado neste trabalho.

**Segurança:** OFFICIAL=n8n; SHADOW=LangGraph; LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. Nenhum banco financeiro de cliente, benchmark, segredo, workflow oficial, privilégio ou cutover foi modificado. Não houve merge.
