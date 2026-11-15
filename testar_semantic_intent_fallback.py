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


def _accepted(
    req: dict, intent: str, concept: str, span: str,
    *, catalog_term: str | None = None,
) -> str:
    target = next(entry for entry in req["allowed_intents"]
                  if entry["intent_name"] == intent)
    lexicon = next(item for item in target["concept_lexicon"]
                   if item["concept_name"] == concept)
    alias = catalog_term if catalog_term is not None else lexicon["terms"][0]
    return json.dumps({
        "status": "selected",
        "intent_name": intent,
        "context_fingerprint": req["context_fingerprint"],
        "bindings": [{
            "concept_name": concept, "question_span": span,
            "catalog_term": alias,
        }],
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
        {**good, "bindings": [{"concept_name": "forged_concept", "question_span": "cash", "catalog_term": "op"}]},
        {**good, "bindings": [{"concept_name": "op", "question_span": "unseen phrase", "catalog_term": "op"}]},
        {**good, "bindings": []},
        {**good, "status": "insufficient"},
        {**good, "bindings": [{"concept_name": "op", "question_span": "cash",
                              "catalog_term": "op", "target_table": "untrusted.facts"}]},
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
            {"concept_name": "op", "question_span": "cash", "catalog_term": "op"},
            {"concept_name": "different_concept", "question_span": "cash", "catalog_term": "different"},
        ],
    }
    try:
        validate_interpretation(
            json.dumps(value), request, {"intent_catalog": {"evaluations": []}},
        )
    except SemanticIntentRejected:
        return
    raise AssertionError("conflicting evidence was accepted")


def test_explicit_matching_model_uses_same_interpreter():
    context = _context("intent_x", "An operation", "op", schema="ledger")
    identity = {"provider_key": "private", "model_key": "model-x", "config_version": "cfg-1"}
    class Model:
        def __init__(self):
            self.calls = 0
        def interpret(self, request):
            self.calls += 1
            return {
                "output_text": _accepted(request, "intent_x", "op", "cash"),
                "provider_name": "private",
                "provider_model": "model-x",
                "token_usage": {"prompt_tokens": 3, "total_tokens": 5},
            }
    model = Model()
    output = create_semantic_classification_node(
        model, interpreter_identity=identity,
    )({
        "question": "Display cash movements", "context": context,
        "llm_selection": dict(identity),
    })
    assert output["final_status"] == "processing"
    assert model.calls == 1
    assert output["intent"] == "intent_x"


def test_explicit_model_mismatch_blocks_request_before_call():
    context = _context("intent_x", "An operation", "op", schema="ledger")
    identity = {"provider_key": "private", "model_key": "model-x", "config_version": "cfg-1"}
    class Model:
        calls = 0
        def interpret(self, request):
            self.calls += 1
            raise AssertionError("mismatched model was called")
    model = Model()
    for item in (
        {**identity, "config_version": "cfg-2"},
        {**identity, "provider_key": "another"},
        {**identity, "model_key": "different"},
    ):
        outcome = create_semantic_classification_node(
            model, interpreter_identity=identity,
        )({
            "question": "Display cash movements", "context": context,
            "llm_selection": item,
        })
        assert outcome["final_status"] == "rejected"
    assert model.calls == 0


def test_gemini_adapter_serializes_semantic_context_only():
    from app.integrations.google_gemini.configuration import GoogleGeminiConfiguration
    from app.integrations.google_gemini.semantic_intent_interpreter import GeminiSemanticIntentInterpreter
    context = _context("intent_x", "An operation", "op", schema="ledger")
    request = prepare_interpretation("Display cash movements", context)
    class GeminiFake:
        def generate_content(self, request, *, payload_builder):
            payload = json.loads(payload_builder(
                request=request,
                configuration=GoogleGeminiConfiguration(model_id="test-model"),
            ))
            prompt = json.loads(payload["contents"][0]["parts"][0]["text"])
            assert prompt["contract_version"] == "semantic-intent-v3"
            assert "table_catalog" not in prompt
            assert "official_sql" not in prompt
            assert prompt["allowed_intents"][0]["intent_name"] == "intent_x"
            return {"status": "success", "output_text": _accepted(
                request, "intent_x", "op", "cash"
            ), "token_usage": {"prompt_tokens": 3, "total_tokens": 7}}
    adapter = GeminiSemanticIntentInterpreter(
        client=GeminiFake(), configuration=GoogleGeminiConfiguration(model_id="test-model"),
    )
    result = adapter.interpret(request)
    assert result["provider_model"] == "test-model"
    assert result["token_usage"]["total_tokens"] == 7


