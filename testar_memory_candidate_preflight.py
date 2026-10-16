from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

from app.domain.context_normalizer import normalize_context_snapshot
from scripts.audit_semantic_candidate_parity_readonly import (
    compare_semantic_snapshots,
)
from scripts.preview_semantic_candidate_readonly import (
    evaluate_in_memory_preflight,
    main,
    synthesize_candidate_snapshot,
)


def _baseline_raw() -> dict:
    return {
        "semantic_agent_version": "synthetic-v1",
        "semantic_context_source": "offline_fixture",
        "regras": [{
            "rule_group": "synthetic",
            "rule_name": "base",
            "rule_content": {},
            "applies_to_intents": [],
            "validation_hint": None,
            "severity": "info",
            "priority": 1,
        }],
        "entidades": [{
            "entity_type": "metric_binding",
            "canonical_value": "measure",
            "user_term": "measure",
            "target_table": None,
            "target_column": None,
            "sql_filter_hint": None,
            "business_rule": {
                "metric_binding": {
                    "metric_concept": "measure",
                    "target_table": "synthetic.facts",
                    "target_column": "amount",
                    "when_present": ["source_a"],
                }
            },
            "priority": 1,
        }],
        "dre": [],
        "padroes": [{
            "intent_name": "trend",
            "pattern_name": "synthetic_trend",
            "business_question_examples": [],
            "required_tables": ["synthetic.facts"],
            "required_rules": [],
            "sql_pattern": "",
            "notes": "synthetic only",
            "priority": 1,
        }],
        "catalogo": [{
            "schema_name": "synthetic",
            "table_name": "facts",
            "table_type": "fact",
            "description": "synthetic fixture",
            "grain": {},
            "primary_key": [],
            "key_columns": [],
            "metric_columns": ["amount"],
            "date_columns": ["event_date"],
            "join_rules": [],
            "ai_hint": {},
            "priority": 1,
        }],
    }


def _policy() -> dict:
    rule = {
        "rule_group": "component_config",
        "rule_name": "temporal_config",
        "rule_content": {
            "component": "temporal_planning",
            "required_intents": ["trend"],
            "date_binding_strategy": "configured_metric_source_date",
            "date_bindings": [{
                "metric_concept": "measure",
                "target_table": "synthetic.facts",
                "target_column": "event_date",
            }],
            "granularities": [{
                "grain": "month",
                "terms": ["monthly", "by month"],
            }],
        },
        "applies_to_intents": ["trend"],
        "validation_hint": None,
        "severity": "error",
        "priority": 20,
    }
    return {
        "source_version": "synthetic-v1",
        "candidate_version": "synthetic-v2",
        "allowed_new_rules": [{
            "rule_group": rule["rule_group"],
            "rule_name": rule["rule_name"],
            "expected_record": rule,
        }],
    }


def _normalized_source() -> dict:
    return normalize_context_snapshot(_baseline_raw())


def test_preview_is_normalized_pure_and_exactly_parity_matched() -> None:
    source = _normalized_source()
    policy = _policy()
    original = deepcopy(source)
    original_policy = deepcopy(policy)
    candidate = synthesize_candidate_snapshot(source, policy)
    assert source == original and policy == original_policy
    assert source["version"] == "synthetic-v1"
    assert candidate["version"] == "synthetic-v2"
    assert candidate["fingerprint"] != source["fingerprint"]
    assert candidate["counts"]["rules"] == source["counts"]["rules"] + 1
    assert len(candidate["rules"]) == len(source["rules"]) + 1
    assert candidate["component_configs"]["temporal_planning"][
        "date_binding_strategy"
    ] == "configured_metric_source_date"
    assert compare_semantic_snapshots(source, candidate, policy)[
        "status"
    ] == "parity_match"
    candidate["rules"][0]["rule_name"] = "changed"
    assert source == original


def test_preview_report_never_claims_activation_or_financial_verification() -> None:
    report = evaluate_in_memory_preflight(_normalized_source(), _policy())
    assert report["parity_status"] == "parity_match"
    assert report["source_fingerprint"] != report["candidate_fingerprint"]
    assert report["candidate_readiness_status"] == "checks_passed"
    assert report["persisted_candidate"] is False
    assert report["activation_authorized"] is False
    assert report["financial_semantics_verified"] is False
    assert report["physical_schema_verified"] is False
    assert report["read_only"] is True
    assert report["benchmark_access"] is False
    assert report["llm_calls"] == 0
    assert report["real_sql_execution"] is False
    assert "amount" not in str(report)
    assert "synthetic.facts" not in str(report)


def test_preview_blocks_missing_temporal_source_without_business_defaults() -> None:
    raw = _baseline_raw()
    raw["catalogo"].append({
        **deepcopy(raw["catalogo"][0]),
        "table_name": "other_facts",
    })
    raw["entidades"].append({
        **deepcopy(raw["entidades"][0]),
        "user_term": "other",
        "business_rule": {
            "metric_binding": {
                "metric_concept": "measure",
                "target_table": "synthetic.other_facts",
                "target_column": "amount",
            }
        },
    })
    result = evaluate_in_memory_preflight(
        normalize_context_snapshot(raw), _policy()
    )
    assert result["status"] == "blocked"
    assert "TEMPORAL_EXPLICIT_BINDING_MISSING_OR_AMBIGUOUS" in (
        result["candidate_readiness_blocking_codes"]
    )


def test_preview_rejects_collisions_and_bad_source() -> None:
    source = _normalized_source()
    for altered in (
        {**source, "version": "unexpected"},
        {**source, "fingerprint": "invalid"},
        {**source, "entities": None},
    ):
        try:
            synthesize_candidate_snapshot(altered, _policy())
        except ValueError:
            pass
        else:
            raise AssertionError("malformed source was accepted")

    duplicate_rule = deepcopy(source)
    duplicate_rule["rules"].append(
        deepcopy(_policy()["allowed_new_rules"][0]["expected_record"])
    )
    try:
        synthesize_candidate_snapshot(duplicate_rule, _policy())
    except ValueError:
        pass
    else:
        raise AssertionError("existing candidate rule was overridden")

    existing_component = deepcopy(source)
    existing_component["rules"][0]["rule_content"] = {
        "component": "temporal_planning"
    }
    try:
        synthesize_candidate_snapshot(existing_component, _policy())
    except ValueError:
        pass
    else:
        raise AssertionError("existing component was overridden")


def test_cli_prevents_database_access_without_sql_execution_gate() -> None:
    with patch("sys.argv", ["preview", "--policy", "unused.json"]), patch.dict(
        "os.environ", {"LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "true"}
    ), patch(
        "scripts.preview_semantic_candidate_readonly.PostgresContextRepository"
    ) as repository:
        assert main() == 3
        repository.assert_not_called()


if __name__ == "__main__":
    test_preview_is_normalized_pure_and_exactly_parity_matched()
    test_preview_report_never_claims_activation_or_financial_verification()
    test_preview_blocks_missing_temporal_source_without_business_defaults()
    test_preview_rejects_collisions_and_bad_source()
    test_cli_prevents_database_access_without_sql_execution_gate()
    print("MEMORY_CANDIDATE_PREFLIGHT=PASS")
