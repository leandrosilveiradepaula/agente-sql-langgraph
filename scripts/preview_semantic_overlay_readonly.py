from __future__ import annotations

"""Build a versioned semantic overlay exclusively in memory.

Business vocabulary is supplied by a reviewed policy; no question examples,
SQL generation, provider, runtime activation or database mutation occurs here.
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
        elif operation == "extend_temporal_granularity_terms":
            if set(raw) != {"operation", "selector", "terms"}:
                raise ValueError("invalid temporal term extension")
            selector = _selector(raw["selector"], {"rule_name", "grain"})
            terms = raw["terms"]
            if not isinstance(terms, list) or not 1 <= len(terms) <= 64:
                raise ValueError("invalid temporal term extension list")
            cleaned = [_required_text(term) for term in terms]
            if len({normalize_search_text(term) for term in cleaned}) != len(cleaned):
                raise ValueError("duplicate temporal term extension")
            changes.append({
                "operation": operation, "selector": selector, "terms": cleaned,
            })
        elif operation == "configure_concept_negation":
            if set(raw) != {"operation", "policy"}:
                raise ValueError("invalid negation policy extension")
            policy = raw["policy"]
            if not isinstance(policy, Mapping) or set(policy) != {
                "cue_phrases", "concept_names", "max_gap_tokens",
            }:
                raise ValueError("invalid negation policy shape")
            for field, limit in (("cue_phrases", 64), ("concept_names", 32)):
                terms = policy[field]
                if (
                    not isinstance(terms, list)
                    or not 1 <= len(terms) <= limit
                    or any(not isinstance(term, str) or not term.strip()
                           for term in terms)
                ):
                    raise ValueError("invalid negation policy terms")
                cleaned = [
                    normalize_search_text(term) if field == "cue_phrases"
                    else term.strip().casefold() for term in terms
                ]
                if any(not term for term in cleaned) or len(cleaned) != len(set(cleaned)):
                    raise ValueError("duplicate negation policy terms")
            gap = policy["max_gap_tokens"]
            if type(gap) is not int or not 0 <= gap <= 3:
                raise ValueError("invalid negation scope distance")
            changes.append({"operation": operation, "policy": {
                "cue_phrases": list(policy["cue_phrases"]),
                "concept_names": list(policy["concept_names"]),
                "max_gap_tokens": gap,
            }})
        elif operation == "extend_negation_scope_concepts":
            if set(raw) != {"operation", "concept_names"}:
                raise ValueError("invalid negation scope extension")
            names = raw["concept_names"]
            if (
                not isinstance(names, list)
                or not 1 <= len(names) <= 32
                or any(not isinstance(name, str) or not name.strip() for name in names)
            ):
                raise ValueError("invalid negation extension concepts")
            normalized = [name.strip().casefold() for name in names]
            if len(set(normalized)) != len(normalized):
                raise ValueError("duplicate negation extension concepts")
            changes.append({
                "operation": operation,
                "concept_names": [name.strip() for name in names],
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
        elif operation == "add_catalog_exclusion":
            if set(raw) != {
                "operation", "source", "target_intent", "rule_name", "priority",
            }:
                raise ValueError("invalid catalog exclusion")
            priority = raw["priority"]
            if type(priority) is not int or not 1 <= priority <= 10000:
                raise ValueError("invalid exclusion priority")
            changes.append({
                "operation": operation,
                "source": _selector(raw["source"], concept_keys),
                "target_intent": _required_text(raw["target_intent"]),
                "rule_name": _required_text(raw["rule_name"]),
                "priority": priority,
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


def _one_intent_rules(
    entities: list[dict[str, Any]], intent_name: str,
) -> list[dict[str, Any]]:
    matching = []
    for entity in entities:
        if (
            entity.get("entity_type") != "intent_definition"
            or entity.get("canonical_value") != intent_name
        ):
            continue
        business = entity.get("business_rule")
        catalog = business.get("intent_catalog") if isinstance(business, Mapping) else None
        rules = catalog.get("rules") if isinstance(catalog, Mapping) else None
        if not isinstance(rules, list) or not all(isinstance(rule, dict) for rule in rules):
            raise ValueError("invalid target intent catalog")
        matching.append(rules)
    if len(matching) != 1:
        raise ValueError("exclusion target intent must match exactly once")
    return matching[0]


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


def _one_temporal_granularity(
    rules: list[dict[str, Any]], selector: Mapping[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Select one named, versioned temporal component and one grain."""
    matches = [
        rule for rule in rules
        if rule.get("rule_group") == "component_config"
        and rule.get("rule_name") == selector["rule_name"]
        and isinstance(rule.get("rule_content"), Mapping)
        and rule["rule_content"].get("component") == "temporal_planning"
    ]
    if len(matches) != 1:
        raise ValueError("temporal configuration selector must match once")
    grains = matches[0]["rule_content"].get("granularities")
    if not isinstance(grains, list) or any(
        not isinstance(grain, dict) for grain in grains
    ):
        raise ValueError("temporal granularities must be a list of objects")
    selected = [
        grain for grain in grains
        if grain.get("grain") == selector["grain"]
    ]
    if len(selected) != 1:
        raise ValueError("temporal grain selector must match exactly once")
    return selected[0], grains