def test_gemini_adapter_refuses_provider_failure():
    from app.integrations.google_gemini.configuration import GoogleGeminiConfiguration
    from app.integrations.google_gemini.semantic_intent_interpreter import GeminiSemanticIntentInterpreter
    class Failing:
        def generate_content(self, request, *, payload_builder):
            return {"status": "provider_unavailable"}
    adapter = GeminiSemanticIntentInterpreter(
        client=Failing(), configuration=GoogleGeminiConfiguration(),
    )
    try:
        adapter.interpret({"contract_version": "semantic-intent-v3"})
    except RuntimeError:
        return
    raise AssertionError("Gemini infrastructure failure was silently accepted")


def test_selected_interpretation_clears_transient_deterministic_error():
    """A successful grounded fallback must not keep the prior rejection."""
    from app.graph.nodes.classify_intent import classify_intent
    context = _context("intent_x", "An operation", "op", schema="ledger")
    state = {
        "question": "Display cash movements",
        "context": context,
        "errors": [],
    }
    initial = classify_intent(state)
    assert initial["final_status"] == "rejected"
    assert initial["errors"][0]["code"] == "INTENT_RESOLUTION_MINIMUM_SCORE_NOT_REACHED"

    class Fake:
        def interpret(self, request):
            return {
                "output_text": _accepted(request, "intent_x", "op", "cash"),
                "provider_name": "test",
                "provider_model": "test",
                "token_usage": {},
            }

    accepted = create_semantic_classification_node(Fake())(state)
    assert accepted["final_status"] == "processing"
    assert accepted["errors"] == []

    preceding = {
        **state,
        "errors": [{"code": "PREEXISTING", "stage": "receive_question"}],
    }
    accepted_with_previous = create_semantic_classification_node(Fake())(preceding)
    assert accepted_with_previous["errors"] == preceding["errors"]



def test_oversized_tenant_catalog_fails_closed_before_provider():
    """A large tenant catalog is rejected, never silently truncated."""
    context = _context("intent_x", "A generic operation", "op", schema="ledger")
    original = context["intent_resolution"]["intent_catalog"][0]
    context["query_patterns"] = []
    context["intent_resolution"]["intent_catalog"] = []
    for index in range(60):
        intent = "operation_" + str(index)
        context["query_patterns"].append({"intent_name": intent})
        entry = deepcopy(original)
        entry["intent_name"] = intent
        entry["semantic_description"] = "z" * 1500
        context["intent_resolution"]["intent_catalog"].append(entry)
    try:
        prepare_interpretation("generic question", context)
    except SemanticIntentRejected as exc:
        assert str(exc) == "semantic_prompt_too_large"
        return
    raise AssertionError("unbounded semantic catalog was accepted")



def test_catalog_alias_is_independent_of_user_quote_and_protected_from_forgery():
    context = _context("intent_x", "Rank metric", "action", schema="ledger")
    request = prepare_interpretation("Top income", context)
    output = _accepted(
        request, "intent_x", "action", "Top", catalog_term="action",
    )
    accepted = validate_interpretation(
        output, request, {"intent_catalog": {"evaluations": []}},
    )
    assert accepted["bindings"][0] == {
        "concept_name": "action", "question_span": "Top",
        "catalog_term": "action",
    }
    for forged in ("forged_metric", "incoming", "", "action OR 1=1"):
        wrong = json.loads(output)
        wrong["bindings"][0]["catalog_term"] = forged
        try:
            validate_interpretation(
                json.dumps(wrong), request,
                {"intent_catalog": {"evaluations": []}},
            )
        except SemanticIntentRejected:
            continue
        raise AssertionError("forged catalog alias was accepted")


