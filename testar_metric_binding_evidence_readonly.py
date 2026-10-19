from __future__ import annotations

from scripts.evaluate_memory_candidate_generalization_readonly import (
    summarize_planned_metric_evidence,
)


def test_structural_metric_evidence_only() -> None:
    private_data = "sensitive-business-value"
    projection = {"diagnostics": {"planned_metric_diagnostic": {
        "metric_requested": True,
        "matched_terms": [private_data],
        "unresolved_terms": [],
        "invalid_metadata_terms": [],
        "binding_context_concepts": [{"concept_name": private_data}],
        "binding_inference": {"status": "not_applicable"},
        "global_binding_status": "not_applicable",
        "binding_failures": [{"binding_diagnostics": [{
            "configured_count": 2,
            "applicable_count": 0,
            "metric_concept": private_data,
            "rejected": [
                {"reason": "when_present_missing", "missing_present": [private_data]},
                {"reason": "when_absent_present", "blocked_absent": [private_data]},
            ],
        }]}],
    }}}
    report = summarize_planned_metric_evidence(projection)
    assert report["metric_requested"] is True
    assert report["matched_metric_term_count"] == 1
    assert report["configured_binding_count"] == 2
    assert report["applicable_binding_count"] == 0
    assert report["rejected_binding_reasons"]["when_present_missing"] == 1
    assert report["rejected_binding_reasons"]["when_absent_present"] == 1
    assert report["missing_required_binding_condition_count"] == 1
    assert report["conflicting_absent_binding_condition_count"] == 1
    assert private_data not in str(report)


def test_empty_or_untrusted_metadata_is_safe() -> None:
    assert summarize_planned_metric_evidence(None) is None
    assert summarize_planned_metric_evidence({}) is None
    projection = {"diagnostics": {"planned_metric_diagnostic": {
        "global_binding_status": "private-content",
        "binding_inference": {"status": "private-content"},
        "matched_terms": "private-content",
        "binding_failures": [None, "private-content"],
    }}}
    report = summarize_planned_metric_evidence(projection)
    assert report["global_binding_status"] == "other"
    assert report["binding_inference_status"] == "other"
    assert report["matched_metric_term_count"] == 0
    assert report["binding_failure_count"] == 2
    assert "private-content" not in str(report)


if __name__ == "__main__":
    test_structural_metric_evidence_only()
    test_empty_or_untrusted_metadata_is_safe()
    print("METRIC_BINDING_EVIDENCE_READONLY=PASS")
