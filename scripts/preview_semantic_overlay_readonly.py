from __future__ import annotations

"""Build a versioned semantic overlay exclusively in memory.

Business vocabulary is supplied by a reviewed policy; no question examples,
SQL generation, provider, runtime activation or database mutation occurs here.
"""

import argparse
import json
import os
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.adapters.postgres.context_repository import PostgresContextRepository
from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.context_validator import validate_context_snapshot
from app.domain.search_text import normalize_search_text
from scripts.audit_semantic_candidate_parity_readonly import parse_parity_policy
from scripts.evaluate_memory_candidate_generalization_readonly import evaluate_suite
from scripts.preflight_semantic_candidate_readonly import evaluate_candidate_readiness
from scripts.preview_semantic_candidate_readonly import (
    _SOURCE_KEYS,
    synthesize_candidate_snapshot,
)


def _required_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("non-empty text required in semantic overlay")
    return value.strip()


def _selector(value: Any, keys: set[str]) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError("semantic selector has invalid shape")
    return {name: _required_text(value[name]) for name in sorted(keys)}


def parse_overlay_policy(value: Any) -> dict[str, Any]:
    """Allow only reviewed semantic operations; fail closed on unexpected fields."""
    if not isinstance(value, Mapping) or set(value) != {
        "source_version", "candidate_version", "changes",
    }:
        raise ValueError("invalid semantic overlay policy")
    source = _required_text(value["source_version"])
    candidate = _required_text(value["candidate_version"])
    if source.casefold() == candidate.casefold():
        raise ValueError("source and candidate must be distinct")
    raw_changes = value["changes"]
    if not isinstance(raw_changes, list) or not 1 <= len(raw_changes) <= 64:
        raise ValueError("semantic overlay needs 1-64 changes")
    changes = []
    concept_keys = {"intent_name", "rule_name", "concept_name"}
    alias_keys = {"entity_type", "user_term", "canonical_value"}
    for raw in raw_changes:
        if not isinstance(raw, Mapping):
            raise ValueError("invalid semantic change")
        operation = raw.get("operation")
        if operation == "extend_concept_terms":
            if set(raw) != {"operation", "selector", "terms"}:
                raise ValueError("invalid term extension")
            selector = _selector(raw["selector"], concept_keys)
            terms = raw["terms"]
            if not isinstance(terms, list) or not 1 <= len(terms) <= 64:
                raise ValueError("invalid term extension list")
            cleaned = [_required_text(term) for term in terms]
            if len({term.casefold() for term in cleaned}) != len(cleaned):
                raise ValueError("duplicate configured terms")
            changes.append({
                "operation": operation, "selector": selector, "terms": cleaned,
            })
        elif operation == "mirror_concept_terms":
            if set(raw) != {"operation", "source", "target"}:
                raise ValueError("invalid semantic mirror")
            changes.append({
                "operation": operation,
                "source": _selector(raw["source"], concept_keys),
                "target": _selector(raw["target"], concept_keys),
            })
        elif operation == "clone_entity_alias":
            if set(raw) != {"operation", "source", "new_user_term"}:
                raise ValueError("invalid alias extension")
            changes.append({
                "operation": operation,
                "source": _selector(raw["source"], alias_keys),
                "new_user_term": _required_text(raw["new_user_term"]),
            })
        else:
            raise ValueError("unsupported semantic overlay operation")
    return {
        "source_version": source,
        "candidate_version": candidate,
        "changes": changes,
    }


def _one_concept(
    entities: list[dict[str, Any]], selector: Mapping[str, str],
) -> dict[str, Any]:
    candidates = []
    for entity in entities:
        if (
            entity.get("entity_type") != "intent_definition"
            or entity.get("canonical_value") != selector["intent_name"]
        ):
            continue
        business = entity.get("business_rule")
        catalog = business.get("intent_catalog") if isinstance(business, Mapping) else None
        rules = catalog.get("rules") if isinstance(catalog, Mapping) else None
        if not isinstance(rules, list):
            continue
        for rule in rules:
            if not isinstance(rule, Mapping) or rule.get("rule_name") != selector["rule_name"]:
                continue
            concepts = rule.get("concepts")
            if not isinstance(concepts, list):
                continue
            candidates.extend(
                concept for concept in concepts
                if isinstance(concept, dict)
                and concept.get("concept_name") == selector["concept_name"]
            )
    if len(candidates) != 1:
        raise ValueError("semantic concept selector must match exactly once")
    return candidates[0]


def _one_entity(
    entities: list[dict[str, Any]], selector: Mapping[str, str],
) -> dict[str, Any]:
    matched = [
        entry for entry in entities
        if all(entry.get(key) == value for key, value in selector.items())
    ]
    if len(matched) != 1:
        raise ValueError("alias prototype must match exactly once")
    return matched[0]


