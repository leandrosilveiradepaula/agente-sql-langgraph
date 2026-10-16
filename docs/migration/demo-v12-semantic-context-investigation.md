# V12 semantic context investigation — proposal, not activation

## Verified baseline

- Source: `demo-finance-v10`, fingerprint `6414f782ada30bebdaca423d327c8ff008d81f199f89918ed9c3b17d1c141a68`.
- V11 is an in-memory, metadata-only extension of v10 for temporal planning, not a promoted runtime version.
- Read-only temporal generalization suite: **7/12**, still **7/12** after structural PR #119.
- PR #120 added redacted correlation between candidates and catalog entries; no business logic changed.
- The evidence below comes from a read-only v10 context dump and the observed suite outputs. Scores and catalog indexes are normalized diagnostics, not expected answers.

| Case | Observed | Relevant semantic evidence | Investigation |
| --- | --- | --- | --- |
| 3 | No intent; 80/80 < 100 | catalog #2 budget_analysis and #5 trend | Determine if trimestral evolution is missing from the **trend** concept or its semantic operation; do not change threshold |
| 4 | realized_analysis 140; temporal guard rejects | #1 realized_analysis has realized_scenario + financial_metric + period_reference and auxiliary score; trend not dominant | Verify explicit longitudinal cues and scenario/operation precedence |
| 7 | No intent; 80 < 100 | #1 realized_analysis while ranking is not competitive | Check conjugations of ordering operations and dimension/metric evidence, with associated versioned operation metadata |
| 9 | Two eligible candidates, 120/120 | #4 ranking vs #1 realized_analysis | Verify whether realized_analysis should be excluded when an **explicit ranking** operation is present; examine adjacent paraphrases without ranking |
| 12 | realized_analysis 100; temporal guard rejects | #1 realized_analysis wins from realized_scenario + period_context, trend not dominant | Check month-by-month temporal series even with no explicit term "trend" |

## Findings from the real catalog

1. The v10 `realized_trend_operation_exclusion` is already declared, but the temporal concept must be satisfied for exclusion to apply. An unmatched lexical variant makes the scenario compete with the operation.
2. The ranking intent contains `ranking_operation_primary` and complement rules; the source alias list includes ranking, maior/maiores, menor/menores etc. Coverage of *ordenar/ordene/ordenados* has not been demonstrated.
3. Many `semantic_projection_auxiliary_*` rules appear across several intents and share financial_metric, analytical_operation, and dimension_grouping concepts. Their matched terms should be inspected before declaring any score contribution redundant.
4. There are no unsatisfied `require` rules in the five failing cases, so the observed failure is **evidence coverage / intent competition**, not missing require-rule eligibility.

## Design constraints for a candidate `demo-finance-v12`

- Do not alter v10 or v11; use a **new, explicitly versioned, in-memory candidate**, with separate fingerprint and reviewed diff.
- Put business terms/aliases, intent compatibility, exclusion semantics, and operation metadata **in the versioned context**, not in Python or n8n.
- Reuse an existing concept and its audited vocabulary when an exclusion references that concept. Avoid maintaining manually duplicated term lists that drift.
- If ranked ordering vocabulary is proposed, include corresponding `analytical_operation` configuration; a classifier result without usable operation binding is not success.
- Treat bare "monthly" or "quarterly" as **period/granularity**, never automatically as a trend. Trend requires a supported longitudinal operation signal. Test ordinary grouped monthly totals as a counterexample.
- Distinguish time reference from time granularity; both can occur independently, and ambiguous references must continue to reject.
- Avoid changes to `minimum_score`, `ambiguity_margin`, golden answers, query-specific SQL, or benchmark data.
- Preserve generated SQL approval, reapproval for any repair, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`, and n8n OFFICIAL.

## Gates before producing or persisting an actual v12 delta

1. Inspect **configured terms, match modes, and priorities** from the v10 `trend_primary`, `realized_trend_operation_exclusion`, `ranking_operation_primary`, and the matched `semantic_projection_auxiliary_*` records. The existing dump contains rule names and concepts but not the terms.
2. Build a **candidate-only overlay** that extends an intent concept using audited vocabulary and alters no source rows; inspect the fingerprint and review each metadata delta independently.
3. Evaluate against new, *independently authored* pairs of positive and counterexample paraphrases: trend vs plain period grouping; ranking vs unranked realized; budget vs realized; posting_date vs accounting_period, with unseen lexical variations. Keep expected intents only in post-execution evaluation.
4. Rerun the 12-case suite for compatibility **after** testing the new generalization suite. Report both improvements and regressions, not only a pass count.
5. Check preflight, context validation, metadata parity, fail-closed temporal reference behavior, planner operation binding, and CI. No SQL execution, no LLM calls for this investigation.
6. A later v12 promotion or database migration requires distinct authorization and a separate release gate.

## Current disposition

The evidence supports a targeted review of versioned semantic vocabulary and exclusion compatibility, **not yet a proven candidate patch**. A term-level audit is the next dependency. No production or shadow context activation is authorized by this document.
