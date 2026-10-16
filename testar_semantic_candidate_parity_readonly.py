from __future__ import annotations

from copy import deepcopy

from scripts.audit_semantic_candidate_parity_readonly import (
    compare_semantic_snapshots,
    parse_parity_policy,
)


def policy() -> dict:
    return {
        "source_version": "synthetic-a",
        "candidate_version": "synthetic-b",
        "allowed_new_rules": [
            {"rule_group": "component_config", "rule_name": "new_feature"}
        ],
    }


def snapshots() -> tuple[dict, dict]:
    original = {
        "version": "synthetic-a",
        "fingerprint": "a" * 64,
        "rules": [
            {"rule_group": "platform", "rule_name": "baseline", "rule_content": {"mode": "safe"}}
        ],
        "entities": [{"entity_type": "synthetic_metric", "canonical_value": "alpha"}],
        "dre_mappings": [],
        "query_patterns": [{"intent_name": "test", "sql_pattern": ""}],
        "table_catalog": [{"schema_name": "test", "table_name": "facts", "date_columns": ["event_date"]}],
    }
    proposed = deepcopy(original)
    proposed["version"] = "synthetic-b"
    proposed["fingerprint"] = "b" * 64
    proposed["rules"].append({
        "rule_group": "component_config",
        "rule_name": "new_feature",
        "rule_content": {"feature": "versioned"},
    })
    return original, proposed


def codes(report: dict) -> set[str]:
    return set(report["blocking_codes"])


def test_parity_matches_only_authorized_addition() -> None:
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


def test_policy_is_strict_and_versioned() -> None:
    for bad in (
        {},
        {"source_version": "x", "candidate_version": "x", "allowed_new_rules": []},
        {"source_version": "x", "candidate_version": "y", "allowed_new_rules": [{}]},
        {"source_version": "x", "candidate_version": "y", "allowed_new_rules": [
            {"rule_group": "A", "rule_name": "b"},
            {"rule_group": "a", "rule_name": "B"},
        ]},
        {"source_version": "x", "candidate_version": "y", "allowed_new_rules": [],
         "allow_everything": True},
    ):
        try:
            parse_parity_policy(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed or permissive policy accepted")


if __name__ == "__main__":
    test_parity_matches_only_authorized_addition()
    test_same_count_payload_mutation_is_blocked()
    test_unlisted_additions_and_removals_are_blocked()
    test_rule_additions_must_exist_exactly_once()
    test_invalid_versions_fingerprints_and_collection_types_fail_closed()
    test_policy_is_strict_and_versioned()
    print("SEMANTIC_CANDIDATE_PARITY_READONLY=PASS")
