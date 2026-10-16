from __future__ import annotations

"""Read-only comparison of versioned semantic snapshots.

No generator, benchmark, data warehouse, SQL executor, migrations or writes.
The policy describes the allowed delta; the Python engine only compares it.
"""

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.adapters.postgres.context_repository import PostgresContextRepository
from app.domain.context_validator import validate_context_snapshot


_COLLECTIONS = (
    "rules",
    "entities",
    "dre_mappings",
    "query_patterns",
    "table_catalog",
)

# Structural rule shape returned by the normalized Postgres context reader.
# Concrete rule content belongs exclusively in the versioned parity policy.
_RULE_FIELDS = {
    "rule_group",
    "rule_name",
    "rule_content",
    "applies_to_intents",
    "validation_hint",
    "severity",
    "priority",
}


def _rule_key(item: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(item.get("rule_group", "")).strip().casefold(),
        str(item.get("rule_name", "")).strip().casefold(),
    )


def parse_parity_policy(value: Any) -> dict[str, Any]:
    """Read strict, versioned authorization for new metadata rule records."""
    if not isinstance(value, Mapping) or set(value) != {
        "source_version", "candidate_version", "allowed_new_rules"
    }:
        raise ValueError("invalid parity policy structure")
    source = value["source_version"]
    candidate = value["candidate_version"]
    if (
        not isinstance(source, str) or not source.strip()
        or not isinstance(candidate, str) or not candidate.strip()
        or source.strip().casefold() == candidate.strip().casefold()
    ):
        raise ValueError("source and candidate versions must differ")
    raw_additions = value["allowed_new_rules"]
    if not isinstance(raw_additions, list):
        raise ValueError("allowed_new_rules must be a list")
    additions: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_additions:
        if not isinstance(item, Mapping) or set(item) != {
            "rule_group", "rule_name", "expected_record"
        }:
            raise ValueError("allowed rule entry must declare its exact expected record")
        group, name = item["rule_group"], item["rule_name"]
        if not isinstance(group, str) or not group.strip() or not isinstance(name, str) or not name.strip():
            raise ValueError("allowed rule selector must have non-empty strings")
        key = (group.strip().casefold(), name.strip().casefold())
        if key in seen:
            raise ValueError("duplicate rule selector")
        expected = item["expected_record"]
        if not isinstance(expected, Mapping) or set(expected) != _RULE_FIELDS:
            raise ValueError("expected record has an invalid structural shape")
        if _rule_key(expected) != key:
            raise ValueError("expected rule identity differs from selector")
        if (
            not isinstance(expected.get("rule_content"), Mapping)
            or not isinstance(expected.get("applies_to_intents"), list)
            or not all(isinstance(x, str) for x in expected["applies_to_intents"])
            or not isinstance(expected.get("severity"), str)
            or not isinstance(expected.get("priority"), int)
            or isinstance(expected.get("priority"), bool)
        ):
            raise ValueError("expected record is incomplete or improperly typed")
        seen.add(key)
        additions.append({
            "rule_group": group.strip(),
            "rule_name": name.strip(),
            "expected_record": dict(expected),
        })
    return {
        "source_version": source.strip(),
        "candidate_version": candidate.strip(),
        "allowed_new_rules": additions,
    }


