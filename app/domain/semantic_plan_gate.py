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
                # The resolver and the Graph use two equivalent evidence
                # shapes. Accept direct signals and matched nested term
                # signals, but never infer an alias from free text.
                signals: list[Any] = []
                direct = concept.get("semantic_signals")
                if isinstance(direct, list):
                    signals.extend(direct)
                terms = concept.get("terms")
                if isinstance(terms, list):
                    for matched_term in terms:
                        if not isinstance(matched_term, Mapping) or (
                            matched_term.get("matched") is not True
                        ):
                            continue
                        details = matched_term.get("match_details")
                        if not isinstance(details, Mapping):
                            continue
                        nested = details.get("semantic_signal")
                        if isinstance(nested, Mapping):
                            signals.append(nested)
                if not signals:
                    return [role]
                for signal in signals:
                    if not isinstance(signal, Mapping) or (
                        signal.get("concept_name") != concept_name
                    ):
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
            # A generic filter is not proof of temporal grounding.
            # Require the cited period alias to survive through a date
            # column explicitly authorized by this tenant's table catalog.
            if not aliases.issubset(
                _authorized_temporal_aliases(context, projection)
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


def _authorized_temporal_aliases(
    context: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> set[str]:
    """Ground period aliases in unambiguous, tenant-authorized date bindings.

    A physical table must be listed under an explicitly allowed schema.
    Duplicate or contradictory catalog entries and filter references never
    become temporal evidence for an optional semantic interpretation.
    """
    catalog = context.get("table_catalog")
    schemas = context.get("allowed_schemas")
    if (
        not isinstance(catalog, list)
        or not isinstance(schemas, list)
        or not schemas
        or any(not isinstance(item, str) or not item.strip() for item in schemas)
    ):
        return set()
    approved = {schema.strip().casefold() for schema in schemas}
    dates: dict[str, set[str]] = {}
    seen_tables: set[str] = set()
    duplicate_tables: set[str] = set()
    for table in catalog:
        if not isinstance(table, Mapping):
            continue
        schema, local = table.get("schema_name"), table.get("table_name")
        if (
            not isinstance(schema, str) or not schema.strip()
            or not isinstance(local, str) or not local.strip()
            or schema.strip().casefold() not in approved
        ):
            continue
        name = f"{schema.strip()}.{local.strip()}".casefold()
        declared = table.get("qualified_name")
        if declared is not None and (
            not isinstance(declared, str)
            or declared.strip().casefold() != name
        ):
            # A contradictory shortcut must not override physical identity.
            continue
        if name in seen_tables:
            duplicate_tables.add(name)
        seen_tables.add(name)
        candidates = table.get("date_columns")
        columns = table.get("columns")
        if not isinstance(candidates, list) or not isinstance(columns, list):
            continue
        available = {
            col["name"].strip().casefold()
            for col in columns
            if isinstance(col, Mapping) and isinstance(col.get("name"), str)
            and col["name"].strip()
        }
        allowed = {
            col.strip().casefold()
            for col in candidates
            if isinstance(col, str) and col.strip()
            and col.strip().casefold() in available
        }
        if allowed:
            dates[name] = allowed
    for name in duplicate_tables:
        dates.pop(name, None)

    def date_target_valid(table: Any, column: Any) -> bool:
        return (
            isinstance(table, str) and isinstance(column, str)
            and column.strip().casefold()
            in dates.get(table.strip().casefold(), set())
        )

    grounded: set[str] = set()
    series = projection.get("temporal_series")
    if isinstance(series, Mapping) and date_target_valid(
        series.get("date_table"), series.get("date_column")
    ):
        terms = series.get("period_reference_terms")
        if isinstance(terms, list):
            grounded.update(
                normalize_search_text(term)
                for term in terms
                if isinstance(term, str) and term.strip()
            )

    filters = projection.get("planned_filters")
    bindings = projection.get("resolved_filter_bindings")
    if not isinstance(filters, list) or not isinstance(bindings, list):
        return grounded

    # A reference is trusted only when all occurrences resolve to the same
    # authorized physical date column. Mixing an allowed and forbidden
    # target under one ref is ambiguity, not a permitted alternative.
    ref_targets: dict[str, tuple[str, str]] = {}
    invalid_refs: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, Mapping):
            continue
        raw_ref = binding.get("binding_ref")
        if not isinstance(raw_ref, str) or not raw_ref.strip():
            continue
        ref = raw_ref.strip().casefold()
        table, column = binding.get("target_table"), binding.get("target_column")
        if not date_target_valid(table, column):
            invalid_refs.add(ref)
            continue
        target = (table.strip().casefold(), column.strip().casefold())
        if ref in ref_targets and ref_targets[ref] != target:
            invalid_refs.add(ref)
        else:
            ref_targets[ref] = target

    for planned in filters:
        if not isinstance(planned, Mapping):
            continue
        ref = planned.get("binding_ref")
        alias = planned.get("matched_user_term")
        if (
            isinstance(ref, str) and ref.strip().casefold() in ref_targets
            and ref.strip().casefold() not in invalid_refs
            and isinstance(alias, str) and alias.strip()
        ):
            grounded.add(normalize_search_text(alias))
    return grounded
