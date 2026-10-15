from __future__ import annotations

from app.domain.planner import _project_temporal_series
from app.domain.context_validator import _validate_temporal_planning_config
from app.domain.sql_generation import _temporal_series


def test_catalog_date_column_without_full_column_inventory() -> None:
    table = {
        "schema_name": "schema_test",
        "table_name": "measurements",
        "qualified_name": "schema_test.measurements",
        "date_columns": ["period_date", "created_date"],
        "columns": [],
    }
    config = {
        "required_intents": ["generic_intent"],
        "date_binding_strategy": "configured_metric_source_date",
        "granularities": [{"grain": "month", "terms": ["monthly"]}],
        "date_bindings": [{
            "metric_concept": "synthetic_metric",
            "target_table": "schema_test.measurements",
            "target_column": "period_date",
        }],
    }
    snapshot = {
        "query_patterns": [{"intent_name": "generic_intent"}],
        "table_catalog": [table],
    }
    issues = []
    _validate_temporal_planning_config(config, snapshot, issues)
    assert not issues, issues

    metric = {
        "metric_ref": "test-ref",
        "metric_concept": "synthetic_metric",
        "target_table": "schema_test.measurements",
        "target_column": "number",
    }
    projection, diagnostic = _project_temporal_series(
        context={"component_configs": {"temporal_planning": config}},
        intent_name="generic_intent",
        normalized_question="Show monthly values",
        planned_metrics=[metric],
        required_tables=[table],
        intent_resolution_result=None,
    )
    assert diagnostic["status"] == "resolved", diagnostic
    assert projection["date_column"] == "period_date"

    sql_input = _temporal_series(
        projection,
        planned_metrics=[metric],
        authorized_tables=[table],
        catalog_columns={"schema_test.measurements": [{"name": "period_date"}]},
    )
    assert sql_input["date_column"] == "period_date"


def test_unknown_date_is_still_rejected() -> None:
    config = {
        "required_intents": ["generic_intent"],
        "date_binding_strategy": "configured_metric_source_date",
        "granularities": [{"grain": "month", "terms": ["monthly"]}],
        "date_bindings": [{
            "metric_concept": "synthetic_metric",
            "target_table": "schema_test.measurements",
            "target_column": "not_in_catalog",
        }],
    }
    errors = []
    _validate_temporal_planning_config(config, {
        "query_patterns": [{"intent_name": "generic_intent"}],
        "table_catalog": [{
            "schema_name": "schema_test",
            "table_name": "measurements",
            "date_columns": ["period_date"],
            "columns": [],
        }],
    }, errors)
    assert any(x["code"] == "TEMPORAL_DATE_COLUMN_UNAUTHORIZED" for x in errors)


if __name__ == "__main__":
    test_catalog_date_column_without_full_column_inventory()
    test_unknown_date_is_still_rejected()
    print("TEMPORAL_CATALOG_COLUMNS=PASS")
