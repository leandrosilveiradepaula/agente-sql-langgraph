from __future__ import annotations

"""Compare two explicitly selected virtual semantic candidates on reviewed suites.

Delegates every evaluation to the existing fail-closed, read-only Shadow
runner. Does not access a database, model, benchmark, generator or executor.
Prints only sanitized post-evaluation metrics; never prints raw runner output.
"""

import argparse
import json
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNNER = "scripts/run_shadow_semantic_overlay_preflight.sh"
POLICY_PATH = re.compile(r"^semantic_context/[A-Za-z0-9._-]+\.json$")
SUITE_PATH = re.compile(r"^scripts/validation/[A-Za-z0-9._-]+\.json$")
FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
MAX_SUITE_FILES = 12
RUN_TIMEOUT_SECONDS = 180


class ComparisonPreflightError(ValueError):
    pass


def _reviewed_engine_revision() -> str:
    """Attest the evaluator git commit to avoid misleading cross-run comparisons."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT, capture_output=True, text=True,
            check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ComparisonPreflightError("cannot attest evaluator revision") from exc
    revision = proc.stdout.strip()
    if proc.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ComparisonPreflightError("invalid evaluator git revision")
    return revision


def _validated_paths(
    base: str, left: str, right: str,
    suites: list[str], fingerprint: str,
) -> None:
    if not all(
        isinstance(path, str) and POLICY_PATH.fullmatch(path)
        for path in (base, left, right)
    ):
        raise ComparisonPreflightError("invalid policy path")
    if left == right:
        raise ComparisonPreflightError("candidate policies must differ")
    if not isinstance(fingerprint, str) or not FINGERPRINT.fullmatch(fingerprint):
        raise ComparisonPreflightError("invalid fingerprint")
    if (
        not isinstance(suites, list)
        or not 1 <= len(suites) <= MAX_SUITE_FILES
        or len(set(suites)) != len(suites)
        or any(not isinstance(item, str) or not SUITE_PATH.fullmatch(item)
               for item in suites)
    ):
        raise ComparisonPreflightError("invalid explicitly selected suites")


def _extract_report(stdout: str) -> dict[str, Any]:
    report = None
    for line in stdout.splitlines():
        if not line.lstrip().startswith("{"):
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and isinstance(value.get("evaluation"), dict):
            report = value
    if report is None:
        raise ComparisonPreflightError("runner produced no evaluation report")
    evaluation = report["evaluation"]
    if not (
        report.get("read_only") is True
        and report.get("real_sql_execution") is False
        and report.get("persisted_candidate") is False
        and report.get("activation_authorized") is False
        and report.get("llm_calls") == 0
        and report.get("benchmark_access") is False
        and evaluation.get("read_only") is True
        and evaluation.get("real_sql_execution") is False
        and evaluation.get("llm_calls") == 0
        and evaluation.get("benchmark_access") is False
    ):
        raise ComparisonPreflightError("missing read-only governance evidence")

    observations = evaluation.get("observations")
    count = evaluation.get("case_count")
    passed = evaluation.get("passed")
    if (
        type(count) is not int or count < 1
        or type(passed) is not int or passed < 0 or passed > count
        or not isinstance(observations, list) or len(observations) != count
        or {item.get("case_index") for item in observations
            if isinstance(item, Mapping)}
           != set(range(1, count + 1))
        or any(not isinstance(item, Mapping)
               or type(item.get("passed")) is not bool
               for item in observations)
        or sum(1 for item in observations if item["passed"]) != passed
    ):
        raise ComparisonPreflightError("invalid evaluation observation contract")
    return report


def _run(
    base: str, candidate: str, suite: str, fingerprint: str,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["bash", RUNNER, base, candidate, fingerprint, suite],
            cwd=ROOT, capture_output=True, text=True,
            check=False, timeout=RUN_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ComparisonPreflightError("runner unavailable or timed out") from exc
    if completed.returncode not in (0, 1):
        # Never print stderr/stdout: unexpected errors can contain secrets.
        raise ComparisonPreflightError("runner failed before evaluation")
    report = _extract_report(completed.stdout)
    if report.get("source_fingerprint") != fingerprint:
        raise ComparisonPreflightError("source fingerprint mismatch")
    if not isinstance(report.get("candidate_version"), str):
        raise ComparisonPreflightError("candidate version missing")
    return report


def _success_indexes(report: Mapping[str, Any]) -> set[int]:
    return {
        item["case_index"]
        for item in report["evaluation"]["observations"]
        if item["passed"] is True
    }


def _sanitized_failures(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expose only numeric rule positions and finite scores, never terms."""
    result = []
    for item in report["evaluation"]["observations"]:
        if item["passed"]:
            continue
        resolution = item.get("resolution_evidence") or {}
        metric = item.get("planned_metric_evidence") or {}
        candidates = (
            resolution.get("candidates", [])
            if isinstance(resolution, Mapping) else []
        )
        catalog = (
            resolution.get("catalog_evidence", [])
            if isinstance(resolution, Mapping) else []
        )
        top_candidates = []
        for candidate in candidates[:3] if isinstance(candidates, list) else []:
            if not isinstance(candidate, Mapping):
                continue
            score = candidate.get("score")
            if (
                type(score) not in (int, float)
                or not -100000 <= score <= 100000
            ):
                continue
            top_candidates.append({
                "catalog_index": candidate.get("catalog_entry_index")
                if type(candidate.get("catalog_entry_index")) is int else None,
                "score": score,
                "signal_count": candidate.get("matched_signal_count")
                if type(candidate.get("matched_signal_count")) is int else None,
            })
        partial_rules = []
        for entry in catalog if isinstance(catalog, list) else []:
            if not isinstance(entry, Mapping):
                continue
            for rule in entry.get("rules", []):
                if not isinstance(rule, Mapping):
                    continue
                matched = rule.get("matched_concept_count")
                required = rule.get("minimum_concept_matches")
                if not (
                    rule.get("effect") == "positive_score"
                    and type(matched) is int and type(required) is int
                    and 0 < matched < required
                ):
                    continue
                partial_rules.append({
                    "catalog_index": entry.get("entry_index")
                    if type(entry.get("entry_index")) is int else None,
                    "rule_index": rule.get("rule_index")
                    if type(rule.get("rule_index")) is int else None,
                    "matched": matched,
                    "required": required,
                })
        result.append({
            "case": item["case_index"],
            "intent": item.get("intent"),
            "plan": item.get("plan_status"),
            "error": item.get("plan_error_code"),
            "temporal_issues": item.get("temporal_issues") or [],
            "resolution_reason": (
                resolution.get("reason")
                if isinstance(resolution, Mapping) else None
            ),
            "metric_inference": (
                metric.get("binding_inference_status")
                if isinstance(metric, Mapping) else None
            ),
            "metric_count": item.get("planned_metric_count")
            if type(item.get("planned_metric_count")) is int else None,
            "top_candidates": top_candidates,
            "partial_scoring_rules": partial_rules[:8],
        })
    return result


