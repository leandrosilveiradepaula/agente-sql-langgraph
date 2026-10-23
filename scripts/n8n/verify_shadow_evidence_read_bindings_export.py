#!/usr/bin/env python3
"""Validate a private n8n evidence-read relay export without touching n8n.

The exported JSON may contain credential reference names: never print the
source, credentials, nodes, URLs or Python exception details.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections.abc import Mapping

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from scripts.n8n.render_parallel_shadow_workflow import (
    ShadowPreparationError,
    validate_internal_base_url,
)
from scripts.n8n.render_shadow_evidence_read_workflow import render

MAX_BYTES = 2 * 1024 * 1024
WORKFLOW_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
URL_EXPR = re.compile(
    r'^=\{\{\s*("(?:\\.|[^"\\])*")\s*\+\s*\$json\.target_path\s*\}\}$'
)
WEBHOOK = "Webhook - Evidence Read"
HTTP_READ = "Read LangGraph Evidence"
AUTH_NODES = frozenset({WEBHOOK, HTTP_READ})


class EvidenceBindingAuditError(ValueError):
    """An explicit error code with no details sourced from a workflow."""


def reject(code: str) -> None:
    raise EvidenceBindingAuditError(code)


def credential_id(node: Mapping) -> str:
    credentials = node.get("credentials")
    if not isinstance(credentials, Mapping) or set(credentials) != {"httpHeaderAuth"}:
        reject("EVIDENCE_CREDENTIAL_REFERENCE_MISSING")
    item = credentials["httpHeaderAuth"]
    if not isinstance(item, Mapping) or any(k not in {"id", "name"} for k in item):
        reject("EVIDENCE_CREDENTIAL_REFERENCE_INVALID")
    identity = item.get("id")
    if not isinstance(identity, str) or not WORKFLOW_ID.fullmatch(identity):
        reject("EVIDENCE_CREDENTIAL_REFERENCE_INVALID")
    return identity


def validate_export(raw: object, workflow_id: str) -> dict[str, object]:
    if not isinstance(workflow_id, str) or not WORKFLOW_ID.fullmatch(workflow_id):
        reject("EVIDENCE_WORKFLOW_ID_INVALID")
    if isinstance(raw, list):
        if len(raw) != 1:
            reject("EVIDENCE_EXPORT_NOT_SINGLE_WORKFLOW")
        raw = raw[0]
    if not isinstance(raw, Mapping) or raw.get("id") != workflow_id:
        reject("EVIDENCE_WORKFLOW_ID_MISMATCH")
    if raw.get("active") is not False or raw.get("isArchived") is True:
        reject("EVIDENCE_WORKFLOW_NOT_INACTIVE")
    if raw.get("pinData") not in ({}, None):
        reject("EVIDENCE_PINNED_DATA_PRESENT")

    nodes = raw.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 5 or any(not isinstance(n, Mapping) for n in nodes):
        reject("EVIDENCE_NODE_SET_MISMATCH")
    by_name = {n.get("name"): n for n in nodes}
    if len(by_name) != 5:
        reject("EVIDENCE_NODE_SET_MISMATCH")
    ids = [n.get("id") for n in nodes]
    if (any(not isinstance(v, str) or not WORKFLOW_ID.fullmatch(v) for v in ids)
            or len(set(ids)) != len(ids)):
        reject("EVIDENCE_NODE_ID_INVALID")

    if HTTP_READ not in by_name:
        reject("EVIDENCE_NODE_SET_MISMATCH")
    expression = by_name[HTTP_READ].get("parameters", {}).get("url")
    if not isinstance(expression, str):
        reject("EVIDENCE_INTERNAL_URL_EXPRESSION_MISMATCH")
    match = URL_EXPR.fullmatch(expression)
    if not match:
        reject("EVIDENCE_INTERNAL_URL_EXPRESSION_MISMATCH")
    try:
        base = json.loads(match.group(1))
        if validate_internal_base_url(base) != base:
            reject("EVIDENCE_INTERNAL_URL_INVALID")
        expected = render(base)
    except (TypeError, ValueError, ShadowPreparationError):
        reject("EVIDENCE_INTERNAL_URL_INVALID")
    expected_by_name = {n["name"]: n for n in expected["nodes"]}
    if set(by_name) != set(expected_by_name):
        reject("EVIDENCE_NODE_SET_MISMATCH")
    if raw.get("connections") != expected.get("connections"):
        reject("EVIDENCE_TOPOLOGY_MISMATCH")

    settings = raw.get("settings")
    if not isinstance(settings, Mapping) or any(
        settings.get(k) != v for k, v in expected["settings"].items()
    ):
        reject("EVIDENCE_PERSISTENCE_UNSAFE")

    for name, node in by_name.items():
        baseline = expected_by_name[name]
        if any(node.get(k) != baseline.get(k) for k in ("type", "typeVersion")):
            reject("EVIDENCE_NODE_CONFIGURATION_DRIFT")
        params = node.get("parameters")
        if not isinstance(params, Mapping):
            reject("EVIDENCE_NODE_CONFIGURATION_DRIFT")
        if name == HTTP_READ:
            # n8n 2.x can omit default GET on export. No other method is safe.
            if "method" not in params:
                params = {**params, "method": "GET"}
            elif params["method"] != "GET":
                reject("EVIDENCE_READ_METHOD_NOT_GET")
        if params != baseline["parameters"]:
            reject("EVIDENCE_NODE_CONFIGURATION_DRIFT")
        if any(node.get(flag) is True for flag in (
            "disabled", "continueOnFail", "alwaysOutputData", "executeOnce", "retryOnFail"
        )):
            reject("EVIDENCE_NODE_RUNTIME_FLAGS_UNSAFE")
        if name not in AUTH_NODES and "credentials" in node:
            reject("EVIDENCE_UNEXPECTED_CREDENTIAL_REFERENCE")

    webhook_credential = credential_id(by_name[WEBHOOK])
    langgraph_credential = credential_id(by_name[HTTP_READ])
    if webhook_credential == langgraph_credential:
        reject("EVIDENCE_CREDENTIAL_BOUNDARY_MISMATCH")

    return {
        "contract": "n8n-evidence-read-g2-binding-audit-v1",
        "status": "pass",
        "read_only": True,
        "workflow_active": False,
        "node_count": 5,
        "webhook_header_auth_bound": True,
        "private_langgraph_http_header_auth_bound": True,
        "webhook_credential_separate": True,
        "langgraph_method": "GET",
        "internal_url_private": True,
        "n8n_env_expressions_required": False,
        "credentials_values_verified": False,
        "authenticated_http_verified": False,
        "shadow_evidence_read_verified": False,
        "tenant_isolation_verified": False,
        "financial_parity_verified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", type=pathlib.Path, required=True)
    parser.add_argument("--workflow-id", required=True)
    args = parser.parse_args(argv)
    try:
        path = args.workflow
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
            reject("EVIDENCE_EXPORT_SIZE_INVALID")
        raw = json.loads(path.read_text(encoding="utf-8"))
        result = validate_export(raw, args.workflow_id)
    except EvidenceBindingAuditError as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}))
        return 2
    except (ValueError, OSError, TypeError, UnicodeError):
        print(json.dumps({"status": "rejected", "reason": "EVIDENCE_EXPORT_INVALID"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
