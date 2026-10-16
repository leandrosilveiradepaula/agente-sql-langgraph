from __future__ import annotations

"""Evaluation-only semantic/planning probe for a virtual candidate context.

Sources and candidate are never written. Expectations are inspected only
AFTER calling the semantic resolver and planner with the raw question.
This module imports no provider, SQL generator, SQL executor or benchmark.
"""

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.adapters.postgres.context_repository import PostgresContextRepository
from app.domain.intent_resolver import resolve_intent
from app.domain.planner import build_query_plan
from scripts.audit_semantic_candidate_parity_readonly import parse_parity_policy
from scripts.preview_semantic_candidate_readonly import (
    evaluate_in_memory_preflight,
    synthesize_candidate_snapshot,
)

_CASE_KEYS = frozenset({
    "question",
    "expected_intent",
    "expected_plan_status",
    "expected_error_code",
    "expected_temporal_issue",
})


def observe_plan(snapshot: Mapping[str, Any], question: str) -> dict[str, Any]:
    """Compute observations without access to expected results or other cases."""
    resolved = resolve_intent(question, snapshot["intent_resolution"])
    intent = resolved.get("intent")
    status, error_code = "intent_not_resolved", None
    projection: Mapping[str, Any] | None = None
    if isinstance(intent, str) and intent.strip():
        plan = build_query_plan(
            context=snapshot,
            intent_name=intent,
            intent_confidence=resolved.get("intent_confidence"),
            normalized_question=resolved.get("normalized_question", question),
            intent_resolution_result=resolved,
        )
        status = plan.get("status", "unknown")
        error_code = plan.get("error_code")
        value = plan.get("projection")
        if isinstance(value, Mapping):
            projection = value

    diagnostic: Mapping[str, Any] = {}
    if projection is not None:
        details = projection.get("diagnostics", {})
        if isinstance(details, Mapping):
            candidate = details.get("temporal_diagnostic", {})
            if isinstance(candidate, Mapping):
                diagnostic = candidate

    # Aggregate resolver evidence without returning questions, matched aliases,
    # configured rules or prompt material. These fields are observational only.
    candidates = resolved.get("candidates", [])
    candidates = candidates if isinstance(candidates, list) else []
    best = resolved.get("best_candidate")
    second = resolved.get("second_candidate")
    best = best if isinstance(best, Mapping) else {}
    second = second if isinstance(second, Mapping) else {}
    config = resolved.get("resolver_configuration")
    config = config if isinstance(config, Mapping) else {}
    catalog = resolved.get("intent_catalog")
    catalog = catalog if isinstance(catalog, Mapping) else {}
    defaults = resolved.get("semantic_defaults")
    defaults = defaults if isinstance(defaults, Mapping) else {}
    reason = resolved.get("reason")

    metric_count = projection.get("planned_metrics", []) if projection else []
    if not isinstance(metric_count, list):
        metric_count = []

    return {
        "intent": intent if isinstance(intent, str) else None,
        "intent_applied": resolved.get("applied") is True,
        "intent_resolution_reason": reason if isinstance(reason, str) else None,
        "candidate_count": len(candidates),
        "best_candidate_score": best.get("score") if isinstance(best.get("score"), (int, float)) else None,
        "second_candidate_score": second.get("score") if isinstance(second.get("score"), (int, float)) else None,
        "minimum_score": config.get("minimum_score") if isinstance(config.get("minimum_score"), (int, float)) else None,
        "ambiguity_margin": config.get("ambiguity_margin") if isinstance(config.get("ambiguity_margin"), (int, float)) else None,
        "intent_catalog_entries_evaluated": catalog.get("entries_evaluated") if isinstance(catalog.get("entries_evaluated"), int) else None,
        "semantic_defaults_applied_count": len(defaults.get("applied", [])) if isinstance(defaults.get("applied"), list) else 0,
        "plan_status": status,
        "plan_error_code": error_code,
        "temporal_status": diagnostic.get("status", "not_applicable"),
        "temporal_issues": sorted({
            issue for issue in diagnostic.get("issues", [])
            if isinstance(issue, str)
        }) if isinstance(diagnostic.get("issues", []), list) else [],
        "planned_metric_count": len(metric_count),
    }