def compare(
    base: str, left: str, right: str,
    suites: list[str], fingerprint: str,
) -> dict[str, Any]:
    _validated_paths(base, left, right, suites, fingerprint)
    summary: list[dict[str, Any]] = []
    total_left = total_right = total_cases = 0
    all_regressions = 0
    for suite in suites:
        prior = _run(base, left, suite, fingerprint)
        proposed = _run(base, right, suite, fingerprint)
        a, b = prior["evaluation"], proposed["evaluation"]
        if a["case_count"] != b["case_count"]:
            raise ComparisonPreflightError("candidate suite count mismatch")
        a_pass = _success_indexes(prior)
        b_pass = _success_indexes(proposed)
        regressions = sorted(a_pass - b_pass)
        total_cases += a["case_count"]
        total_left += a["passed"]
        total_right += b["passed"]
        all_regressions += len(regressions)
        summary.append({
            "suite": suite.rsplit("/", 1)[-1],
            "case_count": a["case_count"],
            "left_version": prior["candidate_version"],
            "left_passed": a["passed"],
            "right_version": proposed["candidate_version"],
            "right_passed": b["passed"],
            "improvements": sorted(b_pass - a_pass),
            "regressions": regressions,
            "remaining_failures": _sanitized_failures(proposed),
        })
    return {
        "read_only": True,
        "real_sql_execution": False,
        "context_persisted": False,
        "activation_authorized": False,
        "llm_calls": 0,
        "suite_results": summary,
        "totals": {
            "cases": total_cases,
            "left_passed": total_left,
            "right_passed": total_right,
            "improved_net": total_right - total_left,
            "regressions": all_regressions,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-policy", required=True)
    parser.add_argument("--left", required=True)
    parser.add_argument("--right", required=True)
    parser.add_argument("--expected-source-fingerprint", required=True)
    parser.add_argument("--suite", action="append", required=True)
    args = parser.parse_args()
    try:
        revision = _reviewed_engine_revision()
        report = compare(
            args.base_policy, args.left, args.right,
            args.suite, args.expected_source_fingerprint,
        )
    except ComparisonPreflightError as exc:
        print("COMPARISON_ABORTED:", str(exc))
        return 2
    except Exception as exc:
        print("COMPARISON_ERROR_TYPE:", type(exc).__name__)
        return 3

    print("EVALUATOR_GIT_SHA:", revision)
    print(
        "NOTE: zero regressions compares contexts on this same evaluator; "
        "it does not validate behavior against older engine commits."
    )
    for result in report["suite_results"]:
        print(
            "SUITE", result["suite"],
            result["left_version"], f'{result["left_passed"]}/{result["case_count"]}',
            result["right_version"], f'{result["right_passed"]}/{result["case_count"]}',
        )
        print("  IMPROVEMENTS:", result["improvements"])
        print("  REGRESSIONS:", result["regressions"])
        for failure in result["remaining_failures"]:
            print("  FAILURE:", json.dumps(failure, sort_keys=True, ensure_ascii=False))
    print("SUMMARY:", json.dumps(report["totals"], sort_keys=True))
    print("READ_ONLY=true SQL_EXECUTION=false ACTIVATION_AUTHORIZED=false")
    return 1 if report["totals"]["regressions"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
