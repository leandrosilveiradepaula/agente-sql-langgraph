"""Tenant-agnostic fail-closed handoff of semantic claims into plans."""
from __future__ import annotations

from copy import deepcopy

from app.domain.semantic_plan_gate import missing_semantic_plan_bindings
from app.graph.nodes.build_plan import build_plan
from testar_planner import _metric_context, _intent_metric_evidence


def _fixture():
    context = _metric_context()
    evidence = _intent_metric_evidence(
        term="amount", operation_term="highest",
    )
    evidence["reason"] = "semantic_interpretation_selected"
    evidence["intent"] = "generic_test_intent"
    return context, evidence


def test_semantic_plan_with_authorized_metric_and_operation_survives():
    context, evidence = _fixture()
    result = build_plan({
        "context": context,
        "question": "highest amount by region",
        "normalized_question": "highest amount by region",
        "intent": "generic_test_intent",
        "intent_confidence": 0.75,
        "intent_resolution_result": evidence,
        "errors": [],
    })
    assert result["final_status"] == "processing", result.get("errors")
    projection = result["query_plan"]["planning_context"]
    assert len(projection["planned_metrics"]) == 1
    assert len(projection["analytical_operations"]) == 1
    assert missing_semantic_plan_bindings(
        context=context, interpretation=evidence,
        query_plan=result["query_plan"],
    ) == []


def test_semantic_claim_without_metric_is_rejected_even_if_plan_is_planned():
    context, evidence = _fixture()
    changed = deepcopy(evidence)
    concepts = changed["best_candidate"]["matches"][0]["match_details"]["concepts"]
    for concept in concepts:
        if concept.get("concept_name") == "financial_metric":
            concept["terms"][0]["normalized_term"] = "not-in-catalog"
            concept["terms"][0]["match_details"]["semantic_signal"]["normalized_term"] = (
                "not-in-catalog"
            )
    output = build_plan({
        "context": context, "question": "highest amount",
        "normalized_question": "highest amount", "intent": "generic_test_intent",
        "intent_confidence": 0.75, "intent_resolution_result": changed,
        "errors": [],
    })
    assert output["final_status"] == "rejected"
    assert output["errors"][-1]["code"] in {
        "PLANNING_SEMANTIC_BINDING_INCOMPLETE",
        "PLANNING_ANALYTICAL_BINDING_INCOMPLETE",
    }
    assert not output.get("query_plan")


def test_guard_cannot_be_bypassed_with_unknown_role_configuration():
    context, evidence = _fixture()
    context["intent_resolution"]["config"]["concept_roles"] = {}
    missing = missing_semantic_plan_bindings(
        context=context, interpretation=evidence,
        query_plan={"planning_context": {"planned_metrics": [],
                                          "analytical_operations": []}},
    )
    assert missing == ["no_plannable_role"]


def test_exact_aliases_are_required_not_merely_same_kind_of_entity():
    context, evidence = _fixture()
    plan = {
        "planning_context": {
            "planned_metrics": [{
                "matched_user_term": "volume",
                "target_table": "any_authorized_table",
            }],
            "analytical_operations": [{
                "matched_user_term": "lowest",
            }],
            "detected_dimensions": [],
        },
    }
    assert missing_semantic_plan_bindings(
        context=context, interpretation=evidence,
        query_plan=plan,
    ) == ["metric", "operation"]


def test_deterministic_plans_are_unchanged_without_llm_interpretation():
    context, evidence = _fixture()
    evidence["reason"] = "score_applied"
    assert missing_semantic_plan_bindings(
        context=context, interpretation=evidence, query_plan={},
    ) == []



def _period_fixture(*, schema: str, table: str, date_column: str):
    context, evidence = _fixture()
    context["intent_resolution"]["config"]["concept_roles"] = {
        "period": ["period_concept"],
    }
    evidence["best_candidate"]["matches"][0]["match_details"]["concepts"].append({
        "concept_name": "period_concept",
        "satisfied": True,
        "semantic_signals": [{
            "concept_name": "period_concept",
            "normalized_term": "during closing cycle",
        }],
    })
    context["table_catalog"].append({
        "schema_name": schema,
        "table_name": table,
        "date_columns": [date_column],
        "columns": [{"name": date_column}, {"name": "product_code"}],
    })
    return context, evidence, schema + "." + table


