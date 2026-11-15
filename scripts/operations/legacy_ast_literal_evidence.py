"""Read-only structural verification of an AST-only n8n literal inventory.

This consumes only sanitized immutable source fingerprints and positional
metadata, never JS code or literal values. The original 3403-literal
heuristic is kept as a baseline comparator, not treated as proof that 3403
is the true number of syntactic string occurrences.
"""
from __future__ import annotations
from collections import Counter
from collections.abc import Mapping
from typing import Any


class AstLiteralEvidenceRejected(ValueError):
    pass


def verify_ast_literal_evidence(
    raw: object,
    previous: object,
) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or not isinstance(previous, Mapping):
        raise AstLiteralEvidenceRejected("MANIFEST_INVALID")
    if (
        raw.get("contract") != "legacy-n8n-ast-all-literal-source-inventory-v1"
        or raw.get("status") != "ALL_AST_LITERALS_PINNED_CLASSIFICATION_CANDIDATES_ONLY"
        or raw.get("parser") != "acorn"
        or not isinstance(raw.get("parser_version"), str)
        or len(raw["parser_version"]) > 35
        or raw.get("code_nodes") != 41
        or raw.get("legacy_original_literal_count") != 3403
        or raw.get("legacy_long_anchor_count") != 1987
        or raw.get("legacy_short_unanchored_count") != 1416
    ):
        raise AstLiteralEvidenceRejected("MANIFEST_PROVENANCE_INVALID")
    for key in (
        "raw_literal_values_published", "original_literal_hashes_published",
        "financial_semantics_approved", "benchmark_accessed",
        "node_code_executed", "customer_financial_sql_executed",
    ):
        if raw.get(key) is not False:
            raise AstLiteralEvidenceRejected("PRIVACY_OR_APPROVAL_INVALID")
    for key in ("published_workflow_sha256", "review_policy_sha256"):
        value = raw.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(
            c not in "0123456789abcdef" for c in value
        ):
            raise AstLiteralEvidenceRejected("UNBOUND_SOURCE_FINGERPRINT")
    nodes = raw.get("nodes")
    old = previous.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 41 or not isinstance(old, list) or len(old) != 41:
        raise AstLiteralEvidenceRejected("NODE_COUNT_INVALID")
    old_by_ordinal = {node["ordinal"]: node for node in old}
    if len({item.get("ordinal") for item in nodes}) != 41:
        raise AstLiteralEvidenceRejected("NEW_SOURCE_AMBIGUOUS")
    if len(old_by_ordinal) != 41:
        raise AstLiteralEvidenceRejected("OLD_SOURCE_AMBIGUOUS")
    total = 0
    sizes = Counter()
    categories = Counter()
    changed = []
    for node in nodes:
        if not isinstance(node, Mapping):
            raise AstLiteralEvidenceRejected("NODE_INVALID")
        ordinal = node.get("ordinal")
        legacy = old_by_ordinal.get(ordinal)
        if not isinstance(legacy, dict) or (
            node.get("code_sha256") != legacy.get("code_sha256")
            or node.get("previous_count") != legacy.get("total_literal_count")
        ):
            raise AstLiteralEvidenceRejected("SOURCE_CODE_NOT_MATCHED")
        count = node.get("syntax_literal_count")
        limit = node.get("source_line_count")
        if (
            type(count) is not int
            or type(limit) is not int
            or count < 0 or limit < 1
            or node.get("delta_from_legacy") != count - node["previous_count"]
            or not isinstance(node.get("entries"), list)
            or len(node["entries"]) != count
        ):
            raise AstLiteralEvidenceRejected("NODE_COUNT_MISMATCH")
        last_offset = -1
        local_size = Counter()
        local_categories = Counter()
        for entry in node["entries"]:
            if (
                not isinstance(entry, list)
                or len(entry) != 6
                or type(entry[0]) is not int
                or type(entry[1]) is not int
                or type(entry[2]) is not int
                or entry[0] <= last_offset
                or entry[1] < 1 or entry[1] > limit
                or entry[2] < 0
                or entry[3] not in ("s", "t")
                or entry[4] not in ("q", "l")
                or entry[5] not in ("F", "T", "S", "U")
            ):
                raise AstLiteralEvidenceRejected("POSITIONAL_SOURCE_INVALID")
            last_offset = entry[0]
            local_size[entry[4]] += 1
            local_categories[entry[5]] += 1
        if (
            node.get("short_syntax_literals") != local_size["q"]
            or node.get("long_syntax_literals") != local_size["l"]
            or node.get("candidate_counts") != {
                c: local_categories[c] for c in "FTSU"
            }
        ):
            raise AstLiteralEvidenceRejected("CLASSIFICATION_COUNT_DRIFT")
        sizes.update(local_size)
        categories.update(local_categories)
        total += count
        if node["delta_from_legacy"]:
            changed.append(ordinal)
    expected_old_total = sum(node["total_literal_count"] for node in old)
    if (
        expected_old_total != 3403
        or total != raw.get("syntax_literal_total")
        or raw.get("short_syntax_literals") != sizes["q"]
        or raw.get("long_syntax_literals") != sizes["l"]
        or total - expected_old_total != raw.get("delta_from_legacy")
        or raw.get("candidate_counts") != {c: categories[c] for c in "FTSU"}
        or sizes["q"] + sizes["l"] != total
    ):
        raise AstLiteralEvidenceRejected("TOTALS_MISMATCH")
    return {
        "code_nodes": len(nodes),
        "ast_syntax_literals": total,
        "ast_short": sizes["q"],
        "ast_long": sizes["l"],
        "delta_from_legacy": total - expected_old_total,
        "changed_ordinal_count": len(changed),
        "status": "SOURCE_ANCHORED_CANDIDATE_TRIAGE_ONLY",
    }
