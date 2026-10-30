# G5 semantic source recovery (2026-10-30)

Operator-verified offline recovery of source semantic catalogs: five collections, 1,381 rows, 11 versions per collection, no financial SQL executed. Physical lineage audit passed. Results are technical candidates, **not accounting approval or new context activation**.

- Rules: 318 records (315 active at snapshot, 3 inactive).
- DRE: 121 records with declared sign, not independently verified.
- Aliases: 738 records (257 with no physical target; 481 with unresolved columns, of which 381 have ambiguous physical table names and 100 have no physical name match).
- SQL patterns: 106, evaluation only, excluded from resolver/planner/generator.
- Physical catalog: 98 records (66 ambiguous physical table names; 10 no match; 22 table-name-only with primary-key columns present).

Evidence source: operator terminal output of `G5_LINEAGE_RESULT=PASS`, `G5_LINEAGE_RECORDS=1381`, `G5_LINEAGE_APPROVED=false`, `G5_LINEAGE_SQL_EXECUTED=false`.

Source remains inactive. All recovered artifacts remain on private VPS filesystems and MUST NOT enter this repository, tool output or prompt. Keep `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`. No migration, financial execution, production changes or cutover is authorized.