def test_end_to_end_semantic_alias_reaches_authorized_planner_bindings():
    from testar_planner import _metric_context
    from app.graph.nodes.build_plan import build_plan
    from app.domain.intent_resolver import resolve_intent

    context = _metric_context()
    context["component_configs"]["semantic_intent_fallback"] = {
        "component": "semantic_intent_fallback", "enabled": True,
        "applied_confidence": 0.75,
    }
    context["intent_resolution"] = deepcopy(
        _context("generic_test_intent", "Rank metric", "analytical_operation",
                 schema="ledger")["intent_resolution"]
    )
    rules = context["intent_resolution"]["intent_catalog"][0]["rules"]
    first = rules[0]["concepts"][0]
    first["terms"] = ["highest"]
    first["normalized_terms"] = ["highest"]
    metric = deepcopy(first)
    metric["concept_name"] = "financial_metric"
    metric["terms"] = ["amount"]
    metric["normalized_terms"] = ["amount"]
    rules[0]["concepts"].append(metric)
    rules[0]["minimum_concept_matches"] = 2
    # The role-to-concept association belongs to the tenant's versioned
    # context, never to a conditional in the SQL or interpreter engine.
    context["intent_resolution"]["config"]["concept_roles"] = {
        "operation": ["analytical_operation"],
        "metric": ["financial_metric"],
    }
    question = "Top amount"
    assert resolve_intent(question, context["intent_resolution"])["applied"] is False

    class FakeModel:
        def interpret(self, request):
            return {
                "output_text": json.dumps({
                    "status": "selected",
                    "intent_name": "generic_test_intent",
                    "context_fingerprint": request["context_fingerprint"],
                    "bindings": [
                        {"concept_name": "analytical_operation",
                         "question_span": "Top", "catalog_term": "highest"},
                        {"concept_name": "financial_metric",
                         "question_span": "amount", "catalog_term": "amount"},
                    ],
                }),
                "provider_name": "fake", "provider_model": "fake",
                "token_usage": {},
            }

    state = {
        "question": question,
        "normalized_question": question.lower(),
        "context": context,
        "errors": [],
    }
    classified = create_semantic_classification_node(FakeModel())(state)
    assert classified["final_status"] == "processing"
    evidence = classified["intent_resolution_result"]["best_candidate"]
    signals = [
        x["semantic_signals"][0]
        for x in evidence["matches"][0]["match_details"]["concepts"]
    ]
    assert [x["normalized_term"] for x in signals] == ["highest", "amount"]
    assert signals[0]["question_span"] == "Top"
    planned = build_plan({**state, **classified})
    assert planned["final_status"] == "processing", planned.get("errors")
    projection = planned["query_plan"]["planning_context"]
    assert [m["matched_user_term"] for m in projection["planned_metrics"]] == ["amount"]
    assert [op["matched_user_term"] for op in projection["analytical_operations"]] == ["highest"]
    assert projection["analytical_operations"][0]["operation_type"] == "ranking"



def _physical_metric_context(*, include_unbacked: bool = True):
    from testar_planner import _metric_context

    physical = _metric_context()
    context = _context(
        "portable_intent", "Interpret one authorized metric",
        "metric_signal", schema="ledger",
    )
    context["entities"] = deepcopy(physical["entities"])
    context["table_catalog"] = deepcopy(physical["table_catalog"])
    context["allowed_schemas"] = deepcopy(physical["allowed_schemas"])
    context["query_patterns"][0]["required_tables"] = [
        "schema_test.fact_metrics",
    ]
    context["intent_resolution"]["config"]["concept_roles"] = {
        "metric": ["metric_signal"],
    }
    terms = ["amount"]
    if include_unbacked:
        terms.append("unmapped_business_phrase")
    rule = context["intent_resolution"]["intent_catalog"][0]["rules"][0]
    rule["concepts"][0]["terms"] = terms
    rule["concepts"][0]["normalized_terms"] = terms
    return context


def test_pre_provider_lexicon_excludes_unbound_financial_synonyms():
    context = _physical_metric_context()
    request = prepare_interpretation(
        "How much amount is active", context,
    )
    allowed = request["allowed_intents"][0]["concept_lexicon"][0]["terms"]
    assert allowed == ["amount"]
    assert "unmapped_business_phrase" not in repr(request)
    assert "schema_test" not in repr(request)
    assert "fact_metrics" not in repr(request)
    good = _accepted(
        request, "portable_intent", "metric_signal",
        "amount", catalog_term="amount",
    )
    result = validate_interpretation(
        good, request, {"intent_catalog": {"evaluations": []}},
    )
    assert result["bindings"][0]["catalog_term"] == "amount"
    forged = json.loads(good)
    forged["bindings"][0]["catalog_term"] = "unmapped_business_phrase"
    try:
        validate_interpretation(
            json.dumps(forged), request,
            {"intent_catalog": {"evaluations": []}},
        )
    except SemanticIntentRejected as exc:
        assert str(exc) == "provider_catalog_term_not_authorized"
    else:
        raise AssertionError("nonphysical metric alias reached the planner")