def _record_counts(value: Any) -> Counter[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        return None
    return Counter(
        json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        for item in value
    )


def compare_semantic_snapshots(
    source: Mapping[str, Any],
    candidate: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail closed on undocumented content drift, even at equal row counts."""
    parsed = parse_parity_policy(policy)
    errors: set[str] = set()
    collections: list[dict[str, Any]] = []

    if source.get("version") != parsed["source_version"]:
        errors.add("SOURCE_VERSION_MISMATCH")
    if candidate.get("version") != parsed["candidate_version"]:
        errors.add("CANDIDATE_VERSION_MISMATCH")
    if not source.get("fingerprint") or not candidate.get("fingerprint"):
        errors.add("FINGERPRINT_MISSING")

    allowed = {
        _rule_key(item): item["expected_record"]
        for item in parsed["allowed_new_rules"]
    }
    allowed_counts = {key: 0 for key in allowed}
    source_rules = source.get("rules")
    candidate_rules = candidate.get("rules")
    candidate_filtered = candidate_rules
    if not isinstance(source_rules, list) or not isinstance(candidate_rules, list):
        errors.add("RULE_COLLECTION_INVALID")
    elif any(not isinstance(item, Mapping) for item in source_rules + candidate_rules):
        errors.add("RULE_COLLECTION_INVALID")
    else:
        original_keys = {_rule_key(item) for item in source_rules}
        if any(key in original_keys for key in allowed):
            errors.add("ALLOWED_RULE_ALREADY_IN_SOURCE")
        candidate_filtered = []
        for rule in candidate_rules:
            key = _rule_key(rule)
            if key in allowed:
                allowed_counts[key] += 1
                if _record_counts([rule]) != _record_counts([allowed[key]]):
                    errors.add("ALLOWED_RULE_PAYLOAD_MISMATCH")
            else:
                candidate_filtered.append(rule)
        if any(count != 1 for count in allowed_counts.values()):
            errors.add("ALLOWED_RULE_MISSING_OR_DUPLICATED")

    for collection in _COLLECTIONS:
        original = source.get(collection)
        proposed = candidate_filtered if collection == "rules" else candidate.get(collection)
        before = _record_counts(original)
        after = _record_counts(proposed)
        matches = before is not None and after is not None and before == after
        if not matches:
            errors.add("COLLECTION_MISMATCH_" + collection.upper())
        collections.append({
            "collection": collection,
            "source_count": len(original) if isinstance(original, list) else None,
            "candidate_count": len(candidate.get(collection)) if isinstance(candidate.get(collection), list) else None,
            "content_equal_except_allowed_rules": matches,
        })

    return {
        "status": "parity_match" if not errors else "blocked",
        "source_version": parsed["source_version"],
        "candidate_version": parsed["candidate_version"],
        "source_fingerprint": source.get("fingerprint"),
        "candidate_fingerprint": candidate.get("fingerprint"),
        "allowed_new_rule_count": len(allowed),
        "collections": collections,
        "blocking_codes": sorted(errors),
        "read_only": True,
        "real_sql_execution": False,
        "llm_calls": 0,
        "benchmark_access": False,
        "financial_validation_complete": False,
        "activation_authorized": False,
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
        policy = parse_parity_policy(json.loads(Path(args.policy).read_text(encoding="utf-8")))
        snapshots: dict[str, Mapping[str, Any]] = {}
        for key in ("source_version", "candidate_version"):
            version = policy[key]
            repo = PostgresContextRepository(
                dsn=os.environ["CONTEXT_POSTGRES_DSN"],
                semantic_agent_version=version,
                context_schema=os.environ.get("POSTGRES_CONTEXT_SCHEMA", "semantic_context"),
            )
            snapshots[key] = repo.load_active_context(user_profile="runtime_validation")

        source = snapshots["source_version"]
        candidate = snapshots["candidate_version"]
        report = compare_semantic_snapshots(source, candidate, policy)
        for key in ("source_version", "candidate_version"):
            validation = validate_context_snapshot(snapshots[key])
            if validation.get("status") != "valid":
                report["status"] = "blocked"
                report["blocking_codes"].append(key.upper() + "_CONTEXT_INVALID")
        if args.expected_source_fingerprint and args.expected_source_fingerprint != source.get("fingerprint"):
            report["status"] = "blocked"
            report["blocking_codes"].append("SOURCE_FINGERPRINT_CHANGED")
        report["blocking_codes"] = sorted(set(report["blocking_codes"]))
        print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False, default=str))
        return 0 if report["status"] == "parity_match" else 1
    except Exception as exc:
        # DB errors may contain network addresses, credentials or SQL details.
        print("PARITY_ERROR_TYPE:", type(exc).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
