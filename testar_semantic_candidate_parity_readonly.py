from __future__ import annotations

from copy import deepcopy

from scripts.audit_semantic_candidate_parity_readonly import (
    compare_semantic_snapshots,
    parse_parity_policy,
)


def new_rule() -> dict:
    return {
        "rule_group": "component_config",
        "rule_name": "new_feature",
        "rule_content": {"feature": "versioned", "limit": 0},
        "applies_to_intents": ["synthetic_intent"],
        "validation_hint": None,
        "severity": "info",
        "priority": 20,
    }


def policy() -> dict:
    return {
        "source_version": "synthetic-a",
        "candidate_version": "synthetic-b",
        "allowed_new_rules": [{
            "rule_group": "component_config",
            "rule_name": "new_feature",
            "expected_record": new_rule(),
        }],
    }


def snapshots() -> tuple[dict, dict]:
    original = {
        "version": "synthetic-a",
        "fingerprint": "a" * 64,
        "rules": [{
            "rule_group": "platform",
            "rule_name": "baseline",
            "rule_content": {"mode": "safe"},
            "applies_to_intents": [],
            "validation_hint": None,
            "severity": "info",
            "priority": 1,
        }],
        "entities": [{"entity_type": "synthetic_metric", "canonical_value": "alpha"}],
        "dre_mappings": [],
        "query_patterns": [{"intent_name": "test", "sql_pattern": ""}],
        "table_catalog": [{
            "schema_name": "test",
            "table_name": "facts",
            "date_columns": ["event_date"],
        }],
    }
    proposed = deepcopy(original)
    proposed["version"] = "synthetic-b"
    proposed["fingerprint"] = "b" * 64
    proposed["rules"].append(new_rule())
    return original, proposed


def codes(report: dict) -> set[str]:
    return set(report["blocking_codes"])


def test_parity_matches_only_exact_authorized_addition() -> None:
    source, candidate = snapshots()
    original = deepcopy(source)
    proposal = deepcopy(candidate)
    report = compare_semantic_snapshots(source, candidate, policy())
    assert report["status"] == "parity_match", report
    assert report["allowed_new_rule_count"] == 1
    assert report["activation_authorized"] is False
    assert report["financial_validation_complete"] is False
    assert report["real_sql_execution"] is False
    assert report["llm_calls"] == 0
    assert report["benchmark_access"] is False
    assert source == original and candidate == proposal


def test_same_count_payload_mutation_is_blocked() -> None:
    src, dest = snapshots()
    dest["entities"][0]["canonical_value"] = "tampered"
    report = compare_semantic_snapshots(src, dest, policy())
    assert report["status"] == "blocked"
    assert "COLLECTION_MISMATCH_ENTITIES" in codes(report)
    assert "tampered" not in str(report)


def test_allowed_rule_content_and_metadata_must_be_exact() -> None:
    for field, value in (
        ("rule_content", {"feature": "versioned", "limit": 999}),
        ("priority", 999),
        ("severity", "critical"),
        ("applies_to_intents", ["another_intent"]),
    ):
        src, dest = snapshots()
        dest["rules"][1][field] = value
        report = compare_semantic_snapshots(src, dest, policy())
        assert report["status"] == "blocked", (field, report)
        assert "ALLOWED_RULE_PAYLOAD_MISMATCH" in codes(report), field
        assert "another_intent" not in str(report)
        assert "999" not in str(report)


def test_unlisted_additions_and_removals_are_blocked() -> None:
    src, dest = snapshots()
    dest["rules"].append({
        "rule_group": "unexpected",
        "rule_name": "secret_override",
        "rule_content": {"new": True},
    })
    assert "COLLECTION_MISMATCH_RULES" in codes(
        compare_semantic_snapshots(src, dest, policy())
    )
    src, dest = snapshots()
    dest["table_catalog"] = []
    assert "COLLECTION_MISMATCH_TABLE_CATALOG" in codes(
        compare_semantic_snapshots(src, dest, policy())
    )


def test_rule_additions_must_exist_exactly_once() -> None:
    src, dest = snapshots()
    dest["rules"] = dest["rules"][:1]
    assert "ALLOWED_RULE_MISSING_OR_DUPLICATED" in codes(
        compare_semantic_snapshots(src, dest, policy())
    )
    src, dest = snapshots()
    dest["rules"].append(deepcopy(dest["rules"][1]))
    assert "ALLOWED_RULE_MISSING_OR_DUPLICATED" in codes(
        compare_semantic_snapshots(src, dest, policy())
    )
    src, dest = snapshots()
    src["rules"].append(deepcopy(dest["rules"][1]))
    assert "ALLOWED_RULE_ALREADY_IN_SOURCE" in codes(
        compare_semantic_snapshots(src, dest, policy())
    )


def test_invalid_versions_fingerprints_and_collection_types_fail_closed() -> None:
    src, dest = snapshots()
    dest["version"] = "unexpected"
    dest["fingerprint"] = ""
    dest["query_patterns"] = "not_a_list"
    report = compare_semantic_snapshots(src, dest, policy())
    assert {
        "CANDIDATE_VERSION_MISMATCH",
        "FINGERPRINT_MISSING",
        "COLLECTION_MISMATCH_QUERY_PATTERNS",
    } <= codes(report)


def test_policy_requires_full_versioned_payload() -> None:
    duplicate = deepcopy(policy()["allowed_new_rules"][0])
    duplicate["rule_group"] = "COMPONENT_CONFIG"
    duplicate["rule_name"] = "NEW_FEATURE"
    for bad in (
        {},
        {"source_version": "x", "candidate_version": "x", "allowed_new_rules": []},
        {"source_version": "x", "candidate_version": "y", "allowed_new_rules": [{}]},
        {"source_version": "x", "candidate_version": "y", "allowed_new_rules": [
            {"rule_group": "component_config", "rule_name": "new_feature"},
        ]},
        {**policy(), "allowed_new_rules": [
            policy()["allowed_new_rules"][0],
            duplicate,
        ]},
        {**policy(), "allowed_new_rules": [
            {**policy()["allowed_new_rules"][0], "expected_record": {"rule_group": "bad"}},
        ]},
        {**policy(), "allowed_new_rules": [
            {**policy()["allowed_new_rules"][0], "expected_record": {
                **new_rule(), "rule_name": "unexpected",
            }},
        ]},
        {**policy(), "allow_everything": True},
    ):
        try:
            parse_parity_policy(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed or permissive parity policy accepted")


if __name__ == "__main__":
    test_parity_matches_only_exact_authorized_addition()
    test_same_count_payload_mutation_is_blocked()
    test_allowed_rule_content_and_metadata_must_be_exact()
    test_unlisted_additions_and_removals_are_blocked()
    test_rule_additions_must_exist_exactly_once()
    test_invalid_versions_fingerprints_and_collection_types_fail_closed()
    test_policy_requires_full_versioned_payload()
    print("SEMANTIC_CANDIDATE_PARITY_READONLY=PASS")
