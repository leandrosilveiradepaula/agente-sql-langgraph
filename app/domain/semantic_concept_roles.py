"""Tenant-versioned binding between *structural* operations and semantic concepts.

No business concept names, aliases, metric names or customer-specific terms
live in this module. Missing role bindings never infer accounting semantics.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

ROLE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MAX_ROLES = 32
MAX_ROLE_CONCEPTS = 64


class ConceptRoleConfigurationError(ValueError):
    """A versioned role mapping is malformed or exceeds platform bounds."""


def parse_concept_roles(
    intent_resolution: Mapping[str, Any],
) -> dict[str, frozenset[str]]:
    if not isinstance(intent_resolution, Mapping):
        raise ConceptRoleConfigurationError("intent_resolution_invalid")
    config = intent_resolution.get("config")
    if not isinstance(config, Mapping):
        raise ConceptRoleConfigurationError("intent_resolver_config_invalid")
    raw = config.get("concept_roles")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping) or len(raw) > MAX_ROLES:
        raise ConceptRoleConfigurationError("concept_roles_invalid")
    roles: dict[str, frozenset[str]] = {}
    for role, names in raw.items():
        if not isinstance(role, str) or ROLE_NAME.fullmatch(role) is None:
            raise ConceptRoleConfigurationError("concept_role_name_invalid")
        if (
            not isinstance(names, list)
            or not 1 <= len(names) <= MAX_ROLE_CONCEPTS
            or any(
                not isinstance(name, str) or not name.strip()
                or len(name.strip()) > 128 for name in names
            )
        ):
            raise ConceptRoleConfigurationError("concept_role_values_invalid")
        normalized = [name.strip().casefold() for name in names]
        if len(set(normalized)) != len(normalized):
            raise ConceptRoleConfigurationError("concept_role_duplicate_concept")
        roles[role] = frozenset(normalized)
    return roles


def role_concepts(
    intent_resolution: Mapping[str, Any],
    role: str,
) -> frozenset[str]:
    if not isinstance(role, str) or ROLE_NAME.fullmatch(role) is None:
        raise ConceptRoleConfigurationError("requested_role_invalid")
    return parse_concept_roles(intent_resolution).get(role, frozenset())


def unknown_role_concepts(
    intent_resolution: Mapping[str, Any],
) -> dict[str, list[str]]:
    """Reference-integrity check, used at context validation and direct calls."""
    roles = parse_concept_roles(intent_resolution)
    entries = intent_resolution.get("intent_catalog")
    if not isinstance(entries, list):
        raise ConceptRoleConfigurationError("intent_catalog_invalid")
    known = {
        str(c.get("concept_name")).strip().casefold()
        for entry in entries if isinstance(entry, Mapping)
        for rule in entry.get("rules", []) if isinstance(rule, Mapping)
        for c in rule.get("concepts", []) if isinstance(c, Mapping)
        and isinstance(c.get("concept_name"), str)
        and c.get("concept_name", "").strip()
    }
    return {
        role: sorted(names - known)
        for role, names in roles.items()
        if names - known
    }
