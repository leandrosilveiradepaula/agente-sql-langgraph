"""Read-only completeness audit of a versioned tenant semantic catalog.

Structural checks only: no question, benchmark, SQL, client-specific concepts,
financial thresholds, or inferred metric/operator mappings are used.
This audit is an inventory and does NOT authorize semantic activation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any

from app.domain.planner import (
    _metric_binding_metadata,
    _metric_metadata,
    _operation_metadata,
    _metric_column_allowed,
)
from app.domain.search_text import normalize_search_text
from app.domain.semantic_concept_roles import (
    ConceptRoleConfigurationError,
    parse_concept_roles,
    unknown_role_concepts,
)


def audit_semantic_catalog(context: Mapping[str, Any]) -> dict[str, Any]:
    """Return aggregate diagnostics; never expose tenant aliases or schema."""
    if not isinstance(context, Mapping):
        return _refused("context_invalid")
    # A valid physical catalog without version provenance must not be
    # described as inventory-complete or eligible for migration review.
    version = context.get("version")
    fingerprint = context.get("fingerprint")
    if not isinstance(version, str) or not version.strip():
        return _refused("context_version_missing")
    if (
        not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or any(c not in "0123456789abcdefABCDEF" for c in fingerprint)
    ):
        return _refused("context_fingerprint_invalid")
    entities = context.get("entities")
    tables = context.get("table_catalog")
    intent = context.get("intent_resolution")
    if not isinstance(entities, list) or not isinstance(tables, list):
        return _refused("catalog_missing")
    if not isinstance(intent, Mapping):
        return _refused("intent_catalog_missing")
    try:
        roles = parse_concept_roles(intent)
        missing = unknown_role_concepts(intent)
    except ConceptRoleConfigurationError:
        return _refused("role_config_invalid")
    if missing:
        return _refused("role_concept_unresolved")

    counts: Counter[str] = Counter()
    issues: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    aliases: dict[tuple[str, str], set[tuple[str, ...]]] = defaultdict(set)
    alias_kinds: dict[str, set[str]] = defaultdict(set)
    canonical_metrics: set[str] = set()
    binding_metrics: set[str] = set()
    for entry in entities:
        if not isinstance(entry, Mapping):
            issues["entity_record_invalid"] += 1
            continue
        kind = entry.get("entity_type")
        if not isinstance(kind, str):
            issues["entity_type_invalid"] += 1
            continue
        # Aggregate only platform-defined types. Custom entity kinds are
        # tenant metadata, not public reporting labels.
        kinds[kind if kind in {
            "analytical_operation", "financial_metric", "metric_binding"
        } else "other"] += 1
        alias = entry.get("user_term")
        normalized_alias = normalize_search_text(alias) if isinstance(alias, str) else ""
        if kind not in {"analytical_operation", "financial_metric", "metric_binding"}:
            continue

        counts["tracked_entities"] += 1
        if not normalized_alias:
            issues["alias_missing"] += 1
            continue
        if kind == "analytical_operation":
            operation = _operation_metadata(entry.get("business_rule"))
            if operation is None or entry.get("canonical_value") != operation["operation_type"]:
                issues["operation_metadata_invalid"] += 1
                continue
            counts["valid_operations"] += 1
            identity = (operation["operation_type"], str(operation.get("direction", "")))
            aliases[(kind, normalized_alias)].add(identity)
            alias_kinds[normalized_alias].add(kind)
        elif kind == "financial_metric":
            metric = _metric_metadata(entry.get("business_rule"))
            canonical = entry.get("canonical_value")
            if not isinstance(canonical, str) or not canonical.strip():
                issues["metric_identity_invalid"] += 1
                continue
            if (
                metric is None
                or metric["metric_concept"] != canonical
                or metric["target_table"] != entry.get("target_table")
                or metric["target_column"] != entry.get("target_column")
                or not _metric_column_allowed(
                    tables,
                    target_table=metric["target_table"],
                    target_column=metric["target_column"],
                )
            ):
                issues["metric_physical_binding_invalid"] += 1
                continue
            counts["valid_metric_aliases"] += 1
            canonical_metrics.add(canonical.casefold())
            aliases[(kind, normalized_alias)].add((
                canonical.casefold(), metric["target_table"].casefold(),
                metric["target_column"].casefold(),
            ))
            alias_kinds[normalized_alias].add(kind)
        else:
            binding, _reason = _metric_binding_metadata(
                entry, table_catalog=tables,
            )
            if binding is None:
                issues["metric_binding_invalid"] += 1
                continue
            counts["valid_metric_bindings"] += 1
            binding_metrics.add(binding["metric_concept"].casefold())
            # Multiple condition-scoped bindings for the same alias are
            # legitimate and deliberately not treated as a simple collision.

    for (kind, _alias), identities in aliases.items():
        if len(identities) > 1:
            issues["operation_alias_ambiguous" if kind == "analytical_operation"
                   else "metric_alias_ambiguous"] += 1
    # Identical aliases attached to both an operation and a metric are
    # ambiguous at the lexical layer. Flag for semantic review; never
    # choose a winner by priority or invent a business-specific override.
    issues["cross_role_alias_ambiguous"] = sum(
        len(kinds) > 1 for kinds in alias_kinds.values()
    )
    if not issues["cross_role_alias_ambiguous"]:
        del issues["cross_role_alias_ambiguous"]
    counts["distinct_metric_concepts"] = len(canonical_metrics)
    counts["distinct_bound_metric_concepts"] = len(binding_metrics)
    counts["metric_concepts_without_explicit_bindings"] = len(
        canonical_metrics - binding_metrics
    )
    counts["bindings_without_named_metric_alias"] = len(
        binding_metrics - canonical_metrics
    )
    counts["configured_structural_roles"] = len(roles)

    # Lack of optional binding aliases is advisory, not an invented financial
    # requirement: legacy metric aliases and standalone aggregations exist.
    critical = sum(issues.values())
    return {
        "status": "REVIEW_REQUIRED" if critical else "INVENTORY_COMPLETE",
        "context_version_present": True,
        "fingerprint_present": True,
        "counts": dict(sorted(counts.items())),
        "entity_types": dict(sorted(kinds.items())),
        "issue_counts": dict(sorted(issues.items())),
        "business_binding_review_required": bool(
            counts["metric_concepts_without_explicit_bindings"]
            or counts["bindings_without_named_metric_alias"]
        ),
        "metric_binding_policy_inferred": False,
        "financial_parity_verified": False,
        "automated_activation_authorized": False,
        "sql_generated": False,
        "sql_executed": False,
        "provider_calls": 0,
    }


def _refused(code: str) -> dict[str, Any]:
    return {
        "status": "BLOCKED",
        "reason": code,
        "automated_activation_authorized": False,
        "sql_generated": False,
        "sql_executed": False,
        "provider_calls": 0,
    }
