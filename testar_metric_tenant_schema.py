"""Tenant schema ACL is mandatory inside physical metric planning.

These tests use synthetic catalog contexts; no database, network, LLM, or
historical SQL. They enforce an independent runtime gate, beyond the static
catalog auditor and final SQL validator.
"""
from __future__ import annotations

from copy import deepcopy

from app.domain.planner import _resolve_planned_metrics, build_query_plan
from testar_planner import (
    _metric_context,
    _append_metric_binding,
    _intent_metric_evidence,
)
from testar_semantic_catalog_audit import _tenant


CARDINALITY = {
    "mode": "single",
    "minimum": 1,
    "maximum": 1,
    "same_metric_concept": True,
    "distinct_bindings": True,
}


def _metric_result(context: dict, term: str = "amount"):
    return _resolve_planned_metrics(
        context=context,
        matched_user_term=term,
        binding_context_concepts=[{"concept_name": "mode_a"}],
        cardinality=CARDINALITY,
    )


def _other_schema_table(context: dict, *, schema: str):
    source = next(
        table for table in context["table_catalog"]
        if table.get("table_name") == "fact_metrics"
    )
    foreign = deepcopy(source)
    foreign["schema_name"] = schema
    context["table_catalog"].append(foreign)


def test_direct_metric_is_rejected_when_schema_not_authorized():
    context = _metric_context()
    original, status, _ = _metric_result(context)
    assert status == "resolved" and len(original) == 1
    context["allowed_schemas"] = ["other_tenant"]
    metrics, status, _ = _metric_result(context)
    assert metrics == []
    assert status == "invalid_metadata"
    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.9,
        normalized_question="highest amount",
        intent_resolution_result=_intent_metric_evidence(
            term="amount", operation_term="highest",
        ),
    )
    assert result["status"] == "rejected"
    assert result["query_plan"] is None
    assert result["error_code"] == "PLANNING_METRIC_BINDING_INCOMPLETE"


def test_unauthorized_metric_binding_cannot_override_direct_alias():
    context = _metric_context()
    _other_schema_table(context, schema="tenant_outside")
    _append_metric_binding(
        context,
        target_table="tenant_outside.fact_metrics",
        when_present=["mode_a"],
    )
    metrics, status, detail = _metric_result(context)
    assert metrics == []
    assert status == "invalid_metadata"
    diagnostics = detail["binding_diagnostics"]
    assert any(
        item.get("reason") == "schema_not_authorized"
        for d in diagnostics for item in d.get("rejected", [])
    )
    assert all(d.get("applicable_count") == 0 for d in diagnostics)


def test_invalid_direct_alias_cannot_seed_valid_conditional_binding():
    context = _metric_context()
    _other_schema_table(context, schema="tenant_outside")
    for entity in context["entities"]:
        if entity.get("entity_type") == "financial_metric" and (
            entity.get("user_term") == "amount"
        ):
            entity["target_table"] = "tenant_outside.fact_metrics"
            entity["business_rule"]["metric"]["target_table"] = (
                "tenant_outside.fact_metrics"
            )
    _append_metric_binding(
        context,
        target_table="schema_test.fact_metrics",
        when_present=["mode_a"],
    )
    metrics, status, _ = _metric_result(context)
    assert metrics == []
    assert status == "invalid_metadata"


def test_conditional_binding_remains_usable_inside_authorized_schema():
    context = _metric_context()
    _append_metric_binding(
        context,
        target_table="schema_test.fact_metrics",
        when_present=["mode_a"],
    )
    metrics, status, detail = _metric_result(context)
    assert status == "resolved"
    assert len(metrics) == 1
    assert metrics[0]["mapping_source"] == "metric_binding"
    assert detail["binding_diagnostics"][0]["status"] == "resolved"


def test_missing_or_malformed_schema_allowlist_fails_closed():
    for malformed in (None, [], "schema_test", ["schema_test", None]):
        context = _metric_context()
        context["allowed_schemas"] = malformed
        metrics, status, _ = _metric_result(context)
        assert metrics == []
        assert status == "invalid_metadata"


def test_same_planner_portable_across_two_distinct_authorized_schemas():
    for schema, table, alias in (
        ("organization_a", "journal_lines", "gross_value"),
        ("organization_b", "payment_records", "net_value"),
    ):
        context = _tenant(schema=schema, table=table, metric=alias)
        metrics, status, _ = _metric_result(context, term=alias)
        assert status == "resolved"
        assert len(metrics) == 1
        assert metrics[0]["target_table"] == schema + "." + table
        context["allowed_schemas"] = ["another_organization"]
        metrics, status, _ = _metric_result(context, term=alias)
        assert metrics == [] and status == "invalid_metadata"



def test_partially_resolved_explicit_metric_is_not_silently_dropped():
    context = _metric_context()
    evidence = _intent_metric_evidence(
        term="amount", operation_term="highest",
    )
    # The strict no-partial-binding contract applies to optional semantic
    # interpretation, not to unchanged legacy deterministic snapshots.
    evidence["reason"] = "semantic_interpretation_selected"
    metric_concept = next(
        c for c in evidence["best_candidate"]["matches"][0][
            "match_details"
        ]["concepts"] if c.get("concept_name") == "financial_metric"
    )
    missing_term = deepcopy(metric_concept["terms"][0])
    missing_term["term"] = "unregistered_measure"
    missing_term["normalized_term"] = "unregistered_measure"
    details = missing_term.get("match_details")
    if isinstance(details, dict):
        signal = details.get("semantic_signal")
        if isinstance(signal, dict):
            signal["term"] = "unregistered_measure"
            signal["normalized_term"] = "unregistered_measure"
    metric_concept["terms"].append(missing_term)
    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.9,
        normalized_question="highest amount and unregistered_measure",
        intent_resolution_result=evidence,
    )
    assert result["status"] == "rejected"
    assert result["error_code"] == "PLANNING_METRIC_BINDING_INCOMPLETE"
    assert result["query_plan"] is None
    projection = result["projection"]
    assert projection["planned_metrics"]
    diagnostic = projection["diagnostics"]["planned_metric_diagnostic"]
    assert diagnostic["unresolved_terms"] == ["unregistered_measure"]


def test_legacy_planning_without_explicit_metric_stays_available():
    from testar_planner import _context

    result = build_query_plan(
        context=_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.9,
        normalized_question="generic analysis",
    )
    assert result["status"] == "planned"
    assert result["query_plan"] is not None


def test_valid_explicit_metric_plans_with_runtime_acl():
    context = _metric_context()
    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.9,
        normalized_question="highest amount",
        intent_resolution_result=_intent_metric_evidence(
            term="amount", operation_term="highest",
        ),
    )
    assert result["status"] == "planned", result.get("error_code")
    assert result["query_plan"]["planning_context"]["planned_metrics"]


if __name__ == "__main__":
    tests = sorted(
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    )
    for name, fn in tests:
        fn()
        print("PASS " + name)
    print("METRIC_TENANT_SCHEMA_TESTS=" + str(len(tests)))
