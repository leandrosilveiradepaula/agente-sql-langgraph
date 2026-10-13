from __future__ import annotations

from unittest.mock import patch

from scripts.run_shadow_context_candidate_readonly import (
    evaluate_candidate,
    plan_expectation_failures,
)


def test_plan_expectations_check_metrics_and_operations() -> None:
    projection = {
        "planned_metrics": [{"metric_ref": "metric-1"}],
        "analytical_operations": [
            {"operation_type": "ranking", "metric_ref": "metric-1"}
        ],
    }
    assert plan_expectation_failures(
        projection,
        {
            "minimum_planned_metrics": 1,
            "operation_type": "ranking",
            "operation_metric_ref": True,
        },
    ) == []
    assert plan_expectation_failures(
        projection,
        {"minimum_planned_metrics": 2, "operation_type": "comparison"},
    ) == [
        "planned_metrics_below_minimum",
        "expected_operation_missing",
    ]


def test_candidate_evaluation_never_sends_expected_values_to_agent() -> None:
    fixture = {
        "question": "Synthetic question",
        "expected_intent": "synthetic_intent",
        "expected_plan": {
            "minimum_planned_metrics": 1,
        },
    }
    resolver = {
        "applied": True,
        "intent": "synthetic_intent",
        "intent_confidence": 0.9,
        "normalized_question": "synthetic question",
    }
    planner_result = {
        "status": "planned",
        "error_code": None,
        "projection": {
            "planned_metrics": [{"metric_ref": "metric-synth"}],
            "analytical_operations": [],
            "diagnostics": {
                "temporal_diagnostic": {
                    "required": False, "status": "not_applicable"
                }
            },
        },
    }
    with patch(
        "scripts.run_shadow_context_candidate_readonly.resolve_intent",
        return_value=resolver,
    ) as intent_call, patch(
        "scripts.run_shadow_context_candidate_readonly.build_query_plan",
        return_value=planner_result,
    ) as planner_call:
        semantic_count, planned_count = evaluate_candidate(
            {"intent_resolution": {}}, [fixture]
        )

    assert (semantic_count, planned_count) == (1, 1)
    assert intent_call.call_args.args[0] == "Synthetic question"
    planner_kwargs = planner_call.call_args.kwargs
    assert planner_kwargs["normalized_question"] == "synthetic question"
    assert "expected_intent" not in str(planner_call.call_args)
    assert "minimum_planned_metrics" not in str(planner_call.call_args)


def test_candidate_evaluation_reports_planning_rejection() -> None:
    fixture = {
        "question": "Another question",
        "expected_intent": "synthetic_intent",
    }
    with patch(
        "scripts.run_shadow_context_candidate_readonly.resolve_intent",
        return_value={
            "applied": True,
            "intent": "synthetic_intent",
            "intent_confidence": 0.95,
            "normalized_question": "another question",
        },
    ), patch(
        "scripts.run_shadow_context_candidate_readonly.build_query_plan",
        return_value={
            "status": "rejected",
            "error_code": "PLANNING_TEMPORAL_BINDING_INCOMPLETE",
            "projection": None,
        },
    ):
        assert evaluate_candidate({"intent_resolution": {}}, [fixture]) == (1, 0)


if __name__ == "__main__":
    tests = [
        test_plan_expectations_check_metrics_and_operations,
        test_candidate_evaluation_never_sends_expected_values_to_agent,
        test_candidate_evaluation_reports_planning_rejection,
    ]
    for test in tests:
        test()
        print("TEST:", test.__name__, "PASS")
