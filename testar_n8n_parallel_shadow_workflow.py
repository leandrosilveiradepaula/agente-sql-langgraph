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


def test_workflow_expressions_and_payload_contracts() -> None:
    """Execute all n8n expressions and Code nodes with synthetic inputs only."""
    node = shutil.which("node")
    if not node:
        raise AssertionError("Node.js is required for expression tests")

    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    javascript = r"""
const assert = require("node:assert/strict");
const flow = JSON.parse(process.argv[1]);
const nodes = Object.fromEntries(flow.nodes.map(n => [n.name, n]));
const requestId = "request-synthetic-1";
const agentRunId = "agent-synthetic-1";
const question = "Generic analysis request, no financial values";
const env = {LANGGRAPH_SHADOW_INTERNAL_BASE_URL: "http://shadow-internal:8000///"};
const payload = {
  contract_version: "1",
  agent_run_id: agentRunId,
  question,
  principal: {id: "user-test", profile: "runtime_validation"},
  correlation_metadata: {
    source: "nextjs_bff", event: "generate", route: "/api/generate-sql",
    request_id: requestId, timestamp: "2026-10-20T00:00:00.000Z"
  }
};
function runCode(name, input, previous = {}) {
  const code = nodes[name].parameters.jsCode;
  const localInput = {first() { return {json: input}; }};
  const selectNode = key => ({
    first() {
      if (!(key in previous)) throw Error("Missing fixture for " + key);
      return {json: previous[key]};
    }
  });
  const out = new Function("$input", "$", code)(localInput, selectNode);
  assert.equal(out.length, 1);
  return out[0].json;
}
function expression(name, field, item) {
  const code = nodes[name].parameters[field];
  assert.ok(code.startsWith("={{") && code.endsWith("}}"));
  return new Function("$env", "$json", "return (" + code.slice(3, -2) + ");")(env, item);
}
const normalized = runCode("Validate Shadow Envelope", {body: payload});
assert.equal(normalized.agent_run_id, agentRunId);
assert.equal(normalized.shadow_request.question, question);
assert.equal(normalized.shadow_request.correlation_metadata.request_id, requestId);
assert.deepEqual(Object.keys(normalized.shadow_request).sort(),
  ["agent_run_id", "contract_version", "correlation_metadata", "principal", "question"].sort());
const ack = JSON.parse(expression("Acknowledge Shadow Receipt", "responseBody", normalized));
assert.deepEqual(ack, {
  contract_version: "1", accepted: true, agent_run_id: agentRunId, event: "generate"
});
const generateUrl = expression("Call LangGraph Shadow", "url", normalized);
assert.equal(generateUrl, "http://shadow-internal:8000/v1/internal/sql-agent/generate");
const outbound = JSON.parse(expression("Call LangGraph Shadow", "jsonBody", normalized));
assert.deepEqual(outbound, normalized.shadow_request);
const response = runCode("Validate LangGraph Response", {
  statusCode: 200,
  body: {contract_version: "1", status: "success", agent_run_id: agentRunId, run_id: "run-one"}
}, {"Validate Shadow Envelope": normalized});
assert.equal(response.run_id, "run-one");
const evidenceUrl = expression("Read Correlated Evidence", "url", response);
assert.equal(evidenceUrl,
  "http://shadow-internal:8000/v1/internal/agent-runs/agent-synthetic-1/shadow-runs?limit=10");
const evidence = runCode("Assert Shadow Evidence", {
  statusCode: 200, body: {
    agent_run_id: agentRunId, items: [{
      agent_run_id: agentRunId, run_id: "run-one", event_type: "generate",
      status: "success", shadow_record_id: "record-one"
    }]
  }
}, {"Validate LangGraph Response": response});
assert.equal(evidence.correlated, true);
assert.equal(evidence.shadow_record_id, "record-one");
assert.throws(() => runCode("Validate Shadow Envelope", {
  body: {...payload, question: ""}
}), /SHADOW_ENVELOPE_QUESTION_REJECTED/);
assert.throws(() => runCode("Validate Shadow Envelope", {
  body: {...payload, correlation_metadata: {...payload.correlation_metadata, route: "/api/other"}}
}), /SHADOW_ENVELOPE_CORRELATION_REJECTED/);
assert.throws(() => runCode("Validate LangGraph Response", {
  statusCode: 200,
  body: {contract_version: "1", status: "success", agent_run_id: "different", run_id: "run-one"}
}, {"Validate Shadow Envelope": normalized}), /LANGGRAPH_SHADOW_GENERATE_RESPONSE_REJECTED/);
const duplicate = {
  agent_run_id: agentRunId,
  run_id: "run-one", event_type: "generate",
  status: "success", shadow_record_id: "record-one"
};
assert.throws(() => runCode("Assert Shadow Evidence", {
  statusCode: 200, body: {agent_run_id: agentRunId, items: [duplicate, duplicate]}
}, {"Validate LangGraph Response": response}),
/LANGGRAPH_SHADOW_EVIDENCE_CORRELATION_REJECTED/);
const sqlOpaque = "  opaque text of approved SQL  ";
const executionPayload = {
  ...payload, question: undefined, approved_sql: sqlOpaque,
  correlation_metadata: {
    ...payload.correlation_metadata, event: "execute_approved", route: "/api/execute-watson"
  }
};
const normalizedExecution = runCode("Validate Shadow Envelope", {body: executionPayload});
assert.equal(normalizedExecution.shadow_request.approved_sql, sqlOpaque);
assert.equal(normalizedExecution.shadow_request.question, undefined);
assert.equal(expression("Call LangGraph Shadow", "url", normalizedExecution),
  "http://shadow-internal:8000/v1/internal/sql-agent/execute-approved-shadow");
const executionResponse = runCode("Validate LangGraph Response", {
  statusCode: 422,
  body: {contract_version: "1", status: "rejected", agent_run_id: agentRunId, run_id: "run-two"}
}, {"Validate Shadow Envelope": normalizedExecution});
assert.equal(executionResponse.status, "rejected");
const executionEvidence = runCode("Assert Shadow Evidence", {
  statusCode: 200, body: {agent_run_id: agentRunId, items: [{
    agent_run_id: agentRunId, run_id: "run-two",
    event_type: "execute_approved_shadow", status: "rejected",
    shadow_record_id: "record-two"
  }]}
}, {"Validate LangGraph Response": executionResponse});
assert.equal(executionEvidence.correlated, true);
console.log("N8N_PARALLEL_SHADOW_CONTRACT_SIMULATION=PASS");
"""
    completed = subprocess.run(
        [node, "-e", javascript, json.dumps(workflow, ensure_ascii=False)],
        cwd=ROOT, capture_output=True, text=True, timeout=15,
        encoding="utf-8", errors="replace",
    )
    assert completed.returncode == 0, (
        "n8n synthetic contract simulation failed: " + completed.stderr[-2000:]
    )


if __name__ == "__main__":
    test_parallel_n8n_workflow_contract()
    test_embedded_javascript_syntax()
    test_workflow_expressions_and_payload_contracts()
    print("N8N_PARALLEL_SHADOW_OFFLINE=PASS")