def apply_semantic_overlay(
    source: Mapping[str, Any], overlay: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply an explicit reviewed delta; preserve source and all non-entity collections."""
    policy = parse_overlay_policy(overlay)
    if source.get("version") != policy["source_version"]:
        raise ValueError("semantic overlay source version mismatch")
    if not isinstance(source.get("fingerprint"), str) or len(source["fingerprint"]) != 64:
        raise ValueError("semantic source fingerprint missing")
    raw: dict[str, Any] = {
        "semantic_agent_version": policy["candidate_version"],
        "semantic_context_source": source.get("source"),
    }
    for normalized_key, raw_key in _SOURCE_KEYS.items():
        records = source.get(normalized_key)
        if not isinstance(records, list) or any(
            not isinstance(item, Mapping) for item in records
        ):
            raise ValueError("invalid semantic source collection")
        raw[raw_key] = deepcopy(records)

    entities = raw["entidades"]
    for change in policy["changes"]:
        operation = change["operation"]
        if operation == "extend_concept_terms":
            concept = _one_concept(entities, change["selector"])
            existing = concept.get("terms")
            if not isinstance(existing, list) or not all(
                isinstance(x, str) for x in existing
            ):
                raise ValueError("invalid existing concept terms")
            mode = concept.get("match_mode")
            normalize = (lambda x: x.casefold()) if mode == "regex" else normalize_search_text
            known = {normalize(x) for x in existing}
            additions = [term for term in change["terms"] if normalize(term) not in known]
            if not additions:
                raise ValueError("semantic term extension has no effective change")
            concept["terms"] = [*existing, *additions]
        elif operation == "mirror_concept_terms":
            source_concept = _one_concept(entities, change["source"])
            target_concept = _one_concept(entities, change["target"])
            if source_concept is target_concept:
                raise ValueError("cannot mirror concept into itself")
            if source_concept.get("match_mode") != target_concept.get("match_mode"):
                raise ValueError("semantic mirror match modes differ")
            if not isinstance(source_concept.get("terms"), list):
                raise ValueError("source terms unavailable")
            if source_concept["terms"] == target_concept.get("terms"):
                raise ValueError("semantic mirror has no effective change")
            target_concept["terms"] = deepcopy(source_concept["terms"])
        else:
            original = _one_entity(entities, change["source"])
            label = change["new_user_term"]
            if any(
                entry.get("entity_type") == original.get("entity_type")
                and str(entry.get("user_term", "")).casefold() == label.casefold()
                for entry in entities
            ):
                raise ValueError("new semantic alias already exists")
            new_entity = deepcopy(original)
            new_entity["user_term"] = label
            entities.append(new_entity)

    candidate = normalize_context_snapshot(raw)
    if candidate["fingerprint"] == source["fingerprint"]:
        raise ValueError("semantic candidate is identical to source")
    for key in ("rules", "dre_mappings", "query_patterns", "table_catalog"):
        if source[key] != candidate[key]:
            raise ValueError("overlay unexpectedly changed protected collection")
    if validate_context_snapshot(candidate)["status"] != "valid":
        raise ValueError("semantic overlay failed context validation")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-policy", required=True)
    parser.add_argument("--overlay", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--expected-source-fingerprint", required=True)
    args = parser.parse_args()

    if os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") != "false":
        print("ABORTED: real SQL execution must remain disabled.")
        return 3
    try:
        base_policy = parse_parity_policy(
            json.loads(Path(args.base_policy).read_text(encoding="utf-8"))
        )
        overlay_policy = parse_overlay_policy(
            json.loads(Path(args.overlay).read_text(encoding="utf-8"))
        )
        if base_policy["candidate_version"] != overlay_policy["source_version"]:
            raise ValueError("virtual version chain mismatch")
        repo = PostgresContextRepository(
            dsn=os.environ["CONTEXT_POSTGRES_DSN"],
            semantic_agent_version=base_policy["source_version"],
            context_schema=os.environ.get("POSTGRES_CONTEXT_SCHEMA", "semantic_context"),
        )
        source = repo.load_active_context(user_profile="runtime_validation")
        if source.get("fingerprint") != args.expected_source_fingerprint:
            print("ABORTED: source fingerprint does not match expected value.")
            return 4
        base = synthesize_candidate_snapshot(source, base_policy)
        candidate = apply_semantic_overlay(base, overlay_policy)
        readiness = evaluate_candidate_readiness(candidate)
        if readiness["status"] != "checks_passed":
            print(json.dumps({
                "status": "blocked_by_metadata",
                "blocking_codes": sorted({
                    item["code"] for item in readiness["blocking_issues"]
                }),
                "real_sql_execution": False,
                "activation_authorized": False,
            }, sort_keys=True))
            return 1
        suite = json.loads(Path(args.cases).read_text(encoding="utf-8"))
        evaluated = evaluate_suite(candidate, suite)
        print(json.dumps({
            "status": evaluated["status"],
            "source_version": source["version"],
            "base_version": base["version"],
            "candidate_version": candidate["version"],
            "source_fingerprint": source["fingerprint"],
            "base_fingerprint": base["fingerprint"],
            "candidate_fingerprint": candidate["fingerprint"],
            "configured_change_count": len(overlay_policy["changes"]),
            "evaluation": evaluated,
            "read_only": True,
            "persisted_candidate": False,
            "real_sql_execution": False,
            "llm_calls": 0,
            "benchmark_access": False,
            "activation_authorized": False,
        }, ensure_ascii=False, sort_keys=True))
        return 0 if evaluated["status"] == "evaluation_passed" else 1
    except Exception as exc:
        # Never print database or business payloads on unexpected failures.
        print("SEMANTIC_OVERLAY_ERROR_TYPE:", type(exc).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