def _extend_temporal_granularity(
    rules: list[dict[str, Any]], selector: Mapping[str, str],
    terms: list[str],
) -> None:
    grain, grains = _one_temporal_granularity(rules, selector)
    existing = grain.get("terms")
    if not isinstance(existing, list) or not all(
        isinstance(term, str) and term.strip() for term in existing
    ):
        raise ValueError("invalid temporal grain terms")
    # A term may not belong to two distinct granularities: that could make
    # an otherwise unambiguous time request reject due to conflicting grains.
    occupied: set[str] = set()
    for item in grains:
        values = item.get("terms")
        if not isinstance(values, list) or not all(
            isinstance(term, str) and term.strip() for term in values
        ):
            raise ValueError("invalid configured temporal vocabulary")
        occupied.update(normalize_search_text(term) for term in values)
    if any(normalize_search_text(term) in occupied for term in terms):
        raise ValueError("temporal extension collides with configured vocabulary")
    grain["terms"] = [*existing, *terms]


def _assert_overlay_rule_scope(
    before: list[dict[str, Any]], after: list[dict[str, Any]],
    allowed_grains: Mapping[tuple[str, str], set[str]],
    permitted_negation_rules: set[tuple[str, str]],
) -> None:
    """Ensure no component metadata changes except appended grain terms."""
    if len(before) != len(after):
        raise ValueError("temporal overlay changed rule count")
    for previous, current in zip(before, after, strict=True):
        identity = (
            previous.get("rule_group"), previous.get("rule_name"),
        )
        if identity != (
            current.get("rule_group"), current.get("rule_name"),
        ):
            raise ValueError("temporal overlay changed rule identity")
        if identity in permitted_negation_rules:
            reviewed = deepcopy(current)
            new_content = reviewed.get("rule_content")
            previous_content = previous.get("rule_content")
            if (
                not isinstance(new_content, dict)
                or not isinstance(previous_content, Mapping)
                or "negation_scope" in previous_content
                or "negation_scope" not in new_content
            ):
                raise ValueError("invalid versioned negation configuration")
            new_content.pop("negation_scope")
            if reviewed != previous:
                raise ValueError("negation overlay changed protected resolver metadata")
            continue
        permitted = allowed_grains.get(identity)
        if not permitted:
            if previous != current:
                raise ValueError("overlay changed protected rule")
            continue
        reviewed = deepcopy(current)
        old = previous.get("rule_content")
        new = reviewed.get("rule_content")
        if not isinstance(old, Mapping) or not isinstance(new, dict):
            raise ValueError("invalid temporal component content")
        old_grains = old.get("granularities")
        new_grains = new.get("granularities")
        if not isinstance(old_grains, list) or not isinstance(new_grains, list):
            raise ValueError("temporal config lost granularities")
        if len(old_grains) != len(new_grains):
            raise ValueError("temporal overlay changed grain count")
        seen: set[str] = set()
        for prior, altered in zip(old_grains, new_grains, strict=True):
            if not isinstance(prior, Mapping) or not isinstance(altered, dict):
                raise ValueError("invalid temporal grain metadata")
            grain = prior.get("grain")
            if grain != altered.get("grain"):
                raise ValueError("temporal overlay changed grain identity")
            if grain not in permitted:
                continue
            existing = prior.get("terms")
            extended = altered.get("terms")
            if (
                not isinstance(existing, list)
                or not isinstance(extended, list)
                or len(extended) <= len(existing)
                or extended[:len(existing)] != existing
            ):
                raise ValueError("temporal extension must append new terms")
            altered["terms"] = deepcopy(existing)
            seen.add(str(grain))
        if seen != permitted or reviewed != previous:
            raise ValueError("overlay changed protected temporal metadata")


