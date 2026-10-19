from __future__ import annotations

"""Synthetic semantic negation contract and versioned v16 isolation tests.

No financial vocabulary, SQL generation, benchmark or provider is used by
these tests. All business selectors live exclusively in overlay JSON.
"""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.context_validator import validate_context_snapshot
from app.domain.intent_resolver import resolve_intent
from scripts.preview_semantic_overlay_readonly import (
    apply_semantic_overlay, main, parse_overlay_policy,
)
from testar_context_validator import _raw_snapshot


ROOT = Path(__file__).resolve().parent
V15 = ROOT / "semantic_context/candidate_overlay_demo_finance_v15.json"
V16 = ROOT / "semantic_context/candidate_overlay_demo_finance_v16.json"
CONTROLS = ROOT / "scripts/validation/demo_finance_v16_negation_temporal_counterexamples.json"


def _policy(cues: list[str] | None = None) -> dict:
    return {
        "source_version": "synthetic-v11",
        "candidate_version": "synthetic-v16",
        "changes": [{
            "operation": "configure_concept_negation",
            "policy": {
                "cue_phrases": cues or [
                    "without", "without computing", "do not show",
                ],
                "concept_names": ["operation_marker"],
                "max_gap_tokens": 1,
            },
        }],
    }


def _catalog_rule(name: str, effect: str, term: str) -> dict:
    return {
        "rule_name": name,
        "effect": effect,
        "score": 120 if effect == "positive_score" else None,
        "priority": 1,
        "minimum_concept_matches": 1,
        "concepts": [{
            "concept_name": (
                "operation_marker" if term == "trajectory" else "dataset_marker"
            ),
            "terms": [term],
            "match_mode": "contains",
            "minimum_term_matches": 1,
        }],
    }


def _synthetic_source() -> dict:
    raw = _raw_snapshot()
    raw["semantic_agent_version"] = "synthetic-v11"
    original = raw["entidades"][1]
    original["business_rule"]["intent_catalog"] = {
        "semantic_description": "Synthetic changing-operation intent.",
        "rules": [_catalog_rule("operation_score", "positive_score", "trajectory")],
    }
    scenario = deepcopy(original)
    scenario["user_term"] = "scenario_definition"
    scenario["canonical_value"] = "scenario_intent"
    scenario["business_rule"]["intent_catalog"] = {
        "semantic_description": "Synthetic nonoperational grouped dataset.",
        "rules": [
            _catalog_rule("scenario_score", "positive_score", "dataset"),
            _catalog_rule("operation_exclusion", "exclude", "trajectory"),
        ],
    }
    raw["entidades"].append(scenario)
    pattern = deepcopy(raw["padroes"][0])
    pattern["intent_name"] = "scenario_intent"
    pattern["pattern_name"] = "scenario_pattern"
    raw["padroes"].append(pattern)
    raw["context_counts"]["entidades"] = len(raw["entidades"])
    raw["context_counts"]["padroes"] = len(raw["padroes"])
    snapshot = normalize_context_snapshot(raw)
    report = validate_context_snapshot(snapshot)
    assert report["status"] == "valid", {item["code"] for item in report["errors"]}
    return snapshot


def test_negation_only_applies_when_versioned_and_opted_in() -> None:
    source = _synthetic_source()
    before = deepcopy(source)
    candidate = apply_semantic_overlay(source, _policy())
    assert source == before
    assert candidate["fingerprint"] != source["fingerprint"]
    assert candidate["rules"] != source["rules"]
    assert candidate["entities"] == source["entities"]
    assert candidate["query_patterns"] == source["query_patterns"]
    assert candidate["table_catalog"] == source["table_catalog"]
    assert candidate["dre_mappings"] == source["dre_mappings"]
    assert candidate["counts"] == source["counts"]
    assert validate_context_snapshot(candidate)["status"] == "valid"

    def intent(snapshot: dict, question: str) -> str | None:
        return resolve_intent(
            question, snapshot["intent_resolution"],
        )["intent"]

    assert intent(source, "show dataset without computing trajectory") == "intent_test"
    assert intent(candidate, "show dataset without computing trajectory") == "scenario_intent"
    assert intent(candidate, "show dataset without trajectory") == "scenario_intent"
    assert intent(candidate, "show dataset, do not show trajectory") == "scenario_intent"
    assert intent(candidate, "show dataset with trajectory") == "intent_test"
    assert intent(candidate, "show dataset without computing, trajectory by month") == "intent_test"
    assert intent(candidate, "show dataset and something unrelated") == "scenario_intent"
    assert intent(candidate, "show trajectory with no dataset") == "intent_test"


