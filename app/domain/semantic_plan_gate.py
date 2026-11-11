"""Fail-closed handoff from optional LLM interpretation to physical planning.

The interpreter only identifies tenant-authored catalog aliases. This gate
verifies that every structural role it identified actually survived the
deterministic planner as an authorized physical projection. It never maps
unknown accounting meanings, synthesizes metrics, or generates SQL.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.domain.search_text import normalize_search_text
from app.domain.semantic_concept_roles import role_concepts

_ROLE_PLAN_COLLECTIONS = {
    "metric": "planned_metrics",
    "operation": "analytical_operations",
    "grouping": "detected_dimensions",
}


def missing_semantic_plan_bindings(
    *,
    context: Mapping[str, Any],
    interpretation: Mapping[str, Any] | None,
    query_plan: Mapping[str, Any],
) -> list[str]:
    """Return structural role names only; never expose user data or aliases."""
    if not isinstance(interpretation, Mapping) or (
        interpretation.get("reason") != "semantic_interpretation_selected"
    ):
        return []
    projection = query_plan.get("planning_context")
    if not isinstance(projection, Mapping):
        return ["missing_planning_projection"]
    resolution = context.get("intent_resolution")
    if not isinstance(resolution, Mapping):
        return ["missing_role_catalog"]

    roles = {
        role: role_concepts(resolution, role)
        for role in (*_ROLE_PLAN_COLLECTIONS, "period")
    }
    candidate = interpretation.get("best_candidate")
    if not isinstance(candidate, Mapping) or candidate.get("intent_name") != (
        interpretation.get("intent")
    ):
        return ["intent_evidence_missing"]
    matches = candidate.get("matches")
    if not isinstance(matches, list):
        return ["intent_evidence_missing"]

    expected: dict[str, set[str]] = {}
    for match in matches:
        if not isinstance(match, Mapping):
            return ["intent_evidence_invalid"]
        details = match.get("match_details")
        concepts = details.get("concepts") if isinstance(details, Mapping) else None
        if not isinstance(concepts, list):
            return ["intent_evidence_invalid"]
        for concept in concepts:
            if not isinstance(concept, Mapping) or concept.get("satisfied") is not True:
                continue
            concept_name = concept.get("concept_name")
            if not isinstance(concept_name, str):
                continue
            assigned_roles = [
                role for role, names in roles.items()
                if concept_name.casefold() in names
            ]
            for role in assigned_roles:
                signals = concept.get("semantic_signals")
                if not isinstance(signals, list) or not signals:
                    return [role]
                for signal in signals:
                    if not isinstance(signal, Mapping):
                        return [role]
                    term = signal.get("normalized_term")
                    if not isinstance(term, str) or not term.strip():
                        return [role]
                    expected.setdefault(role, set()).add(normalize_search_text(term))
    if not expected:
        # An interpretation cannot claim success while providing no role
        # that the tenant's planner can interpret.
        return ["no_plannable_role"]

    missing: list[str] = []
    for role, aliases in expected.items():
        if role == "period":
            # Temporal semantics must be bound by an explicit projector.
            # No invented date or implicit default is allowed here.
            series = projection.get("temporal_series")
            filters = projection.get("planned_filters")
            if not isinstance(series, Mapping) and not (
                isinstance(filters, list) and filters
            ):
                missing.append(role)
            continue
        items = projection.get(_ROLE_PLAN_COLLECTIONS[role])
        if not isinstance(items, list):
            missing.append(role)
            continue
        actual = {
            normalize_search_text(item["matched_user_term"])
            for item in items
            if isinstance(item, Mapping)
            and isinstance(item.get("matched_user_term"), str)
            and item["matched_user_term"].strip()
        }
        if not aliases.issubset(actual):
            missing.append(role)
    return sorted(missing)