def evaluate_suite(
    snapshot: Mapping[str, Any],
    suite: Mapping[str, Any],
) -> dict[str, Any]:
    """Read expectations strictly outside semantic/planning calls."""
    cases = suite.get("cases") if isinstance(suite, Mapping) else None
    if not isinstance(cases, list) or not cases or len(cases) > 256:
        raise ValueError("evaluation suite must contain 1-256 cases")

    observations: list[dict[str, Any]] = []
    passed = 0
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, Mapping) or not set(case) <= _CASE_KEYS:
            raise ValueError("evaluation case contains unsupported fields")
        question = case.get("question")
        expectations = {k: v for k, v in case.items() if k != "question"}
        if (
            not isinstance(question, str) or not question.strip()
            or not expectations
            or any(not isinstance(v, str) or not v.strip() for v in expectations.values())
        ):
            raise ValueError("evaluation case must contain a question and assertions")

        observed = observe_plan(snapshot, question)
        # Nothing from expectations was passed to observe_plan, resolve_intent,
        # build_query_plan, an LLM, a SQL generator or the candidate snapshot.
        failures: list[str] = []
        if "expected_intent" in expectations and (
            observed["intent"] != expectations["expected_intent"]
            or not observed["intent_applied"]
        ):
            failures.append("intent")
        if (
            "expected_plan_status" in expectations
            and observed["plan_status"] != expectations["expected_plan_status"]
        ):
            failures.append("plan_status")
        if (
            "expected_error_code" in expectations
            and observed["plan_error_code"] != expectations["expected_error_code"]
        ):
            failures.append("plan_error_code")
        if (
            "expected_temporal_issue" in expectations
            and expectations["expected_temporal_issue"] not in observed["temporal_issues"]
        ):
            failures.append("temporal_issue")
        ok = not failures
        passed += int(ok)
        observations.append({
            "case_index": index,
            "passed": ok,
            "failed_assertions": failures,
            **observed,
        })

    return {
        "status": "evaluation_passed" if passed == len(cases) else "evaluation_failed",
        "case_count": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "observations": observations,
        "read_only": True,
        "persisted_candidate": False,
        "real_sql_execution": False,
        "llm_calls": 0,
        "benchmark_access": False,
        "financial_semantics_verified": False,
        "activation_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--expected-source-fingerprint")
    args = parser.parse_args()

    if os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") != "false":
        print("ABORTED: real SQL execution must remain disabled.")
        return 3

    try:
        policy = parse_parity_policy(
            json.loads(Path(args.policy).read_text(encoding="utf-8"))
        )
        repository = PostgresContextRepository(
            dsn=os.environ["CONTEXT_POSTGRES_DSN"],
            semantic_agent_version=policy["source_version"],
            context_schema=os.environ.get("POSTGRES_CONTEXT_SCHEMA", "semantic_context"),
        )
        source = repository.load_active_context(user_profile="runtime_validation")
        if (
            args.expected_source_fingerprint is not None
            and source.get("fingerprint") != args.expected_source_fingerprint
        ):
            print("ABORTED: source fingerprint does not match expected value.")
            return 4

        readiness = evaluate_in_memory_preflight(source, policy)
        if readiness["status"] != "metadata_checks_passed":
            print(json.dumps({
                "status": "blocked_by_metadata",
                "preflight": readiness,
                "evaluation_attempted": False,
            }, ensure_ascii=False, sort_keys=True, indent=2))
            return 1

        candidate = synthesize_candidate_snapshot(source, policy)
        suite = json.loads(Path(args.cases).read_text(encoding="utf-8"))
        results = evaluate_suite(candidate, suite)
        print(json.dumps({
            "preflight": readiness,
            "evaluation": results,
            "source_version": source["version"],
            "source_fingerprint": source["fingerprint"],
            "candidate_version": candidate["version"],
            "candidate_fingerprint": candidate["fingerprint"],
        }, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if results["status"] == "evaluation_passed" else 1
    except Exception as exc:
        # Database and validation exceptions can include private metadata.
        print("CANDIDATE_GENERALIZATION_ERROR_TYPE:", type(exc).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
