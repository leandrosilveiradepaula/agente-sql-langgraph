"""Offline candidate n8n approved SQL Shadow witness. No SQL/LLM service called."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "scripts/n8n/candidate_approved_sql_shadow_witness_v1.workflow.json"

def main() -> None:
    flow = json.loads(PATH.read_text(encoding="utf-8"))
    assert flow.get("active") is False and flow.get("pinData") == {}
    assert flow["settings"]["saveDataSuccessExecution"] == "none"
    assert flow["settings"]["saveDataErrorExecution"] == "none"
    assert flow["settings"]["saveManualExecutions"] is False
    names = [
        "Webhook - Approved SQL Shadow Witness",
        "Validate Approved SQL Witness Envelope",
        "Call LangGraph Execute Approved Shadow",
        "Validate Shadow Witness",
        "Return Shadow Witness",
    ]
    assert [node["name"] for node in flow["nodes"]] == names
    nodes = {node["name"]: node for node in flow["nodes"]}
    for before, after in zip(names, names[1:]):
        assert flow["connections"][before]["main"][0][0]["node"] == after
    assert nodes[names[0]]["parameters"]["authentication"] == "headerAuth"
    assert nodes[names[0]]["parameters"]["responseMode"] == "responseNode"
    assert nodes[names[0]]["parameters"]["path"] == "langgraph-candidate-approved-sql-shadow-v1"
    assert nodes[names[2]]["parameters"]["genericAuthType"] == "httpHeaderAuth"
    assert nodes[names[2]]["parameters"]["method"] == "POST"
    assert "/v1/internal/sql-agent/execute-approved-shadow" in nodes[names[2]]["parameters"]["url"]
    assert not any("credentials" in node for node in flow["nodes"])
    assert not any("postgres" in node["type"].casefold() for node in flow["nodes"])
    assert not any("execute_sql_query" in json.dumps(n).casefold() for n in flow["nodes"])
    assert not any(k in json.dumps(flow).casefold() for k in (
        "gold_lancamentos","business_question_examples","sql_infodive",
        "benchmark","ducklake","dev_lakehouse",
    ))
    script = r"""
const assert=require('node:assert/strict');
const f=JSON.parse(process.argv[2]);
const names=Object.fromEntries(f.nodes.map(x=>[x.name,x]));
const execute=(n,body,inputs={})=>
  new Function('$input','$',names[n].parameters.jsCode)(
    {first:()=>({json:body})},name=>({first:()=>({json:inputs[name]})})
  )[0].json;
const uuid=(s)=>s+'00000000-0000-4000-8000-000000000000'.slice(s.length);
const run='11111111-1111-4111-8111-111111111111',
      user='22222222-2222-4222-8222-222222222222',
      org='33333333-3333-4333-8333-333333333333',
      request='44444444-4444-4444-8444-444444444444',
      correlation='55555555-5555-4555-8555-555555555555';
const p={contract_version:'1',agent_run_id:run,
  approved_sql:'SELECT col FROM synthetic_table',
  principal:{id:user,profile:'admin',organization_id:org},
  correlation_metadata:{source:'nextjs_bff',event:'execute_approved_shadow',
    route:'candidate_execute_approved_shadow_v1',timestamp:'2026-10-29T00:00:00Z',
    request_id:correlation,execution_request_id:request,
    approval_binding_sha256:'b'.repeat(64),
    generation_run_id:'lg-original-1',generation_requester_id:user,
    generation_context_version:'context-v1',generation_response_fingerprint:'c'.repeat(64)}};
const env=execute('Validate Approved SQL Witness Envelope',{body:p});
assert.deepEqual(env.shadow_witness_request,p);
assert.throws(()=>execute('Validate Approved SQL Witness Envelope',
  {body:{...p,tenant_id:'injected'}}),/ENVELOPE_INVALID/);
assert.throws(()=>execute('Validate Approved SQL Witness Envelope',
  {body:{...p,principal:{...p.principal,organization_id:'foreign'}}}),/PRINCIPAL_INVALID/);
const ok={contract_version:'1',agent_run_id:run,run_id:'shadow-a',
  status:'success',response_fingerprint:'a'.repeat(64),
  approved_sql_original:p.approved_sql,
  validation:{security:{status:'approved'},contract:{status:'approved'},
    preflight:{status:'approved',executed:false}},
  requires_reapproval:false,repaired_sql_proposal:null,
  metadata:{semantic_lineage_verified:true}};
const context={'Validate Approved SQL Witness Envelope':env};
const witness=execute('Validate Shadow Witness',{body:ok,statusCode:200},context);
assert.equal(witness.status,'success');
assert.equal(witness.real_sql_executed,false);
assert.equal(witness.financial_parity_proven,false);
assert.equal(witness.execution_request_id,request);
assert(!JSON.stringify(witness).includes('synthetic_table'));
assert.throws(()=>execute('Validate Shadow Witness',{body:{...ok,
  metadata:{semantic_lineage_verified:false}},statusCode:200},context),/SEMANTIC_LINEAGE_UNVERIFIED/);
assert.throws(()=>execute('Validate Shadow Witness',{body:{...ok,
  agent_run_id:'foreign'},statusCode:200},context),/EVIDENCE_INVALID/);
assert.throws(()=>execute('Validate Shadow Witness',{body:{...ok,
  approved_sql_original:'SELECT unrelated'},statusCode:200},context),/SQL_PROVENANCE_INVALID/);
assert.throws(()=>execute('Validate Shadow Witness',{body:{...ok,
  validation:{...ok.validation,preflight:{status:'approved',executed:true}}},
  statusCode:200},context),/EXECUTED_FORBIDDEN/);
assert.throws(()=>execute('Validate Shadow Witness',{body:ok,statusCode:503},context),/HTTP_NOT_ACCEPTED/);
const repair={...ok,status:'rejected',requires_reapproval:true,
  repaired_sql_proposal:'SELECT repaired_col FROM synthetic_table'};
const rejected=execute('Validate Shadow Witness',{body:repair,statusCode:422},context);
assert.equal(rejected.requires_reapproval,true);
assert(!JSON.stringify(rejected).includes('repaired_col'));
assert.throws(()=>execute('Validate Shadow Witness',{body:repair,statusCode:200},context),/EVIDENCE_INVALID/);
console.log('G3_APPROVED_SQL_WITNESS=PASS');
"""
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "witness.js"
        path.write_text(script,encoding="utf-8")
        subprocess.run(["node",str(path),json.dumps(flow)],check=True,timeout=30)
    print("G3_APPROVED_SQL_WITNESS_OFFLINE=PASS")

if __name__ == "__main__":
    main()
