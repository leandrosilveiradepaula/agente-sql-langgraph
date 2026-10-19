from __future__ import annotations

"""Synthetic contracts for term-scoped negation and cumulative v17 context.

All business vocabulary stays in the independently versioned JSON context.
Tests below use deliberately synthetic intent/concept names only.
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
V16 = ROOT / "semantic_context/candidate_overlay_demo_finance_v16.json"
V17 = ROOT / "semantic_context/candidate_overlay_demo_finance_v17.json"
CONTROLS = ROOT / "scripts/validation/demo_finance_v17_independent_scoped_negation_cases.json"


def _rule(
    name: str, concept: str, terms: list[str], effect: str = "positive_score",
) -> dict:
    return {
        "rule_name": name, "effect": effect,
        "score": 120 if effect == "positive_score" else None,
        "priority": 1, "minimum_concept_matches": 1,
        "concepts": [{
            "concept_name": concept, "terms": terms,
            "match_mode": "contains", "minimum_term_matches": 1,
        }],
    }


def _source() -> dict:
    raw = _raw_snapshot()
    raw["semantic_agent_version"] = "synthetic-v11"
    definition = raw["entidades"][1]
    definition["business_rule"]["intent_catalog"] = {
        "semantic_description": "Synthetic operation.",
        "rules": [
            _rule("primary", "operation_marker", ["trajectory", "sorting"]),
        ],
    }
    scenario = deepcopy(definition)
    scenario["canonical_value"] = "scenario_intent"
    scenario["user_term"] = "scenario_definition"
    scenario["business_rule"]["intent_catalog"] = {
        "semantic_description": "Synthetic nonoperation.",
        "rules": [
            _rule("scenario", "dataset_marker", ["dataset"]),
            _rule(
                "operation_guard", "operation_marker",
                ["trajectory", "sorting"], "exclude",
            ),
        ],
    }
    raw["entidades"].append(scenario)
    pattern = deepcopy(raw["padroes"][0])
    pattern["intent_name"] = "scenario_intent"
    pattern["pattern_name"] = "scenario_pattern"
    raw["padroes"].append(pattern)
    raw["context_counts"]["entidades"] = len(raw["entidades"])
    raw["context_counts"]["padroes"] = len(raw["padroes"])
    context = normalize_context_snapshot(raw)
    result = validate_context_snapshot(context)
    assert result["status"] == "valid", {
        item["code"] for item in result["errors"]
    }
    return context


def _policy(*, extend: list[str] | None = None) -> dict:
    changes = [{
        "operation": "configure_concept_negation",
        "policy": {
            "cue_phrases": ["without", "do not show"],
            "concept_names": ["operation_marker"],
            "max_gap_tokens": 1,
        },
    }]
    if extend is not None:
        changes.append({
            "operation": "extend_negation_scope_concepts",
            "concept_names": extend,
        })
    return {
        "source_version": "synthetic-v11",
        "candidate_version": "synthetic-v17",
        "changes": changes,
    }


def _intent(context: dict, question: str) -> str | None:
    return resolve_intent(question, context["intent_resolution"])["intent"]


def test_term_scope_does_not_hide_distinct_affirmative_operation() -> None:
    source = _source()
    original = deepcopy(source)
    candidate = apply_semantic_overlay(
        source, _policy(extend=["dataset_marker"]),
    )
    assert source == original
    assert candidate["fingerprint"] != source["fingerprint"]
    assert candidate["rules"] != source["rules"]
    for collection in (
        "entities", "query_patterns", "table_catalog", "dre_mappings",
    ):
        assert candidate[collection] == source[collection]
    assert candidate["counts"] == source["counts"]
    assert validate_context_snapshot(candidate)["status"] == "valid"

    # No semantic negation changes when the config is absent.
    assert _intent(source, "show dataset without trajectory") == "intent_test"
    assert _intent(candidate, "show dataset without trajectory") == "scenario_intent"
    assert _intent(candidate, "show dataset without sorting") == "scenario_intent"
    assert _intent(candidate, "show dataset without trajectory and without sorting") == "scenario_intent"
    assert _intent(candidate, "show dataset sorting without trajectory") == "intent_test"
    assert _intent(candidate, "show dataset trajectory without sorting") == "intent_test"
    assert _intent(candidate, "show dataset trajectory, without trajectory") == "intent_test"
    assert _intent(candidate, "show dataset without sorting; trajectory") == "intent_test"
    assert _intent(candidate, "show dataset with trajectory") == "intent_test"
    assert _intent(candidate, "show dataset and something else") == "scenario_intent"
    # Extending a separate concept must not suppress the positive operation.
    assert _intent(candidate, "show sorting without dataset") == "intent_test"


def test_negated_terms_do_not_return_through_semantic_defaults() -> None:
    candidate = apply_semantic_overlay(_source(), _policy())
    resolution = deepcopy(candidate["intent_resolution"])
    resolution["semantic_defaults"] = {
        "component": "semantic_defaults",
        "rules": [{
            "rule_name": "default_operation",
            "when_present": ["dataset_marker"],
            "when_absent": [],
            "produce": ["operation_marker"],
            "priority": 1,
        }],
    }
    denied = resolve_intent(
        "show dataset without trajectory and without sorting", resolution,
    )
    assert denied["intent"] == "scenario_intent"
    assert not denied["semantic_defaults"]["applied"]
    assert any(
        item["reason"] == "negated_concept_cannot_be_defaulted"
        for item in denied["semantic_defaults"]["suppressed"]
    )
    affirmed = resolve_intent(
        "show dataset sorting without trajectory", resolution,
    )
    assert affirmed["intent"] == "intent_test"


def test_extension_fails_closed_on_invalid_context_or_policy() -> None:
    original = _source()
    before = deepcopy(original)
    valid = _policy(extend=["dataset_marker"])
    bad_changes = [
        [{"operation": "extend_negation_scope_concepts",
          "concept_names": ["dataset_marker"]}],
        [valid["changes"][0], {
            "operation": "extend_negation_scope_concepts",
            "concept_names": ["missing_concept"],
        }],
        [valid["changes"][0], {
            "operation": "extend_negation_scope_concepts",
            "concept_names": ["operation_marker"],
        }],
        [valid["changes"][0], {
            "operation": "extend_negation_scope_concepts",
            "concept_names": ["dataset_marker", "DATASET_MARKER"],
        }],
        [valid["changes"][0], {
            "operation": "extend_negation_scope_concepts",
            "concept_names": [""],
        }],
        [valid["changes"][0], {
            "operation": "extend_negation_scope_concepts",
            "concept_names": ["dataset_marker"], "score": 100,
        }],
    ]
    for changes in bad_changes:
        policy = {
            "source_version": "synthetic-v11",
            "candidate_version": "synthetic-v17",
            "changes": changes,
        }
        try:
            parsed = parse_overlay_policy(policy)
            apply_semantic_overlay(original, parsed)
        except ValueError:
            continue
        raise AssertionError("unsafe negation extension accepted")
    assert original == before


def test_v17_cumulative_and_held_out_expectations_never_enter_context() -> None:
    earlier = parse_overlay_policy(json.loads(V16.read_text(encoding="utf-8")))
    proposal = parse_overlay_policy(json.loads(V17.read_text(encoding="utf-8")))
    assert proposal["source_version"] == earlier["source_version"]
    assert proposal["candidate_version"] != earlier["candidate_version"]
    assert proposal["changes"][:len(earlier["changes"])] == earlier["changes"]
    changes = proposal["changes"][len(earlier["changes"]):]
    assert len(changes) == 2
    assert {change["operation"] for change in changes} == {
        "extend_temporal_granularity_terms",
        "extend_negation_scope_concepts",
    }
    assert "minimum_score" not in json.dumps(changes)
    assert "expected" not in json.dumps(changes)
    assert "question" not in json.dumps(changes)

    controls = json.loads(CONTROLS.read_text(encoding="utf-8"))["cases"]
    assert len(controls) >= 24
    assert len({item["question"] for item in controls}) == len(controls)
    assert len({item["expected_intent"] for item in controls}) >= 4
    assert all(set(item) <= {
        "question", "expected_intent", "expected_plan_status",
        "expected_error_code", "expected_temporal_issue",
    } for item in controls)


def test_shadow_execution_gate_blocks_before_repository() -> None:
    with (
        patch("sys.argv", ["overlay"]),
        patch.dict("os.environ", {"LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "true"}),
        patch("scripts.preview_semantic_overlay_readonly.PostgresContextRepository") as repo,
    ):
        assert main() == 3
        repo.assert_not_called()


if __name__ == "__main__":
    test_term_scope_does_not_hide_distinct_affirmative_operation()
    test_negated_terms_do_not_return_through_semantic_defaults()
    test_extension_fails_closed_on_invalid_context_or_policy()
    test_v17_cumulative_and_held_out_expectations_never_enter_context()
    test_shadow_execution_gate_blocks_before_repository()
    print("V17_SCOPED_NEGATION_GENERALIZATION=PASS")
