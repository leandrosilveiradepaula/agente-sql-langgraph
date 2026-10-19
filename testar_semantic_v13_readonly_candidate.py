from __future__ import annotations

"""Synthetic/contract gates for an unpromoted cumulative v13 semantic overlay.

Only semantic context and synthetic questions are tested here. Live financial
knowledge stays outside Python; no benchmark, provider, SQL or VPS connection.
"""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.context_validator import validate_context_snapshot
from app.domain.intent_resolver import resolve_intent
from scripts.preview_semantic_overlay_readonly import (
    apply_semantic_overlay,
    main,
    parse_overlay_policy,
)
from testar_context_validator import _raw_snapshot


ROOT = Path(__file__).resolve().parent
V12 = ROOT / "semantic_context/candidate_overlay_demo_finance_v12.json"
V13 = ROOT / "semantic_context/candidate_overlay_demo_finance_v13.json"
CONTROLS = (
    ROOT / "scripts/validation/demo_finance_v13_operation_counterexamples.json"
)


def _policies() -> tuple[dict, dict]:
    previous = parse_overlay_policy(json.loads(V12.read_text(encoding="utf-8")))
    proposed = parse_overlay_policy(json.loads(V13.read_text(encoding="utf-8")))
    return previous, proposed


def test_v13_preserves_prior_overlay_as_immutable_prefix() -> None:
    old, new = _policies()
    assert old["source_version"] == new["source_version"] == "demo-finance-v11"
    assert old["candidate_version"] == "demo-finance-v12"
    assert new["candidate_version"] == "demo-finance-v13"
    assert new["changes"][: len(old["changes"])] == old["changes"]
    assert len(new["changes"]) > len(old["changes"])
    assert not any(
        str(change.get("operation", "")).casefold().startswith("execute")
        for change in new["changes"]
    )


def test_new_semantics_are_configured_and_exclusions_follow_the_source() -> None:
    # Business intent labels, rule names and aliases belong to versioned JSON,
    # never to Python assertions. Check semantic relationships structurally.
    old, new = _policies()
    additions = new["changes"][len(old["changes"]):]
    extensions = [
        change for change in additions
        if change["operation"] == "extend_concept_terms"
    ]
    assert len(extensions) == 1
    extension = extensions[0]
    selector = extension["selector"]

    earlier_aliases = [
        change for change in old["changes"]
        if change["operation"] == "clone_entity_alias"
    ]
    assert earlier_aliases
    prototypes = {
        json.dumps(change["source"], sort_keys=True)
        for change in earlier_aliases
    }
    assert len(prototypes) == 1
    original_vocabulary = {
        change["new_user_term"] for change in earlier_aliases
    }
    extended_vocabulary = set(extension["terms"])
    assert original_vocabulary <= extended_vocabulary
    assert extended_vocabulary - original_vocabulary

    mirrors = [
        change for change in additions
        if change["operation"] == "mirror_concept_terms"
    ]
    assert len(mirrors) == 1
    assert mirrors[0]["source"] == selector
    assert mirrors[0]["target"]["intent_name"] != selector["intent_name"]
    assert mirrors[0]["target"]["concept_name"] == selector["concept_name"]

    guards = [
        change for change in additions
        if change["operation"] == "add_catalog_exclusion"
    ]
    assert len(guards) == 1
    assert guards[0]["source"] == selector
    assert guards[0]["target_intent"] != selector["intent_name"]
    assert guards[0]["target_intent"] != mirrors[0]["target"]["intent_name"]

    cloned_aliases = [
        change for change in additions
        if change["operation"] == "clone_entity_alias"
    ]
    assert cloned_aliases
    assert all(
        json.dumps(change["source"], sort_keys=True) in prototypes
        for change in cloned_aliases
    )
    assert {
        change["new_user_term"] for change in cloned_aliases
    } == extended_vocabulary - original_vocabulary


def test_independent_evaluation_is_not_runtime_context() -> None:
    old, new = _policies()
    controls = json.loads(CONTROLS.read_text(encoding="utf-8"))
    questions = [case["question"] for case in controls["cases"]]
    assert len(questions) >= 16
    assert len(set(questions)) == len(questions)
    assert len({case["expected_intent"] for case in controls["cases"]}) >= 4
    assert all(set(case) <= {
        "question", "expected_intent", "expected_plan_status",
        "expected_error_code", "expected_temporal_issue",
    } for case in controls["cases"])
    assert "question" not in json.dumps(new)
    assert "expected_" not in json.dumps(new)
    assert "golden" not in json.dumps(new).casefold()
    assert "benchmark" not in json.dumps(new).casefold()
    assert old["changes"] != new["changes"]


