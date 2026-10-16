from __future__ import annotations

from copy import deepcopy
from app.domain.context_validator import _validate_temporal_planning_config


def snapshot():
    return {
        "query_patterns": [{"intent_name": "synthetic_intent"}],
        "table_catalog": [{
            "schema_name": "schema_test",
            "table_name": "fact_test",
            "date_columns": ["event_date", "created_at"],
            "columns": [
                {"name": "event_date"},
                {"name": "created_at"},
            ],
        }],
    }


def config():
    return {
        "required_intents": ["synthetic_intent"],
        "granularities": [{"grain": "month", "terms": ["monthly"]}],
        "date_binding_strategy": "configured_metric_source_date",
        "date_bindings": [{
            "metric_concept": "synthetic_measure",
            "target_table": "schema_test.fact_test",
            "target_column": "event_date",
        }],
    }


def errors_for(cfg):
    errors = []
    _validate_temporal_planning_config(cfg, snapshot(), errors)
    return [err["code"] for err in errors]


def test_valid_config():
    assert errors_for(config()) == []
    legacy = config()
    legacy["date_binding_strategy"] = "unique_metric_source_catalog_date"
    legacy.pop("date_bindings")
    assert errors_for(legacy) == []


def test_invalid_configs():
    cases = [
        ("required_intents", ["unknown_intent"], "TEMPORAL_INTENT_UNKNOWN"),
        ("granularities", [], "TEMPORAL_GRAINS_INVALID"),
        ("date_binding_strategy", "unknown", "TEMPORAL_STRATEGY_INVALID"),
        ("date_bindings", [], "TEMPORAL_DATE_BINDINGS_INVALID"),
    ]
    for field, value, code in cases:
        candidate = config()
        candidate[field] = value
        assert code in errors_for(candidate), (field, errors_for(candidate))

    candidate = config()
    candidate["date_bindings"][0]["target_column"] = "unlisted"
    assert "TEMPORAL_DATE_COLUMN_UNAUTHORIZED" in errors_for(candidate)
    candidate = config()
    candidate["date_bindings"].append(deepcopy(candidate["date_bindings"][0]))
    assert "TEMPORAL_DATE_BINDING_AMBIGUOUS" in errors_for(candidate)


def test_versioned_temporal_references_are_structurally_valid() -> None:
    cfg = config()
    cfg["reference_selection"] = {
        "default_reference": "base_date",
        "references": [
            {"reference": "base_date", "terms": ["period", "by period"]},
            {"reference": "alternate_date", "terms": ["posting date"]},
        ],
    }
    assert errors_for(cfg) == []
    cfg["reference_selection"]["references"][1]["date_bindings"] = [{
        "metric_concept": "synthetic_measure",
        "target_table": "schema_test.fact_test",
        "target_column": "created_at",
    }]
    assert errors_for(cfg) == []


def test_temporal_reference_alias_and_binding_guardrails() -> None:
    valid = config()
    valid["reference_selection"] = {
        "default_reference": "base_date",
        "references": [
            {"reference": "base_date", "terms": ["period"]},
            {"reference": "other_date", "terms": ["posting date"]},
        ],
    }
    cases = [
        ("missing", lambda x: x["reference_selection"].update(
            {"default_reference": "unlisted"}
        ), "TEMPORAL_REFERENCE_DEFAULT_UNKNOWN"),
        ("duplicate_alias", lambda x: x["reference_selection"]["references"][1].update(
            {"terms": ["period"]}
        ), "TEMPORAL_REFERENCE_TERM_DUPLICATE"),
        ("duplicate_reference", lambda x: x["reference_selection"]["references"][1].update(
            {"reference": "base_date"}
        ), "TEMPORAL_REFERENCE_DUPLICATE"),
        ("empty_terms", lambda x: x["reference_selection"]["references"][1].update(
            {"terms": []}
        ), "TEMPORAL_REFERENCE_ENTRY_INVALID"),
        ("unauthorized_date", lambda x: x["reference_selection"]["references"][1].update(
            {"date_bindings": [{
                "metric_concept": "synthetic_measure",
                "target_table": "schema_test.fact_test",
                "target_column": "not_authorized",
            }]}
        ), "TEMPORAL_REFERENCE_DATE_UNAUTHORIZED"),
        ("default_override", lambda x: x["reference_selection"]["references"][0].update(
            {"date_bindings": [{
                "metric_concept": "synthetic_measure",
                "target_table": "schema_test.fact_test",
                "target_column": "event_date",
            }]}
        ), "TEMPORAL_REFERENCE_BINDINGS_INVALID"),
        ("empty_alt_bindings", lambda x: x["reference_selection"]["references"][1].update(
            {"date_bindings": []}
        ), "TEMPORAL_REFERENCE_BINDINGS_INVALID"),
    ]
    for label, change, code in cases:
        cfg = deepcopy(valid)
        change(cfg)
        assert code in errors_for(cfg), (label, errors_for(cfg))

    cfg = deepcopy(valid)
    cfg["date_binding_strategy"] = "unique_metric_source_catalog_date"
    assert "TEMPORAL_REFERENCE_STRATEGY_UNSUPPORTED" in errors_for(cfg)


if __name__ == "__main__":
    test_valid_config()
    test_invalid_configs()
    test_versioned_temporal_references_are_structurally_valid()
    test_temporal_reference_alias_and_binding_guardrails()
    print("TEMPORAL_CONTEXT_VALIDATION=PASS")
