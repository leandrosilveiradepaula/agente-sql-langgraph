from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.context_validator import validate_context_snapshot
from testar_context_validator import _raw_snapshot
from scripts.preview_semantic_overlay_readonly import (
    apply_semantic_overlay,
    main,
    parse_overlay_policy,
)


def fixture() -> dict:
    # Reuse the validated structural contract rather than inventing an
    # incomplete synthetic context that fails before overlay logic runs.
    raw = _raw_snapshot()
    rules = raw["entidades"][1]["business_rule"]["intent_catalog"]["rules"]
    rules.extend([
        {
            "rule_name": "primary",
            "effect": "positive_score",
            "score": 120,
            "priority": 4,
            "minimum_concept_matches": 1,
            "concepts": [{
                "concept_name": "operation",
                "terms": ["compare"],
                "match_mode": "contains",
                "minimum_term_matches": 1,
            }],
        },
        {
            "rule_name": "exclusion",
            "effect": "exclude",
            "score": None,
            "priority": 5,
            "minimum_concept_matches": 1,
            "concepts": [{
                "concept_name": "operation",
                "terms": ["compare"],
                "match_mode": "contains",
                "minimum_term_matches": 1,
            }],
        },
    ])
    raw["semantic_agent_version"] = "synthetic-v1"
    source = normalize_context_snapshot(raw)
    result = validate_context_snapshot(source)
    assert result["status"] == "valid", {
        item["code"] for item in result["errors"]
    }
    return source

def overlay(changes: list[dict]) -> dict:
    return {
        "source_version": "synthetic-v1",
        "candidate_version": "synthetic-v2",
        "changes": changes,
    }


def selector(rule: str) -> dict:
    return {
        "intent_name": "intent_test",
        "rule_name": rule,
        "concept_name": "operation",
    }


def assert_blocked(source: dict, policy: dict) -> None:
    try:
        apply_semantic_overlay(source, policy)
    except ValueError:
        return
    raise AssertionError("unsafe semantic overlay was accepted")


def test_extend_terms_does_not_mutate_source() -> None:
    source = fixture()
    before = deepcopy(source)
    candidate = apply_semantic_overlay(source, overlay([{
        "operation": "extend_concept_terms",
        "selector": selector("primary"),
        "terms": ["contrast"],
    }]))
    assert source == before
    assert candidate["version"] == "synthetic-v2"
    assert candidate["fingerprint"] != source["fingerprint"]
    assert candidate["rules"] == source["rules"]
    assert candidate["query_patterns"] == source["query_patterns"]
    assert candidate["table_catalog"] == source["table_catalog"]


def test_mirror_terms_requires_compatible_match_modes() -> None:
    source = fixture()
    candidate = apply_semantic_overlay(source, overlay([{
        "operation": "extend_concept_terms",
        "selector": selector("primary"),
        "terms": ["contrast"],
    }, {
        "operation": "mirror_concept_terms",
        "source": selector("primary"),
        "target": selector("exclusion"),
    }]))
    assert candidate["version"] == "synthetic-v2"
    assert source["version"] == "synthetic-v1"


def test_alias_clone_does_not_modify_existing_signal() -> None:
    source = fixture()
    original = deepcopy(source)
    candidate = apply_semantic_overlay(source, overlay([{
        "operation": "clone_entity_alias",
        "source": {
            "entity_type": "intent_signal",
            "user_term": "generic analysis",
            "canonical_value": "intent_test",
        },
        "new_user_term": "alternative analysis",
    }]))
    assert source == original
    assert len(candidate["entities"]) == len(source["entities"]) + 1
    assert candidate["counts"]["entities"] == source["counts"]["entities"] + 1
    assert validate_context_snapshot(candidate)["status"] == "valid"



def test_exact_catalog_exclusion_is_versioned_and_immutable() -> None:
    source = fixture()
    original = deepcopy(source)
    candidate = apply_semantic_overlay(source, overlay([{
        "operation": "add_catalog_exclusion",
        "source": selector("primary"),
        "target_intent": "intent_test",
        "rule_name": "synthetic_operation_guard",
        "priority": 6,
    }]))
    assert source == original
    assert candidate["fingerprint"] != source["fingerprint"]
    assert candidate["counts"] == source["counts"]
    assert candidate["rules"] == source["rules"]
    assert candidate["table_catalog"] == source["table_catalog"]
    rules = candidate["entities"][1]["business_rule"]["intent_catalog"]["rules"]
    addition = [r for r in rules if r["rule_name"] == "synthetic_operation_guard"]
    assert len(addition) == 1
    assert addition[0]["effect"] == "exclude"
    assert addition[0]["score"] is None
    assert addition[0]["concepts"][0]["terms"] == ["compare"]
    assert validate_context_snapshot(candidate)["status"] == "valid"


def test_catalog_exclusion_rejects_implicit_or_ambiguous_mutations() -> None:
    valid = {
        "operation": "add_catalog_exclusion",
        "source": selector("primary"),
        "target_intent": "intent_test",
        "rule_name": "synthetic_operation_guard",
        "priority": 6,
    }
    for bad in (
        {**valid, "target_intent": "missing_intent"},
        {**valid, "rule_name": "primary"},
        {**valid, "source": selector("missing")},
        {**valid, "priority": True},
        {**valid, "priority": 0},
        {**valid, "score": 100},
        {**valid, "effect": "positive_score"},
    ):
        try:
            parse_overlay_policy(overlay([bad]))
        except ValueError:
            continue
        assert_blocked(fixture(), overlay([bad]))



def test_invalid_policies_fail_closed() -> None:
    for policy in (
        {},
        overlay([]),
        {**overlay([{"operation": "drop_rules"}]), "allow_all": True},
        overlay([{"operation": "extend_concept_terms", "selector": selector("missing"), "terms": ["contrast"]}]),
        overlay([{"operation": "extend_concept_terms", "selector": selector("primary"), "terms": ["compare"]}]),
        overlay([{"operation": "clone_entity_alias", "source": {
            "entity_type": "intent_signal",
            "user_term": "generic analysis",
            "canonical_value": "intent_test",
        }, "new_user_term": "generic analysis"}]),
    ):
        try:
            parse_overlay_policy(policy)
        except ValueError:
            continue
        assert_blocked(fixture(), policy)


def test_execution_gate_blocks_before_repository_access() -> None:
    with patch("sys.argv", ["overlay"]), patch.dict(
        "os.environ", {"LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "true"}
    ), patch(
        "scripts.preview_semantic_overlay_readonly.PostgresContextRepository"
    ) as repository:
        assert main() == 3
        repository.assert_not_called()


if __name__ == "__main__":
    test_extend_terms_does_not_mutate_source()
    test_mirror_terms_requires_compatible_match_modes()
    test_alias_clone_does_not_modify_existing_signal()
    test_exact_catalog_exclusion_is_versioned_and_immutable()
    test_catalog_exclusion_rejects_implicit_or_ambiguous_mutations()
    test_invalid_policies_fail_closed()
    test_execution_gate_blocks_before_repository_access()
    print("SEMANTIC_OVERLAY_INVARIANTS=PASS")
