# Demo Finance v16: scoped negation and temporal vocabulary (candidate only)

Status: **unpromoted Shadow preview**. The official answer still comes from n8n.
No SQL generation/execution, LLM calls, benchmark access or context persistence
are required for the semantic overlay preflight.

## Evidence observed before this candidate

- v15 passed **75/84** post-resolution/planning checks, compared with
  **71/84** for v14, with zero regressions observed in these samples.
- Nine cases were not yet accepted; several lacked sufficient context score
  without an explicit financial metric. These must not be patched by lowering
  `minimum_score`.
- Independent new checks showed that an explicitly negated temporal operation
  could still select the `trend` intent; other cases lacked a period grain
  described as `anual` or expressed time series as `série mensal`.

## Structural capability

The intent resolver supports **optional** `negation_scope` in its already
versioned `intent_resolver` component configuration:

```json
{
  "negation_scope": {
    "cue_phrases": ["without", "without calculating"],
    "concept_names": ["synthetic_operation"],
    "max_gap_tokens": 1
  }
}
```

The example is synthetic. In a real context, the phrases, concept names and
distance are always external metadata. There is no business intent, scenario,
account, DRE, table or SQL encoded in the resolver itself.

The configured cues only affect concept terms occurring within a **short,
punctuation-bounded prefix scope**. If a configured concept has an explicitly
negated term, evaluation suppresses that concept across its positive scoring
and exclusion rules for this request, so a denied operation does not both earn
positive evidence and block the affirmative scenario.

This is intentionally conservative. Complex sentences that both negate and
then request the same concept in distinct clauses may require richer
compositional analysis later. The candidate must be evaluated against
affirmative and negative paraphrases to detect and reject regressions.

## Versioned changes

The v16 overlay inherits all prior virtual v15 changes and adds:

- safe year-grain terms (`anual`, `anuais`) in the temporal component;
- qualified time-series vocabulary in the semantic intent catalog;
- corresponding scenario exclusions mirrored from the same intent concept;
- a versioned policy for explicit operation negation, never a Python
  text-specific exception.

The new structural operation `configure_concept_negation` must match exactly
one versioned resolver config and cannot alter existing scores, mappings,
SQL patterns, DRE mappings, catalog, database permissions or other rules.

## Acceptance gates

1. Full offline CI including synthetic positive/negative cases, context
   validation and blocked real-SQL gate.
2. After a reviewed merge, compare virtual **v15 vs v16** via
   `scripts/compare_shadow_semantic_overlays_readonly.py` on all five existing
   suites **and** the independent v16 controls.
3. Check **per-case** regressions (not only totals). Explicit negation must not
   become a shortcut to a fixed intent or metric. Any unresolved question
   remains fail-closed.
4. Do not promote v16 or change the official n8n flow without a separate,
   explicit deployment decision. Do not run paid inference or formal benchmark
   63 as part of this candidate.
