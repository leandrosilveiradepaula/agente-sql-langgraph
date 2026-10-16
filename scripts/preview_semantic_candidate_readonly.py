from __future__ import annotations

"""Preview an immutable semantic candidate entirely in memory.

This module never imports a SQL generator, executor, provider or migration
runner. Business definitions come solely from an explicit versioned policy.
"""

import argparse
import json
import os
import re
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.adapters.postgres.context_repository import PostgresContextRepository
from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.context_validator import validate_context_snapshot
from scripts.audit_semantic_candidate_parity_readonly import (
    compare_semantic_snapshots,
    parse_parity_policy,
)
from scripts.preflight_semantic_candidate_readonly import (
    evaluate_candidate_readiness,
)


_SOURCE_KEYS = {
    "rules": "regras",
    "entities": "entidades",
    "dre_mappings": "dre",
    "query_patterns": "padroes",
    "table_catalog": "catalogo",
}
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")


def synthesize_candidate_snapshot(
    source: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive a hypothetical candidate from a normalized SELECT-only snapshot.

    Never mutates input objects. Fail closed on version, schema, or component
    collisions; do not silently override existing semantic business rules.
    """
    parsed = parse_parity_policy(policy)
    if source.get("version") != parsed["source_version"]:
        raise ValueError("source version does not match candidate policy")
    fingerprint = source.get("fingerprint")
    if not isinstance(fingerprint, str) or not _FINGERPRINT.fullmatch(fingerprint):
        raise ValueError("source fingerprint missing or malformed")

    raw: dict[str, Any] = {
        "semantic_agent_version": parsed["candidate_version"],
        "semantic_context_source": source.get("source"),
    }
    for source_name, target_name in _SOURCE_KEYS.items():
        records = source.get(source_name)
        if not isinstance(records, list) or any(
            not isinstance(item, Mapping) for item in records
        ):
            raise ValueError("source collection missing or malformed")
        raw[target_name] = deepcopy(records)

    existing_rule_names: set[tuple[str, str]] = set()
    configured_components: set[str] = set()
    for rule in raw["regras"]:
        identity = (
            str(rule.get("rule_group", "")).strip().casefold(),
            str(rule.get("rule_name", "")).strip().casefold(),
        )
        if identity in existing_rule_names:
            raise ValueError("source has duplicate rule identity")
        existing_rule_names.add(identity)
        content = rule.get("rule_content")
        if isinstance(content, Mapping):
            component = content.get("component")
            if isinstance(component, str) and component.strip():
                configured_components.add(component.strip().casefold())

    for addition in parsed["allowed_new_rules"]:
        rule = deepcopy(addition["expected_record"])
        identity = (
            rule["rule_group"].strip().casefold(),
            rule["rule_name"].strip().casefold(),
        )
        if identity in existing_rule_names:
            raise ValueError("candidate rule already exists in source")
        existing_rule_names.add(identity)
        component = rule["rule_content"].get("component")
        if isinstance(component, str) and component.strip():
            normalized = component.strip().casefold()
            if normalized in configured_components:
                raise ValueError("candidate component collides with source")
            configured_components.add(normalized)
        raw["regras"].append(rule)

    candidate = normalize_context_snapshot(raw)
    comparison = compare_semantic_snapshots(source, candidate, parsed)
    if comparison["status"] != "parity_match":
        raise ValueError("in-memory clone failed exact metadata parity")
    if candidate["fingerprint"] == source["fingerprint"]:
        raise ValueError("candidate fingerprint unexpectedly unchanged")
    return candidate


def evaluate_in_memory_preflight(
    source: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Pure, sanitized report; never certifies finance semantics or activation."""
    parsed = parse_parity_policy(policy)
    candidate = synthesize_candidate_snapshot(source, parsed)
    parity = compare_semantic_snapshots(source, candidate, parsed)
    source_validation = validate_context_snapshot(source)
    candidate_validation = validate_context_snapshot(candidate)
    readiness = evaluate_candidate_readiness(candidate)

    def validation_codes(report: Mapping[str, Any]) -> list[str]:
        return sorted({
            str(item.get("code", "unknown"))
            for item in report.get("errors", [])
            if isinstance(item, Mapping)
        })

    readiness_codes = sorted({
        str(item.get("code", "unknown"))
        for item in readiness["blocking_issues"]
        if isinstance(item, Mapping)
    })
    is_preflight_ok = (
        parity["status"] == "parity_match"
        and source_validation["status"] == "valid"
        and candidate_validation["status"] == "valid"
        and readiness["status"] == "checks_passed"
    )
    return {
        "status": "metadata_checks_passed" if is_preflight_ok else "blocked",
        "source_version": parsed["source_version"],
        "candidate_version": parsed["candidate_version"],
        "source_fingerprint": source["fingerprint"],
        "candidate_fingerprint": candidate["fingerprint"],
        "parity_status": parity["status"],
        "source_structural_status": source_validation["status"],
        "candidate_structural_status": candidate_validation["status"],
        "source_structural_error_codes": validation_codes(source_validation),
        "candidate_structural_error_codes": validation_codes(candidate_validation),
        "candidate_readiness_status": readiness["status"],
        "candidate_readiness_blocking_codes": readiness_codes,
        "temporal_strategy": readiness["temporal_strategy"],
        "metric_bindings_checked": readiness["metric_bindings_checked"],
        "filter_bindings_checked": readiness["filter_bindings_checked"],
        "persisted_candidate": False,
        "read_only": True,
        "physical_schema_verified": False,
        "financial_semantics_verified": False,
        "activation_authorized": False,
        "real_sql_execution": False,
        "llm_calls": 0,
        "benchmark_access": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    parser.add_argument("--expected-source-fingerprint")
    args = parser.parse_args()

    if os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") != "false":
        print("ABORTED: real SQL execution must remain disabled.")
        return 3

    try:
        policy = parse_parity_policy(
            json.loads(Path(args.policy).read_text(encoding="utf-8"))
        )
        repo = PostgresContextRepository(
            dsn=os.environ["CONTEXT_POSTGRES_DSN"],
            semantic_agent_version=policy["source_version"],
            context_schema=os.environ.get("POSTGRES_CONTEXT_SCHEMA", "semantic_context"),
        )
        source = repo.load_active_context(user_profile="runtime_validation")
        if (
            args.expected_source_fingerprint is not None
            and source.get("fingerprint") != args.expected_source_fingerprint
        ):
            print("ABORTED: source fingerprint does not match expected value.")
            return 4
        report = evaluate_in_memory_preflight(source, policy)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if report["status"] == "metadata_checks_passed" else 1
    except Exception as exc:
        # Database/normalization errors may contain DSNs or sensitive values.
        print("CANDIDATE_PREVIEW_ERROR_TYPE:", type(exc).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
