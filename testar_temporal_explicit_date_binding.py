from __future__ import annotations

from app.domain.planner import _project_temporal_series
from testar_planner import _synthetic_temporal_context


def project(bindings, *, dates=None, strategy="configured_metric_source_date"):
    context = _synthetic_temporal_context()
    cfg = context["component_configs"]["temporal_planning"]
    cfg["date_binding_strategy"] = strategy
    cfg["date_bindings"] = bindings
    table = dict(context["table_catalog"][0])
    table["qualified_name"] = "schema_test.table_test"
    table["date_columns"] = dates if dates is not None else [
        "event_date", "created_at",
    ]
    table["columns"] = list(table["columns"]) + [
        {"name": "created_at", "data_type": "timestamp"},
    ]
    return _project_temporal_series(
        context=context,
        intent_name="generic_test_intent",
        normalized_question="Show monthly totals",
        planned_metrics=[{
            "metric_ref": "synthetic-ref",
            "metric_concept": "measure",
            "target_table": "schema_test.table_test",
            "target_column": "value",
        }],
        required_tables=[table],
        intent_resolution_result=None,
    )


def binding(column="event_date", *, concept="measure", table="schema_test.table_test"):
    return {
        "metric_concept": concept,
        "target_table": table,
        "target_column": column,
    }


def test_explicit_date_bindings() -> None:
    series, diagnostic = project([binding()])
    assert diagnostic["status"] == "resolved", diagnostic
    assert series["date_column"] == "event_date"
    assert series["mapping_source"] == "component_configs.temporal_planning.date_bindings"

    for bindings, expected in [
        ([], "date_bindings_missing_or_invalid"),
        ([binding(), binding("created_at")], "date_binding_ambiguous"),
        ([binding("not_in_catalog")], "date_binding_not_in_catalog"),
        ([binding(concept="other")], "date_binding_not_found"),
        ([binding(table="schema_test.other")], "date_binding_not_found"),
        ([{"metric_concept": "measure"}], "date_bindings_missing_or_invalid"),
    ]:
        series, diagnostic = project(bindings)
        assert series is None
        assert expected in diagnostic["issues"], (expected, diagnostic)


def test_legacy_strategy_remains_unchanged() -> None:
    series, diagnostic = project([], strategy="unique_metric_source_catalog_date")
    assert series is None
    assert "ambiguous_date_columns" in diagnostic["issues"]

    series, diagnostic = project(
        [], strategy="unique_metric_source_catalog_date", dates=["event_date"]
    )
    assert diagnostic["status"] == "resolved", diagnostic
    assert series["date_column"] == "event_date"


if __name__ == "__main__":
    test_explicit_date_bindings()
    test_legacy_strategy_remains_unchanged()
    print("EXPLICIT_TEMPORAL_BINDING=PASS")