def _synthetic_definition(
    intent: str, term: str, concept_name: str,
    *, with_exclusion: bool = False,
) -> dict:
    rules = [{
        "rule_name": "primary",
        "effect": "positive_score",
        "score": 120,
        "priority": 1,
        "minimum_concept_matches": 1,
        "concepts": [{
            "concept_name": concept_name,
            "terms": [term],
            "match_mode": "contains",
            "minimum_term_matches": 1,
        }],
    }]
    if with_exclusion:
        rules.append({
            "rule_name": "prior_exclusion",
            "effect": "exclude",
            "score": None,
            "priority": 2,
            "minimum_concept_matches": 1,
            "concepts": [{
                "concept_name": "operation",
                "terms": ["organize"],
                "match_mode": "contains",
                "minimum_term_matches": 1,
            }],
        })
    return {
        "entity_type": "intent_definition",
        "user_term": f"{intent}_definition",
        "canonical_value": intent,
        "target_table": None,
        "target_column": None,
        "sql_filter_hint": None,
        "business_rule": {
            "intent_catalog": {
                "semantic_description": "Synthetic-only semantic fixture.",
                "rules": rules,
            }
        },
        "priority": 10,
    }


def test_synthetic_operations_override_scenarios_without_lower_threshold() -> None:
    raw = _raw_snapshot()
    raw["semantic_agent_version"] = "synthetic-v11"
    raw["entidades"].extend([
        _synthetic_definition("operation_intent", "organize", "operation"),
        _synthetic_definition("scenario_intent", "scenario", "scenario",
                              with_exclusion=True),
    ])
    # Every synthetic intent must also be declared by an active pattern;
    # the validator requires the intent catalog to reference authorized intents.
    for intent_name in ("operation_intent", "scenario_intent"):
        pattern = deepcopy(raw["padroes"][0])
        pattern["intent_name"] = intent_name
        pattern["pattern_name"] = f"{intent_name}_pattern"
        raw["padroes"].append(pattern)
    raw["context_counts"]["entidades"] = len(raw["entidades"])
    raw["context_counts"]["padroes"] = len(raw["padroes"])
    source = normalize_context_snapshot(raw)
    assert validate_context_snapshot(source)["status"] == "valid"
    before = deepcopy(source)

    policy = {
        "source_version": "synthetic-v11",
        "candidate_version": "synthetic-v13",
        "changes": [
            {
                "operation": "extend_concept_terms",
                "selector": {
                    "intent_name": "operation_intent",
                    "rule_name": "primary",
                    "concept_name": "operation",
                },
                "terms": ["arrange"],
            },
            {
                "operation": "mirror_concept_terms",
                "source": {
                    "intent_name": "operation_intent",
                    "rule_name": "primary",
                    "concept_name": "operation",
                },
                "target": {
                    "intent_name": "scenario_intent",
                    "rule_name": "prior_exclusion",
                    "concept_name": "operation",
                },
            },
            {
                "operation": "add_catalog_exclusion",
                "source": {
                    "intent_name": "operation_intent",
                    "rule_name": "primary",
                    "concept_name": "operation",
                },
                "target_intent": "scenario_intent",
                "rule_name": "new_guard",
                "priority": 3,
            },
        ],
    }
    candidate = apply_semantic_overlay(source, policy)
    assert source == before
    assert candidate["fingerprint"] != source["fingerprint"]
    assert candidate["rules"] == source["rules"]
    assert candidate["query_patterns"] == source["query_patterns"]
    assert candidate["table_catalog"] == source["table_catalog"]

    def intent_for(question: str) -> str | None:
        return resolve_intent(
            question, candidate["intent_resolution"]
        )["intent"]

    assert intent_for("please arrange scenario") == "operation_intent"
    assert intent_for("organize scenario") == "operation_intent"
    assert intent_for("show scenario grouped by team") == "scenario_intent"
    assert intent_for("please arrange figures") == "operation_intent"
    assert intent_for("unknown phrase") is None


def test_real_execution_gate_precedes_context_access() -> None:
    with (
        patch("sys.argv", ["overlay"]),
        patch.dict("os.environ", {"LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "true"}),
        patch("scripts.preview_semantic_overlay_readonly.PostgresContextRepository") as repo,
    ):
        assert main() == 3
        repo.assert_not_called()


if __name__ == "__main__":
    test_v13_preserves_prior_overlay_as_immutable_prefix()
    test_new_semantics_are_configured_and_exclusions_follow_the_source()
    test_independent_evaluation_is_not_runtime_context()
    test_synthetic_operations_override_scenarios_without_lower_threshold()
    test_real_execution_gate_precedes_context_access()
    print("V13_OPERATION_COMPATIBILITY=PASS")
