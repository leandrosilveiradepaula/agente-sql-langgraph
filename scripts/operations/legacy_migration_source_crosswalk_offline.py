"""Auditable, read-only crosswalk: published n8n topology x G5 source metadata.

This utility never connects to a database, decrypts a backup, executes SQL,
calls an LLM or authorizes a semantic mapping. Its inputs are independently
collected workflow/manifest objects. Results contain only hashes, ordinals,
structural counts and unapproved textual references; never raw prompts, SQL,
credentials, URLs, entity names or financial data.

The caller must verify the true product route separately: a published n8n
record is not proof of which workflow an external product calls.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict, deque
from collections.abc import Mapping
from typing import Any

from app.domain.sql_analysis import SqlAnalysisError, analyze_sql
from scripts.audit_n8n_workflow_export_readonly import summarize_workflow

MAX_NODES = 2500
MAX_SOURCE_CANDIDATES = 200000
MAX_CROSSWALK_LINKS = 25000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{2,119}$")
_EDGE_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


class LegacyMigrationInventoryRefused(ValueError):
    """An incomplete or unsafe source cannot be treated as inventory evidence."""


def _deny(reason: str) -> None:
    raise LegacyMigrationInventoryRefused(reason)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_obj(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return _hash_text(raw)


def _schema_guard(
    *,
    inventory: Mapping[str, Any],
    lineage: Mapping[str, Any],
    hints: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> tuple[dict[str, int], set[str], list[Mapping[str, Any]]]:
    if (
        inventory.get("context_activated") is not False
        or lineage.get("mapped_context_approved") is not False
        or hints.get("approved_for_context_activation") is not False
        or hints.get("approved_for_financial_sql") is not False
        or manifest.get("approved_for_generation") is not False
        or manifest.get("approved_for_import") is not False
    ):
        _deny("SOURCE_APPROVAL_BOUNDARY_INVALID")

    source = inventory.get("source_collections")
    versions = manifest.get("versions")
    candidates = hints.get("candidates")
    if (
        not isinstance(source, list) or not source
        or not isinstance(versions, list) or not versions
        or not isinstance(candidates, list)
        or len(candidates) > MAX_SOURCE_CANDIDATES
    ):
        _deny("SOURCE_SHAPE_INVALID")

    counts: dict[str, int] = {}
    historical_only = 0
    for item in source:
        if not isinstance(item, Mapping):
            _deny("SOURCE_COLLECTION_INVALID")
        name, rows, usage = item.get("name"), item.get("rows"), item.get("use")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}", name)
            or name in counts or type(rows) is not int or rows < 0
            or usage not in ("EVALUATION_ONLY", "CONTEXT_REVIEW_ONLY")
        ):
            _deny("SOURCE_COLLECTION_INVALID")
        counts[name] = rows
        if usage == "EVALUATION_ONLY":
            historical_only += rows
    if not historical_only or inventory.get("sql_patterns_classification") != (
        "EVALUATION_ONLY_NOT_GENERATOR_INPUT"
    ):
        _deny("HISTORICAL_SQL_NOT_ISOLATED")
    if sum(counts.values()) != lineage.get("source_row_count"):
        _deny("SOURCE_ROW_COUNT_MISMATCH")

    known_versions: set[str] = set()
    by_collection: Counter[str] = Counter()
    for item in versions:
        if not isinstance(item, Mapping) or not _SHA256.fullmatch(
            str(item.get("source_version_sha256", ""))
        ):
            _deny("SOURCE_VERSION_INVALID")
        version = item["source_version_sha256"]
        if version in known_versions:
            _deny("SOURCE_VERSION_DUPLICATED")
        known_versions.add(version)
        row_counts = item.get("row_counts")
        if not isinstance(row_counts, Mapping):
            _deny("SOURCE_VERSION_ROWS_INVALID")
        for name, n in row_counts.items():
            if name not in counts or type(n) is not int or n < 0:
                _deny("SOURCE_VERSION_ROWS_INVALID")
            by_collection[name] += n
    # The sealed review packets exclude evaluation-only SQL patterns by design.
    for item in source:
        name = item["name"]
        if item["use"] == "CONTEXT_REVIEW_ONLY":
            if by_collection[name] != counts[name]:
                _deny("SOURCE_VERSION_COVERAGE_INCOMPLETE")
        elif by_collection[name] != 0:
            _deny("HISTORICAL_SQL_LEAK_IN_REVIEW_PACKETS")
    if (
        not isinstance(manifest.get("sql_pattern_rows_excluded"), int)
        or manifest["sql_pattern_rows_excluded"] != historical_only
    ):
        _deny("HISTORICAL_SQL_EXCLUSION_COUNT_INVALID")
    for candidate in candidates:
        if (
            not isinstance(candidate, Mapping)
            or candidate.get("source_version_sha256") not in known_versions
            or not _SHA256.fullmatch(
                str(candidate.get("source_record_sha256", ""))
            )
            or candidate.get("collection") not in counts
        ):
            _deny("CANDIDATE_PROVENANCE_INVALID")
    return counts, known_versions, candidates


def _table_or_column_mentioned(text: str, value: Any) -> bool:
    # Only literal identifier occurrence. No client-specific names or
    # synonyms are inferred. This does not prove use of a physical binding.
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        return False
    return re.search(
        r"(?<![A-Za-z0-9_])" + re.escape(value) + r"(?![A-Za-z0-9_])",
        text,
        re.IGNORECASE,
    ) is not None


def _reachable(start: set[int], edges: Mapping[int, set[int]]) -> set[int]:
    visited = set(start)
    pending = deque(sorted(start))
    while pending:
        for nxt in edges.get(pending.popleft(), set()):
            if nxt not in visited:
                visited.add(nxt)
                pending.append(nxt)
    return visited


def _legacy_query_kind(query: str) -> str:
    if not query.strip():
        return "EMPTY"
    if ("$" + "{") in query or "{{" in query:
        return "DYNAMIC_EXPRESSION"
    try:
        analysis = analyze_sql(query)
    except SqlAnalysisError:
        return "UNPARSED_REVIEW_REQUIRED"
    statement = analysis.get("statement_type")
    return (
        "READ_STATEMENT" if analysis.get("starts_with_read_keyword")
        else "NON_READ_STATEMENT" if isinstance(statement, str)
        else "UNCLASSIFIED_STATEMENT"
    )


def build_legacy_migration_inventory(
    *,
    workflow: Mapping[str, Any],
    workflow_source_sha256: str,
    inventory: Mapping[str, Any],
    lineage: Mapping[str, Any],
    hints: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Return an exhaustively indexed but financially UNAPPROVED crosswalk.

    Every n8n node and connection is represented. Raw workflow and G5
    business identifiers are never included in the returned document.
    """
    if not isinstance(workflow, Mapping) or not _SHA256.fullmatch(
        str(workflow_source_sha256)
    ):
        _deny("WORKFLOW_SOURCE_INVALID")
    if (
        workflow.get("active") is not True
        or not isinstance(workflow.get("versionId"), str)
        or not workflow["versionId"]
        or workflow.get("versionId") != workflow.get("activeVersionId")
    ):
        _deny("PUBLISHED_WORKFLOW_NOT_VERIFIED")
    raw_nodes, connections = workflow.get("nodes"), workflow.get("connections")
    if (
        not isinstance(raw_nodes, list)
        or not 1 <= len(raw_nodes) <= MAX_NODES
        or not isinstance(connections, Mapping)
    ):
        _deny("WORKFLOW_SHAPE_INVALID")
    source_counts, source_versions, candidates = _schema_guard(
        inventory=inventory, lineage=lineage, hints=hints, manifest=manifest,
    )
    names: dict[str, int] = {}
    for i, node in enumerate(raw_nodes, 1):
        if (
            not isinstance(node, Mapping)
            or not isinstance(node.get("name"), str)
            or not node["name"]
            or node["name"] in names
        ):
            _deny("WORKFLOW_NODE_IDENTITY_INVALID")
        names[node["name"]] = i

    edges: list[dict[str, int | str]] = []
    forward: dict[int, set[int]] = defaultdict(set)
    backward: dict[int, set[int]] = defaultdict(set)
    for source, ports in connections.items():
        if source not in names or not isinstance(ports, Mapping):
            _deny("WORKFLOW_CONNECTION_INVALID")
        for kind, lanes in ports.items():
            if not isinstance(kind, str) or not _EDGE_TYPE.fullmatch(kind):
                _deny("WORKFLOW_CONNECTION_TYPE_INVALID")
            if not isinstance(lanes, list):
                _deny("WORKFLOW_CONNECTION_INVALID")
            for port_index, destinations in enumerate(lanes):
                if not isinstance(destinations, list):
                    _deny("WORKFLOW_CONNECTION_INVALID")
                for destination in destinations:
                    if (
                        not isinstance(destination, Mapping)
                        or destination.get("node") not in names
                        or type(destination.get("index")) is not int
                        or not 0 <= destination["index"] < 1000
                    ):
                        _deny("WORKFLOW_DANGLING_CONNECTION")
                    frm, to = names[source], names[destination["node"]]
                    edges.append({
                        "from": frm, "to": to,
                        "source_port": port_index,
                        "target_port": destination["index"],
                        "connection_type": kind,
                    })
                    forward[frm].add(to)
                    backward[to].add(frm)
    digest_index = summarize_workflow(dict(workflow), workflow_source_sha256)
    entry = set()
    exit_nodes = set()
    nodes: list[dict[str, Any]] = []
    text_by_node: dict[int, str] = {}
    type_counts: Counter[str] = Counter()
    query_counts: Counter[str] = Counter()
    supported = {
        "code", "postgres", "httpRequest", "if",
        "respondToWebhook", "webhook",
    }
    for i, node in enumerate(raw_nodes, 1):
        params = node.get("parameters") or {}
        if not isinstance(params, Mapping):
            _deny("WORKFLOW_NODE_PARAMS_INVALID")
        fulltype = node.get("type")
        if not isinstance(fulltype, str):
            _deny("WORKFLOW_NODE_TYPE_INVALID")
        category = fulltype.split(".")[-1]
        category = category if category in supported else "other"
        type_counts[category] += 1
        if category == "webhook":
            entry.add(i)
        if category == "respondToWebhook":
            exit_nodes.add(i)
        code = params.get("jsCode")
        query = params.get("query")
        code = code if isinstance(code, str) else ""
        query = query if isinstance(query, str) else ""
        text_by_node[i] = code + "\n" + query
        query_kind = _legacy_query_kind(query) if category == "postgres" else None
        if query_kind:
            query_counts[query_kind] += 1
        node_identity = node.get("id") or node["name"]
        nodes.append({
            "ordinal": i,
            "node_identity_sha256": _hash_text(str(node_identity)),
            "node_type": category,
            "configuration_sha256": _hash_obj(params),
            "code_sha256": _hash_text(code) if code else None,
            "query_sha256": _hash_text(query) if query else None,
            "code_character_count": len(code),
            "query_character_count": len(query),
            "query_shape": query_kind,
            "incoming_node_ordinals": sorted(backward[i]),
            "outgoing_node_ordinals": sorted(forward[i]),
            "review_flags": digest_index["nodes"][i - 1].get(
                "review_flags", []
            ),
            "has_credential_reference": bool(node.get("credentials")),
            "candidate_source_record_links": [],
            "legacy_business_semantics_reviewed": False,
            "migration_classification": "REVIEW_REQUIRED",
        })
    reachable = _reachable(entry, forward)
    on_response_route = reachable & _reachable(exit_nodes, backward)
    matched_source = set()
    matched_versions = set()
    matched_nodes = set()
    reference_counts: Counter[str] = Counter()
    total_links = 0
    for candidate in candidates:
        ver = candidate["source_version_sha256"]
        source_sha = candidate["source_record_sha256"]
        for i in range(1, len(nodes) + 1):
            content = text_by_node[i]
            table_hit = _table_or_column_mentioned(
                content, candidate.get("source_table_ref")
            )
            column_hit = _table_or_column_mentioned(
                content, candidate.get("source_column_ref")
            )
            if not (table_hit or column_hit):
                continue
            total_links += 1
            if total_links > MAX_CROSSWALK_LINKS:
                _deny("CROSSWALK_SIZE_LIMIT")
            matched_nodes.add(i)
            matched_source.add((ver, source_sha))
            matched_versions.add(ver)
            label = (
                "TABLE_AND_COLUMN_TEXT" if table_hit and column_hit
                else "TABLE_TEXT" if table_hit else "COLUMN_TEXT"
            )
            reference_counts[label] += 1
            nodes[i - 1]["candidate_source_record_links"].append({
                "source_version_sha256": ver,
                "source_record_sha256": source_sha,
                "match_class": label,
                "business_equivalence": "NOT_ATTESTED",
            })
    expected_edges = sum(
        len(destinations)
        for channel_groups in connections.values()
        for lanes in channel_groups.values()
        for destinations in lanes
    )
    if len(nodes) != len(raw_nodes) or len(edges) != expected_edges:
        _deny("WORKFLOW_COVERAGE_INCOMPLETE")
    return {
        "contract": "n8n-g5-source-crosswalk-offline-v1",
        "status": "STRUCTURAL_CENSUS_COMPLETE_BUSINESS_REVIEW_PENDING",
        "source": {
            "workflow_export_sha256": workflow_source_sha256,
            "workflow_id_sha256": _hash_text(str(workflow.get("id", ""))),
            "workflow_published_version_equal_to_current": True,
            "product_route_certified": False,
            "g5_archive_sha256": lineage.get("source_archive_sha256"),
            "g5_semantic_version_count": len(source_versions),
            "g5_collection_row_counts": source_counts,
        },
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "node_types": dict(sorted(type_counts.items())),
            "postgres_query_shapes": dict(sorted(query_counts.items())),
            "nodes_reachable_from_webhook": len(reachable),
            "nodes_on_webhook_to_response_path": len(on_response_route),
            "nodes_not_reachable_from_webhook": len(nodes) - len(reachable),
            "g5_identifier_hints": len(candidates),
            "nodes_with_textual_reference": len(matched_nodes),
            "source_records_with_textual_reference": len(matched_source),
            "source_versions_with_textual_reference": len(matched_versions),
            "textual_reference_links": total_links,
            "reference_categories": dict(sorted(reference_counts.items())),
            "financial_business_rules_reviewed": 0,
        },
        "nodes": nodes,
        "edges": edges,
        "g5_versions": sorted(source_versions),
        "sql_patterns_evaluation_only": True,
        "no_raw_sql_prompts_names_or_credentials_in_result": True,
        "business_mapping_approved": False,
        "never_feed_generator_or_planner": True,
        "financial_sql_executed": False,
        "llm_calls": 0,
    }
