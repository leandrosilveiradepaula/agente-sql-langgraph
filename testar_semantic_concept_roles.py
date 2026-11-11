"""Portable structural concept roles, independent of any tenant vocabulary."""
from __future__ import annotations

from copy import deepcopy

from app.domain.intent_resolver import IntentResolverInputError, resolve_intent
from app.domain.planner import build_query_plan
from app.domain.semantic_concept_roles import (
    ConceptRoleConfigurationError,
    parse_concept_roles,
    role_concepts,
    unknown_role_concepts,
)
from testar_intent_resolver import _semantic_metric_context
from testar_planner import _dimension_context, _intent_dimension_evidence


def test_roles_default_to_empty_without_legacy_aliases() -> None:
    assert parse_concept_roles({}) == {}
    assert role_concepts({"config": {}}, "grouping") == frozenset()
    assert parse_concept_roles({
        "config": {"concept_roles": {"grouping": ["custom_axis"]}},
    }) == {"grouping": frozenset({"custom_axis"})}


def test_same_resolver_with_two_unrelated_concept_names() -> None:
    for name in ("dimension_grouping", "breakdown_axis"):
        context = deepcopy(_semantic_metric_context())
        context["config"]["concept_roles"]["grouping"] = [name]
        for entry in context["intent_catalog"]:
            for rule in entry["rules"]:
                for concept in rule["concepts"]:
                    if concept["concept_name"] == "dimension_grouping":
                        concept["concept_name"] = name
        result = resolve_intent(
            "amount distributed across regions last period", context,
        )
        assert result["applied"] is True
        assert result["intent"] == "synthetic_metric"
        found = {
            concept["concept_name"]: concept
            for evaluation in result["intent_catalog"]["evaluations"]
            for rule in evaluation["rules"]
            for concept in rule["concepts"]
        }
        assert name in found
        assert found[name]["satisfied"] is True


def test_portable_planner_same_physical_authorization_with_different_roles() -> None:
    for name in ("dimension_grouping", "segmentation_axis"):
        context = deepcopy(_dimension_context())
        context["intent_resolution"]["config"]["concept_roles"]["grouping"] = [name]
        for entry in context["intent_resolution"]["intent_catalog"]:
            for rule in entry.get("business_rule", {}).get("intent_catalog", {}).get("rules", []):
                for concept in rule.get("concepts", []):
                    if concept.get("concept_name") == "dimension_grouping":
                        concept["concept_name"] = name
        evidence = _intent_dimension_evidence(
            term="by region", matched_tokens=["region"],
        )
        concept = evidence["best_candidate"]["matches"][0]["match_details"]["concepts"][0]
        concept["concept_name"] = name
        concept["terms"][0]["match_details"]["semantic_signal"]["concept_name"] = name
        result = build_query_plan(
            context=context,
            intent_name="generic_test_intent",
            intent_confidence=0.98,
            normalized_question="total amount across regions",
            intent_resolution_result=evidence,
        )
        assert result["status"] == "planned"
        dimension = result["query_plan"]["planning_context"]["detected_dimensions"][0]
        assert dimension["canonical_value"] == "region"
        assert dimension["target_column"] == "region_name"


def test_wrong_role_cannot_promote_arbitrary_concept_into_dimension() -> None:
    context = deepcopy(_dimension_context())
    context["intent_resolution"]["config"]["concept_roles"]["grouping"] = ["unrelated_axis"]
    evidence = _intent_dimension_evidence(
        term="by region", matched_tokens=["region"],
    )
    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="total amount across regions",
        intent_resolution_result=evidence,
    )
    assert result["status"] == "planned"
    assert result["query_plan"]["planning_context"]["detected_dimensions"] == []


def test_unknown_concept_reference_and_invalid_roles_fail_closed() -> None:
    resolution = deepcopy(_semantic_metric_context())
    resolution["config"]["concept_roles"] = {"grouping": ["ghost_axis"]}
    assert unknown_role_concepts(resolution) == {"grouping": ["ghost_axis"]}
    try:
        resolve_intent("amount distributed across regions last period", resolution)
    except IntentResolverInputError as exc:
        assert "concept_role_unknown_concept" in str(exc)
    else:
        raise AssertionError("Unknown role passed to resolver")
    for bad in (
        {"grouping": []},
        {"grouping": ["duplicated", "duplicated"]},
        {"grouping": "wrong"},
        {"!invalid": ["dimension_grouping"]},
        {str(i): ["axis"] for i in range(33)},
    ):
        try:
            parse_concept_roles({"config": {"concept_roles": bad}})
        except ConceptRoleConfigurationError:
            continue
        raise AssertionError("Invalid role mapping accepted")


def test_no_role_does_not_guess_grouping_from_name() -> None:
    context = deepcopy(_dimension_context())
    del context["intent_resolution"]["config"]["concept_roles"]
    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="total amount across regions",
        intent_resolution_result=_intent_dimension_evidence(
            term="by region", matched_tokens=["region"],
        ),
    )
    assert result["status"] == "planned"
    assert result["query_plan"]["planning_context"]["detected_dimensions"] == []



