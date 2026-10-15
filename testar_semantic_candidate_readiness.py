from __future__ import annotations

from copy import deepcopy

from scripts.preflight_semantic_candidate_readonly import (
    evaluate_candidate_readiness,
)


def snapshot() -> dict:
    return {
        "version": "synthetic-v1",
        "fingerprint": "a" * 64,
        "table_catalog": [
            {
                "schema_name": "synthetic",
                "table_name": "facts",
                "metric_columns": ["amount"],
                "date_columns": ["created_at", "recognized_at"],
                "columns": [],
                "ai_hint": {"authorized_filter_columns": ["category"]},
            },
            {
                "schema_name": "synthetic",
                "table_name": "categories",
                "metric_columns": [],
                "date_columns": [],
                "columns": [{"name": "category"}],
            },
        ],
        "entities": [
            {
                "entity_type": "metric_binding",
                "canonical_value": "measure",
                "business_rule": {
                    "metric_binding": {
                        "metric_concept": "measure",
                        "target_table": "synthetic.facts",
                        "target_column": "amount",
                        "required_filter_concepts": ["classification"],
                    }
                },
            },
            {
                "entity_type": "filter_binding",
                "business_rule": {
                    "filter_binding": {
                        "binding_ref": "synthetic-filter",
                        "filter_concept": "classification",
                        "target_table": "synthetic.facts",
                        "target_column": "category",
                        "required": True,
                    }
                },
            },
        ],
        "component_configs": {
            "temporal_planning": {
                "date_binding_strategy": "unique_metric_source_catalog_date",
            }
        },
    }


def codes(report: dict) -> set[str]:
    return {issue["code"] for issue in report["blocking_issues"]}


def test_ambiguous_date_fails_closed() -> None:
    raw = snapshot()
    report = evaluate_candidate_readiness(raw)
    assert report["status"] == "blocked"
    assert "TEMPORAL_DATE_AMBIGUOUS" in codes(report)
    assert report["physical_schema_verified"] is False
    assert report["activation_authorized"] is False
    assert report["llm_calls"] == 0
    assert report["real_sql_execution"] is False


def test_explicit_date_is_configuration_not_code_default() -> None:
    raw = snapshot()
    raw["component_configs"]["temporal_planning"] = {
        "date_binding_strategy": "configured_metric_source_date",
        "date_bindings": [{
            "metric_concept": "measure",
            "target_table": "synthetic.facts",
            "target_column": "recognized_at",
        }],
    }
    report = evaluate_candidate_readiness(raw)
    assert report["status"] == "checks_passed", report
    assert report["finance_semantics_verified"] is False
    assert report["activation_authorized"] is False
    raw["component_configs"]["temporal_planning"]["date_bindings"][0][
        "target_column"
    ] = "not_catalogued"
    assert "TEMPORAL_DATE_NOT_AUTHORIZED" in codes(
        evaluate_candidate_readiness(raw)
    )


def test_filter_missing_or_unapproved_fails_closed() -> None:
    raw = snapshot()
    raw["table_catalog"][0]["date_columns"] = ["created_at"]
    binding = raw["entities"][1]["business_rule"]["filter_binding"]
    binding["target_column"] = "secret_field"
    report = evaluate_candidate_readiness(raw)
    assert "FILTER_COLUMN_NOT_AUTHORIZED" in codes(report)
    binding["target_column"] = "category"
    binding["required"] = False
    report = evaluate_candidate_readiness(raw)
    assert "REQUIRED_FILTER_BINDING_MISSING_OR_AMBIGUOUS" in codes(report)
    binding["required"] = True
    report = evaluate_candidate_readiness(raw)
    assert report["status"] == "checks_passed", report


def test_unselected_table_not_promoted() -> None:
    raw = snapshot()
    raw["entities"][1]["business_rule"]["filter_binding"][
        "target_table"
    ] = "synthetic.missing"
    assert "FILTER_TABLE_NOT_IN_CATALOG" in codes(
        evaluate_candidate_readiness(raw)
    )


def test_readiness_is_pure_and_simulation_is_explicit() -> None:
    raw = snapshot()
    before = deepcopy(raw)
    simulated = evaluate_candidate_readiness(
        raw, simulate_temporal_strategy="configured_metric_source_date"
    )
    assert simulated["temporal_strategy_source"] == "simulation"
    assert "TEMPORAL_EXPLICIT_BINDING_MISSING_OR_AMBIGUOUS" in codes(simulated)
    assert raw == before
    try:
        evaluate_candidate_readiness(raw, simulate_temporal_strategy="other")
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported simulation accepted")


if __name__ == "__main__":
    test_ambiguous_date_fails_closed()
    test_explicit_date_is_configuration_not_code_default()
    test_filter_missing_or_unapproved_fails_closed()
    test_unselected_table_not_promoted()
    test_readiness_is_pure_and_simulation_is_explicit()
    print("SEMANTIC_CANDIDATE_READINESS=PASS")
