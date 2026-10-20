"""Offline contract tests for the separate n8n Shadow orchestrator.

No n8n calls, SQL execution, provider usage or credential access.
"""
from __future__ import annotations
import json
import pathlib
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
WORKFLOW = ROOT / "scripts" / "n8n" / "parallel_langgraph_shadow_v1.workflow.json"

def test_parallel_n8n_workflow_contract() -> None:
    flow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    assert flow["active"] is False
    assert flow["settings"]["saveDataSuccessExecution"] == "none"
    assert flow["settings"]["saveDataErrorExecution"] == "none"
    assert flow["pinData"] == {}
    nodes = flow["nodes"]
    assert len(nodes) == 7
    by_name = {node["name"]: node for node in nodes}
    assert len(by_name) == len(nodes)
    assert len({node["id"] for node in nodes}) == len(nodes)
    webhook = by_name["Webhook - Parallel Shadow"]
    assert webhook["parameters"]["authentication"] == "headerAuth"
    assert webhook["parameters"]["responseMode"] == "responseNode"
    assert webhook["parameters"]["httpMethod"] == "POST"
    assert not any("credentials" in node for node in nodes)
    for node in nodes:
        assert node["type"] in {
            "n8n-nodes-base.webhook", "n8n-nodes-base.code",
            "n8n-nodes-base.respondToWebhook", "n8n-nodes-base.httpRequest",
        }
    assert all("postgres" not in node["type"].lower() for node in nodes)
    expected = [
        "Webhook - Parallel Shadow",
        "Validate Shadow Envelope",
        "Acknowledge Shadow Receipt",
        "Call LangGraph Shadow",
        "Validate LangGraph Response",
        "Read Correlated Evidence",
        "Assert Shadow Evidence",
    ]
    for source, destination in zip(expected, expected[1:]):
        edges = flow["connections"][source]["main"][0]
        assert len(edges) == 1 and edges[0]["node"] == destination
    assert set(flow["connections"]) == set(expected[:-1])
    assert by_name["Acknowledge Shadow Receipt"]["parameters"]["options"]["responseCode"] == 202
    for name in ["Call LangGraph Shadow", "Read Correlated Evidence"]:
        item = by_name[name]
        assert item["parameters"]["genericAuthType"] == "httpHeaderAuth"
        assert "LANGGRAPH_SHADOW_INTERNAL_BASE_URL" in item["parameters"]["url"]
        assert "generativelanguage.googleapis.com" not in json.dumps(item)
    prepare = by_name["Validate Shadow Envelope"]["parameters"]["jsCode"]
    assert "generate" in prepare and "execute_approved" in prepare
    assert "approved_sql" in prepare and "correlation_metadata" in prepare
    assert "SHADOW_ENVELOPE" in prepare
    assert "INTERNAL_GENERATE_QUESTION_REQUIRED" not in prepare
    assert "sql_template" not in prepare.lower()
    assert "SELECT " not in prepare.upper()
    assert "UPDATE " not in prepare.upper()
    assert by_name["Call LangGraph Shadow"]["parameters"]["options"]["response"]["response"]["neverError"] is True
    assert "shadow_record_id" in by_name["Assert Shadow Evidence"]["parameters"]["jsCode"]
    assert not any(node["type"].endswith("manualTrigger") for node in nodes)
    # No customer-specific semantics, exact finance identifiers, secrets or test answers.
    source = json.dumps(flow, ensure_ascii=False).lower()
    for forbidden in ("grupo_dre", "dev_lakehouse", "imd", "versão 2",
                      "business_question_examples", "gemini-2.5", "api_key",
                      "n8n-shadow-probe", "sql-infodive", "gold_lancamentos"):
        assert forbidden not in source, forbidden
    assert "executesql" not in source and "executequery" not in source

def test_embedded_javascript_syntax() -> None:
    node_binary = shutil.which("node")
    if not node_binary:
        return
    flow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    for node in flow["nodes"]:
        code = node["parameters"].get("jsCode")
        if code is None:
            continue
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "test.js"
            path.write_text(code, encoding="utf-8")
            result = subprocess.run(
                [node_binary, "--check", str(path)],
                capture_output=True, text=True, timeout=8,
            )
            assert result.returncode == 0, node["name"]

if __name__ == "__main__":
    test_parallel_n8n_workflow_contract()
    test_embedded_javascript_syntax()
    print("N8N_PARALLEL_SHADOW_OFFLINE=PASS")
