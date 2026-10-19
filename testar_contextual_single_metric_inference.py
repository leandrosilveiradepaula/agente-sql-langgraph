from __future__ import annotations

"""Structural metric inference tests using synthetic versioned bindings only."""

from app.domain.planner import _detect_planned_metrics, build_query_plan
from testar_planner import (
    _append_metric_binding,
    _intent_operation_evidence,
    _metric_context,
)


def _plan_without_literal_metric(context: dict) -> dict:
    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="generic analytical request",
        intent_resolution_result=_intent_operation_evidence(term="generic request"),
    )
    assert result["projection"] is not None
    return result["projection"]


def test_single_metric_inferred_from_unique_configured_binding() -> None:
    context = _metric_context()
    _append_metric_binding(
        context,
        when_present=["generic_required_rule"],
    )
    projection = _plan_without_literal_metric(context)
    metrics = projection["planned_metrics"]
    diagnostic = projection["diagnostics"]["planned_metric_diagnostic"]
    assert len(metrics) == 1
    assert metrics[0]["metric_concept"] == "amount"
    assert metrics[0]["mapping_source"] == "metric_binding"
    assert metrics[0]["detection_source"] == "selected_pattern_context"
    assert diagnostic["metric_requested"] is False
    assert diagnostic["binding_inference"]["status"] == "resolved"
    assert diagnostic["global_binding_status"] == "resolved"


def test_single_metric_not_inferred_without_required_binding_context() -> None:
    context = _metric_context()
    _append_metric_binding(context, when_present=["unmatched_mode"])
    projection = _plan_without_literal_metric(context)
    diagnostic = projection["diagnostics"]["planned_metric_diagnostic"]
    assert projection["planned_metrics"] == []
    assert diagnostic["binding_inference"]["status"] == "not_applicable"


def test_single_metric_not_inferred_if_negated_context_is_present() -> None:
    context = _metric_context()
    _append_metric_binding(
        context,
        when_present=["generic_required_rule"],
        when_absent=["analytical_operation"],
    )
    projection = _plan_without_literal_metric(context)
    assert projection["planned_metrics"] == []
    assert projection["diagnostics"]["planned_metric_diagnostic"][
        "binding_inference"
    ]["status"] == "not_applicable"


def test_single_metric_ambiguous_concepts_fail_closed() -> None:
    context = _metric_context()
    _append_metric_binding(
        context,
        metric_concept="amount",
        target_column="measure_value",
        when_present=["generic_required_rule"],
        user_term="binding alpha",
    )
    _append_metric_binding(
        context,
        metric_concept="volume",
        target_column="volume_value",
        when_present=["generic_required_rule"],
        user_term="binding beta",
    )
    projection = _plan_without_literal_metric(context)
    diagnostic = projection["diagnostics"]["planned_metric_diagnostic"]
    assert projection["planned_metrics"] == []
    assert diagnostic["binding_inference"]["status"] == "ambiguous_metric_concept"


def test_no_implicit_metric_when_context_evidence_is_absent() -> None:
    context = _metric_context()
    _append_metric_binding(context, when_present=["mode_a"])
    metrics, diagnostic = _detect_planned_metrics(
        context=context,
        intent_resolution_result={"intent": "generic_test_intent", "candidates": []},
        selected_pattern={},
        normalized_question="generic request",
        dimension_terms=[],
    )
    assert metrics == []
    assert diagnostic["binding_inference"]["status"] == "not_applicable"


if __name__ == "__main__":
    test_single_metric_inferred_from_unique_configured_binding()
    test_single_metric_not_inferred_without_required_binding_context()
    test_single_metric_not_inferred_if_negated_context_is_present()
    test_single_metric_ambiguous_concepts_fail_closed()
    test_no_implicit_metric_when_context_evidence_is_absent()
    print("CONTEXTUAL_SINGLE_METRIC_INFERENCE=PASS")
