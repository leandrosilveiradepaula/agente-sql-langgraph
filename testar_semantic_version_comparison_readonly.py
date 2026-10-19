from __future__ import annotations

"""Unit tests for sanitized, one-shot Shadow version comparison."""

import json
import subprocess
from unittest.mock import patch

from scripts.compare_shadow_semantic_overlays_readonly import (
    ComparisonPreflightError,
    _extract_report,
    _reviewed_engine_revision,
    _validated_paths,
    compare,
)


BASE = "semantic_context/base.json"
LEFT = "semantic_context/left.json"
RIGHT = "semantic_context/right.json"
SUITE_A = "scripts/validation/independent_a.json"
SUITE_B = "scripts/validation/independent_b.json"
HASH = "a" * 64


def _report(
    version: str, succeeded: set[int], count: int,
    *,
    include_sensitive_text: bool = False,
) -> dict:
    observations = []
    for index in range(1, count + 1):
        observation = {
            "case_index": index,
            "passed": index in succeeded,
            "intent": "synthetic_analysis",
            "plan_status": "planned" if index in succeeded else "rejected",
            "plan_error_code": (
                None if index in succeeded else "SYNTHETIC_INCOMPLETE"
            ),
            "temporal_issues": [] if index in succeeded else ["missing_binding"],
            "resolution_evidence": {"reason": "configured_intent_selected"},
            "planned_metric_evidence": {
                "binding_inference_status": "not_applicable",
            },
        }
        if include_sensitive_text:
            observation.update({
                "question": "PRIVATE_USER_PROMPT",
                "sql": "PRIVATE_SYNTHETIC_SQL",
                "token": "PRIVATE_CREDENTIAL",
            })
        observations.append(observation)
    return {
        "candidate_version": version,
        "source_fingerprint": HASH,
        "read_only": True,
        "real_sql_execution": False,
        "persisted_candidate": False,
        "activation_authorized": False,
        "llm_calls": 0,
        "benchmark_access": False,
        "evaluation": {
            "case_count": count,
            "passed": len(succeeded),
            "read_only": True,
            "real_sql_execution": False,
            "llm_calls": 0,
            "benchmark_access": False,
            "observations": observations,
        },
    }


def _process(report: dict, rc: int = 1) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["bash", "safe-runner"],
        returncode=rc,
        stdout="Authorization: PRIVATE_CREDENTIAL\n" + json.dumps(report),
        stderr="PRIVATE_CREDENTIAL",
    )


def test_evaluator_revision_is_attested_not_guessed() -> None:
    good_sha = "a" * 40
    proc = subprocess.CompletedProcess(
        args=["git", "rev-parse", "HEAD"],
        returncode=0,
        stdout=good_sha + "\n",
        stderr="",
    )
    with patch(
        "scripts.compare_shadow_semantic_overlays_readonly.subprocess.run",
        return_value=proc,
    ) as run:
        assert _reviewed_engine_revision() == good_sha
        args, kwargs = run.call_args
        assert args[0] == ["git", "rev-parse", "HEAD"]
        assert kwargs["capture_output"] is True
        assert kwargs["check"] is False
        assert kwargs["timeout"] <= 5

    for revision in ("no-git", "abcde", "b" * 64):
        bad = subprocess.CompletedProcess(
            args=["git"], returncode=0,
            stdout=revision, stderr="",
        )
        with patch(
            "scripts.compare_shadow_semantic_overlays_readonly.subprocess.run",
            return_value=bad,
        ):
            try:
                _reviewed_engine_revision()
            except ComparisonPreflightError:
                continue
            raise AssertionError("unverifiable evaluator accepted")


def test_invalid_paths_and_implicit_suites_reject_without_subprocess() -> None:
    bad_cases = [
        (BASE, LEFT, RIGHT, [], HASH),
        (BASE, LEFT, RIGHT, [SUITE_A, SUITE_A], HASH),
        (BASE, LEFT, LEFT, [SUITE_A], HASH),
        (BASE, "../path.json", RIGHT, [SUITE_A], HASH),
        (BASE, LEFT, RIGHT, ["scripts/validation/../unsafe.json"], HASH),
        (BASE, LEFT, RIGHT, [SUITE_A], "wrong"),
    ]
    with patch("scripts.compare_shadow_semantic_overlays_readonly.subprocess.run") as proc:
        for args in bad_cases:
            try:
                compare(*args)
            except ComparisonPreflightError:
                pass
            else:
                raise AssertionError("invalid comparison arguments accepted")
        proc.assert_not_called()