def test_unbound_required_metric_role_blocks_before_provider_call():
    from unittest.mock import patch

    context = _physical_metric_context(include_unbacked=False)
    concept = context["intent_resolution"]["intent_catalog"][0]["rules"][0]["concepts"][0]
    concept["terms"] = ["not_in_physical_catalog"]
    concept["normalized_terms"] = ["not_in_physical_catalog"]
    try:
        prepare_interpretation("Show the metric", context)
    except SemanticIntentRejected as exc:
        assert str(exc) == "catalog_no_grounded_intents"
    else:
        raise AssertionError("unplannable catalog offered to model")

    class NeverCall:
        def interpret(self, request):
            raise AssertionError("model must not see ungrounded catalog")
    with patch(
        "app.graph.nodes.semantic_classification.classify_intent",
        return_value={
            "final_status": "rejected",
            "intent_resolution_result": {
                "reason": "minimum_score_not_reached",
                "intent_catalog": {"evaluations": []},
            },
            "errors": [],
        },
    ):
        result = create_semantic_classification_node(NeverCall())({
            "question": "Show the metric", "context": context,
            "errors": [],
        })
    assert result["final_status"] == "rejected"


def test_conflicting_physical_metrics_are_not_llm_catalog_aliases():
    from testar_planner import _append_metric_alias

    context = _physical_metric_context(include_unbacked=False)
    _append_metric_alias(
        context, user_term="amount", canonical_value="second_measure",
        metric_concept="second_measure",
        target_table="schema_test.fact_metrics",
        target_column="volume_value",
    )
    try:
        prepare_interpretation("How much", context)
    except SemanticIntentRejected as exc:
        assert str(exc) == "catalog_no_grounded_intents"
    else:
        raise AssertionError("ambiguous physical metric was offered to model")


def test_two_physically_different_clients_use_same_pre_provider_guard():
    from testar_planner import _metric_context

    for schema, table, alias in (
        ("company_alpha", "journal_entries", "net_flow"),
        ("company_beta", "operational_events", "settled_volume"),
    ):
        context = _physical_metric_context()
        def replace(value):
            if isinstance(value, dict):
                return {key: replace(child) for key, child in value.items()}
            if isinstance(value, list):
                return [replace(item) for item in value]
            if isinstance(value, str):
                return (value.replace("schema_test", schema)
                        .replace("fact_metrics", table)
                        .replace("amount", alias))
            return value
        context = replace(context)
        request = prepare_interpretation("Compute unfamiliar measure", context)
        assert request["allowed_intents"][0]["concept_lexicon"][0]["terms"] == [
            alias,
        ]
        assert schema not in repr(request)
        assert table not in repr(request)
        assert "unmapped_business_phrase" not in repr(request)


def test_missing_physical_catalog_refuses_metric_only_llm_request():
    context = _physical_metric_context()
    context["table_catalog"] = []
    try:
        prepare_interpretation("Metric value", context)
    except SemanticIntentRejected as exc:
        assert str(exc) == "catalog_no_grounded_intents"
    else:
        raise AssertionError("unknown metric table was considered authorized")


def test_invalid_structural_role_configuration_refuses_before_model():
    context = _physical_metric_context()
    for invalid in (
        {"metric": "metric_signal"},
        {"metric": ["metric_signal", "metric_signal"]},
        {"client_specific_rule": ["metric_signal"]},
    ):
        context["intent_resolution"]["config"]["concept_roles"] = invalid
        try:
            prepare_interpretation("Give authorized metric", context)
        except SemanticIntentRejected as exc:
            assert str(exc) == "semantic_role_config_invalid"
        else:
            raise AssertionError("invalid structural role was tolerated")



def test_unplannable_intent_does_not_disable_other_authorized_intents():
    context = _physical_metric_context(include_unbacked=False)
    second = deepcopy(context["intent_resolution"]["intent_catalog"][0])
    second["intent_name"] = "unplannable_intent"
    second["semantic_description"] = "A distinct candidate without metrics"
    for concept in second["rules"][0]["concepts"]:
        concept["terms"] = ["not_a_metric"]
        concept["normalized_terms"] = ["not_a_metric"]
    context["intent_resolution"]["intent_catalog"].append(second)
    context["query_patterns"].append({
        "intent_name": "unplannable_intent",
        "required_tables": ["schema_test.fact_metrics"],
    })
    request = prepare_interpretation("Summarize a known measure", context)
    assert [x["intent_name"] for x in request["allowed_intents"]] == [
        "portable_intent"
    ]
    assert "unplannable_intent" not in repr(request)


