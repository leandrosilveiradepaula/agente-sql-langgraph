#!/usr/bin/env python3
"""Render the private, INACTIVE evidence read relay (offline only)."""
from __future__ import annotations
import argparse
import json
import pathlib
import sys
from scripts.n8n.render_parallel_shadow_workflow import (
    ShadowPreparationError, validate_internal_base_url, write_private_candidate
)
TEMPLATE=pathlib.Path(__file__).with_name("parallel_shadow_evidence_read_v1.workflow.json")
NAMES=["Webhook - Evidence Read","Validate Evidence Read Envelope","Read LangGraph Evidence","Sanitize Evidence Response","Respond Safe Evidence"]

def load_template():
    try:
        w=json.loads(TEMPLATE.read_text(encoding="utf-8"))
    except (OSError,ValueError,UnicodeError) as exc:
        raise ShadowPreparationError("EVIDENCE_TEMPLATE_INVALID") from exc
    if not isinstance(w,dict) or w.get("active") is not False or w.get("pinData")!={} or "id" in w or not isinstance(w.get("nodes"),list):
        raise ShadowPreparationError("EVIDENCE_TEMPLATE_UNSAFE")
    nodes=w["nodes"]
    if [n.get("name") for n in nodes]!=NAMES or any("credentials" in n for n in nodes):
        raise ShadowPreparationError("EVIDENCE_TEMPLATE_UNSAFE")
    settings=w.get("settings") or {}
    if any(settings.get(k)!=v for k,v in (("saveDataSuccessExecution","none"),("saveDataErrorExecution","none"),("saveManualExecutions",False),("saveExecutionProgress",False))):
        raise ShadowPreparationError("EVIDENCE_PERSISTENCE_UNSAFE")
    byname={n["name"]:n for n in nodes}
    web=byname[NAMES[0]].get("parameters",{})
    read=byname[NAMES[2]].get("parameters",{})
    if (web.get("path")!="langgraph-shadow-evidence-v1" or web.get("authentication")!="headerAuth" or web.get("httpMethod")!="POST" or
        read.get("method")!="GET" or read.get("genericAuthType")!="httpHeaderAuth" or read.get("authentication")!="genericCredentialType" or
        "$env.LANGGRAPH_SHADOW_INTERNAL_BASE_URL" not in read.get("url","")):
        raise ShadowPreparationError("EVIDENCE_TRANSPORT_UNSAFE")
    expected={NAMES[i]:{"main":[[{"node":NAMES[i+1],"type":"main","index":0}]]} for i in range(4)}
    if w.get("connections")!=expected:
        raise ShadowPreparationError("EVIDENCE_TOPOLOGY_UNSAFE")
    return w

def render(internal_base_url):
    base=validate_internal_base_url(internal_base_url)
    w=load_template()
    byname={n["name"]:n for n in w["nodes"]}
    byname[NAMES[2]]["parameters"]["url"]="={{ "+json.dumps(base,ensure_ascii=True)+" + $json.target_path }}"
    if "$env." in json.dumps(w):
        raise ShadowPreparationError("EVIDENCE_RENDER_UNSAFE")
    return w

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--check-template",action="store_true")
    p.add_argument("--internal-base-url")
    p.add_argument("--output",type=pathlib.Path)
    a=p.parse_args()
    try:
        if a.check_template:
            load_template()
            print("EVIDENCE_READ_TEMPLATE=PASS active=false")
            return 0
        if not a.internal_base_url or not a.output:
            raise ShadowPreparationError("EVIDENCE_RENDER_ARGUMENTS_REQUIRED")
        write_private_candidate(render(a.internal_base_url),a.output)
    except ShadowPreparationError as exc:
        print("EVIDENCE_READ_RENDER=REJECTED "+str(exc))
        return 2
    print("EVIDENCE_READ_RENDER=PASS active=false secrets_embedded=false")
    return 0
if __name__=="__main__":
    sys.exit(main())
