from __future__ import annotations

from scripts.audit_semantic_context_readonly import inventory


def test_audit_preserves_unknown_business_semantics() -> None:
    snapshot = {
        "version": "synthetic-v1",
        "fingerprint": "a" * 64,
        "entities": [
            {
                "entity_type": "financial_metric",
                "user_term": "metric alpha",
                "canonical_value": "alpha",
                "target_table": "test.fact",
                "target_column": "value",
                "business_rule": {"metric": {"metric_concept": "alpha"}},
            },
            {
                "entity_type": "metric_binding",
                "user_term": "binding alpha",
                "canonical_value": "alpha",
                "target_table": "test.fact",
                "target_column": "value",
                "business_rule": {"metric_binding": {
                    "metric_concept": "alpha",
                    "when_present": ["selected"],
                }},
            },
        ],
        "dre_mappings": [],
        "table_catalog": [],
        "component_configs": {},
    }
    result = inventory(snapshot, term="metric alpha")
    assert result["term_probe"]["status"] == "candidate_bindings_present"
    assert result["llm_calls"] == 0
    assert result["real_sql_execution"] is False
    assert result["metric_alias_count"] == 1
    assert result["metric_binding_count"] == 1
    assert result["revenue_dre_mapping_count"] == 0


if __name__ == "__main__":
    test_audit_preserves_unknown_business_semantics()
    print("SEMANTIC_CONTEXT_AUDIT=PASS")
