"""Conservative source-bound triage of legacy n8n JavaScript literals.

This *audit only* utility receives the privately held baseline of >10-character
literal occurrences. All 41 published Code bodies must match that baseline
before classification. The report never includes the literal or its raw hash.
Automatic categories are review *candidates*, not accounting attestations.
No SQL, n8n, LLM or benchmark is executed/read by this module.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import argparse
import json
from pathlib import Path
import re
import unicodedata
from typing import Any

from scripts.operations.legacy_functional_inventory_offline import (
    InventoryRejected, build_inventory, parse_roles,
)

# Financial review stems/legacy node roles are in versioned audit DATA,
# never embedded in Python or passed to the semantic runtime/generator.

_FUNCTION = re.compile(
    r"\b(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\("
)

_KIND_CODES = {"single": "s", "double": "d", "template": "t"}


def _fail(reason: str):
    raise InventoryRejected(reason)


def _fold(value: str) -> str:
    decomp=unicodedata.normalize("NFKD",value.casefold())
    return "".join(char for char in decomp if not unicodedata.combining(char))


def validate_review_policy(raw: object) -> dict[str, Any]:
    """Audit instructions versioned as data; never knowledge for generation."""
    expected = {
        "contract", "source_use", "business_review_nodes",
        "transitional_review_nodes", "review_stems", "human_financial_approval",
    }
    if not isinstance(raw,dict) or set(raw)!=expected or (
        raw["contract"]!="legacy-n8n-audit-review-signals-v1"
        or raw["source_use"]!="EVALUATION_ONLY_NEVER_GENERATOR"
        or raw["human_financial_approval"] is not False
    ):
        _fail("REVIEW_POLICY_INVALID")
    groups=[]
    for key in ("business_review_nodes","transitional_review_nodes"):
        nodes=raw[key]
        if (
            not isinstance(nodes,list)
            or not nodes
            or not all(type(n) is int and 1<=n<=68 for n in nodes)
            or len(set(nodes))!=len(nodes)
        ):
            _fail("REVIEW_POLICY_NODES_INVALID")
        groups.append(set(nodes))
    if groups[0]&groups[1]:
        _fail("REVIEW_POLICY_AMBIGUOUS")
    stems=raw["review_stems"]
    if (
        not isinstance(stems,list) or not 1<=len(stems)<=100
        or not all(
            isinstance(term,str) and 3<=len(term.strip())<=64
            and term.strip().isalpha()
            for term in stems
        )
    ):
        _fail("REVIEW_POLICY_STEMS_INVALID")
    folded=[_fold(term.strip()) for term in stems]
    if len(set(folded))!=len(folded):
        _fail("REVIEW_POLICY_STEMS_AMBIGUOUS")
    return {
        **raw,
        "review_stems": folded,
    }


def _candidate_for_line(
    node: int, line: str, nearest_function: str | None,
    policy: dict[str, Any],
) -> str:
    """Queue-only, never a factual or accounting rule classification."""
    stems=policy["review_stems"]
    business=set(policy["business_review_nodes"])
    transitional=set(policy["transitional_review_nodes"])
    full_text=_fold(line)
    function=_fold(nearest_function or "")
    if any(term in full_text for term in stems) or (
        node in business and function
        and any(term in function for term in stems)
    ):
        return "F"  # FORBIDDEN_CANDIDATE only
    if node in transitional:
        return "T"  # TRANSITIONAL_CANDIDATE
    if node not in business:
        return "S"  # STRUCTURAL_CANDIDATE
    return "U"  # manual review required


def classify_source_literals(
    workflow: object,
    baseline: dict[str, Any],
    roles: dict[int, tuple[str, str]],
    literal_inventory: dict[str, Any],
    review_policy: dict[str, Any],
) -> dict[str, Any]:
    policy=validate_review_policy(review_policy)
    crosswalk = build_inventory(workflow, roles, baseline)
    if isinstance(workflow, list):
        workflow = workflow[0]
    if (
        not isinstance(literal_inventory, dict)
        or literal_inventory.get("code_node_count") != 41
        or not isinstance(literal_inventory.get("nodes"), list)
        or len(literal_inventory["nodes"]) != 41
    ):
        _fail("LITERAL_SOURCE_INDEX_INVALID")
    if literal_inventory.get("counts") != {
        "literal_over_10_count": 1987,
        "long_template_over_500_count": 3,
        "string_literal_count": 3403,
    }:
        _fail("LITERAL_BASELINE_TOTAL_DRIFT")
    if not crosswalk["identities_configs_bodies_and_edges_matched_baseline"]:
        _fail("WORKFLOW_UNVERIFIED")
    indexed = {
        item["node_ordinal"]: item
        for item in literal_inventory["nodes"]
        if isinstance(item, dict) and type(item.get("node_ordinal")) is int
    }
    if len(indexed) != 41:
        _fail("LITERAL_ORDINAL_AMBIGUOUS")
    nodes = []
    candidates = []
    total = Counter()
    for original in crosswalk["nodes"]:
        if original["node_type"] != "code":
            continue
        ordinal = original["ordinal"]
        old = indexed.get(ordinal)
        if old is None:
            _fail("MISSING_LEGACY_CODE_INDEX")
        code = workflow["nodes"][ordinal-1].get("parameters",{}).get("jsCode")
        if not isinstance(code, str) or old.get("code_sha256") != sha256(code.encode()).hexdigest():
            _fail("SOURCE_JS_DRIFT")
        lines = code.splitlines()
        if not isinstance(old.get("literal_hash_and_lines"), list):
            _fail("LITERAL_ANCHORS_INVALID")
        if (
            old.get("line_count") != code.count("\n") + 1
            or old.get("literal_over_10_count") != len(old["literal_hash_and_lines"])
            or type(old.get("string_literal_count")) is not int
            or old["string_literal_count"] < old["literal_over_10_count"]
        ):
            _fail("LITERAL_NODE_COUNT_DRIFT")
        functions = []
        for line_no, content in enumerate(lines, 1):
            m = _FUNCTION.search(content)
            if m:
                functions.append((line_no, m.group(1)))
        kinds = Counter()
        risk = Counter()
        anchored_lines = set()
        for position, item in enumerate(old["literal_hash_and_lines"], 1):
            line_no = item.get("line")
            kind = item.get("kind")
            old_hash = item.get("sha256")
            if (
                type(line_no) is not int
                or not 1 <= line_no <= len(lines)
                or kind not in _KIND_CODES
                or not isinstance(old_hash,str)
                or not re.fullmatch("[0-9a-f]{64}",old_hash)
            ):
                _fail("LITERAL_ANCHOR_UNSAFE")
            nearest = next((name for start,name in reversed(functions) if start <= line_no),None)
            category = _candidate_for_line(ordinal, lines[line_no-1], nearest, policy)
            # Stable positional indices point to the privately held literal
            # index; literal values or their hashes are NEVER public.
            candidates.append([ordinal,position,line_no,_KIND_CODES[kind],category])
            risk[category] += 1
            kinds[kind] += 1
            anchored_lines.add(line_no)
        short_count = old["string_literal_count"]-old["literal_over_10_count"]
        total.update(risk)
        total["SHORT_UNANCHORED"] += short_count
        nodes.append({
            "ordinal":ordinal,
            "code_sha256":old["code_sha256"],
            "total_literal_count":old["string_literal_count"],
            "long_anchored_count":len(old["literal_hash_and_lines"]),
            "short_unanchored_count":short_count,
            "line_anchors":len(anchored_lines),
            "candidate_counts":dict(sorted(risk.items())),
            "status":"AUTOMATIC_SOURCE_TRIAGE_NOT_SEMANTICALLY_APPROVED",
        })
    if (
        len(nodes)!=41
        or len(candidates)!=1987
        or sum(n["total_literal_count"] for n in nodes)!=3403
        or sum(n["short_unanchored_count"] for n in nodes)!=1416
    ):
        _fail("LITERAL_COVERAGE_INCOMPLETE")
    return {
        "contract":"legacy-n8n-long-literal-triage-v1",
        "status":"ALL_LONG_LITERAL_ANCHORS_TRIAGED_AS_CANDIDATES",
        "source":"PUBLISHED_WORKFLOW_MATCHED_PRIVATE_BASELINE",
        "review_policy_sha256": sha256(json.dumps(
            review_policy,ensure_ascii=True,sort_keys=True,separators=(",",":")
        ).encode()).hexdigest(),
        "code_nodes":41,
        "all_literal_occurrences":3403,
        "long_literal_occurrences_anchored":1987,
        "short_literal_occurrences_unanchored":1416,
        "candidate_totals":dict(sorted(total.items())),
        "classification_labels":{
            "F":"FORBIDDEN_CANDIDATE_NEEDS_ACCOUNTING_REVIEW",
            "T":"TRANSITIONAL_CANDIDATE_REVIEW_REQUIRED",
            "S":"STRUCTURAL_CANDIDATE_REVIEW_REQUIRED",
            "U":"UNRESOLVED_MANUAL_REVIEW",
            "SHORT_UNANCHORED":"SHORT_LITERAL_NOT_IN_PRIOR_INDIVIDUAL_INDEX",
        },
        "raw_literals_published":False,
        "literal_content_hashes_published":False,
        "code_or_sql_copied_into_runtime":False,
        "financial_meaning_approved":False,
        "benchmark_accessed":False,
        "source_sql_executed":False,
        "nodes":nodes,
        "candidate_ledger":candidates,
    }


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--published-workflow",type=Path,required=True)
    p.add_argument("--baseline",type=Path,required=True)
    p.add_argument("--roles-md",type=Path,required=True)
    p.add_argument("--literal-index",type=Path,required=True)
    p.add_argument("--review-policy",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    x=p.parse_args()
    if x.out.exists() or not x.out.parent.is_dir():
        _fail("OUTPUT_ALREADY_PRESENT_OR_PARENT_MISSING")
    data=classify_source_literals(
        json.loads(x.published_workflow.read_text(encoding="utf-8")),
        json.loads(x.baseline.read_text(encoding="utf-8")),
        parse_roles(x.roles_md.read_text(encoding="utf-8")),
        json.loads(x.literal_index.read_text(encoding="utf-8")),
        json.loads(x.review_policy.read_text(encoding="utf-8")),
    )
    x.out.write_text(json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=True)+"\n")
    print("LONG_LITERAL_SOURCE_TRIAGE=COMPLETE_CANDIDATES_ONLY")
    print("CODE_NODES="+str(data["code_nodes"]))
    print("ANCHORED_LONG="+str(data["long_literal_occurrences_anchored"]))
    print("SHORT_UNANCHORED="+str(data["short_literal_occurrences_unanchored"]))
    print("CANDIDATE_TOTALS="+str(data["candidate_totals"]))
    print("FINANCIAL_SEMANTICS_APPROVED=false")


if __name__=="__main__":
    main()