def test_negated_concept_cannot_reappear_via_semantic_defaults() -> None:
    source = _synthetic_source()
    candidate = apply_semantic_overlay(source, _policy())
    semantics = deepcopy(candidate["intent_resolution"])
    semantics["semantic_defaults"] = {
        "component": "semantic_defaults",
        "rules": [{
            "rule_name": "default_operation",
            "when_present": ["dataset_marker"],
            "when_absent": [],
            "produce": ["operation_marker"],
            "priority": 1,
        }],
    }
    resolved = resolve_intent(
        "show dataset without computing trajectory", semantics,
    )
    assert resolved["intent"] == "scenario_intent"
    assert not resolved["semantic_defaults"]["applied"]
    assert any(
        item["reason"] == "negated_concept_cannot_be_defaulted"
        for item in resolved["semantic_defaults"]["suppressed"]
    )


def test_invalid_negation_policies_are_rejected_without_mutation() -> None:
    source = _synthetic_source()
    old = deepcopy(source)
    valid = _policy()["changes"][0]
    bad = [
        {**valid, "policy": {**valid["policy"], "max_gap_tokens": True}},
        {**valid, "policy": {**valid["policy"], "max_gap_tokens": 100}},
        {**valid, "policy": {**valid["policy"], "cue_phrases": ["without", "WITHOUT"]}},
        {**valid, "policy": {**valid["policy"], "cue_phrases": [""]}},
        {**valid, "policy": {**valid["policy"], "concept_names": ["not_declared"]}},
        {**valid, "policy": {**valid["policy"], "concept_names": []}},
        {**valid, "policy": {**valid["policy"], "threshold": 10}},
        {**valid, "score": 5},
    ]
    for change in bad:
        policy = {
            "source_version": "synthetic-v11",
            "candidate_version": "synthetic-v16",
            "changes": [change],
        }
        try:
            parsed = parse_overlay_policy(policy)
            apply_semantic_overlay(source, parsed)
        except ValueError:
            continue
        raise AssertionError("unsafe negation config was accepted")
    assert source == old


def test_validator_rejects_malformed_stored_negation_config() -> None:
    values = [
        {"cue_phrases": ["without"], "concept_names": ["unknown"], "max_gap_tokens": 1},
        {"cue_phrases": ["without", "WITHOUT"], "concept_names": ["first_concept"], "max_gap_tokens": 1},
        {"cue_phrases": ["without"], "concept_names": ["first_concept"], "max_gap_tokens": -1},
        {"cue_phrases": [], "concept_names": ["first_concept"], "max_gap_tokens": 1},
        {"cue_phrases": ["without"], "concept_names": ["first_concept"], "max_gap_tokens": "1"},
    ]
    for negation in values:
        raw = _raw_snapshot()
        raw["regras"][0]["rule_content"]["negation_scope"] = negation
        validated = validate_context_snapshot(normalize_context_snapshot(raw))
        assert validated["status"] == "invalid"


def test_v16_remains_cumulative_and_does_not_embed_questions() -> None:
    prior = parse_overlay_policy(json.loads(V15.read_text(encoding="utf-8")))
    proposed = parse_overlay_policy(json.loads(V16.read_text(encoding="utf-8")))
    assert proposed["source_version"] == prior["source_version"]
    assert proposed["changes"][:len(prior["changes"])] == prior["changes"]
    additions = proposed["changes"][len(prior["changes"]):]
    assert len(additions) == 5
    assert [change["operation"] for change in additions] == [
        "extend_temporal_granularity_terms", "extend_concept_terms",
        "mirror_concept_terms", "mirror_concept_terms",
        "configure_concept_negation",
    ]
    assert all(change["source"] == additions[1]["selector"] for change in additions[2:4])
    assert len({tuple(sorted(c["target"].items())) for c in additions[2:4]}) == 2
    assert "score" not in json.dumps(additions).casefold()
    assert "minimum_score" not in json.dumps(additions).casefold()
    assert "expected" not in json.dumps(additions).casefold()
    assert "question" not in json.dumps(additions).casefold()


def test_held_out_controls_stay_evaluation_only() -> None:
    controls = json.loads(CONTROLS.read_text(encoding="utf-8"))["cases"]
    assert len(controls) >= 24
    assert len({case["question"] for case in controls}) == len(controls)
    assert len({case["expected_intent"] for case in controls}) >= 4
    assert all(
        set(case) <= {
            "question", "expected_intent", "expected_plan_status",
            "expected_error_code", "expected_temporal_issue",
        }
        for case in controls
    )


def test_real_sql_execution_prevented_before_repository_access() -> None:
    with (
        patch("sys.argv", ["overlay"]),
        patch.dict("os.environ", {"LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "true"}),
        patch("scripts.preview_semantic_overlay_readonly.PostgresContextRepository") as repo,
    ):
        assert main() == 3
        repo.assert_not_called()


if __name__ == "__main__":
    test_negation_only_applies_when_versioned_and_opted_in()
    test_negated_concept_cannot_reappear_via_semantic_defaults()
    test_invalid_negation_policies_are_rejected_without_mutation()
    test_validator_rejects_malformed_stored_negation_config()
    test_v16_remains_cumulative_and_does_not_embed_questions()
    test_held_out_controls_stay_evaluation_only()
    test_real_sql_execution_prevented_before_repository_access()
    print("V16_NEGATION_TEMPORAL_CONTRACT=PASS")
