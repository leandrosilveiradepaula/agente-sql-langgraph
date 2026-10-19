from __future__ import annotations

"""Evaluation-only semantic/planning probe for a virtual candidate context.

Sources and candidate are never written. Expectations are inspected only
AFTER calling the semantic resolver and planner with the raw question.
This module imports no provider, SQL generator, SQL executor or benchmark.
"""

import argparse
import json
import os
from math import isfinite
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


def summarize_resolution_evidence(resolved: Mapping[str, Any]) -> dict[str, Any]:
    """Numerical/structural attribution from actual resolver output.

    The report omits full questions, normalized text, signal patterns,
    configured terms, matched tokens, intent/concept names, descriptions
    and SQL. Ordinal indexes refer to the normalized catalog. No expected
    intent or test assertion is passed here.
    """
    config = resolved.get("resolver_configuration")
    config = config if isinstance(config, Mapping) else {}
    raw_candidates = resolved.get("candidates")
    candidates = raw_candidates if isinstance(raw_candidates, list) else []
    raw_catalog = resolved.get("intent_catalog")
    catalog = raw_catalog if isinstance(raw_catalog, Mapping) else {}
    raw_evaluations = catalog.get("evaluations")
    evaluations = raw_evaluations if isinstance(raw_evaluations, list) else []
    fallback = resolved.get("token_fallback")
    fallback = fallback if isinstance(fallback, Mapping) else {}
    defaults = resolved.get("semantic_defaults")
    defaults = defaults if isinstance(defaults, Mapping) else {}

    def safe_count(value: Any) -> int:
        return len(value) if isinstance(value, list) else 0

    def numeric(value: Any) -> float | None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        number = float(value)
        return number if isfinite(number) else None

    # Join internal candidate names to the catalog only transiently.
    # The public report contains ordinal positions, never business labels.
    catalog_positions = {
        entry.get("intent_name"): index
        for index, entry in enumerate(evaluations, start=1)
        if isinstance(entry, Mapping)
        and isinstance(entry.get("intent_name"), str)
    }
    evidence_candidates: list[dict[str, Any]] = []
    for rank, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, Mapping):
            continue
        matches = candidate.get("matches")
        matches = matches if isinstance(matches, list) else []
        catalog_match_count = sum(
            1 for item in matches
            if isinstance(item, Mapping)
            and item.get("match_strategy") == "intent_catalog_rule"
        )
        evidence_candidates.append({
            "candidate_rank": rank,
            "catalog_entry_index": catalog_positions.get(candidate.get("intent_name")),
            "score": numeric(candidate.get("score")),
            "positive_score": numeric(candidate.get("positive_score")),
            "negative_score": numeric(candidate.get("negative_score")),
            "matched_signal_count": len(matches) - catalog_match_count,
            "matched_catalog_scoring_rules": catalog_match_count,
        })

    catalog_evidence: list[dict[str, Any]] = []
    for entry_index, entry in enumerate(evaluations, start=1):
        if not isinstance(entry, Mapping):
            continue
        rules = entry.get("rules")
        rules = rules if isinstance(rules, list) else []
        rule_evidence: list[dict[str, Any]] = []
        for index, rule in enumerate(rules):
            if not isinstance(rule, Mapping):
                continue
            concepts = rule.get("concepts")
            concepts = concepts if isinstance(concepts, list) else []
            rule_evidence.append({
                "rule_index": index + 1,
                "effect": rule.get("effect"),
                "satisfied": rule.get("satisfied") is True,
                "matched_concept_count": rule.get("matched_concept_count"),
                "minimum_concept_matches": rule.get("minimum_concept_matches"),
                "concepts": [
                    {
                        "concept_index": concept_index,
                        "satisfied": concept.get("satisfied") is True,
                        "matched_term_count": concept.get("matched_term_count"),
                        "minimum_term_matches": concept.get("minimum_term_matches"),
                    }
                    for concept_index, concept in enumerate(concepts, start=1)
                    if isinstance(concept, Mapping)
                ],
            })
        missing_required_concepts = [
            {
                "rule_index": rule["rule_index"],
                "concept_indexes": [
                    item["concept_index"]
                    for item in rule["concepts"]
                    if not item["satisfied"]
                ],
            }
            for rule in rule_evidence
            if rule["effect"] == "require" and not rule["satisfied"]
        ]
        catalog_evidence.append({
            "entry_index": entry_index,
            "missing_required_concepts": missing_required_concepts,
            "eligible": entry.get("eligible") is True,
            "excluded": entry.get("excluded") is True,
            "required_rule_count": entry.get("require_rule_count"),
            "satisfied_required_rule_count": entry.get(
                "satisfied_require_rule_count"
            ),
            "catalog_positive_score": numeric(entry.get("positive_score")),
            "catalog_negative_score": numeric(entry.get("negative_score")),
            "rules": rule_evidence,
        })

    return {
        "reason": resolved.get("reason"),
        "minimum_score": numeric(config.get("minimum_score")),
        "ambiguity_margin": numeric(config.get("ambiguity_margin")),
        "candidate_count": len(evidence_candidates),
        "candidates": evidence_candidates,
        "token_fallback_enabled": fallback.get("enabled") is True,
        "token_fallback_used": fallback.get("used_for_selected_intent") is True,
        "semantic_default_count": safe_count(defaults.get("applied")),
        "semantic_defaults_suppressed_count": safe_count(defaults.get("suppressed")),
        "catalog_entries_evaluated": len(catalog_evidence),
        "catalog_evidence": catalog_evidence,
    }


