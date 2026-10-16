from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

from app.domain.context_normalizer import normalize_context_snapshot
from scripts.preview_semantic_overlay_readonly import (
    apply_semantic_overlay,
    main,
    parse_overlay_policy,
)


def fixture() -> dict:
    raw = {
        "semantic_agent_version": "synthetic-v1",
        "semantic_context_source": "offline_fixture",
        "regras": [],
        "entidades": [
            {
                "entity_type": "intent_definition",
                "canonical_value": "synthetic_intent",
                "user_term": "synthetic_intent",
                "business_rule": {
                    "intent_catalog": {
                        "rules": [
                            {
                                "rule_name": "primary",
                                "effect": "positive_score",
                                "score": 120,
                                "concepts": [
                                    {"concept_name": "operation", "terms": ["compare"], "match_mode": "phrase"}
                                ],
                            },
                            {
                                "rule_name": "exclusion",
                                "effect": "exclude",
                                "concepts": [
                                    {"concept_name": "operation", "terms": ["compare"], "match_mode": "phrase"}
                                ],
                            },
                        ],
                    }
                },
                "priority": 1,
            },
            {
                "entity_type": "operation_alias",
                "canonical_value": "compare",
                "user_term": "compare",
                "business_rule": {},
                "priority": 1,
            },
        ],
        "dre": [],
        "padroes": [],
        "catalogo": [],
    }
    return normalize_context_snapshot(raw)


def overlay(changes: list[dict]) -> dict:
    return {
        "source_version": "synthetic-v1",
        "candidate_version": "synthetic-v2",
        "changes": changes,
    }


def selector(rule: str) -> dict:
    return {
        "intent_name": "synthetic_intent",
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
        "operation": "mirror_concept_terms",
        "source": selector("primary"),
        "target": selector("exclusion"),
    }, {
        "operation": "extend_concept_terms",
        "selector": selector("primary"),
        "terms": ["contrast"],
    }]))
    assert candidate["version"] == "synthetic-v2"
    assert source["version"] == "synthetic-v1"


def test_invalid_policies_fail_closed() -> None:
    for policy in (
        {},
        overlay([]),
        {**overlay([{"operation": "drop_rules"}]), "allow_all": True},
        overlay([{"operation": "extend_concept_terms", "selector": selector("missing"), "terms": ["contrast"]}]),
        overlay([{"operation": "extend_concept_terms", "selector": selector("primary"), "terms": ["compare"]}]),
        overlay([{"operation": "clone_entity_alias", "source": {
            "entity_type": "operation_alias",
            "user_term": "compare",
            "canonical_value": "compare",
        }, "new_user_term": "compare"}]),
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
    test_invalid_policies_fail_closed()
    test_execution_gate_blocks_before_repository_access()
    print("SEMANTIC_OVERLAY_INVARIANTS=PASS")
