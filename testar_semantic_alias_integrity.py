"""Safety regressions for tenant-agnostic semantic alias identity.

No external services, benchmark, historical SQL or company-specific rules.
"""
from __future__ import annotations

from copy import deepcopy

from app.domain.planner import (
    _grouping_terms_from_intent_evidence,
    _resolve_analytical_operation,
    _resolve_planned_metrics,
    build_query_plan,
    PlanningRejection,
)
from testar_planner import (
    _metric_context,
    _intent_metric_evidence,
    _intent_metric_operation_dimension_evidence,
    _append_metric_alias,
)


def _ambiguous_metric_context():
    context = _metric_context()
    _append_metric_alias(
        context,
        user_term="amount",
        canonical_value="second_measure",
        metric_concept="second_measure",
        target_table="schema_test.fact_metrics",
        target_column="volume_value",
    )
    return context


def _expect_rejection(fn, code):
    try:
        fn()
    except PlanningRejection as exc:
        assert exc.code == code, (exc.code, code)
    else:
        raise AssertionError("conflicting alias silently accepted")


def test_metric_alias_priority_never_chooses_different_physical_measures():
    context = _ambiguous_metric_context()
    for index, entity in enumerate(context["entities"]):
        if entity.get("entity_type") == "financial_metric" and entity.get("user_term") == "amount":
            entity["priority"] = 999 - index
    _expect_rejection(
        lambda: _resolve_planned_metrics(
            context=context,
            matched_user_term="amount",
            binding_context_concepts=[],
            cardinality={"mode": "single", "minimum": 1, "maximum": 1,
                         "same_metric_concept": True, "distinct_bindings": True},
        ),
        "PLANNING_METRIC_ALIAS_AMBIGUOUS",
    )
    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.96,
        normalized_question="highest amount",
        intent_resolution_result=_intent_metric_evidence(
            term="amount", operation_term="highest",
        ),
    )
    assert result["status"] == "rejected"
    assert result["error_code"] == "PLANNING_METRIC_ALIAS_AMBIGUOUS"
    assert result["query_plan"] is None


def test_equivalent_duplicate_metric_records_remain_idempotent():
    context = _metric_context()
    first = next(e for e in context["entities"] if
                 e.get("entity_type") == "financial_metric"
                 and e.get("user_term") == "amount")
    copy = deepcopy(first)
    copy["priority"] = 90
    context["entities"].append(copy)
    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.96,
        normalized_question="highest amount",
        intent_resolution_result=_intent_metric_evidence(
            term="amount", operation_term="highest",
        ),
    )
    assert result["status"] == "planned", result.get("error_code")
    assert len(result["query_plan"]["planning_context"]["planned_metrics"]) == 1


def test_conflicting_operation_alias_does_not_choose_by_priority():
    context = _metric_context()
    original = next(e for e in context["entities"]
                    if e.get("entity_type") == "analytical_operation"
                    and e.get("user_term") == "highest")
    alternate = deepcopy(original)
    alternate["business_rule"]["operation"]["direction"] = "ascending"
    alternate["priority"] = -100
    context["entities"].append(alternate)
    _expect_rejection(
        lambda: _resolve_analytical_operation(
            context["entities"], matched_user_term="highest",
        ),
        "PLANNING_OPERATION_ALIAS_AMBIGUOUS",
    )
    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.96,
        normalized_question="highest amount",
        intent_resolution_result=_intent_metric_evidence(
            term="amount", operation_term="highest",
        ),
    )
    assert result["status"] == "rejected"
    assert result["error_code"] == "PLANNING_OPERATION_ALIAS_AMBIGUOUS"
    assert result["query_plan"] is None


def test_equivalent_duplicate_operations_remain_usable():
    context = _metric_context()
    original = next(e for e in context["entities"]
                    if e.get("entity_type") == "analytical_operation"
                    and e.get("user_term") == "highest")
    alternate = deepcopy(original)
    alternate["priority"] = 99
    context["entities"].append(alternate)
    operation = _resolve_analytical_operation(
        context["entities"], matched_user_term="highest",
    )
    assert operation is not None
    assert operation["direction"] == "descending"


def test_grouping_cannot_read_foreign_best_candidate():
    evidence = _intent_metric_operation_dimension_evidence(
        metric_term="amount", operation_term="highest",
        dimension_term="by region", dimension_tokens=["by", "region"],
    )
    foreign = deepcopy(evidence["best_candidate"])
    foreign["intent_name"] = "foreign_intent"
    evidence["best_candidate"] = foreign
    evidence["intent"] = "generic_test_intent"
    assert _grouping_terms_from_intent_evidence(
        evidence, grouping_concepts=frozenset({"dimension_grouping"}),
    ) == []
    selected = deepcopy(foreign)
    selected["intent_name"] = "generic_test_intent"
    evidence["candidates"] = [selected]
    pairs = _grouping_terms_from_intent_evidence(
        evidence, grouping_concepts=frozenset({"dimension_grouping"}),
    )
    assert len(pairs) == 1


def test_alias_collision_fails_closed_across_unrelated_tenant_schemas():
    from testar_semantic_catalog_audit import _tenant

    for schema, table, measure in (
        ("finance_alpha", "ledger_entries", "net_flow"),
        ("finance_beta", "posting_records", "recognized_total"),
    ):
        context = _tenant(schema=schema, table=table, metric=measure)
        context["intent_resolution"]["config"]["concept_roles"] = {
            "metric": ["financial_metric"],
            "operation": ["analytical_operation"],
        }
        metric_alias = next(
            e["user_term"] for e in context["entities"]
            if e.get("entity_type") == "financial_metric"
        )
        metric_entries = [
            e for e in context["entities"]
            if e.get("entity_type") == "financial_metric"
            and e.get("user_term") != metric_alias
        ]
        assert metric_entries
        alternate = deepcopy(metric_entries[0])
        alternate["user_term"] = metric_alias
        alternate["priority"] = -50
        context["entities"].append(alternate)
        result = build_query_plan(
            context=context,
            intent_name="generic_test_intent",
            intent_confidence=0.96,
            normalized_question="highest " + metric_alias,
            intent_resolution_result=_intent_metric_evidence(
                term=metric_alias, operation_term="highest",
            ),
        )
        assert result["status"] == "rejected", result.get("status")
        assert result["error_code"] == "PLANNING_METRIC_ALIAS_AMBIGUOUS"
        assert result["query_plan"] is None


if __name__ == "__main__":
    tests = sorted(
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    )
    for name, fn in tests:
        fn()
        print("PASS " + name)
    print("SEMANTIC_ALIAS_INTEGRITY_TESTS=" + str(len(tests)))
