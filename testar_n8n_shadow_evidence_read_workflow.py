#!/usr/bin/env python3
"""Offline verification of n8n evidence bridge Code nodes."""
from __future__ import annotations
import json
import pathlib
import shutil
import subprocess
from scripts.n8n.render_shadow_evidence_read_workflow import load_template, render, ShadowPreparationError

def main():
    w=load_template()
    assert len(w["nodes"])==5 and not w["active"]
    assert all("credentials" not in n for n in w["nodes"])
    rendered=render("http://internal-shadow-service:8000")
    assert "$env" not in json.dumps(rendered)
    for url in ("https://example.com","http://127.0.0.1:8000","http://169.254.169.254:80"):
        try: render(url)
        except ShadowPreparationError: pass
        else: raise AssertionError("Rejected URL accepted")
    if not shutil.which("node"):
        raise AssertionError("Node required for JavaScript contract tests")
    byname={n["name"]:n for n in w["nodes"]}
    source=byname["Validate Evidence Read Envelope"]["parameters"]["jsCode"]
    sanitizer=byname["Sanitize Evidence Response"]["parameters"]["jsCode"]
    js=r'''
const vm=require('node:vm'), assert=require('node:assert/strict');
const validate=JSON.parse(process.argv[1]), sanitize=JSON.parse(process.argv[2]);
const run=(code,input,source)=>vm.runInNewContext('(function(){'+code+'})()',{
  $input:{first:()=>({json:input})},
  $:()=>({first:()=>({json:source})}),Number,Object,Array,Set,encodeURIComponent
},{timeout:1000})[0].json;
const req={contract_version:'1',request_id:'req-1',operation:'list',agent_run_id:'agent-1',limit:10};
const v=run(validate,{body:req});
assert.equal(v.target_path,'/v1/internal/agent-runs/agent-1/shadow-runs?limit=10');
for(const bad of [{...req,agent_run_id:'../secret'},{...req,target_path:'http://evil.invalid'},{...req,limit:51},{...req,operation:'wrong'}])
 assert.throws(()=>run(validate,{body:bad}));
const detail=run(validate,{body:{contract_version:'1',request_id:'req-2',operation:'detail',shadow_record_id:'shadow-1'}});
assert.equal(detail.target_path,'/v1/internal/shadow-runs/shadow-1');
const graph=run(validate,{body:{contract_version:'1',request_id:'req-3',operation:'visualization',shadow_record_id:'shadow-1'}});
assert.equal(graph.target_path,'/v1/internal/shadow-runs/shadow-1/visualization');
const item={agent_run_id:'agent-1',shadow_record_id:'shadow-1',run_id:'run-1',event_type:'generate',status:'rejected',created_at:'2026-10-22T00:00:00Z',completed_at:null,raw_sql:'SELECT confidential'};
const safe=run(sanitize,{statusCode:200,body:{contract_version:'1',agent_run_id:'agent-1',items:[item]}},v);
assert.equal(safe.safe_response.items.length,1);
assert.equal(JSON.stringify(safe).includes('confidential'),false);
assert.throws(()=>run(sanitize,{statusCode:401,body:{}},v));
assert.throws(()=>run(sanitize,{statusCode:200,body:{contract_version:'1',agent_run_id:'another',items:[item]}},v));
assert.throws(()=>run(sanitize,{statusCode:200,body:{contract_version:'1',agent_run_id:'agent-1',items:[item,item]}},v));
const d=run(sanitize,{statusCode:200,body:{contract_version:'1',...item}},detail);
assert.equal(d.safe_response.shadow_record_id,'shadow-1');
const g=run(sanitize,{statusCode:200,body:{contract_version:'1',run:item,steps:[{id:'step-1',label:'security_gate',status:'success',order:1,metadata:{duration_ms:2,raw_sql:'SELECT private'}}],edges:[],flags:{has_error:false}}},graph);
assert.equal(g.safe_response.steps[0].metadata.duration_ms,2);
assert.equal(JSON.stringify(g).includes('private'),false);
const canonical={...item,status:undefined,final_status:'rejected',created_at:'2026-10-22T00:00:00+00:00',requires_reapproval:true};
const canonicalList=run(sanitize,{statusCode:200,body:{contract_version:'1',agent_run_id:'agent-1',items:[canonical]}},v);
assert.equal(canonicalList.safe_response.items[0].status,'rejected');
const canonicalDetail=run(sanitize,{statusCode:200,body:{contract_version:'1',...canonical}},detail);
assert.equal(canonicalDetail.safe_response.status,'rejected');
const canonicalGraph=run(sanitize,{statusCode:200,body:{
 contract_version:'1',run:{...canonical,requires_reapproval:undefined},
 steps:[
  {id:'step-1',label:'security_gate',status:'ok',sequence:1,step_type:'gate',metadata:{duration_ms:3,secret:'secret-hidden'}},
  {id:'step-2',label:'repair_sql',status:'warning',sequence:2,step_type:'repair',metadata:{repair_attempt:1,raw_sql:'SELECT hidden'}}
 ],
 edges:[{source:'step-1',target:'step-2',edge_type:'repair'}],
 flags:{requires_reapproval:true,has_repair:true,has_error:false,persistence_failure:true,has_unknown_evidence:true}
}},graph);
assert.equal(canonicalGraph.safe_response.run.status,'rejected');
assert.equal(canonicalGraph.safe_response.run.requires_reapproval,true);
assert.equal(canonicalGraph.safe_response.run.has_repair,true);
assert.equal(canonicalGraph.safe_response.steps[0].order,1);
assert.equal(canonicalGraph.safe_response.steps[0].metadata.duration_ms,3);
assert.equal(canonicalGraph.safe_response.steps[0].metadata.kind,'gate');
assert.equal(canonicalGraph.safe_response.steps[1].metadata.kind,'repair');
assert.equal(canonicalGraph.safe_response.steps[1].metadata.repair_attempt,1);
assert.equal(canonicalGraph.safe_response.edges[0].label,'repair');
assert.deepEqual(Array.from(canonicalGraph.safe_response.flags.warnings),[
 'shadow_persistence_failure','shadow_evidence_incomplete'
]);
assert.equal(JSON.stringify(canonicalGraph).includes('SELECT hidden'),false);
assert.equal(JSON.stringify(canonicalGraph).includes('secret-hidden'),false);
// Reject timestamp/status/step/edge content that could carry SQL or secrets.
assert.throws(()=>run(sanitize,{statusCode:200,body:{contract_version:'1',...item,created_at:'SELECT secret'}},detail));
assert.throws(()=>run(sanitize,{statusCode:200,body:{contract_version:'1',...item,status:'SELECT secret'}},detail));
assert.throws(()=>run(sanitize,{statusCode:200,body:{contract_version:'1',...item,event_type:'SELECT secret'}},detail));
assert.throws(()=>run(sanitize,{statusCode:200,body:{contract_version:'1',...item,status:'rejected',final_status:'success'}},detail));
for(const bad of [
  {steps:[{id:'step-1',label:'SELECT secret',status:'ok',sequence:1,step_type:'gate'}]},
  {steps:[{id:'step-1',label:'security_gate',status:'ok',sequence:1,step_type:'SELECT secret'}]},
  {steps:[{id:'step-1',label:'security_gate',status:'ok',sequence:1,order:2,step_type:'gate'}]},
  {edges:[{source:'step-1',target:'step-2',edge_type:'SELECT secret'}]},
  {edges:[{source:'step-1',target:'step-2',edge_type:'repair',label:'normal'}]},
  {edges:[{source:'step-1',target:'step-2',label:'SELECT confidential'}]}
]){
 const base={contract_version:'1',run:{...canonical,requires_reapproval:undefined},
  steps:[{id:'step-1',label:'security_gate',status:'ok',sequence:1,step_type:'gate'},
         {id:'step-2',label:'repair_sql',status:'warning',sequence:2,step_type:'repair'}],
  edges:[{source:'step-1',target:'step-2',edge_type:'repair'}],flags:{}};
 assert.throws(()=>run(sanitize,{statusCode:200,body:{...base,...bad}},graph));
}
const shortList=run(validate,{body:{...req,limit:1}});
assert.throws(()=>run(sanitize,{statusCode:200,body:{contract_version:'1',agent_run_id:'agent-1',items:[item,{...item,shadow_record_id:'shadow-2'}]}},shortList));

assert.throws(()=>run(sanitize,{statusCode:200,body:{contract_version:'1',run:item,steps:[{id:'step-1',label:'security_gate',status:'success',order:1}],edges:[{source:'step-1',target:'missing'}]}},graph));
console.log('EVIDENCE_READ_NODE_BEHAVIOR=PASS');
'''
    r=subprocess.run(["node","-e",js,json.dumps(source),json.dumps(sanitizer)],capture_output=True,text=True,timeout=15)
    if r.returncode: raise AssertionError(r.stderr[-1000:])
    print(r.stdout.strip())
    print("EVIDENCE_READ_RELAY_OFFLINE=PASS sql_execution=false llm_calls=0")
if __name__=="__main__":main()
