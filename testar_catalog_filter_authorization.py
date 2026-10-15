from __future__ import annotations

from copy import deepcopy
from app.domain.planner import _include_authorized_filter_columns
from app.domain.context_validator import _validate_table_catalog


def test_filter_allowlist_is_catalog_controlled() -> None:
    table = {
        "qualified_name": "synthetic.fact",
        "schema_name": "synthetic",
        "table_name": "fact",
        "ai_hint": {"authorized_filter_columns": ["category_code"]},
        "columns": [],
        "key_columns": ["id"],
        "metric_columns": ["amount"],
        "date_columns": ["event_date"],
    }
    bindings = [{
        "binding_ref": "synthetic-ref",
        "filter_concept": "category",
        "target_table": "synthetic.fact",
        "target_column": "category_code",
        "operator": "=",
        "value": "alpha",
        "required": True,
        "scope": "where",
        "join_path": [],
    }]
    columns = {"synthetic.fact": []}
    _include_authorized_filter_columns(columns, bindings, [table])
    assert columns["synthetic.fact"] == [{"name": "category_code"}]

    wrong = deepcopy(bindings)
    wrong[0]["target_column"] = "not_authorized"
    columns = {"synthetic.fact": []}
    _include_authorized_filter_columns(columns, wrong, [table])
    assert columns["synthetic.fact"] == []

    columns = {"synthetic.fact": []}
    _include_authorized_filter_columns(columns, bindings, [])
    assert columns["synthetic.fact"] == []


def test_catalog_rejects_invalid_allowlist() -> None:
    table = {
        "schema_name": "synthetic",
        "table_name": "fact",
        "ai_hint": {"authorized_filter_columns": ["field", "FIELD"]},
    }
    errors = []
    _validate_table_catalog([table], errors)
    assert any(
        item["code"] == "TABLE_FILTER_COLUMNS_INVALID" for item in errors
    )


if __name__ == "__main__":
    test_filter_allowlist_is_catalog_controlled()
    test_catalog_rejects_invalid_allowlist()
    print("CATALOG_FILTER_AUTHORIZATION=PASS")