def test_unrelated_filter_cannot_satisfy_semantic_period_role():
    context, evidence, qualified = _period_fixture(
        schema="ledger_a", table="entries", date_column="period_day",
    )
    plan = {
        "planning_context": {
            "temporal_series": None,
            "planned_filters": [{
                "binding_ref": "filter-x",
                "matched_user_term": "during closing cycle",
            }],
            "resolved_filter_bindings": [{
                "binding_ref": "filter-x",
                "target_table": qualified,
                "target_column": "product_code",
            }],
        },
    }
    assert missing_semantic_plan_bindings(
        context=context, interpretation=evidence, query_plan=plan,
    ) == ["period"]
    # Simply appending an unrelated filter is never time authorization.
    plan["planning_context"]["planned_filters"].append({
        "binding_ref": "other",
        "matched_user_term": "product",
    })
    assert missing_semantic_plan_bindings(
        context=context, interpretation=evidence, query_plan=plan,
    ) == ["period"]


def test_period_filter_must_match_both_alias_and_authorized_date_target():
    context, evidence, qualified = _period_fixture(
        schema="ledger_b", table="transactions", date_column="posting_date",
    )
    plan = {
        "planning_context": {
            "temporal_series": None,
            "planned_filters": [{
                "binding_ref": "f-date",
                "matched_user_term": "wrong-period-alias",
            }],
            "resolved_filter_bindings": [{
                "binding_ref": "f-date",
                "target_table": qualified,
                "target_column": "posting_date",
            }],
        },
    }
    assert missing_semantic_plan_bindings(
        context=context, interpretation=evidence, query_plan=plan,
    ) == ["period"]
    plan["planning_context"]["planned_filters"][0][
        "matched_user_term"
    ] = "during closing cycle"
    assert missing_semantic_plan_bindings(
        context=context, interpretation=evidence, query_plan=plan,
    ) == []
    plan["planning_context"]["resolved_filter_bindings"][0][
        "target_column"
    ] = "unregistered_date"
    assert missing_semantic_plan_bindings(
        context=context, interpretation=evidence, query_plan=plan,
    ) == ["period"]


def test_temporal_series_needs_authorized_date_and_cited_period():
    context, evidence, qualified = _period_fixture(
        schema="bookkeeping_x", table="period_movements",
        date_column="settlement_date",
    )
    plan = {
        "planning_context": {
            "temporal_series": {
                "date_table": qualified, "date_column": "settlement_date",
                "period_reference_terms": [],
            },
        },
    }
    assert missing_semantic_plan_bindings(
        context=context, interpretation=evidence, query_plan=plan,
    ) == ["period"]
    plan["planning_context"]["temporal_series"][
        "period_reference_terms"
    ] = ["during closing cycle"]
    assert missing_semantic_plan_bindings(
        context=context, interpretation=evidence, query_plan=plan,
    ) == []
    plan["planning_context"]["temporal_series"][
        "date_column"
    ] = "some_other_field"
    assert missing_semantic_plan_bindings(
        context=context, interpretation=evidence, query_plan=plan,
    ) == ["period"]


def test_period_validation_ports_without_date_field_hardcoding():
    for schema, table, column in (
        ("client_one", "ledger", "posted_at"),
        ("client_two", "payables", "clearing_day"),
    ):
        context, evidence, qualified = _period_fixture(
            schema=schema, table=table, date_column=column,
        )
        plan = {
            "planning_context": {
                "planned_filters": [{
                    "binding_ref": "date-binding",
                    "matched_user_term": "during closing cycle",
                }],
                "resolved_filter_bindings": [{
                    "binding_ref": "date-binding",
                    "target_table": qualified,
                    "target_column": column,
                }],
            },
        }
        assert missing_semantic_plan_bindings(
            context=context, interpretation=evidence, query_plan=plan,
        ) == []
        assert schema not in str(missing_semantic_plan_bindings(
            context=context, interpretation=evidence, query_plan=plan,
        ))


if __name__ == "__main__":
    import inspect
    tests = sorted(
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and inspect.isfunction(fn)
    )
    for name, fn in tests:
        fn()
        print("PASS " + name)
    print("SEMANTIC_PLAN_GATE_TESTS=" + str(len(tests)))
