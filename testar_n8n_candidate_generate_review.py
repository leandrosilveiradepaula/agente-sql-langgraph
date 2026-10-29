"""Offline contract for the isolated generate-only candidate, not a live LLM test."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "scripts/n8n/candidate_generate_review_v1.workflow.json"

def main() -> None:
    flow = json.loads(PATH.read_text(encoding="utf-8"))
    assert flow["active"] is False and flow["pinData"] == {}
    assert flow["settings"]["saveDataSuccessExecution"] == "none"
    assert flow["settings"]["saveDataErrorExecution"] == "none"
    names = [node["name"] for node in flow["nodes"]]
    assert names == [
        "Webhook - Candidate Generate",
        "Validate Candidate Envelope",
        "Call LangGraph Generate",
        "Validate Candidate Result",
        "Return Candidate SQL",
    ]
    for first, second in zip(names, names[1:]):
        assert flow["connections"][first]["main"][0][0]["node"] == second
    nodes = {node["name"]: node for node in flow["nodes"]}
    assert nodes[names[0]]["parameters"]["authentication"] == "headerAuth"
    assert nodes[names[0]]["parameters"]["responseMode"] == "responseNode"
    assert nodes[names[2]]["parameters"]["genericAuthType"] == "httpHeaderAuth"
    assert "/v1/internal/sql-agent/generate" in nodes[names[2]]["parameters"]["url"]
    assert not any("credentials" in node for node in flow["nodes"])
    assert not any("postgres" in node["type"].lower() for node in flow["nodes"])
    assert not any("execute-approved" in json.dumps(node).lower() for node in flow["nodes"])
    assert not any(word in json.dumps(flow).lower() for word in (
        "select *", "sql_infodive", "gold_lancamentos", "grupo_dre",
        "benchmark", "business_question_examples", "dev_lakehouse",
    ))
    script = r"""
const assert = require('node:assert/strict');
const flow=JSON.parse(process.argv[1]);
const nodes=Object.fromEntries(flow.nodes.map(n=>[n.name,n]));
const run=(name,body,prior={})=>
  new Function('$input','$',nodes[name].parameters.jsCode)(
    {first:()=>({json:body})},
    n=>({first:()=>({json:prior[n]})})
  )[0].json;
const payload={contract_version:'1',agent_run_id:'run-1',question:'An original request',principal:{id:'user-1',profile:'analyst',organization_id:'tenant-1'},correlation_metadata:{source:'nextjs_bff',event:'generate',route:'/api/generate-sql',timestamp:'2026-10-29T00:00:00Z',request_id:'req-1'}};
const envelope=run('Validate Candidate Envelope',{body:payload});
assert.equal(envelope.candidate_request.question,payload.question);
assert.equal(envelope.candidate_request.principal.organization_id,'tenant-1');
assert.throws(()=>run('Validate Candidate Envelope',{body:{...payload,sql:'SELECT 1'}}),/ENVELOPE_INVALID/);
assert.throws(()=>run('Validate Candidate Envelope',{body:{...payload,principal:{...payload.principal,organization_id:''}}}),/TENANT_INVALID/);
const response={contract_version:'1',agent_run_id:'run-1',run_id:'lg-1',status:'success',sql:'SELECT 1',intent:'aggregate',gates:{security:{status:'approved'},contract:{status:'approved'}},preflight:{status:'approved',executed:false},response_fingerprint:'a'.repeat(64)};
const output=run('Validate Candidate Result',{body:response},{'Validate Candidate Envelope':envelope});
assert.equal(output.real_sql_executed,false);
assert.equal(output.requires_human_approval,true);
assert.equal(output.sql,'SELECT 1');
assert.throws(()=>run('Validate Candidate Result',{body:{...response,preflight:{status:'approved',executed:true}}},{'Validate Candidate Envelope':envelope}),/NOT_VALIDATED/);
assert.throws(()=>run('Validate Candidate Result',{body:{...response,agent_run_id:'another'}} ,{'Validate Candidate Envelope':envelope}),/RESPONSE_INVALID/);
console.log('G3_CANDIDATE_GENERATE_ONLY=PASS');
"""
    with tempfile.TemporaryDirectory() as directory:
        file = Path(directory) / "candidate-test.js"
        file.write_text(script, encoding="utf-8")
        subprocess.run(["node", str(file), json.dumps(flow)], check=True, timeout=30)
    print("G3_CANDIDATE_OFFLINE=PASS")

if __name__ == "__main__":
    main()
