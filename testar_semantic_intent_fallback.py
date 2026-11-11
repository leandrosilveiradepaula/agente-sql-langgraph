"""Two materially different tenant contexts and negative safety cases.

Only synthetic metadata and a deterministic fake model are used.
No benchmark, network, provider call, financial SQL or database mutation.
"""
from __future__ import annotations

import json
from copy import deepcopy

from app.domain.semantic_intent_fallback import (
    SemanticIntentRejected,
    prepare_interpretation,
    validate_interpretation,
    versioned_policy,
)
from app.graph.nodes.semantic_classification import create_semantic_classification_node


def _context(intent: str, description: str, concept: str, *, schema: str) -> dict:
    return {
        "version": "tenant-context-v1",
        "fingerprint": "a" * 64 if schema == "ledger" else "b" * 64,
        "component_configs": {
            "semantic_intent_fallback": {
                "component": "semantic_intent_fallback",
                "enabled": True,
                "applied_confidence": 0.75,
            },
        },
        "query_patterns": [
            {"intent_name": intent, "required_tables": [schema + ".facts"]}
        ],
        "table_catalog": [
            {"schema_name": schema, "table_name": "facts",
             "metric_columns": ["amount"] if schema == "ledger" else ["quantity"]},
        ],
        "intent_resolution": {
            "config": {
                "component": "intent_resolver",
                "minimum_score": 100,
                "ambiguity_margin": 10,
                "applied_confidence": 0.9,
                "fallback_to_previous_intent": False,
                "token_fallback": {"enabled": False},
            },
            "signals": [],
            "intent_catalog": [{
                "intent_name": intent,
                "definition_name": "test-definition",
                "semantic_description": description,
                "rules": [
                    {"rule_name": "required-concept", "effect": "require",
                     "minimum_concept_matches": 1,
                     "concepts": [{
                         "concept_name": concept,
                         "terms": [concept],
                         "normalized_terms": [concept],
                         "match_mode": "contains",
                         "minimum_term_matches": 1,
                     }]},
                ],
            }],
            "semantic_defaults": {},
        },
    }


def _accepted(req: dict, intent: str, concept: str, span: str) -> str:
    return json.dumps({
        "status": "selected",
        "intent_name": intent,
        "context_fingerprint": req["context_fingerprint"],
        "bindings": [{"concept_name": concept, "question_span": span}],
    })


def test_independent_tenant_catalogs():
    contexts = (
        (_context("summarize_flow", "Summarize inflow", "inflow", schema="ledger"),
         "Give the inflow of this month", "summarize_flow", "inflow", "inflow"),
        (_context("inventory_projection", "Project inventory levels",
                  "forecast", schema="stockroom"),
         "Show projected stock holdings", "inventory_projection",
         "forecast", "projected"),
    )
    for context, question, intent, concept, span in contexts:
        policy = versioned_policy(context)
        assert policy is not None
        request = prepare_interpretation(question, context)
        assert "SELECT * FROM" not in repr(request).upper()
        assert "sql_pattern" not in repr(request)
        assert context["table_catalog"][0]["schema_name"] not in repr(request)
        result = validate_interpretation(
            _accepted(request, intent, concept, span),
            request,
            {"intent_catalog": {"evaluations": []}},
        )
        assert result["intent_name"] == intent
        assert result["bindings"][0]["question_span"] == span


def test_closed_without_opt_in():
    context = _context("intent_x", "An operation", "op", schema="ledger")
    del context["component_configs"]["semantic_intent_fallback"]
    assert versioned_policy(context) is None
    context["component_configs"]["semantic_intent_fallback"] = {
        "component": "semantic_intent_fallback",
        "enabled": False,
        "applied_confidence": 0.75,
    }
    assert versioned_policy(context) is None


def test_rejects_forged_intent_evidence_context_or_requirements():
    context = _context("intent_x", "An operation", "op", schema="ledger")
    request = prepare_interpretation("Display cash movements", context)
    good = json.loads(_accepted(request, "intent_x", "op", "cash"))
    variants = [
        {**good, "intent_name": "forged_intent"},
        {**good, "context_fingerprint": "0" * 64},
        {**good, "bindings": [{"concept_name": "forged_concept", "question_span": "cash"}]},
        {**good, "bindings": [{"concept_name": "op", "question_span": "unseen phrase"}]},
        {**good, "bindings": []},
        {**good, "status": "insufficient"},
        {**good, "bindings": [{"concept_name": "op", "question_span": "cash",
                              "target_table": "untrusted.facts"}]},
    ]
    for bad in variants:
        try:
            validate_interpretation(
                json.dumps(bad), request, {"intent_catalog": {"evaluations": []}}
            )
        except SemanticIntentRejected:
            continue
        raise AssertionError("forged interpretation accepted")


