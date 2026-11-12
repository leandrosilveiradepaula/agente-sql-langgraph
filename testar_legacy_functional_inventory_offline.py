"""Offline invariant tests for the full static n8n review without private data."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from scripts.operations.legacy_functional_inventory_offline import (
    InventoryRejected, build_inventory, digest, digest_obj, parse_roles, render_markdown,
)

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "docs/audits/legacy-n8n-functional-inventory-20261112.json"


def _fake():
    nodes = [
        {"name": "fixture-entrance", "id": "node-a",
         "type": "n8n-nodes-base.webhook", "parameters": {"path": "PRIVATE_NEVER_COPY"}},
        {"name": "fixture-transform", "id": "node-b",
         "type": "n8n-nodes-base.code",
         "parameters": {"jsCode": 'return [{"json":{"value":"PRIVATE_NEVER_COPY"}}]'}},
        {"name": "fixture-response", "id": "node-c",
         "type": "n8n-nodes-base.respondToWebhook", "parameters": {}},
    ]
    workflow = {
        "active": True, "versionId": "published", "activeVersionId": "published",
        "id": "fixture-secret-id", "nodes": nodes,
        "connections": {
            "fixture-entrance": {"main": [[{"node": "fixture-transform", "index": 0}]]},
            "fixture-transform": {"main": [[{"node": "fixture-response", "index": 0}]]},
        },
    }
    baseline = {
        "nodes": [
            {
                "ordinal": i, "node_type": n["type"].split(".")[-1],
                "node_identity_sha256": digest(n["id"]),
                "configuration_sha256": digest_obj(n["parameters"]),
                "code_sha256": digest(n["parameters"]["jsCode"]) if "jsCode" in n["parameters"] else None,
                "query_sha256": None,
            }
            for i, n in enumerate(nodes, 1)
        ],
        "edges": [
            {"from": 1, "to": 2, "connection_type": "main", "source_port": 0, "target_port": 0},
            {"from": 2, "to": 3, "connection_type": "main", "source_port": 0, "target_port": 0},
        ],
    }
    roles = {1: ("Request intake", "n8n"), 2: ("Sanitize context", "logic"), 3: ("Respond", "n8n")}
    return workflow, roles, baseline


def _must_reject(w, r, b, message):
    try:
        build_inventory(w, r, b, expected_nodes=3, expected_edges=2)
    except InventoryRejected:
        return
    raise AssertionError(message)


def test_valid_three_node_synthetic_and_no_sensitive_output():
    w, roles, baseline = _fake()
    result = build_inventory(w, roles, baseline, expected_nodes=3, expected_edges=2)
    assert result["node_count"] == 3
    assert result["edge_count"] == 2
    assert result["reachable_count"] == 3
    assert result["source_sql_executed"] is False
    assert "PRIVATE_NEVER_COPY" not in json.dumps(result)
    assert "fixture-secret-id" not in json.dumps(result)
    assert "fixture-entrance" not in json.dumps(result)
    assert result["nodes"][1]["code_sha256"]


def test_parameter_or_code_mutation_refused():
    w, roles, baseline = _fake()
    w["nodes"][1]["parameters"]["jsCode"] += " // changed"
    _must_reject(w, roles, baseline, "Code changed without review")


def test_different_topology_refused_even_when_nodes_match():
    w, roles, baseline = _fake()
    w["connections"]["fixture-entrance"]["main"][0][0]["node"] = "fixture-response"
    _must_reject(w, roles, baseline, "Edges changed without review")


def test_draft_or_unpublished_refused():
    w, roles, baseline = _fake()
    w["activeVersionId"] = "unpublished"
    _must_reject(w, roles, baseline, "Draft accepted")
    w, roles, baseline = _fake()
    w["active"] = False
    _must_reject(w, roles, baseline, "Inactive accepted")


def test_missing_role_and_duplicate_identity_refused():
    w, roles, baseline = _fake()
    del roles[2]
    _must_reject(w, roles, baseline, "Missing role accepted")
    w, roles, baseline = _fake()
    w["nodes"][1]["id"] = w["nodes"][0]["id"]
    _must_reject(w, roles, baseline, "Duplicate node identity accepted")


def test_role_parser_requires_exact_index_coverage():
    valid = "| 1 | Intake | n8n |\n| 2 | Transform | LangGraph |\n| 3 | Response | n8n |\n"
    assert len(parse_roles(valid, count=3)) == 3
    for bad in (valid.replace("| 3 |", "| 2 |"), valid.replace("| 2 |", "| 4 |")):
        try:
            parse_roles(bad, count=3)
        except InventoryRejected:
            pass
        else:
            raise AssertionError("Role map mismatch accepted")


def test_public_review_has_68_nodes_and_all_ports():
    report = json.loads(PUBLIC.read_text())
    import hashlib
    role_text = (ROOT / "docs/audits/LEGACY-N8N-PRODUCT-FUNCTIONAL-MAP-20261111.md").read_text(encoding="utf-8")
    assert report["role_source_sha256"] == hashlib.sha256(role_text.encode("utf-8")).hexdigest()
    assert report["node_count"] == 68
    assert report["edge_count"] == 78
    assert report["identities_configs_bodies_and_edges_matched_baseline"] is True
    assert report["source_sql_executed"] is False
    assert report["financial_meaning_approved"] is False
    assert {n["ordinal"] for n in report["nodes"]} == set(range(1, 69))
    assert len([n for n in report["nodes"] if n["node_type"] == "code"]) == 41
    assert len([n for n in report["nodes"] if n["node_type"] == "if"]) == 10
    assert len([n for n in report["nodes"] if n["node_type"] == "postgres"]) == 11
    assert len([n for n in report["nodes"] if n["node_type"] == "httpRequest"]) == 2
    assert len([n for n in report["nodes"] if n["source_reachability"] == "NOT_REACHABLE_FROM_WEBHOOK"]) == 8
    assert report["technical_gates_not_human_approval"] == [25, 29, 62]
    assert len({(e["from"],e["to"],e["source_port"],e["target_port"]) for e in report["edges"]}) == 78
    assert report["classes"] == {"FORBIDDEN": 10, "STRUCTURAL": 25, "TRANSITIONAL": 33}
    for node in report["nodes"]:
        assert node["functional_role"] and node["proposed_owner"]
        assert len(node["node_id_sha256"]) == 64
        assert len(node["parameter_sha256"]) == 64
        assert node["review_scope"] == "SOURCE_BOUND_STATIC_FUNCTIONAL_INVENTORY"
    rendered = render_markdown(report)
    assert rendered.count("| CODE_TRANSFORM |") >= 1
    assert rendered.count(" | STRUCTURAL |") == 0  # Uses short visual classes
    assert "PRIVATE_NEVER_COPY" not in rendered


def main():
    count = 0
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            count += 1
            print("PASS", name)
    print("TOTAL_TESTS", count)


if __name__ == "__main__":
    main()