# Only protocol-level binding statuses are allowed into evaluation evidence.
# Never emit metric/condition names, source tables, SQL or user vocabulary.
_PUBLIC_BINDING_STATUSES = frozenset({
    "resolved",
    "unresolved",
    "not_applicable",
    "invalid_metadata",
    "ambiguous_metric_concept",
    "metric_binding_not_applicable",
    "metric_binding_ambiguous",
    "metric_binding_below_minimum",
    "metric_binding_above_maximum",
    "metric_binding_ref_missing",
    "metric_binding_duplicate_ref",
    "metric_binding_concept_mismatch",
    "metric_binding_cardinality_conflict",
})


def summarize_planned_metric_evidence(
    projection: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Reduce planner binding evidence to counts and structural statuses.

    The projection itself can include business names and physical metadata.
    None is returned. This is evaluation-only, never a planning input.
    """
    if not isinstance(projection, Mapping):
        return None
    diagnostics = projection.get("diagnostics")
    if not isinstance(diagnostics, Mapping):
        return None
    metric = diagnostics.get("planned_metric_diagnostic")
    if not isinstance(metric, Mapping):
        return None

    def count(value: Any) -> int:
        return len(value) if isinstance(value, list) else 0

    def status(value: Any) -> str:
        return (
            value if isinstance(value, str)
            and value in _PUBLIC_BINDING_STATUSES
            else "other"
        )

    inference = metric.get("binding_inference")
    inference = inference if isinstance(inference, Mapping) else {}
    failures = metric.get("binding_failures")
    failures = failures if isinstance(failures, list) else []
    nested = []
    for failure in failures:
        if not isinstance(failure, Mapping):
            continue
        bindings = failure.get("binding_diagnostics")
        if isinstance(bindings, list):
            nested.extend(item for item in bindings if isinstance(item, Mapping))
    inferred_bindings = inference.get("binding_diagnostics")
    if not nested and isinstance(inferred_bindings, list):
        nested.extend(item for item in inferred_bindings if isinstance(item, Mapping))

    rejected_conditions = {
        "when_present_missing": 0,
        "when_absent_present": 0,
        "invalid_metadata": 0,
        "invalid_physical_target": 0,
    }
    required_missing = 0
    forbidden_present = 0
    configured_count = 0
    applicable_count = 0
    for entry in nested:
        configured = entry.get("configured_count")
        applicable = entry.get("applicable_count")
        if type(configured) is int and configured >= 0:
            configured_count += configured
        if type(applicable) is int and applicable >= 0:
            applicable_count += applicable
        rejected = entry.get("rejected")
        if not isinstance(rejected, list):
            continue
        for item in rejected:
            if not isinstance(item, Mapping):
                continue
            reason = item.get("reason")
            if isinstance(reason, str) and reason in rejected_conditions:
                rejected_conditions[reason] += 1
            required_missing += count(item.get("missing_present"))
            forbidden_present += count(item.get("blocked_absent"))

    return {
        "metric_requested": metric.get("metric_requested") is True,
        "matched_metric_term_count": count(metric.get("matched_terms")),
        "unresolved_metric_term_count": count(metric.get("unresolved_terms")),
        "invalid_metadata_metric_term_count": count(metric.get("invalid_metadata_terms")),
        "binding_context_concept_count": count(metric.get("binding_context_concepts")),
        "binding_failure_count": len(failures),
        "binding_inference_status": status(inference.get("status")),
        "global_binding_status": status(metric.get("global_binding_status")),
        "configured_binding_count": configured_count,
        "applicable_binding_count": applicable_count,
        "rejected_binding_reasons": rejected_conditions,
        "missing_required_binding_condition_count": required_missing,
        "conflicting_absent_binding_condition_count": forbidden_present,
    }


def observe_plan(snapshot: Mapping[str, Any], question: str) -> dict[str, Any]:
    """Compute observations without access to expected results or other cases."""
    resolved = resolve_intent(question, snapshot["intent_resolution"])
    evidence = summarize_resolution_evidence(resolved)
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

    metric_count = projection.get("planned_metrics", []) if projection else []
    if not isinstance(metric_count, list):
        metric_count = []

    return {
        "intent": intent if isinstance(intent, str) else None,
        "intent_applied": resolved.get("applied") is True,
        "planned_metric_evidence": summarize_planned_metric_evidence(projection),
        "plan_status": status,
        "plan_error_code": error_code,
        "temporal_status": diagnostic.get("status", "not_applicable"),
        "temporal_issues": sorted({
            issue for issue in diagnostic.get("issues", [])
            if isinstance(issue, str)
        }) if isinstance(diagnostic.get("issues", []), list) else [],
        "planned_metric_count": len(metric_count),
        "_resolver_evidence": evidence,
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
        resolution_evidence = observed.pop("_resolver_evidence", None)
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
        record = {
            "case_index": index,
            "passed": ok,
            "failed_assertions": failures,
            **observed,
        }
        if not ok and resolution_evidence is not None:
            record["resolution_evidence"] = resolution_evidence
        observations.append(record)

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
