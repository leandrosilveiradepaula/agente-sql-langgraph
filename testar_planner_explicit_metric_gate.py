from __future__ import annotations

from app.domain.planner import _explicit_metric_bindings_complete


def test_explicit_metric_binding_gate() -> None:
    def projection(requested, metrics, unresolved=None, invalid=None):
        return {
            "planned_metrics": metrics,
            "diagnostics": {
                "planned_metric_diagnostic": {
                    "metric_requested": requested,
                    "unresolved_terms": unresolved or [],
                    "invalid_metadata_terms": invalid or [],
                }
            },
        }

    metric = {"metric_ref": "metric-synthetic-1"}
    assert _explicit_metric_bindings_complete(projection(False, []))
    assert _explicit_metric_bindings_complete(projection(True, [metric]))
    assert not _explicit_metric_bindings_complete(projection(True, []))
    assert not _explicit_metric_bindings_complete(
        projection(True, [metric], unresolved=["not_mapped"])
    )
    assert not _explicit_metric_bindings_complete(
        projection(True, [metric], invalid=["invalid_mapping"])
    )
    assert not _explicit_metric_bindings_complete(
        projection(True, [{"metric_ref": ""}])
    )


def test_gate_is_business_agnostic() -> None:
    for label in ("measure_alpha", "measure_beta", "unknown_metric"):
        result = {
            "planned_metrics": [],
            "diagnostics": {
                "planned_metric_diagnostic": {
                    "metric_requested": True,
                    "unresolved_terms": [label],
                    "invalid_metadata_terms": [],
                }
            },
        }
        assert not _explicit_metric_bindings_complete(result)


if __name__ == "__main__":
    test_explicit_metric_binding_gate()
    test_gate_is_business_agnostic()
    print("EXPLICIT_METRIC_GATE=PASS")
