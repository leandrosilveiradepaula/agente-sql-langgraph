"""Read-only audit of legacy n8n semantic coupling to source catalogs.

Consumes supplied workflow export + G5 inventory/hints/manifests. No DB,
n8n API, LLM, SQL execution, GPG operations, authorization changes or network
access. Findings are static evidence only and NEVER approve accounting.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any

# Structural programming syntax, never a customer's table, metric or intent.
_IDENTIFIER = r"[A-Za-z_$][A-Za-z0-9_$]*"
_STATIC_MAP = re.compile(
    rf"(?ms)^\s*(?:const|let|var)\s+({_IDENTIFIER})\s*=\s*"
    r"\{([^{}]{1,6000})\}\s*;"
)
_MAP_ITEM = re.compile(
    rf"({_IDENTIFIER})\s*:\s*(['\"])([A-Za-z_][A-Za-z0-9_]*)\2"
)
_VERSION_SELECTOR = re.compile(
    r"(?i)\b(?:semantic_)?agent_version\s*=\s*(['\"])([^'\"]{1,180})\1"
)
_TENANT_SELECTOR = re.compile(
    r"(?i)\b(?:tenant_id|organization_id|organization_uuid)\b"
)
_APPROVED_STATUS = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class LegacyAuditBlocked(ValueError):
    """Untrustworthy or missing source evidence: refuse an audit result."""


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _valid_string(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 180


def _status(value: object) -> str:
    if isinstance(value, str) and _APPROVED_STATUS.fullmatch(value):
        return value
    return "UNKNOWN_OR_REDACTED"


def audit_legacy_semantic_coupling(
    *,
    workflow: Mapping[str, Any],
    source_inventory: Mapping[str, Any],
    source_hints: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Inspect source selection, fixed versions and candidate table mappings.

    A matching table name, even in all versions, is not a valid accounting
    mapping. Human approval and physical introspection remain separate.
    """
    if not isinstance(workflow, Mapping):
        raise LegacyAuditBlocked("WORKFLOW_INVALID")
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 2048:
        raise LegacyAuditBlocked("WORKFLOW_NODES_INVALID")
    if workflow.get("active") is not True or (
        workflow.get("activeVersionId") != workflow.get("versionId")
    ):
        raise LegacyAuditBlocked("PUBLISHED_WORKFLOW_NOT_ATTESTED")

    manifest_versions = source_manifest.get("versions")
    collections = source_inventory.get("source_collections")
    candidates = source_hints.get("candidates")
    if (
        not isinstance(collections, list)
        or not isinstance(candidates, list)
        or not isinstance(manifest_versions, list)
        or not 1 <= len(collections) <= 128
        or not 1 <= len(manifest_versions) <= 500
        or len(candidates) > 100_000
    ):
        raise LegacyAuditBlocked("G5_EVIDENCE_INVALID")
    if source_manifest.get("approved_for_generation") is not False:
        raise LegacyAuditBlocked("G5_SOURCE_UNSAFE_FOR_GENERATION")
    if (
        source_inventory.get("sql_patterns_classification")
        != "EVALUATION_ONLY_NOT_GENERATOR_INPUT"
    ):
        raise LegacyAuditBlocked("HISTORICAL_SQL_NOT_SEGREGATED")

    version_set: set[str] = set()
    for version in manifest_versions:
        if not isinstance(version, Mapping) or not _valid_string(
            version.get("source_version_sha256")
        ):
            raise LegacyAuditBlocked("G5_VERSION_INVALID")
        identifier = version["source_version_sha256"]
        if identifier in version_set:
            raise LegacyAuditBlocked("G5_VERSIONS_DUPLICATED")
        version_set.add(identifier)
    catalog_names: dict[str, str] = {}
    for collection in collections:
        if not isinstance(collection, Mapping) or not _valid_string(
            collection.get("name")
        ):
            raise LegacyAuditBlocked("G5_CATALOG_INVALID")
        key = collection["name"].casefold()
        if key in catalog_names:
            raise LegacyAuditBlocked("G5_CATALOG_DUPLICATED")
        use = collection.get("use")
        if use not in ("EVALUATION_ONLY", "SOURCE_SEMANTIC_REVIEW_ONLY"):
            # Never silently treat unknown original business content as safe.
            raise LegacyAuditBlocked("G5_CATALOG_USE_UNREVIEWED")
        catalog_names[key] = use

    refs: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise LegacyAuditBlocked("G5_HINT_INVALID")
        version = candidate.get("source_version_sha256")
        if version not in version_set:
            raise LegacyAuditBlocked("G5_HINT_VERSION_UNVERIFIED")
        name = candidate.get("source_table_ref")
        if isinstance(name, str) and name.strip():
            refs[name.casefold().rsplit(".", 1)[-1]].append(candidate)

    results = []
    seen_names: set[str] = set()
    total_js_lines = 0
    map_count = 0
    alias_count = 0
    matched_aliases = 0
    for ordinal, node in enumerate(nodes, 1):
        if not isinstance(node, Mapping):
            raise LegacyAuditBlocked("WORKFLOW_NODE_INVALID")
        name = node.get("name")
        if not _valid_string(name) or name in seen_names:
            raise LegacyAuditBlocked("WORKFLOW_NODE_NAME_INVALID")
        seen_names.add(name)
        kind = str(node.get("type") or "").rsplit(".", 1)[-1]
        params = node.get("parameters")
        if not isinstance(params, Mapping):
            params = {}
        entry: dict[str, Any] = {
            "ordinal": ordinal,
            "node_sha256": _sha(name),
            "type": kind,
            "semantic_status": "REVIEW_REQUIRED",
        }
        if kind == "postgres":
            query = params.get("query")
            query = query if isinstance(query, str) else ""
            visible = [
                collection
                for collection in collections
                if re.search(
                    rf"(?i)\b{re.escape(collection['name'])}\b", query
                )
            ]
            fixed = _VERSION_SELECTOR.findall(query)
            entry["source_catalog_references"] = [
                {
                    "collection_name": col["name"],
                    "use": col["use"],
                }
                for col in visible
            ]
            entry["inline_version_literal_count"] = len(fixed)
            entry["inline_version_sha256_unique"] = sorted(
                {_sha(version) for _, version in fixed}
            )
            entry["has_explicit_tenant_column_reference"] = (
                _TENANT_SELECTOR.search(query) is not None
            )
            entry["query_sha256"] = _sha(query)
            entry["reads_evaluation_only_content"] = any(
                col["use"] == "EVALUATION_ONLY" for col in visible
            )
        elif kind == "code":
            js = params.get("jsCode")
            js = js if isinstance(js, str) else ""
            total_js_lines += len(js.splitlines())
            entry["code_sha256"] = _sha(js)
            entry["line_count"] = len(js.splitlines())
            found_maps: list[dict[str, Any]] = []
            for map_match in _STATIC_MAP.finditer(js):
                entries = _MAP_ITEM.findall(map_match.group(2))
                if not entries:
                    continue
                # Candidate patterns only. Do not assume object values are
                # physical tables without comparing to source hints.
                matches = []
                for alias, _, table in entries:
                    alias_count += 1
                    source_matches = refs.get(table.casefold(), [])
                    status_counts = Counter(
                        _status(x.get("candidate_status"))
                        for x in source_matches
                    )
                    matched_aliases += bool(source_matches)
                    matches.append(
                        {
                            "alias_sha256": _sha(alias),
                            "value_sha256": _sha(table),
                            "source_hint_count": len(source_matches),
                            "source_version_count": len({
                                x["source_version_sha256"]
                                for x in source_matches
                            }),
                            "candidate_status_counts": dict(
                                sorted(status_counts.items())
                            ),
                            "accounting_equivalence_approved": False,
                        }
                    )
                map_count += 1
                line_number = js.count("\n", 0, map_match.start()) + 1
                found_maps.append(
                    {
                        "variable_name_sha256": _sha(map_match.group(1)),
                        "source_line": line_number,
                        "simple_string_binding_count": len(entries),
                        "bindings": matches,
                    }
                )
            entry["static_object_maps"] = found_maps
        results.append(entry)

    loaded_evaluation = [
        {
            "ordinal": e["ordinal"],
            "collections": sorted(
                x["collection_name"]
                for x in e.get("source_catalog_references", [])
                if x["use"] == "EVALUATION_ONLY"
            ),
        }
        for e in results
        if e.get("reads_evaluation_only_content")
    ]
    fixed_version_nodes = [
        {
            "ordinal": e["ordinal"],
            "selector_count": e["inline_version_literal_count"],
            "version_hashes": e["inline_version_sha256_unique"],
            "has_explicit_tenant_column_reference": e[
                "has_explicit_tenant_column_reference"
            ],
        }
        for e in results
        if e.get("inline_version_literal_count", 0)
    ]
    return {
        "contract": "legacy-semantic-static-coupling-audit-v1",
        "status": "SOURCE_REVIEW_ONLY_NOT_FINANCIAL_EQUIVALENCE",
        "node_count": len(results),
        "source_version_count": len(version_set),
        "g5_hint_count": len(candidates),
        "static_object_map_count": map_count,
        "static_binding_candidate_count": alias_count,
        "static_bindings_with_textual_g5_hints": matched_aliases,
        "total_js_lines": total_js_lines,
        "fixed_source_version_nodes": fixed_version_nodes,
        "evaluation_only_sources_read_by_legacy": loaded_evaluation,
        "nodes": results,
        "business_mappings_approved": False,
        "historical_sql_suitable_for_generation": False,
        "financial_sql_executed": False,
        "llm_called": False,
        "contains_raw_legacy_queries_or_js_or_alias_values": False,
    }
