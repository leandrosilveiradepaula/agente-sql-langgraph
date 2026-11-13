# Evidencia de hardcodes do n8n - fonte publicada

**Escopo:** 68 nos e 78 arestas verificados. Auditoria estatica SANITIZADA da versao publicada, sem valores, SQL, prompts, credenciais ou benchmark.

- Codigos JS indexados: 41/41.
- Pontos ancorados em linhas do codigo real: 24 em 10 nos, incluindo o PostgreSQL 5.
- Esses pontos NAO equivalem a uma revisao individual dos 3.403 literais: os sites remanescentes ainda nao sao classificados.
- Cada referencia tem ordinal, linha, SHA-256 de linha/janela, tipo de regra e destino generico, sem texto confidencial.

## Evidencia por fonte

| No | Linhas SHA-10 | Sites | Destinos de externalizacao |
|---:|---|---:|---|
| 5 | 7 (ec134a1a1a), 17 (ec134a1a1a), 27 (ec134a1a1a), 37 (ec134a1a1a), 47 (ec134a1a1a) | 5 | TENANT_VERSION_CONFIGURATION |
| 6 | 393 (68b720ac0f), 415 (24626982f9) | 2 | APPROVED_INTENT_CATALOG, APPROVED_METRIC_AND_ALIAS_CATALOG |
| 7 | 28 (3c887b1437), 41 (f2f54646c2) | 2 | EXCLUDE_HISTORICAL_SQL_FROM_GENERATOR |
| 8 | 588 (abb0ec6871), 649 (85d169c12b), 744 (1bb2b1f602) | 3 | APPROVED_METRIC_FORMULAS_AND_SIGN_RULES, APPROVED_RATIO_OF_SUMS_CONTEXT, APPROVED_TENANT_FINANCIAL_CATALOG |
| 15 | 10 (f9a3059fce) | 1 | TENANT_VERSION_CONFIGURATION |
| 19 | 41 (91ed6dc3fa) | 1 | CONFIGURABLE_LLM_PROVIDER |
| 22 | 853 (4c0093eda4), 1054 (1409b364ce), 1073 (8d84f8117c), 1105 (bcec001d5e), 2030 (e5da44b3de) | 5 | APPROVED_PHYSICAL_AND_JOIN_CATALOG, APPROVED_TENANT_FINANCIAL_CATALOG, GENERIC_PLANNER_AND_APPROVED_GRAIN_CATALOG, GENERIC_PLANNER_AND_APPROVED_METRIC_CATALOG |
| 23 | 378 (9b142a0d9e) | 1 | APPROVED_METRIC_CATALOG |
| 32 | 534 (37c232a9c2), 668 (4dae5bafb3) | 2 | APPROVED_REPORT_SEMANTICS |
| 54 | 110 (c9ee678331), 184 (3ba20e8223) | 2 | APPROVED_DIMENSION_AND_ALIAS_CATALOG, APPROVED_METRIC_AND_ALIAS_CATALOG |

## Tratamento de engenharia reversa

- STRUCTURAL: parsing, validacao, controlos, grao generico, conector, retorno e mecanismos de processo; permitidos no motor.
- TRANSITIONAL: versao fixa, compatibilidade de provider, cache e outros contratos herdados; documentar/parametrizar.
- FORBIDDEN: tabela, coluna, formula, DRE, orcamento, sinal, alias, conta, marca ou filtros de cliente hardcoded no motor; apenas em catalogo aprovado por tenant.
- Uma alegacao no contexto accounting_definition_attested=True NAO substitui aprovacao contabil da fonte original.

## Externalizacao FUNCIONAL neste bloco

- Opt-in versionado metric_source_compositions[].calculation com operacao ratio_of_sums, grupos de fontes numerador/denominador, sinais de fontes e escala configurados por tenant.
- Normalizacao + fingerprint do snapshot e validacao do plano antes de compilar SQL. Rejeitar fonte desconhecida/duplicada/omitida, escala incorreta ou formula SQL injetada.
- PostgreSQL calcula SUM de cada grupo antes de dividir, usando NULLIF para denominador zero, sem denominadores inventados. SqlContract verifica a SQL gerada contra o plano.
- Provas com duas estruturas sintéticas materialmente distintas. Nenhum mapeamento real dos 77 registros G5 cifrados foi usado ou inferido.

## Pendencias posteriores

- Revisar demais sites dos 41 codigos e validar regras financeiras por tenant. Esta e prova de origem de 24 pontos, NAO homologacao de todos os literais.
- Desbloquear e aprovar o contexto financeiro G5 em gate separado para usar semantica real, sem copiar o SQL de 63 benchmarks.
- Integracao oficial/Shadow Gemini e equivalencia financeira continuam etapas diferentes; nao assumir paridade pela prova de DSL.

**OFFICIAL=n8n; SHADOW=LangGraph; LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false. Sem deploy, alteracao n8n/DB, merge ou cutover.**
