# Negation-aware intent eligibility — unpromoted Shadow candidate v18

## Confirmed evidence (VPS on merged v17 evaluator)

v16 vs v17 on seven suites: 118/146 vs 125/146, +7, with zero
**same-engine** candidate regressions. However, the v16 candidate previously
passed 104/116 on the six earlier suites when evaluated with the pre-v17
code. Evaluated with the v17 code, v16 passed **102/116** on those exact
same suites (118 total minus 16 of 30 new cases). This is **cross-engine
behavior drift**, and the absence of candidate regressions is not proof
of engine backward compatibility.

The newest suite contains multiple cases in which the user expressly
denies an analytical operation, yet a different intent whose operation
was denied still collects scores from scenario/metric evidence and wins.
Some selected comparison intents planned with zero resolved metrics.
No real SQL was executed, and none of these outcomes certifies finance
correctness.

## Generalizable design

- Retain the v17 lexical negation matcher and concept-level scoring.
- Add a distinct, **opt-in eligibility gate**. It applies only when a
  versioned association of an intent and a concept exists, a lexical
  term belonging to that operation within a *positive or require* catalog
  rule was explicitly denied, **and no affirmative term in that same
  operation concept of that intent was matched**.
- The gate blocks eligibility even if unrelated scenario signals accumulated
  more than `minimum_score`. A requested comparison with affirmative
  operator remains allowed. Implicit multi-scenario analysis is not
  blocked in the absence of explicit denial.
- The new structural overlay operation `add_negation_intent_gate` selects
  already configured intent/concept metadata, validates that the concept
  belongs to a positive/required rule and to the opt-in negation policy,
  and modifies only the virtual resolver component configuration.
- This rule is **not** a workaround for a phrase, question, or benchmark.
  It is a general linguistic contradiction guard. The business-specific
  intent and concept association belongs exclusively to the versioned
  semantic overlay, never in Python.

## Testing and limitations

Offline synthetic tests test high scenario score with a denied operator,
the opposite with a genuinely affirmative operator, mixed-denial and
affirmation across clauses, implicit two-scenario meaning, unknown/duplicate
gate rejection, immutable source and Shadow SQL gate. Independent controls
are evaluation-only, not prompts, SQL examples, or lookup.

Real acceptance requires read-only virtual v17 vs v18 comparison across
**all seven previous suites plus the new 36-case independent suite** on a
single attested evaluator commit (182 checks each). Inspect per-case
regressions and do not promote on aggregate success alone.

The comparison CLI now emits `EVALUATOR_GIT_SHA` and a warning about
cross-engine comparability. A future comparison against an older engine
must run separately with the same snapshot, because its old results are
not reproduced by testing two candidate contexts on one newer codebase.

## Explicit non-goals

No new default metric, no lowering thresholds, no question-specific SQL,
no model/LLM calls, no stored benchmark evaluation injected into a
generator, no context promotion, no n8n replacement, no schema changes,
no SQL execution or privileged database write. n8n remains OFFICIAL and
LangGraph remains SHADOW.
