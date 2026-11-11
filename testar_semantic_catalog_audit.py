"""No-LLM, no-database tenant metadata audit; synthetic cross-client fixtures."""
from __future__ import annotations

from copy import deepcopy

from app.domain.semantic_catalog_audit import audit_semantic_catalog
from testar_planner import _metric_context, _append_metric_alias, _append_metric_binding


def _base_context():
    # Tests focus on physical metadata independently of role bindings.
    # This legacy test fixture contains names not present in its synthetic
    # intent catalog; role validation is tested separately below.
    context = _metric_context()
    context["intent_resolution"]["config"]["concept_roles"] = {}
    return context


def _tenant(*, schema: str, table: str, metric: str) -> dict:
    context = deepcopy(_base_context())
    # Changing all schema references is deliberate: the engine, not these
    # test values, is the product. No branches depend on client identity.
    def rewrite(value):
        if isinstance(value, dict):
            return {k: rewrite(v) for k, v in value.items()}
        if isinstance(value, list):
            return [rewrite(v) for v in value]
        if isinstance(value, str):
            return value.replace("schema_test", schema).replace(
                "fact_metrics", table,
            ).replace("amount", metric)
        return value
    return rewrite(context)


def test_two_distinct_tenants_use_identical_audit_code():
    for schema, table, metric in (
        ("bookkeeping", "ledger_entries", "net_measure"),
        ("customer_erp", "transactions", "settled_value"),
    ):
        original = _tenant(schema=schema, table=table, metric=metric)
        before = deepcopy(original)
        result = audit_semantic_catalog(original)
        assert original == before
        assert result["status"] == "INVENTORY_COMPLETE", result
        assert result["counts"]["valid_metric_aliases"] == 2
        assert result["counts"]["valid_operations"] == 2
        assert result["counts"]["metric_concepts_without_explicit_bindings"] == 2
        assert result["business_binding_review_required"] is True
        assert result["financial_parity_verified"] is False
        assert result["automated_activation_authorized"] is False
        assert result["provider_calls"] == 0
        assert result["sql_executed"] is False
        assert schema not in repr(result)
        assert table not in repr(result)
        assert metric not in repr(result)


def test_invalid_physical_metric_is_reported_without_leaking_metadata():
    context = _base_context()
    metric = next(e for e in context["entities"] if e["entity_type"] == "financial_metric")
    metric["target_column"] = "nonexistent_column"
    result = audit_semantic_catalog(context)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["issue_counts"]["metric_physical_binding_invalid"] == 1
    assert "nonexistent_column" not in repr(result)


def test_ambiguous_aliases_require_review_not_priority_guess():
    context = _base_context()
    _append_metric_alias(
        context, user_term="amount", canonical_value="different_measure",
        metric_concept="different_measure",
        target_table="schema_test.fact_metrics", target_column="volume_value",
    )
    result = audit_semantic_catalog(context)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["issue_counts"]["metric_alias_ambiguous"] == 1


def test_valid_conditional_binding_does_not_claim_every_metric_complete():
    context = _base_context()
    _append_metric_binding(context, when_present=["approved_predicate"])
    result = audit_semantic_catalog(context)
    assert result["status"] == "INVENTORY_COMPLETE", result
    assert result["counts"]["valid_metric_bindings"] == 1
    assert result["counts"]["metric_concepts_without_explicit_bindings"] == 1
    assert result["business_binding_review_required"] is True


def test_invalid_binding_and_missing_roles_are_fail_closed():
    context = _base_context()
    _append_metric_binding(context, when_present=["approved_predicate"])
    entity = context["entities"][-1]
    entity["target_column"] = "unknown_column"
    output = audit_semantic_catalog(context)
    assert output["status"] == "REVIEW_REQUIRED"
    assert output["issue_counts"]["metric_binding_invalid"] == 1
    context["intent_resolution"]["config"]["concept_roles"] = {
        "operation": ["nonexistent_concept"],
    }
    blocked = audit_semantic_catalog(context)
    assert blocked["status"] == "BLOCKED"
    assert blocked["reason"] == "role_concept_unresolved"


def test_context_and_question_data_never_enter_reports():
    context = _base_context()
    context["secret_question"] = "confidential_question_marker"
    context["private_sql"] = "SELECT secret_text FROM vault"
    result = audit_semantic_catalog(context)
    assert result["status"] == "INVENTORY_COMPLETE"
    assert "confidential_question_marker" not in repr(result)
    assert "SELECT secret_text" not in repr(result)
    assert "financial_metric" in result["entity_types"]
    assert result["metric_binding_policy_inferred"] is False


if __name__ == "__main__":
    tests = sorted(
        (name, value) for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    )
    for name, test in tests:
        test()
        print("PASS " + name)
    print("SEMANTIC_CATALOG_AUDIT_TESTS=" + str(len(tests)))
