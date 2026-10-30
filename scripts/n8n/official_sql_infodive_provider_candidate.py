"""Offline/read-only rehearsal of the n8n official LLM provider transport switch.

Does not write n8n, deploy, run SQL, invoke an LLM, or print secrets.
The stored n8n export is NOT proof of the published workflow revision.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from ipaddress import ip_address

MAX_BYTES = 16_000_000
N8N_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
N8N_CONTAINER = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")


class Blocked(ValueError):
    pass


def check(condition: bool, code: str) -> None:
    if not condition:
        raise Blocked(code)


def fingerprint(obj: object) -> str:
    return hashlib.sha256(json.dumps(
        obj, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    ).encode()).hexdigest()


def _downstream(workflow: dict, source: str, target: str) -> bool:
    for output in workflow.get("connections", {}).get(source, {}).get("main", []):
        if isinstance(output, list):
            for edge in output:
                if isinstance(edge, dict) and edge.get("node") == target:
                    return True
    return False


def discover_pairs(workflow: dict, workflow_id: str) -> dict[str, str]:
    check(workflow.get("id") == workflow_id, "WORKFLOW_ID_MISMATCH")
    nodes = workflow.get("nodes")
    check(isinstance(nodes, list) and 1 <= len(nodes) <= 2500, "NODE_COUNT_INVALID")
    check(all(isinstance(n, dict) and isinstance(n.get("name"), str)
              and isinstance(n.get("id"), str) for n in nodes), "NODE_INVALID")
    check(len({n["name"] for n in nodes}) == len(nodes)
          and len({n["id"] for n in nodes}) == len(nodes), "NODE_DUPLICATED")
    found = {}
    for source in nodes:
        if source.get("type") != "n8n-nodes-base.httpRequest":
            continue
        params = source.get("parameters")
        if not isinstance(params, dict):
            continue
        url = params.get("url")
        if not isinstance(url, str) or "generativelanguage.googleapis.com" not in url:
            continue
        check(":generateContent" in url, "GEMINI_HTTP_CONTRACT_CHANGED")
        downstream = [n for n in nodes if n.get("type") == "n8n-nodes-base.code"
                      and _downstream(workflow, source["name"], n["name"])]
        check(len(downstream) == 1, "GEMINI_CONSUMER_NOT_UNIQUE")
        consumer = downstream[0]
        script = consumer.get("parameters", {}).get("jsCode", "")
        check(isinstance(script, str), "GEMINI_CONSUMER_CODE_INVALID")
        if "respostaGemini.candidates?.[0]?.content?.parts?.[0]?.text ||" in script:
            role, original = "generate", "respostaGemini.candidates?.[0]?.content?.parts?.[0]?.text ||"
        elif "obj.candidates?.[0]?.content?.parts?.[0]?.text ||" in script:
            role, original = "repair", "obj.candidates?.[0]?.content?.parts?.[0]?.text ||"
        else:
            raise Blocked("GEMINI_CONSUMER_UNKNOWN")
        check(role not in found and script.count(original) == 1, "GEMINI_ROLE_AMBIGUOUS")
        found[role + "_http"] = source["id"]
        found[role + "_consumer"] = consumer["id"]
    check(len(found) == 4, "EXPECTED_GENERATE_AND_REPAIR_NOT_FOUND")
    return found


def _provider_config(config: dict) -> tuple[str, str, int, str, str, str | None]:
    expected = {"url", "model", "max_tokens", "credential_id", "credential_name",
                "credential_type", "host"}
    check(isinstance(config, dict) and not set(config).difference(expected),
          "CONFIG_KEYS_INVALID")
    url, model = config.get("url"), config.get("model")
    check(isinstance(url, str) and isinstance(model, str) and 1 <= len(model) <= 128,
          "PROVIDER_CONFIG_INVALID")
    parsed = urlsplit(url)
    check(parsed.path.endswith("/api/chat/completions")
          and not (parsed.username or parsed.password or parsed.query or parsed.fragment),
          "PROVIDER_URL_INVALID")
    if parsed.scheme == "http":
        try:
            address = ip_address(parsed.hostname or "")
        except ValueError:
            raise Blocked("PROVIDER_HTTP_NOT_PRIVATE") from None
        check(address.is_private or address.is_loopback, "PROVIDER_HTTP_NOT_PRIVATE")
    else:
        check(parsed.scheme == "https" and bool(parsed.hostname),
              "PROVIDER_SCHEME_INVALID")
    count = config.get("max_tokens")
    check(type(count) is int and 1 <= count <= 16000, "MAX_TOKENS_INVALID")
    credential_type = config.get("credential_type")
    check(credential_type in {"httpBearerAuth", "httpHeaderAuth"},
          "CREDENTIAL_TYPE_INVALID")
    cid, cname, host = config.get("credential_id"), config.get("credential_name"), config.get("host")
    check(isinstance(cid, str) and bool(N8N_ID.fullmatch(cid))
          and isinstance(cname, str) and 1 <= len(cname) <= 128,
          "CREDENTIAL_REFERENCE_INVALID")
    check(host is None or (isinstance(host, str)
          and re.fullmatch(r"[a-zA-Z0-9.-]{1,253}", host) is not None
          and parsed.scheme == "http"), "PROVIDER_HOST_INVALID")
    return url, model, count, cid, credential_type, host


def prepare_candidate(workflow: dict, workflow_id: str, config: dict) -> tuple[dict, dict]:
    pairs = discover_pairs(workflow, workflow_id)
    url, model, max_tokens, cid, credential_type, host = _provider_config(config)
    updated = copy.deepcopy(workflow)
    by_id = {node["id"]: node for node in updated["nodes"]}
    old_by_id = {node["id"]: node for node in workflow["nodes"]}
    for role in ("generate", "repair"):
        node = by_id[pairs[role + "_http"]]
        original = old_by_id[node["id"]]
        check(node.get("type") == "n8n-nodes-base.httpRequest", "HTTP_NODE_INVALID")
        params = node.get("parameters", {})
        check(params.get("method") == "POST" and params.get("sendBody") is True
              and params.get("specifyBody") == "json"
              and params.get("jsonBody") == "={{ $json.body }}",
              "LEGACY_REQUEST_CONTRACT_CHANGED")
        check(params.get("sendQuery") is True
              and [p.get("name") for p in params.get("queryParameters", {}).get("parameters", [])] == ["key"]
              and not node.get("credentials"), "LEGACY_KEY_CONTRACT_CHANGED")
        check(":generateContent" in params.get("url", ""), "GEMINI_URL_CHANGED")
        params["url"] = url
        params["sendQuery"] = False
        params["queryParameters"] = {"parameters": []}
        params["authentication"] = "genericCredentialType"
        params["genericAuthType"] = credential_type
        headers = [{"name": "Content-Type", "value": "application/json"}]
        if host:
            headers.append({"name": "Host", "value": host})
        params["sendHeaders"] = True
        params["headerParameters"] = {"parameters": headers}
        # Transform the existing model-neutral SQL prompt, not semantic rules.
        params["jsonBody"] = "={{({model:" + json.dumps(model) + \
            ",messages:[{role:'user',content:$json.body.contents[0].parts[0].text}]," + \
            "temperature:0,max_tokens:" + str(max_tokens) + ",stream:false})}}"
        node["credentials"] = {credential_type: {
            "id": cid, "name": config["credential_name"]
        }}
        check(original.get("retryOnFail") == node.get("retryOnFail"), "RETRY_CHANGED")
        consumer = by_id[pairs[role + "_consumer"]]
        check(consumer.get("type") == "n8n-nodes-base.code", "CONSUMER_TYPE_INVALID")
        script = consumer.get("parameters", {}).get("jsCode")
        original_field = ("respostaGemini" if role == "generate" else "obj")
        legacy = original_field + ".candidates?.[0]?.content?.parts?.[0]?.text ||"
        check(isinstance(script, str) and script.count(legacy) == 1, "PARSER_CHANGED")
        consumer["parameters"]["jsCode"] = script.replace(
            legacy, original_field + ".choices?.[0]?.message?.content ||\n  " + legacy, 1
        )
    changed = [node_id for node_id in old_by_id if old_by_id[node_id] != by_id[node_id]]
    check(set(changed) == set(pairs.values()) and len(changed) == 4,
          "UNEXPECTED_NODE_CHANGES")
    check({k:v for k,v in updated.items() if k != "nodes"} ==
          {k:v for k,v in workflow.items() if k != "nodes"},
          "WORKFLOW_METADATA_CHANGED")
    for node_id in changed:
        before, after = old_by_id[node_id], by_id[node_id]
        check({k:v for k,v in before.items() if k not in ("parameters","credentials")} ==
              {k:v for k,v in after.items() if k not in ("parameters","credentials")},
              "NODE_METADATA_CHANGED")
    return updated, {
        "stored_sha256": fingerprint(workflow),
        "candidate_sha256": fingerprint(updated),
        "changed_nodes": len(changed),
        "other_nodes_unchanged": len(old_by_id)-len(changed),
        "connections_changed": False,
        "settings_changed": False,
        "published_attested": False,
        "llm_calls": 0,
        "financial_sql_executed": False,
    }


def _read_export(container: str, workflow_id: str) -> dict:
    check(bool(N8N_CONTAINER.fullmatch(container)) and bool(N8N_ID.fullmatch(workflow_id)),
          "EXPORT_ID_INVALID")
    cmd = ["docker", "exec", "-u", "node", "-e", "N8N_LOG_OUTPUT=console",
           "-e", "N8N_LOG_LEVEL=info", container, "n8n",
           "export:workflow", "--id=" + workflow_id]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                              timeout=80, check=False)
    except (OSError, subprocess.SubprocessError):
        raise Blocked("CLI_UNAVAILABLE") from None
    check(proc.returncode == 0 and len(proc.stdout) < MAX_BYTES,
          "CLI_EXPORT_FAILED")
    decoder = json.JSONDecoder()
    matches = []
    for marker in re.finditer(r"\[\s*\{", proc.stdout):
        try:
            value, _ = decoder.raw_decode(proc.stdout[marker.start():])
        except ValueError:
            continue
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict) and value[0].get("id") == workflow_id:
            matches.append(value[0])
    check(len(matches) == 1, "CLI_EXPORT_UNVERIFIABLE")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n8n-container", required=True)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    print("PROVIDER_SWITCH_MODE=READ_ONLY_NO_APPLY")
    try:
        workflow = _read_export(args.n8n_container, args.workflow_id)
        pairs = discover_pairs(workflow, args.workflow_id)
        print("PROVIDER_SWITCH_STORED_SHA256=" + fingerprint(workflow))
        print("PROVIDER_SWITCH_STORED_NODES=" + str(len(workflow["nodes"])))
        for key, value in pairs.items():
            print("PROVIDER_SWITCH_" + key.upper() + "_ID=" + value)
        if args.audit_only:
            print("PROVIDER_SWITCH_STATUS=STORED_AUDIT_ONLY")
            return 0
        check(args.config is not None and args.config.is_file()
              and args.config.stat().st_size <= 65536, "CONFIG_MISSING")
        config = json.loads(args.config.read_text(encoding="utf-8"))
        _, report = prepare_candidate(workflow, args.workflow_id, config)
        for key, value in report.items():
            print("PROVIDER_SWITCH_" + key.upper() + "=" + str(value))
        print("PROVIDER_SWITCH_STATUS=CANDIDATE_IN_MEMORY_ONLY")
        return 0
    except Blocked as error:
        print("PROVIDER_SWITCH_STATUS=BLOCKED")
        print("PROVIDER_SWITCH_REASON=" + str(error))
        return 2
    except (OSError, ValueError, TypeError):
        print("PROVIDER_SWITCH_STATUS=BLOCKED")
        print("PROVIDER_SWITCH_REASON=INPUT_INVALID")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
