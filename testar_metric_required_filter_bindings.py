from __future__ import annotations

from app.domain.planner import _detect_planned_filters, _metric_binding_rule
from app.graph.nodes.generate_sql import create_generate_sql_node
from testar_generate_sql import FakeSqlGenerator, _state


def metric(concepts):
    return {
        "metric_ref": "synthetic-ref",
        "required_filter_concepts": concepts,
    }


def binding(required=True):
    return {
        "entity_type": "filter_binding",
        "canonical_value": "synthetic_category",
        "business_rule": {
            "filter_binding": {
                "binding_ref": "synthetic-filter-ref",
                "filter_concept": "synthetic_category",
                "required": required,
                "scope": "where",
                "target_table": "schema_test.table_test",
                "target_column": "category",
                "operator": "=",
                "value": "synthetic-value",
                "join_path": [],
            }
        },
    }


def test_metric_injects_required_filter_without_phrase_lookup():
    planned, diagnostic = _detect_planned_filters(
        context={"entities": [binding()]},
        intent_resolution_result=None,
        planned_metrics=[metric(["synthetic_category"])],
    )
    assert diagnostic["status"] == "resolved", diagnostic
    assert len(planned) == 1
    assert planned[0]["required"] is True
    assert planned[0]["detection_source"] == "versioned_metric_binding"
    assert "target_column" not in planned[0]


def test_missing_or_optional_filter_fails_closed():
    for entities in ([], [binding(False)]):
        planned, diagnostic = _detect_planned_filters(
            context={"entities": entities},
            intent_resolution_result=None,
            planned_metrics=[metric(["synthetic_category"])],
        )
        assert planned == []
        assert diagnostic["status"] == "unresolved"
        assert diagnostic["unresolved"]


def test_metric_rule_preserves_filter_concepts():
    raw = {
        "metric_binding": {
            "metric_concept": "synthetic_metric",
            "target_table": "schema_test.table_test",
            "target_column": "value",
            "when_present": ["synthetic_scenario"],
            "when_absent": [],
            "required_filter_concepts": ["synthetic_category"],
        }
    }
    assert _metric_binding_rule(raw)["required_filter_concepts"] == [
        "synthetic_category"
    ]


def test_unresolved_filter_does_not_invoke_provider():
    generator = FakeSqlGenerator()
    state = _state()
    plan = dict(state["query_plan"])
    projection = dict(plan["planning_context"])
    diagnostics = dict(projection.get("diagnostics") or {})
    diagnostics["planned_filter_diagnostic"] = {
        "status": "unresolved",
        "unresolved": [{"filter_concept": "synthetic_category"}],
    }
    projection["diagnostics"] = diagnostics
    plan["planning_context"] = projection
    state["query_plan"] = plan
    result = create_generate_sql_node(generator)(state)
    assert generator.calls == 0
    assert result["final_status"] == "rejected"


if __name__ == "__main__":
    test_metric_injects_required_filter_without_phrase_lookup()
    test_missing_or_optional_filter_fails_closed()
    test_metric_rule_preserves_filter_concepts()
    test_unresolved_filter_does_not_invoke_provider()
    print("METRIC_REQUIRED_FILTERS=PASS")
