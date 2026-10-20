from __future__ import annotations

"""Opt-in negated-operation eligibility tests without business vocabulary."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.context_validator import validate_context_snapshot
from app.domain.intent_resolver import resolve_intent
from scripts.preview_semantic_overlay_readonly import (
    apply_semantic_overlay, parse_overlay_policy, main,
)
from testar_context_validator import _raw_snapshot


ROOT = Path(__file__).resolve().parent
V17 = ROOT / "semantic_context/candidate_overlay_demo_finance_v17.json"
V18 = ROOT / "semantic_context/candidate_overlay_demo_finance_v18.json"
CONTROLS = ROOT / "scripts/validation/demo_finance_v18_independent_negation_eligibility_cases.json"


def _concept(name: str, terms: list[str]) -> dict:
    return {
        "concept_name": name,
        "terms": terms,
        "match_mode": "contains",
        "minimum_term_matches": 1,
    }


def _rule(
    name: str, concepts: list[dict], score: int,
    minimum: int = 1,
) -> dict:
    return {
        "rule_name": name,
        "effect": "positive_score",
        "score": score,
        "priority": 1,
        "minimum_concept_matches": minimum,
        "concepts": concepts,
    }


def _synthetic_source() -> dict:
    raw = _raw_snapshot()
    raw["semantic_agent_version"] = "synthetic-v11"
    combined = raw["entidades"][1]
    combined["business_rule"]["intent_catalog"] = {
        "semantic_description": "Synthetic paired-mode interpretation.",
        "rules": [
            _rule("first_context", [_concept("first_mode", ["alpha"])], 90),
            _rule("second_context", [_concept("second_mode", ["beta"])], 90),
            _rule(
                "explicit_operator",
                [
                    _concept("op_signal", ["compare", "relate"]),
                    _concept("first_mode", ["alpha"]),
                    _concept("second_mode", ["beta"]),
                ],
                80, 3,
            ),
        ],
    }
    plain = deepcopy(combined)
    plain["canonical_value"] = "plain_intent"
    plain["user_term"] = "plain_definition"
    plain["business_rule"]["intent_catalog"] = {
        "semantic_description": "Synthetic first-mode interpretation.",
        "rules": [
            _rule("plain_mode", [_concept("first_mode", ["alpha"])], 120),
        ],
    }
    raw["entidades"].append(plain)
    pattern = deepcopy(raw["padroes"][0])
    pattern["pattern_name"] = "plain_pattern"
    pattern["intent_name"] = "plain_intent"
    raw["padroes"].append(pattern)
    raw["context_counts"]["entidades"] = len(raw["entidades"])
    raw["context_counts"]["padroes"] = len(raw["padroes"])
    source = normalize_context_snapshot(raw)
    report = validate_context_snapshot(source)
    assert report["status"] == "valid", {
        issue["code"] for issue in report["errors"]
    }
    return source


def _policy(*, gated: bool = True, gate: dict | None = None) -> dict:
    changes = [{
        "operation": "configure_concept_negation",
        "policy": {
            "cue_phrases": ["without", "do not"],
            "concept_names": ["op_signal"],
            "max_gap_tokens": 1,
        },
    }]
    if gated:
        changes.append({
            "operation": "add_negation_intent_gate",
            "selector": gate or {
                "intent_name": "intent_test",
                "concept_name": "op_signal",
            },
        })
    return {
        "source_version": "synthetic-v11",
        "candidate_version": "synthetic-v18",
        "changes": changes,
    }


def _intent(snapshot: dict, question: str) -> str | None:
    return resolve_intent(
        question, snapshot["intent_resolution"],
    )["intent"]


def test_explicit_denial_blocks_scenario_only_comparison() -> None:
    source = _synthetic_source()
    source_copy = deepcopy(source)
    ungated = apply_semantic_overlay(source, _policy(gated=False))
    gated = apply_semantic_overlay(source, _policy())
    assert source == source_copy
    assert gated["fingerprint"] != ungated["fingerprint"]
    for collection in ("entities", "table_catalog", "query_patterns", "dre_mappings"):
        assert source[collection] == gated[collection]
    assert source["counts"] == gated["counts"]
    assert validate_context_snapshot(gated)["status"] == "valid"

    # The pre-existing score might exceed the threshold from scenarios.
    assert _intent(ungated, "show alpha beta without compare") == "intent_test"
    assert _intent(gated, "show alpha beta without compare") == "plain_intent"
    assert _intent(gated, "show alpha beta without relate") == "plain_intent"
    assert _intent(gated, "show alpha beta do not compare") == "plain_intent"
    assert _intent(gated, "show alpha beta without compare; relate") == "intent_test"

    # Explicit affirmative operations remain eligible, including mixed scope.
    assert _intent(gated, "show alpha beta compare") == "intent_test"
    assert _intent(gated, "show alpha beta relate without compare") == "intent_test"
    assert _intent(gated, "show alpha beta compare without relate") == "intent_test"
    # Implicit multi-scenario meaning is not falsely negated without a cue.
    assert _intent(gated, "show alpha beta") == "intent_test"
    assert _intent(gated, "show alpha") == "plain_intent"


def test_gate_validation_rejects_unlicensed_selector() -> None:
    source = _synthetic_source()
    before = deepcopy(source)
    invalid = [
        _policy(gate={"intent_name": "unknown", "concept_name": "op_signal"}),
        _policy(gate={"intent_name": "plain_intent", "concept_name": "op_signal"}),
        _policy(gate={"intent_name": "intent_test", "concept_name": "not_allowed"}),
        {**_policy(), "changes": _policy()["changes"][1:]},
        {**_policy(), "changes": [*_policy()["changes"], _policy()["changes"][1]]},
        {**_policy(), "changes": [
            *_policy()["changes"],
            {"operation": "add_negation_intent_gate",
             "selector": {"intent_name": "intent_test",
                          "concept_name": "op_signal", "score": 200}},
        ]},
    ]
    for candidate in invalid:
        try:
            apply_semantic_overlay(source, candidate)
        except ValueError:
            continue
        raise AssertionError("invalid gate accepted")
    assert source == before


def test_stored_gate_config_is_always_checked_by_context_validator() -> None:
    bad_values = [
        [],
        [{"intent_name": "unknown", "concept_name": "first_concept"}],
        [{"intent_name": "intent_test", "concept_name": "unknown"}],
        [{"intent_name": "intent_test", "concept_name": "first_concept"},
         {"intent_name": "intent_test", "concept_name": "first_concept"}],
        [{"intent_name": "intent_test", "concept_name": "first_concept", "score": 50}],
    ]
    for gates in bad_values[1:]:
        raw = _raw_snapshot()
        raw["regras"][0]["rule_content"]["negation_scope"] = {
            "cue_phrases": ["without"],
            "concept_names": ["first_concept"],
            "max_gap_tokens": 1,
            "intent_gates": gates,
        }
        report = validate_context_snapshot(normalize_context_snapshot(raw))
        assert report["status"] == "invalid"


def test_v18_is_only_versioned_context_and_never_benchmark_lookup() -> None:
    previous = parse_overlay_policy(json.loads(V17.read_text(encoding="utf-8")))
    next_policy = parse_overlay_policy(json.loads(V18.read_text(encoding="utf-8")))
    assert next_policy["changes"][:len(previous["changes"])] == previous["changes"]
    added = next_policy["changes"][len(previous["changes"]):]
    assert len(added) == 1
    assert added[0]["operation"] == "add_negation_intent_gate"
    assert set(added[0]["selector"]) == {"intent_name", "concept_name"}
    assert all(
        forbidden not in json.dumps(added).casefold()
        for forbidden in ("benchmark", "golden", "threshold", "expected", "question")
    )

    cases = json.loads(CONTROLS.read_text(encoding="utf-8"))["cases"]
    assert len(cases) >= 20
    assert len({case["question"] for case in cases}) == len(cases)
    assert len({case["expected_intent"] for case in cases}) >= 4
    assert all(
        set(case) <= {"question", "expected_intent",
                      "expected_plan_status", "expected_error_code",
                      "expected_temporal_issue"}
        for case in cases
    )


def test_real_sql_execution_guard_stops_before_repository() -> None:
    with (
        patch("sys.argv", ["semantic-overlay"]),
        patch.dict("os.environ", {"LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "true"}),
        patch("scripts.preview_semantic_overlay_readonly.PostgresContextRepository") as repo,
    ):
        assert main() == 3
        repo.assert_not_called()


if __name__ == "__main__":
    test_explicit_denial_blocks_scenario_only_comparison()
    test_gate_validation_rejects_unlicensed_selector()
    test_stored_gate_config_is_always_checked_by_context_validator()
    test_v18_is_only_versioned_context_and_never_benchmark_lookup()
    test_real_sql_execution_guard_stops_before_repository()
    print("NEGATION_INTENT_ELIGIBILITY_GENERALIZATION=PASS")
