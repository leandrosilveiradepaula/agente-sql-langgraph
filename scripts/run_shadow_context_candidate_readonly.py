from __future__ import annotations

"""Read-only semantic/planning evaluation of an isolated context version.

No provider, generator, SQL executor, benchmark loader or evidence-writer imports.
The evaluation fixture is read only after semantic resolution and planning.
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


def plan_expectation_failures(
    projection: Mapping[str, Any] | None,
    expected: Any,
) -> list[str]:
    if not isinstance(expected, Mapping):
        return []
    if not isinstance(projection, Mapping):
        return ["projection_missing"]

    metrics = projection.get("planned_metrics", [])
    operations = projection.get("analytical_operations", [])
    metrics = metrics if isinstance(metrics, list) else []
    operations = operations if isinstance(operations, list) else []
    failures: list[str] = []

    minimum = expected.get("minimum_planned_metrics")
    if isinstance(minimum, int) and not isinstance(minimum, bool):
        if len(metrics) < minimum:
            failures.append("planned_metrics_below_minimum")

    op_type = expected.get("operation_type")
    if isinstance(op_type, str):
        matched = [
            item for item in operations
            if isinstance(item, Mapping) and item.get("operation_type") == op_type
        ]
        if not matched:
            failures.append("expected_operation_missing")
        if expected.get("operation_metric_ref") is True and not any(
            isinstance(item.get("metric_ref"), str)
            and bool(item["metric_ref"].strip())
            for item in matched
        ):
            failures.append("operation_metric_ref_missing")
        min_operands = expected.get("minimum_operand_metric_refs")
        if isinstance(min_operands, int) and not isinstance(min_operands, bool):
            count = max(
                (
                    len(item.get("operand_metric_refs", []))
                    for item in matched
                    if isinstance(item.get("operand_metric_refs"), list)
                ),
                default=0,
            )
            if count < min_operands:
                failures.append("operand_metric_refs_below_minimum")

    return failures


def evaluate_candidate(snapshot: Mapping[str, Any], cases: list[Any]) -> tuple[int, int]:
    semantic_passed = 0
    planning_passed = 0
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, Mapping):
            raise ValueError("invalid evaluation case")
        question = case.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("case question missing")
        # Keep evaluation-only expected values strictly OUTSIDE every agent call.
        intent = resolve_intent(question, snapshot["intent_resolution"])
        observed_intent = intent.get("intent")
        semantic_ok = (
            intent.get("applied") is True
            and observed_intent == case.get("expected_intent")
        )
        semantic_passed += int(semantic_ok)
        status, code = "intent_not_resolved", None
        projection: Mapping[str, Any] | None = None
        if isinstance(observed_intent, str) and observed_intent.strip():
            plan = build_query_plan(
                context=snapshot,
                intent_name=observed_intent,
                intent_confidence=intent.get("intent_confidence"),
                normalized_question=intent.get("normalized_question", question),
                intent_resolution_result=intent,
            )
            status = plan.get("status", "unknown")
            code = plan.get("error_code")
            raw = plan.get("projection")
            projection = raw if isinstance(raw, Mapping) else None

        expected_plan_status = case.get("expected_plan_status", "planned")
        failures = plan_expectation_failures(
            projection, case.get("expected_plan")
        )
        plan_ok = (
            semantic_ok and status == expected_plan_status and not failures
        )
        planning_passed += int(plan_ok)

        diagnostic = (
            (projection.get("diagnostics", {}) if projection else {})
            .get("temporal_diagnostic", {})
        )
        if not isinstance(diagnostic, Mapping):
            diagnostic = {}
        metric_count = len(projection.get("planned_metrics", [])) if projection else 0
        print("CASE:", index)
        print("INTENT:", observed_intent)
        print("INTENT_RESULT:", "PASS" if semantic_ok else "FAIL")
        print("PLAN_STATUS:", status)
        print("PLAN_ERROR_CODE:", code)
        print("PLANNED_METRICS:", metric_count)
        print("TEMPORAL_REQUIRED:", diagnostic.get("required", False))
        print("TEMPORAL_STATUS:", diagnostic.get("status", "not_applicable"))
        print("TEMPORAL_ISSUES:", diagnostic.get("issues", []))
        print("EXPECTATION_FAILURES:", failures)
        print("PLAN_RESULT:", "PASS" if plan_ok else "FAIL")
        print("---")

    print("SEMANTIC_SUMMARY:", f"{semantic_passed}/{len(cases)} PASS")
    print("PLANNING_SUMMARY:", f"{planning_passed}/{len(cases)} PASS")
    return semantic_passed, planning_passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--cases", required=True)
    args = parser.parse_args()

    if os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION", "").casefold() != "false":
        print("ABORTED: real SQL execution must remain explicitly disabled.")
        return 3

    suite = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("evaluation suite contains no cases")

    repo = PostgresContextRepository(
        dsn=os.environ["CONTEXT_POSTGRES_DSN"],
        semantic_agent_version=args.version,
        context_schema=os.environ.get(
            "POSTGRES_CONTEXT_SCHEMA", "semantic_context"
        ),
    )
    snapshot = repo.load_active_context(user_profile="runtime_validation")
    if snapshot.get("version") != args.version:
        print("ABORTED: unexpected semantic context version.")
        return 4
    print("SUITE:", suite.get("suite", "semantic-candidate-readonly"))
    print("VERSION:", snapshot["version"])
    print("FINGERPRINT:", snapshot["fingerprint"])
    semantics, plans = evaluate_candidate(snapshot, cases)
    return 0 if semantics == plans == len(cases) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # A psycopg exception could contain connection metadata; never echo it.
        print("VALIDATION_ERROR_TYPE:", type(exc).__name__)
        raise SystemExit(2) from None
