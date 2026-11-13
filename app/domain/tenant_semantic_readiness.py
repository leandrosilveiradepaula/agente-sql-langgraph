"""Offline physical-schema preflight for customer-provided semantic contexts.

No client-specific table names, SQL examples, accounting interpretations,
database connections or benchmark answers live here. The caller must acquire
physical metadata through an independently authorized, read-only adapter.
This module can only reject inconsistent mappings: it NEVER approves them.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from app.domain.context_normalizer import (
    ContextNormalizationError,
    normalize_context_snapshot,
)
from app.domain.context_validator import validate_context_snapshot

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_MAX_TABLES = 2048
_MAX_COLUMNS = 2048
_FIELD_CLASSES = ("primary_key", "key_columns", "metric_columns", "date_columns")


def _identity_hash(*parts: str) -> str:
    return hashlib.sha256(
        json.dumps(parts, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


def _is_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _physical_tables(value: object) -> dict[tuple[str, str], frozenset[str]]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= _MAX_TABLES
    ):
        raise ValueError("PHYSICAL_METADATA_REQUIRED")
    tables: dict[tuple[str, str], frozenset[str]] = {}
    for entry in value:
        if not isinstance(entry, Mapping):
            raise ValueError("PHYSICAL_METADATA_INVALID")
        schema = entry.get("schema_name")
        name = entry.get("table_name")
        columns = entry.get("columns")
        if not _is_identifier(schema) or not _is_identifier(name):
            raise ValueError("PHYSICAL_IDENTIFIER_INVALID")
        if (
            not isinstance(columns, list)
            or not 1 <= len(columns) <= _MAX_COLUMNS
            or not all(_is_identifier(x) for x in columns)
        ):
            raise ValueError("PHYSICAL_COLUMNS_INVALID")
        ident = (schema, name)
        if ident in tables or len(columns) != len(set(columns)):
            raise ValueError("PHYSICAL_CATALOG_AMBIGUOUS")
        tables[ident] = frozenset(columns)
    return tables


def assess_tenant_semantic_candidate(
    *,
    raw_context: Mapping[str, Any],
    tenant_id: str,
    semantic_version: str,
    physical_catalog: list[dict[str, Any]],
    metadata_readonly_attested: bool,
) -> dict[str, Any]:
    """Return sanitized preflight findings; approval is ALWAYS a separate gate.

    Physical metadata must come from an authorized read-only inspection of
    that customer's DB, not from the user's question or an LLM guess.
    """
    if not metadata_readonly_attested:
        raise ValueError("PHYSICAL_METADATA_NOT_ATTESTED")
    if (
        not isinstance(raw_context, Mapping)
        or not isinstance(tenant_id, str)
        or not tenant_id.strip()
        or not isinstance(semantic_version, str)
        or not semantic_version.strip()
    ):
        raise ValueError("UNTRUSTED_TENANT_CONTEXT")
    if (
        raw_context.get("tenant_id") != tenant_id
        or raw_context.get("semantic_agent_version") != semantic_version
        or raw_context.get("historical_evaluation_sql_excluded") is not True
    ):
        raise ValueError("CONTEXT_PROVENANCE_INVALID")
    physical = _physical_tables(physical_catalog)
    try:
        snapshot = normalize_context_snapshot(raw_context)
    except (ContextNormalizationError, TypeError, ValueError):
        raise ValueError("CONTEXT_NORMALIZATION_FAILED") from None
    result = validate_context_snapshot(snapshot)
    problems: list[dict[str, str]] = []
    if result["status"] != "valid":
        for issue in result["errors"]:
            problems.append({
                "code": "SEMANTIC_CONTRACT_INVALID",
                "reference_sha256": _identity_hash(
                    str(issue.get("code", "")),
                    str(issue.get("path", "")),
                ),
            })
    table_catalog = snapshot["table_catalog"]
    if not table_catalog:
        problems.append({
            "code": "NO_SEMANTIC_TABLE_CATALOG",
            "reference_sha256": _identity_hash(tenant_id, semantic_version),
        })
    verified = 0
    for table in table_catalog:
        schema = table.get("schema_name")
        name = table.get("table_name")
        if not _is_identifier(schema) or not _is_identifier(name):
            problems.append({
                "code": "SEMANTIC_TABLE_ID_INVALID",
                "reference_sha256": _identity_hash(str(schema), str(name)),
            })
            continue
        key = (schema, name)
        allowed = physical.get(key)
        if allowed is None:
            problems.append({
                "code": "PHYSICAL_TABLE_NOT_FOUND",
                "reference_sha256": _identity_hash(schema, name),
            })
            continue
        verified += 1
        for field in _FIELD_CLASSES:
            names = table.get(field) or []
            if (
                not isinstance(names, list)
                or not all(_is_identifier(x) for x in names)
            ):
                problems.append({
                    "code": "SEMANTIC_COLUMN_DECLARATION_INVALID",
                    "reference_sha256": _identity_hash(schema, name, field),
                })
                continue
            for column in names:
                if column not in allowed:
                    problems.append({
                        "code": "PHYSICAL_COLUMN_NOT_FOUND",
                        "reference_sha256": _identity_hash(
                            schema, name, field, column
                        ),
                    })
    problems.sort(key=lambda x: (x["code"], x["reference_sha256"]))
    return {
        "contract": "customer-semantic-physical-preflight-v1",
        "status": (
            "PHYSICALLY_CONSISTENT_REQUIRES_BUSINESS_APPROVAL"
            if not problems else "REJECTED"
        ),
        "context_fingerprint": snapshot["fingerprint"],
        "physical_catalog_digest_sha256": _identity_hash(
            *[
                x + "." + y + ":" + ",".join(sorted(cols))
                for (x, y), cols in sorted(physical.items())
            ]
        ),
        "tenant_id_sha256": _identity_hash(tenant_id),
        "semantic_version_sha256": _identity_hash(semantic_version),
        "semantic_table_count": len(table_catalog),
        "physical_table_count": len(physical),
        "verified_semantic_tables": verified,
        "issues": problems,
        "financial_meanings_attested": False,
        "approved_for_sql_generation": False,
        "approved_for_real_sql_execution": False,
        "benchmark_used_as_generator_context": False,
    }
