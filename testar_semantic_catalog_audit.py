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



def test_catalog_without_version_or_fingerprint_fails_closed():
    for key, invalid, reason in (
        ("version", "", "context_version_missing"),
        ("fingerprint", None, "context_fingerprint_invalid"),
        ("fingerprint", "invalid", "context_fingerprint_invalid"),
    ):
        context = _base_context()
        context[key] = invalid
        report = audit_semantic_catalog(context)
        assert report["status"] == "BLOCKED"
        assert report["reason"] == reason
        assert report["automated_activation_authorized"] is False


def test_same_alias_for_metric_and_operation_requires_review():
    context = _base_context()
    operation = next(
        entry for entry in context["entities"]
        if entry.get("entity_type") == "analytical_operation"
    )
    metric = next(
        entry for entry in context["entities"]
        if entry.get("entity_type") == "financial_metric"
    )
    operation["user_term"] = metric["user_term"]
    report = audit_semantic_catalog(context)
    assert report["status"] == "REVIEW_REQUIRED"
    assert report["issue_counts"]["cross_role_alias_ambiguous"] == 1
    assert "user_term" not in repr(report)


def test_custom_entity_type_is_not_disclosed():
    context = _base_context()
    context["entities"].append({
        "entity_type": "internal_customer_secret_taxonomy",
        "user_term": "confidential_marker",
    })
    report = audit_semantic_catalog(context)
    assert report["status"] == "INVENTORY_COMPLETE"
    assert report["entity_types"]["other"] >= 1
    assert "internal_customer_secret_taxonomy" not in repr(report)
    assert "confidential_marker" not in repr(report)



def test_semantic_vocabulary_gap_is_detected_without_inventing_aliases():
    context = _base_context()
    metric_alias = next(
        entry["user_term"] for entry in context["entities"]
        if entry.get("entity_type") == "financial_metric"
    )
    operation_alias = next(
        entry["user_term"] for entry in context["entities"]
        if entry.get("entity_type") == "analytical_operation"
    )
    context["intent_resolution"] = {
        "config": {
            "concept_roles": {
                "metric": ["measure_class"],
                "operation": ["operation_class"],
            },
        },
        "intent_catalog": [
            {
                "intent_name": "synthetic_operation",
                "rules": [{
                    "effect": "require",
                    "concepts": [
                        {"concept_name": "measure_class",
                         "terms": [metric_alias, "unmapped_user_synonym"]},
                        {"concept_name": "operation_class",
                         "terms": [operation_alias, "unmapped_operation_synonym"]},
                    ],
                }],
            },
        ],
    }
    report = audit_semantic_catalog(context)
    assert report["status"] == "INVENTORY_COMPLETE"
    for role in ("metric", "operation"):
        assert report["semantic_role_lexicon_coverage"][role] == {
            "catalog_alias_terms": 2,
            "physically_resolved_terms": 1,
            "unbound_alias_terms": 1,
        }
    assert report["semantic_fallback_binding_review_required"] is True
    assert "unmapped_user_synonym" not in repr(report)
    assert "unmapped_operation_synonym" not in repr(report)
    assert report["financial_parity_verified"] is False
    assert report["automated_activation_authorized"] is False


def test_lexicon_differences_do_not_change_context_of_tenant_schemas():
    base = _base_context()
    for schema, table, term in (
        ("alpha_ledger", "balance_rows", "flow"),
        ("beta_book", "invoice_facts", "volume"),
    ):
        context = _tenant(schema=schema, table=table, metric=term)
        alias = next(
            entry["user_term"] for entry in context["entities"]
            if entry.get("entity_type") == "financial_metric"
        )
        context["intent_resolution"] = {
            "config": {"concept_roles": {"metric": ["role_measure"]}},
            "intent_catalog": [{
                "intent_name": "tenant_metric_operation",
                "rules": [{
                    "effect": "positive_score",
                    "concepts": [{
                        "concept_name": "role_measure",
                        "terms": [alias],
                    }],
                }],
            }],
        }
        report = audit_semantic_catalog(context)
        assert report["status"] == "INVENTORY_COMPLETE"
        assert report["semantic_role_lexicon_coverage"]["metric"] == {
            "catalog_alias_terms": 1,
            "physically_resolved_terms": 1,
            "unbound_alias_terms": 0,
        }
        assert report["semantic_fallback_binding_review_required"] is False
        assert schema not in repr(report)
        assert table not in repr(report)


if __name__ == "__main__":
    tests = sorted(
        (name, value) for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    )
    for name, test in tests:
        test()
        print("PASS " + name)
    print("SEMANTIC_CATALOG_AUDIT_TESTS=" + str(len(tests)))
