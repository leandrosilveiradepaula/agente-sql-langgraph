from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / "scripts/n8n/shadow_correlation_manual_test.workflow.json"


def test_isolated_workflow_contract():
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    nodes = workflow["nodes"]
    assert workflow["active"] is False
    assert workflow["settings"]["saveDataSuccessExecution"] == "none"
    assert workflow["settings"]["saveDataErrorExecution"] == "none"
    assert len(nodes) == 6
    assert sum(node["type"] == "n8n-nodes-base.manualTrigger" for node in nodes) == 1
    assert all(
        node["type"] != "n8n-nodes-base.webhook"
        for node in nodes
    )
    assert all("credentials" not in node for node in nodes)
    assert all("pinData" not in node for node in nodes)

    by_name = {node["name"]: node for node in nodes}
    assert len(by_name) == len(nodes)
    assert len(workflow["connections"]) == len(nodes) - 1
    visited = [nodes[0]["name"]]
    while visited[-1] in workflow["connections"]:
        destinations = workflow["connections"][visited[-1]]["main"]
        assert len(destinations) == 1 and len(destinations[0]) == 1
        visited.append(destinations[0][0]["node"])
    assert len(visited) == len(nodes)
    assert len(set(visited)) == len(nodes)

    code = by_name["Build Synthetic Request"]["parameters"]["jsCode"]
    assert "question: ''" in code
    assert "official_flow_modified: false" in code

    http_nodes = [node for node in nodes if node["type"] == "n8n-nodes-base.httpRequest"]
    assert len(http_nodes) == 2
    for node in http_nodes:
        p = node["parameters"]
        assert p["authentication"] == "genericCredentialType"
        assert p["genericAuthType"] == "httpHeaderAuth"
        assert p["options"]["response"]["response"]["neverError"] is True
        assert p["options"]["response"]["response"]["fullResponse"] is True
        assert p["options"]["timeout"] == 10000

    assert http_nodes[0]["parameters"]["method"] == "POST"
    assert http_nodes[0]["parameters"]["url"].endswith("/v1/internal/sql-agent/generate")
    assert http_nodes[1]["parameters"]["method"] == "GET"
    assert "/v1/internal/agent-runs/" in http_nodes[1]["parameters"]["url"]
    assert "statusCode !== 422" in by_name["Assert Pre-LLM Rejection"]["parameters"]["jsCode"]
    assert "run_id === expected.run_id" in by_name["Assert Evidence Correlation"]["parameters"]["jsCode"]

    rendered = json.dumps(workflow, ensure_ascii=False).casefold()
    for secret_or_real_execution in (
        '"authorization"',
        '"apikey"',
        '"password"',
        '"token"',
        "execute-approved-shadow",
        "langgraph_allow_real_sql_execution=true",
        "n8n-nodes-base.scheduletrigger",
        "n8n-nodes-base.webhook",
    ):
        assert secret_or_real_execution not in rendered


if __name__ == "__main__":
    test_isolated_workflow_contract()
    print("ISOLATED_N8N_SHADOW_WORKFLOW=PASS")
