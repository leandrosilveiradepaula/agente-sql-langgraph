from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

from scripts.evaluate_memory_candidate_generalization_readonly import (
    evaluate_suite,
    main,
    observe_plan,
    summarize_resolution_evidence,
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


def test_failed_resolution_evidence_explains_scores_without_leaking_terms() -> None:
    """All token/term/SQL payloads are excluded from structural diagnostics."""
    sensitive = "sensitive-user-phrase-not-for-output"
    resolved = {
        "reason": "ambiguous_candidates",
        "resolver_configuration": {
            "minimum_score": 95,
            "ambiguity_margin": 15,
            "example_question": sensitive,
        },
        "candidates": [
            {
                "intent_name": "generic_first",
                "score": 130,
                "positive_score": 130,
                "negative_score": 0,
                "matches": [
                    {
                        "pattern": sensitive,
                        "match_strategy": "configured_signal",
                        "match_details": {"raw_tokens": [sensitive]},
                    },
                    {
                        "pattern": sensitive,
                        "match_strategy": "intent_catalog_rule",
                    },
                ],
            },
            {
                "intent_name": "generic_second",
                "score": 125,
                "positive_score": 125,
                "negative_score": 0,
                "matches": [{"pattern": sensitive, "match_strategy": "other"}],
            },
        ],
        "intent_catalog": {
            "evaluations": [{
                "intent_name": "generic_first",
                "eligible": False,
                "excluded": True,
                "require_rule_count": 2,
                "satisfied_require_rule_count": 1,
                "positive_score": 25,
                "negative_score": 0,
                "rules": [{
                    "rule_name": sensitive,
                    "effect": "require",
                    "satisfied": False,
                    "matched_concept_count": 1,
                    "minimum_concept_matches": 2,
                    "concepts": [{
                        "concept_name": "operation_type",
                        "satisfied": False,
                        "matched_term_count": 0,
                        "minimum_term_matches": 1,
                        "terms": [{"term": sensitive}],
                        "semantic_signals": [{"matched_tokens": [sensitive]}],
                    }],
                }],
            }],
        },
        "token_fallback": {
            "enabled": True,
            "used_for_selected_intent": False,
            "configuration": {"sensitive": sensitive},
        },
        "semantic_defaults": {
            "applied": [{"concept_name": sensitive}],
            "suppressed": [{"secret": sensitive}],
        },
    }
    # Client-controlled labels are never echoed in an evaluation report.
    resolved["candidates"][0]["intent_name"] = sensitive
    resolved["intent_catalog"]["evaluations"][0]["intent_name"] = sensitive
    resolved["intent_catalog"]["evaluations"][0]["rules"][0]["concepts"][0][
        "concept_name"
    ] = sensitive
    report = summarize_resolution_evidence(resolved)
    assert report["reason"] == "ambiguous_candidates"
    assert report["minimum_score"] == 95
    assert report["ambiguity_margin"] == 15
    assert report["candidate_count"] == 2
    assert report["candidates"][0]["candidate_rank"] == 1
    assert "intent" not in report["candidates"][0]
    assert report["catalog_evidence"][0]["entry_index"] == 1
    assert "intent" not in report["catalog_evidence"][0]
    assert report["catalog_evidence"][0]["rules"][0]["concepts"][0][
        "concept_index"
    ] == 1
    assert "concept" not in report["catalog_evidence"][0]["rules"][0]["concepts"][0]
    assert report["candidates"][0]["matched_signal_count"] == 1
    assert report["candidates"][0]["matched_catalog_scoring_rules"] == 1
    assert report["catalog_evidence"][0]["required_rule_count"] == 2
    assert report["catalog_evidence"][0]["excluded"] is True
    assert report["catalog_evidence"][0]["rules"][0]["concepts"][0][
        "matched_term_count"
    ] == 0
    assert report["semantic_default_count"] == 1
    assert report["semantic_defaults_suppressed_count"] == 1
    assert sensitive not in str(report)
    for secret_field in (
        "pattern", "term", "normalized_term", "matched_tokens",
        "semantic_signals", "sql", "raw_question", "description",
        "rule_name", "secret",
    ):
        assert f"'{secret_field}':" not in str(report)


def test_detailed_evidence_appears_only_for_failed_evaluation() -> None:
    suite = {"cases": [
        {
            "question": "Test monthly totals",
            "expected_intent": "synthetic_intent",
            "expected_plan_status": "rejected",
        },
        {
            "question": "Unseen monthly totals",
            "expected_intent": "different_intent",
        },
    ]}
    diagnostic = {"reason": "minimum_score_not_reached"}
    with patch(
        "scripts.evaluate_memory_candidate_generalization_readonly.resolve_intent",
        return_value={
            "applied": True,
            "intent": "synthetic_intent",
            "intent_confidence": 0.9,
            "normalized_question": "Test monthly totals",
            "reason": "minimum_score_not_reached",
            "resolver_configuration": {"minimum_score": 100, "ambiguity_margin": 20},
            "candidates": [],
            "intent_catalog": {"evaluations": []},
        }
    ), patch(
        "scripts.evaluate_memory_candidate_generalization_readonly.build_query_plan",
        return_value={
            "status": "rejected",
            "error_code": "PLANNING_TEMPORAL_REFERENCE_UNSUPPORTED",
            "projection": None,
        },
    ):
        output = evaluate_suite(mock_snapshot(), suite)
    assert output["passed"] == 1 and output["failed"] == 1
    assert "resolution_evidence" not in output["observations"][0]
    assert output["observations"][1]["resolution_evidence"]["minimum_score"] == 100
    assert output["observations"][1]["resolution_evidence"]["reason"] == diagnostic["reason"]
    assert "Unseen monthly totals" not in str(output)


def test_diagnostic_nonfinite_scores_are_redacted() -> None:
    report = summarize_resolution_evidence({
        "reason": "minimum_score_not_reached",
        "resolver_configuration": {
            "minimum_score": float("inf"),
            "ambiguity_margin": float("nan"),
        },
        "candidates": [
            {"intent_name": "sensitive", "score": float("inf"),
             "positive_score": float("nan"), "negative_score": False},
        ],
    })
    assert report["minimum_score"] is None
    assert report["ambiguity_margin"] is None
    assert report["candidates"][0]["score"] is None
    assert report["candidates"][0]["positive_score"] is None
    assert report["candidates"][0]["negative_score"] is None
    assert "sensitive" not in str(report)


def test_no_candidate_resolution_diagnostic_is_fail_closed() -> None:
    result = summarize_resolution_evidence({
        "reason": "minimum_score_not_reached",
        "resolver_configuration": {"minimum_score": 100},
        "candidates": [],
        "intent_catalog": {"evaluations": []},
    })
    assert result["candidate_count"] == 0
    assert result["reason"] == "minimum_score_not_reached"
    assert result["catalog_entries_evaluated"] == 0


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
    test_failed_resolution_evidence_explains_scores_without_leaking_terms()
    test_detailed_evidence_appears_only_for_failed_evaluation()
    test_no_candidate_resolution_diagnostic_is_fail_closed()
    test_diagnostic_nonfinite_scores_are_redacted()
    test_malformed_suite_rejected_before_any_semantic_call()
    test_real_planner_rejects_unhandled_reference_for_novel_intent()
    test_runner_aborts_before_reader_when_real_sql_flag_is_not_false()
    print("MEMORY_CANDIDATE_GENERALIZATION=PASS")
