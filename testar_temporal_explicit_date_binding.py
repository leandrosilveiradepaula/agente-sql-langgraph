from __future__ import annotations

from app.domain.planner import _project_temporal_series
from testar_planner import _synthetic_temporal_context


def project(
    bindings, *, dates=None, strategy="configured_metric_source_date",
    source_table="schema_test.table_test",
):
    context = _synthetic_temporal_context()
    cfg = context["component_configs"]["temporal_planning"]
    cfg["date_binding_strategy"] = strategy
    cfg["date_bindings"] = bindings
    table = dict(context["table_catalog"][0])
    table["qualified_name"] = source_table
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
            "target_table": source_table,
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


def test_same_metric_concept_selects_the_correct_source_date() -> None:
    # Synthetic metric sources can share a concept without sharing time columns.
    # Binding order must not influence selection.
    declared = [
        binding("created_at", table="schema_test.second_source"),
        binding("event_date", table="schema_test.first_source"),
    ]
    for source, column in (
        ("schema_test.first_source", "event_date"),
        ("schema_test.second_source", "created_at"),
    ):
        for configured in (declared, list(reversed(declared))):
            series, diagnostic = project(
                configured, source_table=source,
            )
            assert diagnostic["status"] == "resolved", diagnostic
            assert series["date_table"] == source
            assert series["date_column"] == column
            assert series["mapping_source"] == (
                "component_configs.temporal_planning.date_bindings"
            )

    # A request for an unconfigured third metric source must not fall back
    # to a date binding declared for another source.
    series, diagnostic = project(
        declared, source_table="schema_test.unconfigured_source"
    )
    assert series is None
    assert "date_binding_not_found" in diagnostic["issues"]


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
    test_same_metric_concept_selects_the_correct_source_date()
    test_legacy_strategy_remains_unchanged()
    print("EXPLICIT_TEMPORAL_BINDING=PASS")