def test_analytical_operation_requires_real_metadata_before_provider():
    context = _physical_metric_context(include_unbacked=False)
    concept = {
        "concept_name": "operation_signal",
        "terms": ["highest", "invented_sort_direction"],
        "normalized_terms": ["highest", "invented_sort_direction"],
        "match_mode": "contains",
        "minimum_term_matches": 1,
    }
    rule = context["intent_resolution"]["intent_catalog"][0]["rules"][0]
    rule["concepts"].append(concept)
    rule["minimum_concept_matches"] = 2
    context["intent_resolution"]["config"]["concept_roles"][
        "operation"
    ] = ["operation_signal"]
    request = prepare_interpretation("Which entries rank highest", context)
    lexicon = {
        x["concept_name"]: x["terms"]
        for x in request["allowed_intents"][0]["concept_lexicon"]
    }
    assert lexicon["operation_signal"] == ["highest"]
    assert lexicon["metric_signal"] == ["amount"]
    assert "invented_sort_direction" not in repr(request)

    # A second, physically conflicting definition under the same alias
    # cannot be disambiguated by metadata priority or by the model.
    alternate = next(
        e for e in context["entities"]
        if e.get("entity_type") == "analytical_operation"
        and e.get("user_term") == "highest"
    )
    conflicting = deepcopy(alternate)
    conflicting["business_rule"]["operation"]["direction"] = "ascending"
    context["entities"].append(conflicting)
    try:
        prepare_interpretation("Which entries rank highest", context)
    except SemanticIntentRejected as exc:
        assert str(exc) == "catalog_no_grounded_intents"
    else:
        raise AssertionError("conflicting operation alias offered to model")




def test_schema_not_authorized_for_tenant_never_reaches_model():
    context = _physical_metric_context(include_unbacked=False)
    context["allowed_schemas"] = ["not_the_metric_schema"]
    try:
        prepare_interpretation("How much is available", context)
    except SemanticIntentRejected as exc:
        assert str(exc) == "catalog_no_grounded_intents"
    else:
        raise AssertionError("unauthorized schema exposed via metric grounding")


def test_same_semantic_concept_cannot_have_two_structural_roles():
    context = _physical_metric_context(include_unbacked=False)
    context["intent_resolution"]["config"]["concept_roles"] = {
        "metric": ["metric_signal"],
        "operation": ["METRIC_SIGNAL"],
    }
    try:
        prepare_interpretation("How much is available", context)
    except SemanticIntentRejected as exc:
        assert str(exc) == "semantic_role_config_invalid"
    else:
        raise AssertionError("overlapping roles accepted before provider")



def test_unmapped_metric_phrase_cannot_be_assigned_accounting_meaning():
    context = _physical_metric_context(include_unbacked=False)
    request = prepare_interpretation(
        "Show portfolio liquidity", context,
    )
    value = _accepted(
        request, "portable_intent", "metric_signal",
        "liquidity", catalog_term="amount",
    )
    try:
        validate_interpretation(
            value, request, {"intent_catalog": {"evaluations": []}},
        )
    except SemanticIntentRejected as exc:
        assert str(exc) == "provider_metric_alias_unverified"
    else:
        raise AssertionError("unmapped business phrase silently became a metric")

    authorized = prepare_interpretation("Show amount", context)
    good = _accepted(
        authorized, "portable_intent", "metric_signal",
        "amount", catalog_term="amount",
    )
    result = validate_interpretation(
        good, authorized, {"intent_catalog": {"evaluations": []}},
    )
    assert result["bindings"][0]["catalog_term"] == "amount"


def test_metric_evidence_policy_is_scoped_to_metric_role_only():
    context = _context("intent_x", "Describe an operation", "op", schema="ledger")
    request = prepare_interpretation("Top entries", context)
    assert request["allowed_intents"][0]["literal_metric_concepts"] == []
    output = _accepted(
        request, "intent_x", "op",
        "Top", catalog_term="op",
    )
    accepted = validate_interpretation(
        output, request, {"intent_catalog": {"evaluations": []}},
    )
    assert accepted["bindings"][0]["question_span"] == "Top"


if __name__ == "__main__":
    # The repository uses explicit script entrypoints, not pytest discovery.
    # Ensure this module actually runs in scripts/check_all.py and CI.
    import inspect
    tests = sorted(
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and inspect.isfunction(fn)
        and fn.__module__ == __name__
    )
    if not tests:
        raise AssertionError("semantic_fallback_tests_missing")
    for name, test in tests:
        test()
        print("PASS " + name)
    print("SEMANTIC_FALLBACK_TESTS_PASS=" + str(len(tests)))
