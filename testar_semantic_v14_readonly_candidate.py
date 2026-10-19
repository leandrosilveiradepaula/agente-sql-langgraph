from __future__ import annotations

"""Contract tests for versioned, virtual and read-only temporal vocabulary."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.context_validator import validate_context_snapshot
from scripts.preview_semantic_overlay_readonly import (
    apply_semantic_overlay,
    main,
    parse_overlay_policy,
)
from testar_context_validator import _raw_snapshot


ROOT = Path(__file__).resolve().parent


def _source() -> dict:
    raw = _raw_snapshot()
    raw["semantic_agent_version"] = "synthetic-v11"
    raw["regras"].append({
        "rule_group": "component_config",
        "rule_name": "synthetic_time_config",
        "rule_content": {
            "component": "temporal_planning",
            "required_intents": ["intent_test"],
            "granularities": [
                {"grain": "month", "terms": ["monthly"]},
                {"grain": "quarter", "terms": ["quarterly"]},
            ],
            "date_binding_strategy": "configured_metric_source_date",
            "date_bindings": [{
                "metric_concept": "metric_x",
                "target_table": "schema_test.table_test",
                "target_column": "event_date",
            }],
        },
        "applies_to_intents": ["intent_test"],
        "validation_hint": None,
        "severity": "error",
        "priority": 3,
    })
    raw["context_counts"]["regras"] = len(raw["regras"])
    source = normalize_context_snapshot(raw)
    assert validate_context_snapshot(source)["status"] == "valid"
    return source


def _change(*terms: str, grain: str = "month") -> dict:
    return {
        "operation": "extend_temporal_granularity_terms",
        "selector": {
            "rule_name": "synthetic_time_config",
            "grain": grain,
        },
        "terms": list(terms),
    }


def _policy(*changes: dict) -> dict:
    return {
        "source_version": "synthetic-v11",
        "candidate_version": "synthetic-v14",
        "changes": list(changes),
    }


def _grains(snapshot: dict) -> list[dict]:
    configs = snapshot["component_configs"]
    return configs["temporal_planning"]["granularities"]


def _fails_closed(source: dict, policy: dict) -> None:
    try:
        apply_semantic_overlay(source, policy)
    except ValueError:
        return
    raise AssertionError("unsafe temporal overlay was accepted")


def test_versioned_temporal_extension_is_immutable_and_scoped() -> None:
    source = _source()
    original = deepcopy(source)
    candidate = apply_semantic_overlay(
        source, _policy(_change("months", "monthly intervals")),
    )
    assert source == original
    assert candidate["version"] == "synthetic-v14"
    assert candidate["fingerprint"] != source["fingerprint"]
    assert _grains(candidate)[0]["terms"] == [
        "monthly", "months", "monthly intervals",
    ]
    assert _grains(candidate)[1]["terms"] == ["quarterly"]
    assert _grains(source)[0]["terms"] == ["monthly"]
    assert candidate["entities"] == source["entities"]
    assert candidate["query_patterns"] == source["query_patterns"]
    assert candidate["table_catalog"] == source["table_catalog"]
    assert candidate["dre_mappings"] == source["dre_mappings"]
    assert candidate["counts"] == source["counts"]
    assert validate_context_snapshot(candidate)["status"] == "valid"


def test_duplicate_or_cross_grain_terms_fail_closed() -> None:
    source = _source()
    for change in (
        _change("monthly"),
        _change("quarterly"),
        _change("months", "months"),
        _change("month", "MONTH"),
        _change("months", grain="year"),
        {**_change("months"), "selector": {
            "rule_name": "missing_rule", "grain": "month",
        }},
        {**_change("months"), "selector": {
            "rule_name": "synthetic_time_config", "grain": "month",
            "hidden": "anything",
        }},
        {**_change("months"), "effect": "set_score"},
    ):
        _fails_closed(source, _policy(change))
    assert validate_context_snapshot(source)["status"] == "valid"


def test_versioned_v14_is_cumulative_with_no_threshold_mutations() -> None:
    old = parse_overlay_policy(json.loads(
        (ROOT / "semantic_context/candidate_overlay_demo_finance_v13.json")
        .read_text(encoding="utf-8")
    ))
    new = parse_overlay_policy(json.loads(
        (ROOT / "semantic_context/candidate_overlay_demo_finance_v14.json")
        .read_text(encoding="utf-8")
    ))
    assert old["source_version"] == new["source_version"]
    assert new["candidate_version"] != old["candidate_version"]
    assert new["changes"][: len(old["changes"])] == old["changes"]
    additions = new["changes"][len(old["changes"]):]
    assert len(additions) == 1
    assert additions[0]["operation"] == "extend_temporal_granularity_terms"
    assert set(additions[0]["selector"]) == {"rule_name", "grain"}
    assert not any(
        "minimum_score" in str(item)
        or "ambiguity_margin" in str(item)
        or "expected" in str(item).casefold()
        for item in new["changes"]
    )


def test_independent_controls_are_not_part_of_agent_context() -> None:
    suite = json.loads(
        (ROOT / "scripts/validation/demo_finance_v14_temporal_counterexamples.json")
        .read_text(encoding="utf-8")
    )
    policy = json.loads(
        (ROOT / "semantic_context/candidate_overlay_demo_finance_v14.json")
        .read_text(encoding="utf-8")
    )
    questions = [case["question"] for case in suite["cases"]]
    assert len(questions) >= 12
    assert len(set(questions)) == len(questions)
    assert len({case["expected_intent"] for case in suite["cases"]}) >= 4
    assert all(set(case) <= {
        "question", "expected_intent", "expected_plan_status",
        "expected_error_code", "expected_temporal_issue",
    } for case in suite["cases"])
    assert "question" not in json.dumps(policy)
    assert "expected_" not in json.dumps(policy)
    assert "benchmark" not in json.dumps(policy).casefold()


def test_real_execution_fails_before_context_repository() -> None:
    with (
        patch("sys.argv", ["overlay"]),
        patch.dict("os.environ", {"LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "true"}),
        patch("scripts.preview_semantic_overlay_readonly.PostgresContextRepository") as repo,
    ):
        assert main() == 3
        repo.assert_not_called()


if __name__ == "__main__":
    test_versioned_temporal_extension_is_immutable_and_scoped()
    test_duplicate_or_cross_grain_terms_fail_closed()
    test_versioned_v14_is_cumulative_with_no_threshold_mutations()
    test_independent_controls_are_not_part_of_agent_context()
    test_real_execution_fails_before_context_repository()
    print("V14_TEMPORAL_CONTEXT_COVERAGE=PASS")