def test_two_tenants_with_different_physical_schemas_and_concepts() -> None:
    def rename(value, old, new):
        if isinstance(value, dict):
            return {k: rename(v, old, new) for k, v in value.items()}
        if isinstance(value, list):
            return [rename(v, old, new) for v in value]
        return value.replace(old, new) if isinstance(value, str) else value

    for concept_name, schema_name, table_name in (
        ("dimension_grouping", "schema_test", "dim_region"),
        ("allocation_axis", "erp_books", "cost_axis"),
    ):
        context = deepcopy(_dimension_context())
        context = rename(context, "schema_test", schema_name)
        context = rename(context, "dim_region", table_name)
        context["intent_resolution"]["config"]["concept_roles"]["grouping"] = [concept_name]
        for entry in context["intent_resolution"]["intent_catalog"]:
            for rule in entry.get("business_rule", {}).get("intent_catalog", {}).get("rules", []):
                for concept in rule.get("concepts", []):
                    if concept.get("concept_name") == "dimension_grouping":
                        concept["concept_name"] = concept_name
        evidence = _intent_dimension_evidence(term="by region", matched_tokens=["region"])
        item = evidence["best_candidate"]["matches"][0]["match_details"]["concepts"][0]
        item["concept_name"] = concept_name
        item["terms"][0]["match_details"]["semantic_signal"]["concept_name"] = concept_name
        plan = build_query_plan(
            context=context,
            intent_name="generic_test_intent",
            intent_confidence=0.98,
            normalized_question="total amount across regions",
            intent_resolution_result=evidence,
        )
        assert plan["status"] == "planned"
        dimension = plan["query_plan"]["planning_context"]["detected_dimensions"][0]
        assert dimension["target_table"] == schema_name + "." + table_name
        assert dimension["target_column"] == "region_name"



def test_metric_and_operation_roles_port_across_client_vocabularies() -> None:
    from testar_planner import _metric_context, _intent_metric_evidence

    for operation_concept, metric_concept in (
        ("analytical_operation", "financial_metric"),
        ("measure_aggregation", "book_value"),
    ):
        context = deepcopy(_metric_context())
        context["intent_resolution"]["config"]["concept_roles"].update({
            "operation": [operation_concept],
            "metric": [metric_concept],
        })
        evidence = _intent_metric_evidence(
            term="amount", operation_term="highest",
        )
        for concept in evidence["best_candidate"]["matches"][0]["match_details"]["concepts"]:
            if concept["concept_name"] == "analytical_operation":
                concept["concept_name"] = operation_concept
            elif concept["concept_name"] == "financial_metric":
                concept["concept_name"] = metric_concept
            for term in concept.get("terms", []):
                term["match_details"]["semantic_signal"]["concept_name"] = concept["concept_name"]
        result = build_query_plan(
            context=context,
            intent_name="generic_test_intent",
            intent_confidence=0.98,
            normalized_question="highest amount by region",
            intent_resolution_result=evidence,
        )
        assert result["status"] == "planned"
        projection = result["query_plan"]["planning_context"]
        assert len(projection["planned_metrics"]) == 1
        assert len(projection["analytical_operations"]) == 1
        assert projection["analytical_operations"][0]["operation_type"] == "ranking"


def test_missing_roles_never_infer_metric_or_operation_from_concept_name() -> None:
    from testar_planner import _metric_context, _intent_metric_evidence

    context = deepcopy(_metric_context())
    del context["intent_resolution"]["config"]["concept_roles"]["metric"]
    del context["intent_resolution"]["config"]["concept_roles"]["operation"]
    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="highest amount",
        intent_resolution_result=_intent_metric_evidence(
            term="amount", operation_term="highest",
        ),
    )
    assert result["status"] == "planned"
    projection = result["query_plan"]["planning_context"]
    assert projection["planned_metrics"] == []
    assert projection["analytical_operations"] == []



def test_period_role_matches_selected_tenant_concepts_only() -> None:
    from app.domain.planner import _matched_temporal_period_terms

    for concept_name in ("period_reference", "fiscal_time_axis"):
        evidence = {
            "intent": "tenant_query",
            "best_candidate": {
                "intent_name": "tenant_query",
                "matches": [{
                    "match_details": {
                        "concepts": [{
                            "concept_name": concept_name,
                            "satisfied": True,
                            "terms": [{
                                "matched": True,
                                "normalized_term": "last closed period",
                            }],
                        }],
                    },
                }],
            },
            "candidates": [],
        }
        assert _matched_temporal_period_terms(
            evidence, period_concepts=frozenset({concept_name}),
        ) == ["last closed period"]
        assert _matched_temporal_period_terms(
            evidence, period_concepts=frozenset(),
        ) == []


def test_context_role_reference_integrity_is_generic_across_multiple_roles() -> None:
    resolution = deepcopy(_semantic_metric_context())
    resolution["config"]["concept_roles"] = {
        "grouping": ["dimension_grouping"],
        "operation": ["operation"],
        "metric": ["metric"],
        "period": ["period"],
    }
    assert unknown_role_concepts(resolution) == {}
    resolution["config"]["concept_roles"]["period"] = ["missing_time_concept"]
    assert unknown_role_concepts(resolution) == {
        "period": ["missing_time_concept"],
    }


if __name__ == "__main__":
    tests = sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v))
    for name, fn in tests:
        fn()
        print("PASS " + name)
    print("SEMANTIC_ROLE_TESTS=" + str(len(tests)))
