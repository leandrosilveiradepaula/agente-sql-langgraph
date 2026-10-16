from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

from scripts.evaluate_memory_candidate_generalization_readonly import (
    evaluate_suite,
    main,
    observe_plan,
)
from testar_planner import _pattern, _synthetic_temporal_context


def mock_snapshot() -> dict:
    return {"intent_resolution": {"synthetic": "signals"}}


def mock_intent(question: str, context: dict) -> dict:
    assert isinstance(question, str)
    assert context == {"synthetic": "signals"}
    return {
        "applied": True,
        "intent": "synthetic_intent",
        "intent_confidence": 0.9,
        "normalized_question": question,
    }


def mock_plan(**kwargs) -> dict:
    assert set(kwargs) == {
        "context",
        "intent_name",
        "intent_confidence",
        "normalized_question",
        "intent_resolution_result",
    }
    assert kwargs["intent_name"] == "synthetic_intent"
    assert kwargs["normalized_question"] == "Test monthly totals"
    assert kwargs["context"] == mock_snapshot()
    return {
        "status": "rejected",
        "error_code": "PLANNING_TEMPORAL_REFERENCE_UNSUPPORTED",
        "projection": None,
    }


def test_expectations_never_enter_semantic_or_planner_calls() -> None:
    suite = {
        "cases": [{
            "question": "Test monthly totals",
            "expected_intent": "synthetic_intent",
            "expected_plan_status": "rejected",
            "expected_error_code": "PLANNING_TEMPORAL_REFERENCE_UNSUPPORTED",
        }],
    }
    snapshot = mock_snapshot()
    before = deepcopy(suite)
    with patch(
        "scripts.evaluate_memory_candidate_generalization_readonly.resolve_intent",
        side_effect=mock_intent,
    ) as intent, patch(
        "scripts.evaluate_memory_candidate_generalization_readonly.build_query_plan",
        side_effect=mock_plan,
    ) as planner:
        result = evaluate_suite(snapshot, suite)
    assert intent.call_count == planner.call_count == 1
    assert suite == before
    assert result["status"] == "evaluation_passed"
    assert result["passed"] == 1
    assert result["real_sql_execution"] is False
    assert result["persisted_candidate"] is False
    assert result["activation_authorized"] is False
    assert result["llm_calls"] == 0
    assert result["benchmark_access"] is False
    assert "question" not in str(result)
    assert "Test monthly totals" not in str(result)
    assert "expected_intent" not in str(result)


def test_failed_expectations_are_evaluation_only_and_sanitized() -> None:
    suite = {
        "cases": [{
            "question": "Test monthly totals",
            "expected_intent": "not_the_intent",
            "expected_plan_status": "planned",
            "expected_error_code": "SOMETHING_ELSE",
            "expected_temporal_issue": "not_present",
        }],
    }
    with patch(
        "scripts.evaluate_memory_candidate_generalization_readonly.resolve_intent",
        side_effect=mock_intent,
    ), patch(
        "scripts.evaluate_memory_candidate_generalization_readonly.build_query_plan",
        side_effect=mock_plan,
    ):
        result = evaluate_suite(mock_snapshot(), suite)
    assert result["status"] == "evaluation_failed"
    assert result["failed"] == 1
    assert result["observations"][0]["failed_assertions"] == [
        "intent", "plan_status", "plan_error_code", "temporal_issue",
    ]
    assert "SOMETHING_ELSE" not in str(result)


def test_malformed_suite_rejected_before_any_semantic_call() -> None:
    malformed = [
        {},
        {"cases": []},
        {"cases": [{}]},
        {"cases": [{"question": "valid but missing checks"}]},
        {"cases": [{"question": "", "expected_intent": "x"}]},
        {"cases": [{"question": "question", "expected_sql": "SELECT 1"}]},
        {"cases": [{"question": "question", "expected_intent": None}]},
        {"cases": [{"question": "question", "expected_plan_status": 1}]},
    ]
    with patch(
        "scripts.evaluate_memory_candidate_generalization_readonly.resolve_intent"
    ) as intent:
        for bad in malformed:
            try:
                evaluate_suite(mock_snapshot(), bad)
            except ValueError:
                pass
            else:
                raise AssertionError("invalid evaluation suite accepted")
        intent.assert_not_called()


def test_real_planner_rejects_unhandled_reference_for_novel_intent() -> None:
    context = _synthetic_temporal_context()
    p = _pattern(pattern_name="other_intent_pattern")
    p["intent_name"] = "independent_intent"
    context["query_patterns"].append(p)
    context["component_configs"]["temporal_planning"]["reference_selection"] = {
        "default_reference": "basic_date",
        "references": [
            {"reference": "basic_date", "terms": ["by default period"]},
            {"reference": "other_date", "terms": ["by alternate event date"]},
        ],
    }
    candidate = {
        "cases": [{
            "question": "Group measures by alternate event date",
            "expected_intent": "independent_intent",
            "expected_plan_status": "rejected",
            "expected_error_code": "PLANNING_TEMPORAL_REFERENCE_UNSUPPORTED",
        }],
    }

    with patch(
        "scripts.evaluate_memory_candidate_generalization_readonly.resolve_intent",
        return_value={
            "applied": True,
            "intent": "independent_intent",
            "intent_confidence": 0.95,
        },
    ):
        result = evaluate_suite(context, candidate)
    assert result["status"] == "evaluation_passed", result
    assert result["observations"][0]["plan_error_code"] == (
        "PLANNING_TEMPORAL_REFERENCE_UNSUPPORTED"
    )


def test_runner_aborts_before_reader_when_real_sql_flag_is_not_false() -> None:
    with patch(
        "sys.argv",
        ["candidate-eval", "--policy", "unused", "--cases", "unused"],
    ), patch.dict(
        "os.environ", {"LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "true"}
    ), patch(
        "scripts.evaluate_memory_candidate_generalization_readonly."
        "PostgresContextRepository",
    ) as reader:
        assert main() == 3
        reader.assert_not_called()


if __name__ == "__main__":
    test_expectations_never_enter_semantic_or_planner_calls()
    test_failed_expectations_are_evaluation_only_and_sanitized()
    test_malformed_suite_rejected_before_any_semantic_call()
    test_real_planner_rejects_unhandled_reference_for_novel_intent()
    test_runner_aborts_before_reader_when_real_sql_flag_is_not_false()
    print("MEMORY_CANDIDATE_GENERALIZATION=PASS")