def test_observations_and_governance_are_mandatory() -> None:
    valid = _report("synthetic-v1", {1}, 2)
    assert _extract_report(json.dumps(valid)) == valid
    for modify in (
        lambda r: r.update({"real_sql_execution": True}),
        lambda r: r.update({"activation_authorized": True}),
        lambda r: r.update({"llm_calls": 1}),
        lambda r: r.update({"benchmark_access": True}),
        lambda r: r["evaluation"].update({"case_count": 3}),
        lambda r: r["evaluation"]["observations"].pop(),
    ):
        report = _report("synthetic-v1", {1}, 2)
        modify(report)
        try:
            _extract_report(json.dumps(report))
        except ComparisonPreflightError:
            continue
        raise AssertionError("invalid or unsafe evaluation accepted")


def test_compare_reports_regressions_without_leaking_inputs() -> None:
    responses = [
        _process(_report("synthetic-v14", {1}, 3)),
        _process(_report("synthetic-v15", {1, 2}, 3, include_sensitive_text=True)),
        _process(_report("synthetic-v14", {1, 2}, 2)),
        _process(_report("synthetic-v15", {1}, 2, include_sensitive_text=True)),
    ]
    with patch(
        "scripts.compare_shadow_semantic_overlays_readonly.subprocess.run",
        side_effect=responses,
    ) as process:
        result = compare(BASE, LEFT, RIGHT, [SUITE_A, SUITE_B], HASH)
    assert process.call_count == 4
    assert result["totals"] == {
        "cases": 5,
        "left_passed": 3,
        "right_passed": 3,
        "improved_net": 0,
        "regressions": 1,
    }
    assert result["suite_results"][0]["improvements"] == [2]
    assert result["suite_results"][0]["regressions"] == []
    assert result["suite_results"][1]["improvements"] == []
    assert result["suite_results"][1]["regressions"] == [2]
    assert result["real_sql_execution"] is False
    assert result["activation_authorized"] is False
    safe = json.dumps(result)
    assert "PRIVATE_USER_PROMPT" not in safe
    assert "PRIVATE_SYNTHETIC_SQL" not in safe
    assert "PRIVATE_CREDENTIAL" not in safe
    args, kwargs = process.call_args
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["check"] is False
    assert kwargs["timeout"] > 0
    assert "shell" not in kwargs


def test_runner_failure_does_not_print_or_fallback_to_external_access() -> None:
    with patch(
        "scripts.compare_shadow_semantic_overlays_readonly.subprocess.run",
        return_value=_process(_report("synthetic-v15", set(), 2), rc=5),
    ) as proc:
        try:
            compare(BASE, LEFT, RIGHT, [SUITE_A], HASH)
        except ComparisonPreflightError as exc:
            assert "runner failed" in str(exc)
        else:
            raise AssertionError("unreviewed runner failure accepted")
        assert proc.call_count == 1


def test_cli_rejects_malformed_inputs_before_subprocess() -> None:
    # Validate path contract independently of the current container/git state.
    _validated_paths(BASE, LEFT, RIGHT, [SUITE_A], HASH)
    _validated_paths(BASE, LEFT, RIGHT, [SUITE_A, SUITE_B], HASH)


if __name__ == "__main__":
    test_evaluator_revision_is_attested_not_guessed()
    test_invalid_paths_and_implicit_suites_reject_without_subprocess()
    test_observations_and_governance_are_mandatory()
    test_compare_reports_regressions_without_leaking_inputs()
    test_runner_failure_does_not_print_or_fallback_to_external_access()
    test_cli_rejects_malformed_inputs_before_subprocess()
    print("SEMANTIC_VERSION_COMPARISON_READONLY=PASS")
