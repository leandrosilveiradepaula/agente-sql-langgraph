from __future__ import annotations

from copy import deepcopy

from app.domain.sql_generation import (
    SqlGenerationInputError,
    build_sql_generation_request,
)
from app.domain.planner import _detect_planned_filters
from testar_planned_filters_e2e import _binding, _plan, _raw_context


def test_metric_concept_matching_case_insensitive():
    entities = [{
        "entity_type": "filter_binding",
        "canonical_value": "category_alpha",
        "business_rule": {"filter_binding": _binding()},
    }]
    planned, diag = _detect_planned_filters(
        context={"entities": entities},
        intent_resolution_result=None,
        planned_metrics=[{"required_filter_concepts": ["CATEGORY_ALPHA"]}],
    )
    assert diag["status"] == "resolved", diag
    assert planned[0]["required"] is True
    assert planned[0]["detection_source"] == "versioned_metric_binding"


def test_preprovider_rejects_non_catalog_filter_targets():
    plan = _plan("synthetic report for alpha class", _raw_context(binding=_binding()))
    assert build_sql_generation_request(plan)
    changed = deepcopy(plan)
    planning = changed["planning_context"]
    binding = planning["resolved_filter_bindings"][0]
    binding["target_column"] = "not_authorized"
    try:
        build_sql_generation_request(changed)
    except SqlGenerationInputError:
        pass
    else:
        raise AssertionError("Uncatalogued filter target was accepted")


if __name__ == "__main__":
    test_metric_concept_matching_case_insensitive()
    test_preprovider_rejects_non_catalog_filter_targets()
    print("PREPROVIDER_FILTER_AUTHORIZATION=PASS")