def test_deterministic_ambiguity_never_delegates_to_llm():
    from unittest.mock import patch
    context = _context("intent_x", "An operation", "op", schema="ledger")
    class NeverCall:
        def interpret(self, request):
            raise AssertionError("provider unexpectedly called")
    with patch("app.graph.nodes.semantic_classification.classify_intent", return_value={
        "final_status": "rejected",
        "intent_resolution_result": {"reason": "ambiguous_candidates"},
        "errors": [],
    }):
        result = create_semantic_classification_node(NeverCall())({
            "question": "any", "context": context,
        })
    assert result["final_status"] == "rejected"


def test_low_score_can_pass_with_grounding_but_not_skip_physical_planning():
    from unittest.mock import patch
    context = _context("intent_x", "An operation", "op", schema="ledger")
    class FakeModel:
        calls = 0
        def interpret(self, request):
            self.calls += 1
            return {"output_text": _accepted(request, "intent_x", "op", "cash"), "provider_name": "test_provider", "provider_model": "test_model", "token_usage": {"total_tokens": 13}}
    model = FakeModel()
    with patch("app.graph.nodes.semantic_classification.classify_intent", return_value={
        "final_status": "rejected",
        "intent_resolution_result": {
            "reason": "minimum_score_not_reached",
            "intent_catalog": {"evaluations": []},
        },
        "errors": [],
    }):
        result = create_semantic_classification_node(model)({
            "question": "Display cash movements", "context": context,
        })
    assert model.calls == 1
    assert result["final_status"] == "processing"
    assert result["intent"] == "intent_x"
    assert result["intent_resolution_result"]["best_candidate"]["matches"]
    assert "query_plan" not in result
    assert "generated_sql" not in result


def test_excluded_catalog_intent_cannot_be_reinstated():
    context = _context("intent_x", "An operation", "op", schema="ledger")
    request = prepare_interpretation("Display cash movements", context)
    with_deny = {"intent_catalog": {"evaluations": [
        {"intent_name": "intent_x", "eligible": False, "excluded": True}
    ]}}
    try:
        validate_interpretation(
            _accepted(request, "intent_x", "op", "cash"), request, with_deny,
        )
    except SemanticIntentRejected:
        return
    raise AssertionError("excluded intent incorrectly reinstated")


def test_real_resolver_low_score_can_use_grounded_catalog_without_threshold_change():
    """Exercises the actual deterministic node and optional semantic node."""
    context = _context("intent_x", "A generic operation", "op", schema="ledger")
    from app.domain.intent_resolver import resolve_intent
    deterministic = resolve_intent(
        "Display cash movements", context["intent_resolution"]
    )
    assert deterministic["reason"] == "minimum_score_not_reached"
    assert deterministic["applied"] is False
    assert deterministic["intent_catalog"]["evaluations"][0]["eligible"] is False

    class FakeModel:
        def interpret(self, request):
            return {
                "output_text": _accepted(
                    request, "intent_x", "op", "cash"
                ),
                "provider_name": "fake_provider",
                "provider_model": "fake_model",
                "token_usage": {"total_tokens": 8},
            }

    state = {
        "question": "Display cash movements",
        "normalized_question": "display cash movements",
        "context": context,
        "errors": [],
    }
    result = create_semantic_classification_node(FakeModel())(state)
    assert result["final_status"] == "processing"
    assert result["intent"] == "intent_x"
    assert result["semantic_interpretation_result"]["token_usage"]["total_tokens"] == 8
    assert result["semantic_interpretation_result"]["provider_model"] == "fake_model"
    assert result["intent_resolution_result"]["reason"] == "semantic_interpretation_selected"
    # The classifier does not create SQL, plan, execute privileges or approvals.
    assert "query_plan" not in result and "generated_sql" not in result


def test_explicit_llm_override_never_uses_unrelated_default_interpreter():
    context = _context("intent_x", "An operation", "op", schema="ledger")
    class NeverCall:
        def interpret(self, request):
            raise AssertionError("wrong model used")
    outcome = create_semantic_classification_node(NeverCall())({
        "question": "Display cash movements",
        "context": context,
        "llm_selection": {
            "provider_key": "another-provider",
            "model_key": "other-model",
            "config_version": "v2",
        },
    })
    assert outcome["final_status"] == "rejected"


def test_two_concepts_cannot_use_same_span_as_independent_evidence():
    context = _context("intent_x", "An operation", "op", schema="ledger")
    c = context["intent_resolution"]["intent_catalog"][0]["rules"][0]
    other = deepcopy(c["concepts"][0])
    other["concept_name"] = "different_concept"
    other["terms"] = ["different"]
    other["normalized_terms"] = ["different"]
    c["concepts"].append(other)
    request = prepare_interpretation("Cash movement detail", context)
    value = {
        "status": "selected", "intent_name": "intent_x",
        "context_fingerprint": request["context_fingerprint"],
        "bindings": [
            {"concept_name": "op", "question_span": "cash"},
            {"concept_name": "different_concept", "question_span": "cash"},
        ],
    }
    try:
        validate_interpretation(
            json.dumps(value), request, {"intent_catalog": {"evaluations": []}},
        )
    except SemanticIntentRejected:
        return
    raise AssertionError("conflicting evidence was accepted")
