# Triagem da fonte publicada: 3.403 literais JS

**Escopo e limite:** 41/41 codigos JS do workflow publicado conferidos por SHA de corpo com baseline privado, 68 nos e 78 arestas conferidos. Inventario anterior: 3.403 ocorrencias; so 1.987 acima de 10 caracteres tinham hash/linha individuais. Outras 1.416 permanecem agregadas por no, NAO classificadas individualmente.

## Censo

- 3403 literais totais; 1987 entradas longas com linha/tipo/indice verificados contra corpo imutavel do n8n publicado.
- 1416 ocorrencias curtas ainda nao individualmente ancoradas.
- 1144 FORBIDDEN candidatos; 187 TRANSITIONAL; 424 STRUCTURAL; 232 indeterminados. Todos os 1.987 sao TRIAGEM AUTOMATICA por linha e familia de funcao, sem aprovacao contabil individual.
- JSON contem ordinal, indice de ocorrencia no inventario privado, linha, tipo e classe candidata, com hash da politica audit-only. Sem strings, hashes de valores, SQL ou prompts. Auditoria nao e conhecimento de runtime.

## Concentração por no

| No | Total | Longas ancoradas | Curtas pendentes | F cand. | T cand. | S cand. | Sem classe |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 58 | 11 | 47 | 1 | 0 | 10 | 0 |
| 3 | 2 | 2 | 0 | 0 | 0 | 2 | 0 |
| 6 | 256 | 175 | 81 | 172 | 0 | 0 | 3 |
| 7 | 34 | 14 | 20 | 5 | 0 | 9 | 0 |
| 8 | 13 | 8 | 5 | 1 | 0 | 0 | 7 |
| 9 | 28 | 20 | 8 | 1 | 0 | 19 | 0 |
| 11 | 161 | 80 | 81 | 57 | 0 | 0 | 23 |
| 12 | 155 | 90 | 65 | 20 | 0 | 70 | 0 |
| 13 | 73 | 47 | 26 | 1 | 0 | 46 | 0 |
| 15 | 206 | 124 | 82 | 49 | 75 | 0 | 0 |
| 17 | 18 | 11 | 7 | 0 | 11 | 0 | 0 |
| 19 | 233 | 114 | 119 | 44 | 70 | 0 | 0 |
| 20 | 7 | 2 | 5 | 0 | 2 | 0 | 0 |
| 22 | 726 | 509 | 217 | 416 | 0 | 0 | 93 |
| 23 | 24 | 17 | 7 | 16 | 0 | 0 | 1 |
| 24 | 204 | 148 | 56 | 81 | 0 | 67 | 0 |
| 26 | 14 | 8 | 6 | 0 | 0 | 8 | 0 |
| 28 | 137 | 70 | 67 | 10 | 0 | 60 | 0 |
| 30 | 24 | 16 | 8 | 2 | 0 | 14 | 0 |
| 31 | 5 | 2 | 3 | 0 | 0 | 2 | 0 |
| 32 | 495 | 260 | 235 | 192 | 0 | 0 | 68 |
| 33 | 6 | 4 | 2 | 0 | 0 | 4 | 0 |
| 34 | 17 | 7 | 10 | 1 | 0 | 6 | 0 |
| 38 | 7 | 4 | 3 | 0 | 0 | 4 | 0 |
| 39 | 3 | 3 | 0 | 0 | 0 | 3 | 0 |
| 40 | 2 | 2 | 0 | 0 | 0 | 2 | 0 |
| 43 | 3 | 3 | 0 | 0 | 0 | 3 | 0 |
| 44 | 13 | 6 | 7 | 0 | 0 | 6 | 0 |
| 47 | 3 | 3 | 0 | 0 | 0 | 3 | 0 |
| 50 | 4 | 4 | 0 | 0 | 0 | 4 | 0 |
| 52 | 21 | 5 | 16 | 0 | 0 | 5 | 0 |
| 53 | 15 | 7 | 8 | 0 | 7 | 0 | 0 |
| 54 | 241 | 111 | 130 | 74 | 0 | 0 | 37 |
| 55 | 48 | 23 | 25 | 0 | 0 | 23 | 0 |
| 57 | 28 | 15 | 13 | 0 | 0 | 15 | 0 |
| 59 | 25 | 10 | 15 | 0 | 0 | 10 | 0 |
| 60 | 21 | 9 | 12 | 0 | 0 | 9 | 0 |
| 61 | 25 | 13 | 12 | 1 | 0 | 12 | 0 |
| 64 | 34 | 22 | 12 | 0 | 22 | 0 | 0 |
| 65 | 10 | 6 | 4 | 0 | 0 | 6 | 0 |
| 68 | 4 | 2 | 2 | 0 | 0 | 2 | 0 |

## Contrato de seguranca e uso

- Nenhum literal, regra financeira ou resposta benchmark foi importado ao planejador, LLM ou LangGraph.
- F, T e S sao candidatos e podem ter falsos positivos/negativos. U nao possui evidencia suficiente nem para classificacao candidata. Antes de ativar, revisar significado e reconciliar com catalogo aprovado por tenant.
- F sinaliza risco de hardcode de negocio proibido NO CODIGO NOVO, nao uma regra contabil completa/validada.
- Corpus de 3.403 reconciliado com baseline anterior, mas a revisao individual esta incompleta: 1.416 sem ancora e 1.987 apenas triados automaticamente.
- Os 63 casos historicos, SQL e golden answers sao exclusivamente avaliacao offline posterior.

## Externalizacao

Contrato generico de composicoes, sinais, filtros, periodos e razao de somatorios ja e implementado. Comportamentos seguintes so podem ser migrados com mapeamento e significado externo aprovado, sem deduzir contas e filtros de hashes.

**Estado:** triagem automatica do corpus de literais longos concluida; certificacao contabil por literal e revisao dos curtos ABERTAS.
