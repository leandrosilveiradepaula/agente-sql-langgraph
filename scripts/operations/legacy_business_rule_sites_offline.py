"""Bounded, source-anchored inventory of legacy financial rule debt.

Audit-only: never imports business definitions into the product, graph or
generator. All source expressions (including SQL, prompts and literal values)
remain private. A matching anchor proves a code site, NOT accounting meaning.
This source inventory is independent of the 63-case evaluation corpus.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from scripts.operations.legacy_functional_inventory_offline import (
    InventoryRejected,
    build_inventory,
    parse_roles,
)


# Explicit code-site evidence from the currently published workflow, not
# runtime client logic. Each item: ordinal, starting source line, match token,
# risk, migration destination. Value snippets never leave the private auditor.
_ANCHORS: tuple[tuple[int, int, str, str, str], ...] = (
    (5, 7, "ec134a1a1a29ae075c084fa9de56a2497c9dcce34c3ae909f2cf1cbb7fa69704", "TRANSITIONAL_VERSION_SELECTOR", "TENANT_VERSION_CONFIGURATION"),
    (5, 17, "ec134a1a1a29ae075c084fa9de56a2497c9dcce34c3ae909f2cf1cbb7fa69704", "TRANSITIONAL_VERSION_SELECTOR", "TENANT_VERSION_CONFIGURATION"),
    (5, 27, "ec134a1a1a29ae075c084fa9de56a2497c9dcce34c3ae909f2cf1cbb7fa69704", "TRANSITIONAL_VERSION_SELECTOR", "TENANT_VERSION_CONFIGURATION"),
    (5, 37, "ec134a1a1a29ae075c084fa9de56a2497c9dcce34c3ae909f2cf1cbb7fa69704", "TRANSITIONAL_VERSION_SELECTOR", "TENANT_VERSION_CONFIGURATION"),
    (5, 47, "ec134a1a1a29ae075c084fa9de56a2497c9dcce34c3ae909f2cf1cbb7fa69704", "TRANSITIONAL_VERSION_SELECTOR", "TENANT_VERSION_CONFIGURATION"),
    (6, 393, "68b720ac0fbc33f2f94e21e25d4035383b09e0eff409e3aae88f93ba3e242e57", "BUSINESS_METRIC_LEXICON", "APPROVED_METRIC_AND_ALIAS_CATALOG"),
    (6, 415, "24626982f932f53f18cdd1df9b97e15aaf3e1abe051a9245d26ede0ba312c339", "BUSINESS_INTENT_RESOLUTION", "APPROVED_INTENT_CATALOG"),
    (7, 28, "3c887b14378ae9195c66bcd56b591babcd00003850e4988bb3b1693e11acb92a", "LEGACY_PATTERN_CONSUMPTION", "EXCLUDE_HISTORICAL_SQL_FROM_GENERATOR"),
    (7, 41, "f2f54646c2658ebed57786a9fcc39a9d886d141e0b82a701ef810c2afe83e93e", "LEGACY_PATTERN_SELECTION", "EXCLUDE_HISTORICAL_SQL_FROM_GENERATOR"),
    (8, 588, "abb0ec6871bc5ea9d5daec0a3dc3880a78c669f131a51d3cecc9d1144e243c9f", "INLINE_FINANCIAL_RULE_SECTION", "APPROVED_TENANT_FINANCIAL_CATALOG"),
    (8, 649, "85d169c12b9fea331c009efbd22a9bfed0c4a08f4c6d2ed20535b7b4d18a2aa4", "INLINE_DERIVED_RATIO_DEFINITION", "APPROVED_RATIO_OF_SUMS_CONTEXT"),
    (8, 744, "1bb2b1f6024484ce332f9076e523cf62222b83ba846aedb1953195b029c016e2", "INLINE_BUDGET_COMPARISON", "APPROVED_METRIC_FORMULAS_AND_SIGN_RULES"),
    (15, 10, "f9a3059fcee43e6482386c8fbb354584e7d45f42bb07fea918096737acc47669", "TRANSITIONAL_AGENT_VERSION", "TENANT_VERSION_CONFIGURATION"),
    (19, 41, "91ed6dc3fa608adf5a862e3586c21a333e1b621866b90743ad40caf49ba51c87", "TRANSITIONAL_PROVIDER_VERSION", "CONFIGURABLE_LLM_PROVIDER"),
    (22, 853, "4c0093eda49678a9239766238bf4574a19576d9c015695dbac03e6d551e1f41c", "INLINE_PHYSICAL_SOURCE_BINDINGS", "APPROVED_PHYSICAL_AND_JOIN_CATALOG"),
    (22, 1054, "1409b364cee7c70de7b19f817a5ef3d57be7b74596389c229cf26e3970b9e80c", "MIXED_COMPARISON_CONTRACT", "GENERIC_PLANNER_AND_APPROVED_METRIC_CATALOG"),
    (22, 1073, "8d84f8117c5bb51295310b3d421e30250b9b01cd96e9658111e7d87edcbfebcd", "GENERIC_GRAIN_WITH_LITERAL_BINDINGS", "GENERIC_PLANNER_AND_APPROVED_GRAIN_CATALOG"),
    (22, 1105, "bcec001d5e381931ed71bda084a4b991864e2779f57ef8d955408e3cab1f238b", "INLINE_MANAGERIAL_RULES", "APPROVED_TENANT_FINANCIAL_CATALOG"),
    (22, 2030, "e5da44b3de42aef5a40dded3f9a8a635233606f46af6e61be2871ed91d294782", "INLINE_FINANCIAL_PLANNING", "GENERIC_PLANNER_AND_APPROVED_METRIC_CATALOG"),
    (23, 378, "9b142a0d9e1b7b689c9565b8ef096e3738b25b9b48c7ea3c8358becfea0ba959", "FIXED_METRIC_BINDINGS", "APPROVED_METRIC_CATALOG"),
    (32, 534, "37c232a9c2642394237ba2bb37402bc8a22c3ab4208a52c0cf4831039bfbe371", "BUSINESS_REPORT_DESCRIPTOR", "APPROVED_REPORT_SEMANTICS"),
    (32, 668, "4dae5bafb35c20de1b870f2b0f45e117e3bf5b7e6f732d08ae00d9283da52aa5", "BUSINESS_METRIC_LANGUAGE", "APPROVED_REPORT_SEMANTICS"),
    (54, 110, "c9ee678331c130ad0b68016858bc7ed86e3cf6664f3b0a716bc3bb1f8aa0936c", "FIXED_DIMENSION_LEXICON", "APPROVED_DIMENSION_AND_ALIAS_CATALOG"),
    (54, 184, "3ba20e822372583bab7672c9661e6b76991382bdc0fabd5b779f1043b65563f7", "FIXED_METRIC_LEXICON", "APPROVED_METRIC_AND_ALIAS_CATALOG"),
)


def _sha(data: str) -> str:
    return sha256(data.encode("utf-8")).hexdigest()


def inspect_anchor(
    lines: list[str], line_number: int, token: str,
    *, private_window: int = 3,
) -> dict[str, Any]:
    """Pin exact source SHA without storing a client identifier or literal."""
    if not isinstance(lines, list) or type(line_number) is not int:
        raise InventoryRejected("RULE_SITE_SOURCE_INVALID")
    if not 1 <= line_number <= len(lines) or not isinstance(token,str) or len(token)!=64:
        raise InventoryRejected("RULE_SITE_OUT_OF_BOUNDS")
    if _sha(lines[line_number-1]) != token:
        raise InventoryRejected("RULE_SITE_ANCHOR_DRIFT")
    start = max(0, line_number - private_window - 1)
    end = min(len(lines), line_number + private_window)
    window = "\n".join(lines[start:end])
    return {
        "start_line": line_number,
        "window_start": start + 1,
        "window_end": end,
        "line_sha256": _sha(lines[line_number - 1]),
        "window_sha256": _sha(window),
    }


def build_rule_site_inventory(
    raw: object,
    roles: dict[int, tuple[str, str]],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    verified = build_inventory(raw, roles, baseline)
    if isinstance(raw, list):
        raw = raw[0]
    code_nodes = {
        n["ordinal"]: n for n in verified["nodes"] if n["node_type"] == "code"
    }
    if len(code_nodes) != 41 or len(_ANCHORS) < 20:
        raise InventoryRejected("RULE_SITE_COVERAGE_INVALID")
    nodes = raw["nodes"]
    sites = []
    for index, line_number, anchor, reason, destination in _ANCHORS:
        if index != 5 and index not in code_nodes:
            raise InventoryRejected("RULE_SITE_NODE_NOT_CODE")
        node = nodes[index - 1]
        source = node["parameters"].get(
            "query" if index == 5 else "jsCode"
        )
        if not isinstance(source, str):
            raise InventoryRejected("RULE_SITE_SOURCE_MISSING")
        found = inspect_anchor(source.splitlines(), line_number, anchor)
        sites.append({
            "node_ordinal": index,
            **found,
            "source_type": "QUERY" if index == 5 else "NODE_JS",
            "site_kind": reason,
            "migration_target": destination,
            "status": "LEGACY_SOURCE_CONFIRMED_CONTEXT_NOT_ACCOUNTING_ATTESTED",
            "financial_value_imported": False,
        })
    # Every Code node is represented, not automatically financially approved.
    grouped = Counter(site["node_ordinal"] for site in sites)
    coverage = [
        {
            "node_ordinal": ordinal,
            "code_sha256": node["code_sha256"],
            "line_count": len(nodes[ordinal - 1]["parameters"]["jsCode"].splitlines()),
            "source_anchors_reviewed": grouped[ordinal],
            "review_status": (
                "KNOWN_FINANCIAL_OR_MIXED_RULE_SITES_PINNED"
                if grouped[ordinal] else "CODE_SOURCE_INDEXED_NO_RULE_ATTESTATION"
            ),
        }
        for ordinal, node in sorted(code_nodes.items())
    ]
    return {
        "contract": "legacy-financial-rule-sites-offline-v1",
        "status": "SITES_PINNED_FINANCIAL_CLASSIFICATION_PARTIAL",
        "source_nodes": 68,
        "code_nodes_indexed": len(coverage),
        "postgres_nodes_indexed": 11,
        "exact_config_and_body_match": True,
        "unique_pinned_sites": len(sites),
        "nodes_with_pinned_sites": len(grouped),
        "source_review": "STATIC_PUBLISHED_WORKFLOW",
        "accounting_approval": False,
        "raw_financial_literals_exported": False,
        "benchmark_accessed": False,
        "source_sql_executed": False,
        "runtime_changed": False,
        "sites": sites,
        "code_coverage": coverage,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--published-workflow", type=Path, required=True)
    parser.add_argument("--roles-md", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--private-report", type=Path, required=True)
    args = parser.parse_args()
    if args.private_report.exists() or not args.private_report.parent.is_dir():
        raise InventoryRejected("PRIVATE_REPORT_PATH_INVALID")
    result = build_rule_site_inventory(
        json.loads(args.published_workflow.read_text(encoding="utf-8")),
        parse_roles(args.roles_md.read_text(encoding="utf-8")),
        json.loads(args.baseline.read_text(encoding="utf-8")),
    )
    args.private_report.write_text(
        json.dumps(result, sort_keys=True, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print("BUSINESS_RULE_SITE_INVENTORY=SOURCE_PINNED")
    print("CODE_NODES_INDEXED="+str(result["code_nodes_indexed"]))
    print("PINNED_SITES="+str(result["unique_pinned_sites"]))
    print("NODES_WITH_SITES="+str(result["nodes_with_pinned_sites"]))
    print("PRIVATE_REPORT_SHA256="+sha256(args.private_report.read_bytes()).hexdigest())
    print("FINANCIAL_SEMANTICS_APPROVED=false")


if __name__ == "__main__":
    main()