def apply_semantic_overlay(
    source: Mapping[str, Any], overlay: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply an explicit reviewed delta; preserve source and all non-entity collections."""
    policy = parse_overlay_policy(overlay)
    if source.get("version") != policy["source_version"]:
        raise ValueError("semantic overlay source version mismatch")
    fingerprint = source.get("fingerprint")
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise ValueError("semantic source fingerprint missing or malformed")
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
    allowed_temporal_rule_grains: dict[tuple[str, str], set[str]] = {}
    allowed_negation_rules: set[tuple[str, str]] = set()
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
        elif operation == "extend_temporal_granularity_terms":
            selector = change["selector"]
            _extend_temporal_granularity(raw["regras"], selector, change["terms"])
            identity = ("component_config", selector["rule_name"])
            allowed_temporal_rule_grains.setdefault(identity, set()).add(
                selector["grain"]
            )
        elif operation == "configure_concept_negation":
            matches = [
                rule for rule in raw["regras"]
                if isinstance(rule.get("rule_content"), Mapping)
                and rule["rule_content"].get("component") == "intent_resolver"
            ]
            if len(matches) != 1:
                raise ValueError("resolver negation component must match once")
            target = matches[0]
            content = target["rule_content"]
            if "negation_scope" in content:
                raise ValueError("resolver negation policy already configured")
            content["negation_scope"] = deepcopy(change["policy"])
            identity = (target["rule_group"], target["rule_name"])
            allowed_negation_rules.add(identity)
        elif operation == "extend_negation_scope_concepts":
            matches = [
                rule for rule in raw["regras"]
                if isinstance(rule.get("rule_content"), Mapping)
                and rule["rule_content"].get("component") == "intent_resolver"
            ]
            if len(matches) != 1:
                raise ValueError("resolver negation extension selector ambiguous")
            target = matches[0]
            policy_config = target["rule_content"].get("negation_scope")
            if not isinstance(policy_config, dict):
                raise ValueError("negation scope must be configured first")
            existing = policy_config.get("concept_names")
            if not isinstance(existing, list) or not all(
                isinstance(name, str) and name.strip() for name in existing
            ):
                raise ValueError("invalid negation scope concepts")
            known = {name.strip().casefold() for name in existing}
            added = [name.strip() for name in change["concept_names"]]
            if (
                len(existing) + len(added) > 32
                or any(name.casefold() in known for name in added)
            ):
                raise ValueError("negation extension conflicts with existing policy")
            policy_config["concept_names"] = [*existing, *added]
            identity = (target["rule_group"], target["rule_name"])
            if identity not in allowed_negation_rules:
                raise ValueError("negation extension has no authorized base policy")
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
        elif operation == "add_catalog_exclusion":
            concept = deepcopy(_one_concept(entities, change["source"]))
            concept.pop("normalized_terms", None)
            if not isinstance(concept.get("terms"), list) or not concept["terms"]:
                raise ValueError("exclusion source concept lacks vocabulary")
            rules = _one_intent_rules(entities, change["target_intent"])
            if any(
                str(rule.get("rule_name", "")).casefold()
                == change["rule_name"].casefold()
                for rule in rules
            ):
                raise ValueError("catalog exclusion already exists")
            rules.append({
                "rule_name": change["rule_name"],
                "effect": "exclude",
                "concepts": [concept],
                "minimum_concept_matches": 1,
                "score": None,
                "priority": change["priority"],
            })
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
    for key in ("dre_mappings", "query_patterns", "table_catalog"):
        if source[key] != candidate[key]:
            raise ValueError("overlay unexpectedly changed protected collection")
    _assert_overlay_rule_scope(
        source["rules"], candidate["rules"], allowed_temporal_rule_grains,
        allowed_negation_rules,
    )
    if validate_context_snapshot(candidate)["status"] != "valid":
        raise ValueError("semantic overlay failed context validation")
    return candidate


def main() -> int:
    # Fail before CLI parsing or any file/repository operation.
    # A disabled real-execution gate is mandatory even for malformed requests.
    if os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") != "false":
        print("ABORTED: real SQL execution must remain disabled.")
        return 3

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-policy", required=True)
    parser.add_argument("--overlay", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--expected-source-fingerprint", required=True)
    args = parser.parse_args()

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
        baseline = evaluate_suite(base, suite)
        evaluated = evaluate_suite(candidate, suite)
        baseline_passed = {
            item["case_index"] for item in baseline["observations"]
            if item["passed"]
        }
        candidate_passed = {
            item["case_index"] for item in evaluated["observations"]
            if item["passed"]
        }
        print(json.dumps({
            "baseline_summary": {
                "passed": baseline["passed"],
                "failed": baseline["failed"],
                "case_count": baseline["case_count"],
                "regressed_case_indexes": sorted(baseline_passed - candidate_passed),
                "improved_case_indexes": sorted(candidate_passed - baseline_passed),
            },
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
