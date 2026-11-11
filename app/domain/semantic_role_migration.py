"""Dry-run-only tenant semantic role migration, with independent evidence.

The source of truth is a versioned raw semantic snapshot, not a question, SQL,
benchmark, customer name, or a hardcoded role-to-concept map.

No database, network, SQL generator, or model dependencies are used.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from app.domain.semantic_catalog_audit import audit_semantic_catalog
from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.context_validator import validate_context_snapshot
from app.domain.intent_resolver import resolve_intent
from app.domain.planner import build_query_plan
from app.domain.search_text import normalize_search_text
from app.domain.semantic_concept_roles import (
    ConceptRoleConfigurationError,
    parse_concept_roles,
    unknown_role_concepts,
)

_MAX_QUESTIONS = 500
_MAX_QUESTION_LENGTH = 16000
_MAX_RULE_CONTENT_BYTES = 131072


class SemanticRoleMigrationRefused(ValueError):
    """A candidate cannot be staged safely using the supplied metadata."""


def _as_mapping(value: Any, *, code: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticRoleMigrationRefused(code)
    return deepcopy(dict(value))


def _canonical_without_role_differences(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    candidate = deepcopy(dict(snapshot))
    candidate.pop("version", None)
    candidate.pop("fingerprint", None)
    for collection in (candidate.get("rules", []),):
        for rule in collection:
            if (isinstance(rule, dict)
                    and isinstance(rule.get("rule_content"), dict)
                    and rule["rule_content"].get("component") == "intent_resolver"):
                rule["rule_content"].pop("concept_roles", None)
    components = candidate.get("component_configs")
    if isinstance(components, dict):
        config = components.get("intent_resolver")
        if isinstance(config, dict):
            config.pop("concept_roles", None)
    resolution = candidate.get("intent_resolution")
    if isinstance(resolution, dict):
        config = resolution.get("config")
        if isinstance(config, dict):
            config.pop("concept_roles", None)
    return candidate


def prepare_role_migration(
    source_raw_snapshot: Mapping[str, Any],
    *,
    candidate_version: str,
    role_bindings: Mapping[str, list[str]],
    expected_source_fingerprint: str,
) -> dict[str, Any]:
    """Create an isolated draft; never write a context or authorize activation.

    Changes are restricted to the raw semantic version and one versioned
    intent_resolver rule's concept_roles. Both normalized snapshots are
    checked independently and all other canonical fields must match.
    """
    source_raw = _as_mapping(source_raw_snapshot, code="source_raw_invalid")
    if (not isinstance(candidate_version, str)
            or not candidate_version.strip()
            or len(candidate_version) > 256):
        raise SemanticRoleMigrationRefused("candidate_version_invalid")
    candidate_version = candidate_version.strip()
    if not isinstance(role_bindings, Mapping) or not role_bindings:
        raise SemanticRoleMigrationRefused("role_bindings_missing")
    try:
        parsed = parse_concept_roles({"config": {"concept_roles": role_bindings}})
    except ConceptRoleConfigurationError as exc:
        raise SemanticRoleMigrationRefused("role_bindings_invalid") from exc
    if not parsed:
        raise SemanticRoleMigrationRefused("role_bindings_missing")

    version_field = (
        "semantic_agent_version" if "semantic_agent_version" in source_raw
        else "version" if "version" in source_raw
        else None
    )
    if version_field is None:
        raise SemanticRoleMigrationRefused("source_version_missing")

    try:
        original = normalize_context_snapshot(source_raw)
    except Exception as exc:
        raise SemanticRoleMigrationRefused("source_normalization_failed") from exc
    if validate_context_snapshot(original)["status"] != "valid":
        raise SemanticRoleMigrationRefused("source_context_invalid")
    if (
        not isinstance(expected_source_fingerprint, str)
        or original["fingerprint"] != expected_source_fingerprint
    ):
        raise SemanticRoleMigrationRefused("source_fingerprint_mismatch")
    if original["version"] == candidate_version:
        raise SemanticRoleMigrationRefused("version_not_advanced")

    candidate_raw = deepcopy(source_raw)
    candidate_raw[version_field] = candidate_version
    raw_rules = candidate_raw.get(
        "regras" if "regras" in candidate_raw else "rules"
    )
    if not isinstance(raw_rules, list):
        raise SemanticRoleMigrationRefused("source_rules_missing")
    resolver_indexes: list[int] = []
    for i, record in enumerate(raw_rules):
        if not isinstance(record, Mapping):
            raise SemanticRoleMigrationRefused("source_rule_invalid")
        content = record.get("rule_content")
        if isinstance(content, str):
            if len(content.encode("utf-8")) > _MAX_RULE_CONTENT_BYTES:
                raise SemanticRoleMigrationRefused("source_rule_content_excessive")
            # Existing versioned catalogs may contain opaque non-JSON business
            # rules. These are not resolver configuration and must remain
            # byte-for-byte unchanged. Never skip a malformed config object.
            if not content.lstrip().startswith("{"):
                if record.get("rule_group") == "config":
                    raise SemanticRoleMigrationRefused("source_rule_json_invalid")
                continue
            try:
                content = json.loads(content)
            except (TypeError, ValueError) as exc:
                raise SemanticRoleMigrationRefused("source_rule_json_invalid") from exc
        if isinstance(content, Mapping) and content.get("component") == "intent_resolver":
            resolver_indexes.append(i)
    if len(resolver_indexes) != 1:
        raise SemanticRoleMigrationRefused("resolver_rule_not_unique")

    i = resolver_indexes[0]
    rule = deepcopy(dict(raw_rules[i]))
    content = rule["rule_content"]
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (TypeError, ValueError) as exc:
            raise SemanticRoleMigrationRefused("resolver_rule_json_invalid") from exc
    content = _as_mapping(content, code="resolver_rule_invalid")
    content["concept_roles"] = {
        key: sorted(values)
        for key, values in sorted(
            ((role, list(names)) for role, names in role_bindings.items()),
            key=lambda item: item[0],
        )
    }
    rule["rule_content"] = content
    raw_rules[i] = rule

    try:
        candidate = normalize_context_snapshot(candidate_raw)
    except Exception as exc:
        raise SemanticRoleMigrationRefused("candidate_normalization_failed") from exc
    if validate_context_snapshot(candidate)["status"] != "valid":
        raise SemanticRoleMigrationRefused("candidate_context_invalid")
    if unknown_role_concepts(candidate["intent_resolution"]):
        raise SemanticRoleMigrationRefused("candidate_role_reference_missing")
    if original["fingerprint"] == candidate["fingerprint"]:
        raise SemanticRoleMigrationRefused("fingerprint_not_advanced")
    if _canonical_without_role_differences(original) != (
        _canonical_without_role_differences(candidate)
    ):
        raise SemanticRoleMigrationRefused("unapproved_context_changes")

    return {
        "status": "PREPARED_NOT_ACTIVATED",
        "source": original,
        "candidate": candidate,
        "candidate_raw": candidate_raw,
        "role_count": len(parsed),
    }


def audit_role_migration_questions(
    prepared: Mapping[str, Any],
    questions: Sequence[str],
) -> dict[str, Any]:
    """Compare two versions blindly, without SQL, golden answers or LLM calls.

    Aggregated decision/plan changes require human review. No question text,
    generated query, expected SQL or per-case response is returned.
    """
    if (not isinstance(questions, (list, tuple))
            or not 1 <= len(questions) <= _MAX_QUESTIONS
            or any(
                not isinstance(q, str)
                or not 0 < len(q.strip()) <= _MAX_QUESTION_LENGTH
                for q in questions
            )):
        raise SemanticRoleMigrationRefused("questions_invalid")
    if prepared.get("status") != "PREPARED_NOT_ACTIVATED":
        raise SemanticRoleMigrationRefused("unprepared_candidate")
    source = _as_mapping(prepared.get("source"), code="source_missing")
    candidate = _as_mapping(prepared.get("candidate"), code="candidate_missing")
    intent_changes = 0
    plan_changes = 0
    rejected_source = 0
    rejected_candidate = 0
    planned_source = 0
    planned_candidate = 0
    planned_to_rejected = 0
    rejected_to_planned = 0
    planned_projection_changes = 0
    rejection_codes: dict[str, int] = {}
    changed_fields: dict[str, int] = {}
    missing_operand_operations: dict[str, int] = {}
    rejected_case_cause_counts: dict[str, int] = {}
    projected_fields = (
        "detected_dimensions",
        "planned_metrics",
        "analytical_operations",
        "temporal_series",
        "planned_filters",
        "resolved_filter_bindings",
        "authorized_joins",
    )

    for question in questions:
        try:
            source_intent = resolve_intent(question, source["intent_resolution"])
            candidate_intent = resolve_intent(question, candidate["intent_resolution"])
        except Exception as exc:
            raise SemanticRoleMigrationRefused("intent_audit_failed") from exc
        old_identity = (source_intent["applied"], source_intent.get("intent"), source_intent["reason"])
        new_identity = (candidate_intent["applied"], candidate_intent.get("intent"), candidate_intent["reason"])
        intent_changes += old_identity != new_identity
        rejected_source += not source_intent["applied"]
        rejected_candidate += not candidate_intent["applied"]

        old_plan = _safe_plan(source, source_intent, question)
        new_plan = _safe_plan(candidate, candidate_intent, question)
        planned_source += old_plan is not None and old_plan["status"] == "planned"
        planned_candidate += new_plan is not None and new_plan["status"] == "planned"
        changed = _plan_signature(old_plan) != _plan_signature(new_plan)
        plan_changes += changed
        old_status = old_plan["status"] if old_plan is not None else "not_applicable"
        new_status = new_plan["status"] if new_plan is not None else "not_applicable"
        if old_status == "planned" and new_status == "rejected":
            planned_to_rejected += 1
            code = new_plan.get("error_code")
            if isinstance(code, str) and code:
                rejection_codes[code] = rejection_codes.get(code, 0) + 1
            # Aggregate only structural proof gaps. Never disclose individual
            # questions, tenant tables, aliases, metrics or binding names.
            projection = new_plan.get("projection")
            if isinstance(projection, Mapping):
                for cause in _structural_rejection_causes(projection):
                    rejected_case_cause_counts[cause] = (
                        rejected_case_cause_counts.get(cause, 0) + 1
                    )
                metrics = projection.get("planned_metrics")
                operations = projection.get("analytical_operations")
                if isinstance(metrics, list) and isinstance(operations, list):
                    present = {
                        metric.get("metric_ref")
                        for metric in metrics if isinstance(metric, Mapping)
                        and isinstance(metric.get("metric_ref"), str)
                    }
                    for operation in operations:
                        if not isinstance(operation, Mapping):
                            continue
                        kind = operation.get("operation_type")
                        if kind == "comparison":
                            refs = operation.get("operand_metric_refs")
                            cardinality = operation.get("binding_cardinality")
                            minimum = cardinality.get("minimum") if isinstance(
                                cardinality, Mapping
                            ) else None
                            incomplete = (
                                type(minimum) is not int
                                or not isinstance(refs, list)
                                or len(refs) < minimum
                                or any(ref not in present for ref in refs)
                            )
                        elif kind == "ranking":
                            ref = operation.get("metric_ref")
                            incomplete = not isinstance(ref, str) or ref not in present
                        else:
                            incomplete = True
                        if incomplete:
                            label = kind if kind in {"comparison", "ranking"} else "other"
                            missing_operand_operations[label] = (
                                missing_operand_operations.get(label, 0) + 1
                            )
        if old_status == "rejected" and new_status == "planned":
            rejected_to_planned += 1
        if changed and old_status == "planned" and new_status == "planned":
            planned_projection_changes += 1
            old_projection = (
                (old_plan.get("query_plan") or {}).get("planning_context") or {}
            )
            new_projection = (
                (new_plan.get("query_plan") or {}).get("planning_context") or {}
            )
            for field in projected_fields:
                if _canonical_json(old_projection.get(field)) != (
                    _canonical_json(new_projection.get(field))
                ):
                    changed_fields[field] = changed_fields.get(field, 0) + 1

    source_catalog_audit = audit_semantic_catalog(source)
    candidate_catalog_audit = audit_semantic_catalog(candidate)
    requires_review = bool(
        intent_changes
        or plan_changes
        or source_catalog_audit["status"] != "INVENTORY_COMPLETE"
        or candidate_catalog_audit["status"] != "INVENTORY_COMPLETE"
    )
    return {
        "status": "REVIEW_REQUIRED" if requires_review else "NO_DETECTED_DRIFT",
        "source_version": source["version"],
        "source_fingerprint": source["fingerprint"],
        "candidate_version": candidate["version"],
        "candidate_fingerprint": candidate["fingerprint"],
        "question_count": len(questions),
        "source_catalog_audit": source_catalog_audit,
        "candidate_catalog_audit": candidate_catalog_audit,
        "intent_decisions_changed": intent_changes,
        "planning_projections_changed": plan_changes,
        "rejected_source": rejected_source,
        "rejected_candidate": rejected_candidate,
        "planned_source": planned_source,
        "planned_candidate": planned_candidate,
        "planned_to_rejected": planned_to_rejected,
        "rejected_to_planned": rejected_to_planned,
        "planned_projection_changes": planned_projection_changes,
        "rejection_code_counts": dict(sorted(rejection_codes.items())),
        "changed_projection_field_counts": dict(sorted(changed_fields.items())),
        "incomplete_analytical_operand_counts": dict(
            sorted(missing_operand_operations.items())
        ),
        "rejected_case_cause_counts": dict(
            sorted(rejected_case_cause_counts.items())
        ),
        "sql_generated": False,
        "sql_executed": False,
        "provider_calls": 0,
        "automated_activation_authorized": False,
    }


def _structural_rejection_causes(projection: Mapping[str, Any]) -> list[str]:
    """Privacy-safe structural failure classes, counted once per rejected case.

    No labels, questions, SQL, names of tenant tables or metric aliases leave
    this function. Multiple causes can coexist in the same rejected case.
    """
    found: set[str] = set()
    metrics = projection.get("planned_metrics")
    if isinstance(metrics, list) and not metrics:
        found.add("no_projected_metric")
    diagnostics = projection.get("diagnostics")
    if not isinstance(diagnostics, Mapping):
        return sorted(found)
    metric = diagnostics.get("planned_metric_diagnostic")
    if isinstance(metric, Mapping):
        if metric.get("unresolved_terms"):
            found.add("metric_alias_unresolved")
        if metric.get("invalid_metadata_terms"):
            found.add("metric_metadata_invalid")
        if metric.get("binding_failures"):
            found.add("metric_binding_not_applicable_or_invalid")
        inference = metric.get("binding_inference")
        if isinstance(inference, Mapping) and inference.get("status") == (
            "ambiguous_metric_concept"
        ):
            found.add("metric_concept_inference_ambiguous")
        for failure in metric.get("binding_failures", []):
            if not isinstance(failure, Mapping):
                continue
            for diagnostic in failure.get("binding_diagnostics", []):
                if not isinstance(diagnostic, Mapping):
                    continue
                for rejected in diagnostic.get("rejected", []):
                    if not isinstance(rejected, Mapping):
                        continue
                    reason = rejected.get("reason")
                    if reason == "when_present_missing":
                        found.add("binding_required_concept_missing")
                    elif reason == "when_absent_present":
                        found.add("binding_forbidden_concept_present")
    analytical = diagnostics.get("analytical_operation_diagnostic")
    if isinstance(analytical, Mapping):
        if analytical.get("unresolved_terms"):
            found.add("operation_alias_unresolved")
        if analytical.get("invalid_metadata_terms"):
            found.add("operation_metadata_invalid")
        dimension = analytical.get("dimension_compatibility")
        if isinstance(dimension, Mapping) and dimension.get("status") not in (
            "passed", "not_applicable", None
        ):
            found.add("comparison_dimension_incompatible")
    return sorted(found)


def _safe_plan(
    context: dict[str, Any],
    intent: Mapping[str, Any],
    question: str,
) -> dict[str, Any] | None:
    if not intent["applied"]:
        return None
    try:
        return build_query_plan(
            context=context,
            intent_name=intent["intent"],
            intent_confidence=intent["intent_confidence"],
            normalized_question=normalize_search_text(question),
            intent_resolution_result=intent,
        )
    except Exception as exc:
        raise SemanticRoleMigrationRefused("planning_audit_failed") from exc


def _plan_signature(result: Mapping[str, Any] | None) -> Any:
    if result is None:
        return None
    if result.get("status") != "planned":
        return (result.get("status"), result.get("error_code"))
    plan = result.get("query_plan") or {}
    projection = plan.get("planning_context") or {}
    keys = (
        "detected_dimensions",
        "planned_metrics",
        "analytical_operations",
        "temporal_series",
        "planned_filters",
        "resolved_filter_bindings",
        "authorized_joins",
    )
    return (
        "planned",
        _canonical_json({key: projection.get(key) for key in keys}),
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False, default=str,
    )
