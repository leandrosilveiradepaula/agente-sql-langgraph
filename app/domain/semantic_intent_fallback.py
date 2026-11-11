"""Provider-neutral, opt-in semantic interpretation grounded in a tenant catalog.

Only the original question and a projected set of authorized intent definitions
reach the model. No benchmark, SQL, physical table, golden answer, or tenant
credential is included. The response cannot authorize a metric or a query.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from app.domain.search_text import normalize_search_text

CONTRACT_VERSION = "semantic-intent-v2"
MAX_INTERPRETATION_REQUEST_BYTES = 65_536


class SemanticIntentRejected(ValueError):
    """Invalid, ambiguous or ungrounded semantic interpretation."""


def versioned_policy(context: Mapping[str, Any]) -> dict[str, Any] | None:
    components = context.get("component_configs")
    if not isinstance(components, Mapping):
        raise SemanticIntentRejected("component_configs_invalid")
    raw = components.get("semantic_intent_fallback")
    if raw is None:
        return None
    if not isinstance(raw, Mapping) or set(raw) != {
        "component", "enabled", "applied_confidence"
    } or raw.get("component") != "semantic_intent_fallback":
        raise SemanticIntentRejected("fallback_config_invalid")
    if type(raw.get("enabled")) is not bool:
        raise SemanticIntentRejected("fallback_enabled_invalid")
    confidence = raw.get("applied_confidence")
    if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
            or not 0.0 < float(confidence) <= 1.0):
        raise SemanticIntentRejected("fallback_confidence_invalid")
    return dict(raw) if raw["enabled"] else None


def prepare_interpretation(
    question: str,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    """Project only allowed intent vocabulary, never SQL or example answers."""
    if not isinstance(question, str) or not 0 < len(question.strip()) <= 16000:
        raise SemanticIntentRejected("question_invalid")
    version = context.get("version")
    fingerprint = context.get("fingerprint")
    if (not isinstance(version, str) or not version
            or not isinstance(fingerprint, str)
            or not re.fullmatch("[0-9a-f]{64}", fingerprint)):
        raise SemanticIntentRejected("context_identity_invalid")
    resolution = context.get("intent_resolution")
    patterns = context.get("query_patterns")
    if not isinstance(resolution, Mapping) or not isinstance(patterns, list):
        raise SemanticIntentRejected("catalog_missing")
    authorized = {
        p.get("intent_name")
        for p in patterns if isinstance(p, Mapping)
        and isinstance(p.get("intent_name"), str)
    }
    catalog = resolution.get("intent_catalog")
    if not isinstance(catalog, list) or not 1 <= len(catalog) <= 128:
        raise SemanticIntentRejected("catalog_invalid")
    intents: list[dict[str, Any]] = []
    used: set[str] = set()
    for entry in catalog:
        if not isinstance(entry, Mapping):
            raise SemanticIntentRejected("catalog_entry_invalid")
        name = entry.get("intent_name")
        description = entry.get("semantic_description")
        rules = entry.get("rules")
        if (not isinstance(name, str) or name not in authorized
                or name.casefold() in used or not isinstance(description, str)
                or not description.strip() or len(description) > 1500
                or not isinstance(rules, list) or len(rules) > 128):
            raise SemanticIntentRejected("catalog_entry_unusable")
        used.add(name.casefold())
        required: list[dict[str, Any]] = []
        concepts: set[str] = set()
        lexicon: dict[str, set[str]] = {}
        for rule in rules:
            if not isinstance(rule, Mapping):
                raise SemanticIntentRejected("catalog_rule_invalid")
            effect = rule.get("effect")
            names = []
            for concept in rule.get("concepts", []):
                if not isinstance(concept, Mapping):
                    raise SemanticIntentRejected("catalog_concept_invalid")
                cname = concept.get("concept_name")
                if not isinstance(cname, str) or not cname.strip():
                    raise SemanticIntentRejected("catalog_concept_invalid")
                names.append(cname)
                if effect in {"require", "positive_score"}:
                    terms = concept.get("terms")
                    if (not isinstance(terms, list) or len(terms) > 128
                            or any(not isinstance(term, str)
                                   or not 0 < len(term.strip()) <= 256
                                   for term in terms)):
                        raise SemanticIntentRejected("catalog_terms_invalid")
                    lexicon.setdefault(cname, set()).update(
                        term.strip() for term in terms
                    )
            if effect in {"require", "positive_score"}:
                concepts.update(names)
            if effect == "require":
                required.append({
                    "concept_names": names,
                    "minimum_concept_matches": rule.get("minimum_concept_matches"),
                })
        if not concepts:
            raise SemanticIntentRejected("catalog_without_groundable_concepts")
        intents.append({
            "intent_name": name,
            "semantic_description": description,
            "allowed_concepts": sorted(concepts),
            "concept_lexicon": [
                {"concept_name": name, "terms": sorted(lexicon.get(name, set()))}
                for name in sorted(concepts)
            ],
            "required_concept_groups": required,
        })
    request = {
        "contract_version": CONTRACT_VERSION,
        "task": (
            "Interpret the user's financial question; do not generate SQL. "
            "Choose precisely one intent from allowed_intents only if supported "
            "by quoted spans from the question. Bind each quote to a "
            "concept_name and an EXACT catalog_term from that concept's "
            "concept_lexicon; the catalog_term may differ from the user quote. "
            "Never generate an alias or metric that is not present in the "
            "catalog. Respect every required_concept_group. Return "
            "insufficient if no authorized catalog term preserves the meaning. "
            "Return only JSON with exactly keys: status ('selected' or "
            "'insufficient'), intent_name (name or null), context_fingerprint "
            "(exact supplied value), bindings (list of objects with exactly "
            "concept_name, question_span and catalog_term). Do not invent "
            "vocabulary, use historical answers or infer unknown accounting "
            "mappings."
        ),
        "question": question,
        "context_version": version,
        "context_fingerprint": fingerprint,
        "allowed_intents": intents,
    }
    # Structural bound: prevent unbounded catalog/model costs for any tenant.
    # Refuse before making a provider request rather than truncating rules.
    serialized = json.dumps(request, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > MAX_INTERPRETATION_REQUEST_BYTES:
        raise SemanticIntentRejected("semantic_prompt_too_large")
    return request


def validate_interpretation(
    raw_output: str,
    request: Mapping[str, Any],
    deterministic_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail closed: an LLM cannot invent intents, concepts or quoted evidence."""
    if not isinstance(raw_output, str) or len(raw_output) > 32_768:
        raise SemanticIntentRejected("provider_output_invalid")
    try:
        data = json.loads(raw_output)
    except (TypeError, ValueError) as exc:
        raise SemanticIntentRejected("provider_output_not_json") from exc
    if not isinstance(data, dict) or set(data) != {
        "status", "intent_name", "context_fingerprint", "bindings"
    }:
        raise SemanticIntentRejected("provider_shape_invalid")
    if data["context_fingerprint"] != request.get("context_fingerprint"):
        raise SemanticIntentRejected("provider_context_mismatch")
    if data["status"] == "insufficient":
        if data["intent_name"] is not None or data["bindings"] != []:
            raise SemanticIntentRejected("provider_abstention_invalid")
        raise SemanticIntentRejected("provider_abstained")
    if data["status"] != "selected":
        raise SemanticIntentRejected("provider_status_invalid")
    name = data["intent_name"]
    options = request.get("allowed_intents", [])
    target = next(
        (p for p in options if isinstance(p, Mapping)
         and p.get("intent_name") == name), None
    )
    if target is None:
        raise SemanticIntentRejected("provider_intent_unknown")
    evaluations = (
        deterministic_result.get("intent_catalog", {}).get("evaluations", [])
    )
    if any(
        isinstance(ev, Mapping) and ev.get("intent_name") == name
        and ev.get("excluded") is True
        for ev in evaluations
    ):
        raise SemanticIntentRejected("provider_intent_excluded")
    bindings = data["bindings"]
    if not isinstance(bindings, list) or not 1 <= len(bindings) <= 32:
        raise SemanticIntentRejected("provider_evidence_missing")
    allowed = set(target["allowed_concepts"])
    question = normalize_search_text(request["question"])
    observed: set[str] = set()
    seen_bindings: set[tuple[str, str]] = set()
    span_owner: dict[str, str] = {}
    safe: list[dict[str, str]] = []
    for item in bindings:
        if not isinstance(item, dict) or set(item) != {
            "concept_name", "question_span", "catalog_term"
        }:
            raise SemanticIntentRejected("provider_binding_invalid")
        concept, span = item["concept_name"], item["question_span"]
        catalog_term = item["catalog_term"]
        if (not isinstance(concept, str) or concept not in allowed
                or not isinstance(span, str) or not 0 < len(span) <= 256):
            raise SemanticIntentRejected("provider_binding_unknown")
        if not isinstance(catalog_term, str) or not 0 < len(catalog_term) <= 256:
            raise SemanticIntentRejected("provider_catalog_term_invalid")
        lexicons = target.get("concept_lexicon")
        if not isinstance(lexicons, list):
            raise SemanticIntentRejected("catalog_lexicon_invalid")
        permitted_terms = {
            normalize_search_text(term): term
            for entry in lexicons
            if isinstance(entry, Mapping) and entry.get("concept_name") == concept
            for term in entry.get("terms", [])
            if isinstance(term, str) and term.strip()
        }
        normalized_catalog_term = normalize_search_text(catalog_term)
        if (
            not normalized_catalog_term
            or normalized_catalog_term not in permitted_terms
        ):
            raise SemanticIntentRejected("provider_catalog_term_not_authorized")
        authorized_catalog_term = permitted_terms[normalized_catalog_term]
        normalized_span = normalize_search_text(span)
        if not normalized_span or not re.search(
            r"(?<!\w)" + re.escape(normalized_span) + r"(?!\w)", question
        ):
            raise SemanticIntentRejected("provider_span_not_in_question")
        key = (concept, normalized_span)
        if key in seen_bindings:
            raise SemanticIntentRejected("provider_duplicate_binding")
        seen_bindings.add(key)
        previous_owner = span_owner.setdefault(normalized_span, concept)
        if previous_owner != concept:
            raise SemanticIntentRejected("provider_span_concept_conflict")
        observed.add(concept)
        safe.append({
            "concept_name": concept,
            "question_span": span,
            "catalog_term": authorized_catalog_term,
        })
    for requirement in target["required_concept_groups"]:
        required = requirement["concept_names"]
        minimum = requirement["minimum_concept_matches"]
        if (type(minimum) is not int or minimum <= 0
                or len(observed.intersection(required)) < minimum):
            raise SemanticIntentRejected("provider_requirements_unmet")
    return {
        "intent_name": name,
        "bindings": safe,
        "context_fingerprint": request["context_fingerprint"],
        "resolution_source": "grounded_semantic_model",
    }
