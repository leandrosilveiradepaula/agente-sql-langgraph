from __future__ import annotations

from app.graph.nodes.generate_sql import (
    _explicit_metric_bindings_complete,
    create_generate_sql_node,
)
from testar_generate_sql import FakeSqlGenerator, _state


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


def test_provider_not_called_for_unresolved_explicit_metric() -> None:
    generator = FakeSqlGenerator()
    node = create_generate_sql_node(generator)
    state = _state()
    plan = dict(state["query_plan"])
    planning_context = dict(plan["planning_context"])
    planning_context["planned_metrics"] = []
    diagnostics = dict(planning_context.get("diagnostics", {}))
    diagnostics["planned_metric_diagnostic"] = {
        "metric_requested": True,
        "unresolved_terms": ["synthetic_metric"],
        "invalid_metadata_terms": [],
    }
    planning_context["diagnostics"] = diagnostics
    plan["planning_context"] = planning_context
    state["query_plan"] = plan
    result = node(state)
    assert generator.calls == 0
    assert result["final_status"] == "rejected"
    assert result["failure_stage"] == "generate_sql"
    assert result["errors"][0]["code"] == "SQL_GENERATION_PLAN_INVALID"


def test_provider_called_when_metric_binding_complete() -> None:
    generator = FakeSqlGenerator()
    node = create_generate_sql_node(generator)
    state = _state()
    plan = dict(state["query_plan"])
    planning_context = dict(plan["planning_context"])
    planning_context["planned_metrics"] = [{"metric_ref": "metric-synthetic"}]
    diagnostics = dict(planning_context.get("diagnostics", {}))
    diagnostics["planned_metric_diagnostic"] = {
        "metric_requested": True,
        "unresolved_terms": [],
        "invalid_metadata_terms": [],
    }
    planning_context["diagnostics"] = diagnostics
    plan["planning_context"] = planning_context
    state["query_plan"] = plan
    result = node(state)
    assert generator.calls == 1
    assert result["final_status"] == "processing"


if __name__ == "__main__":
    test_explicit_metric_binding_gate()
    test_gate_is_business_agnostic()
    test_provider_not_called_for_unresolved_explicit_metric()
    test_provider_called_when_metric_binding_complete()
    print("EXPLICIT_METRIC_GATE=PASS")
