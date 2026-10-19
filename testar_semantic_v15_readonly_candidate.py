from __future__ import annotations

"""Offline governance gates for unpromoted cumulative versioned v15 context."""

import json
from pathlib import Path
from unittest.mock import patch

from scripts.preview_semantic_overlay_readonly import (
    main,
    parse_overlay_policy,
)


ROOT = Path(__file__).resolve().parent
PREVIOUS = ROOT / "semantic_context/candidate_overlay_demo_finance_v14.json"
PROPOSED = ROOT / "semantic_context/candidate_overlay_demo_finance_v15.json"
SUITE = ROOT / "scripts/validation/demo_finance_v15_independent_inflection_controls.json"


def _policies() -> tuple[dict, dict]:
    old = parse_overlay_policy(json.loads(PREVIOUS.read_text(encoding="utf-8")))
    new = parse_overlay_policy(json.loads(PROPOSED.read_text(encoding="utf-8")))
    return old, new


def test_v15_is_cumulative_and_does_not_mutate_other_context() -> None:
    old, new = _policies()
    assert new["source_version"] == old["source_version"]
    assert new["candidate_version"] != old["candidate_version"]
    assert new["changes"][:len(old["changes"])] == old["changes"]
    assert len(new["changes"]) == len(old["changes"]) + 3
    assert all(
        change["operation"] not in {
            "execute", "activate", "promote", "update_sql",
        }
        for change in new["changes"]
    )


def test_single_operation_vocabulary_is_mirrored_to_all_scenario_guards() -> None:
    old, new = _policies()
    additions = new["changes"][len(old["changes"]):]
    primary = additions[0]
    assert primary["operation"] == "extend_concept_terms"
    assert len(primary["terms"]) >= 5
    assert len(set(primary["terms"])) == len(primary["terms"])
    source = primary["selector"]
    # Names are read from externally versioned context. Python tests
    # validate shape and relationships, not finance-specific vocabulary.
    mirrors = additions[1:]
    assert all(change["operation"] == "mirror_concept_terms" for change in mirrors)
    assert all(change["source"] == source for change in mirrors)
    assert len({tuple(sorted(change["target"].items())) for change in mirrors}) == 2
    assert all(
        change["target"]["concept_name"] == source["concept_name"]
        for change in mirrors
    )
    assert all(
        change["target"]["intent_name"] != source["intent_name"]
        for change in mirrors
    )
    assert all(
        "score" not in json.dumps(change).casefold()
        and "benchmark" not in json.dumps(change).casefold()
        and "expected" not in json.dumps(change).casefold()
        for change in additions
    )


def test_independent_controls_never_enter_policy_or_generation() -> None:
    old, new = _policies()
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    cases = suite["cases"]
    assert len(cases) >= 20
    assert len({case["question"] for case in cases}) == len(cases)
    assert len({case["expected_intent"] for case in cases}) >= 4
    assert all(set(case) <= {
        "question", "expected_intent", "expected_plan_status",
        "expected_error_code", "expected_temporal_issue",
    } for case in cases)
    assert all(
        "question" not in change and "expected_intent" not in change
        for change in new["changes"]
    )
    assert old["changes"] != new["changes"]


def test_real_sql_gate_prevents_any_context_load() -> None:
    with (
        patch("sys.argv", ["semantic-overlay"]),
        patch.dict("os.environ", {"LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "true"}),
        patch("scripts.preview_semantic_overlay_readonly.PostgresContextRepository") as repo,
    ):
        assert main() == 3
        repo.assert_not_called()


if __name__ == "__main__":
    test_v15_is_cumulative_and_does_not_mutate_other_context()
    test_single_operation_vocabulary_is_mirrored_to_all_scenario_guards()
    test_independent_controls_never_enter_policy_or_generation()
    test_real_sql_gate_prevents_any_context_load()
    print("V15_TREND_INFLECTION_CONTEXT=PASS")
