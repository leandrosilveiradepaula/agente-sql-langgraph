#!/usr/bin/env python3
"""Validate one private n8n Shadow workflow export against an exact contract.

Inactive draft is the DEFAULT. The explicit --expect-active mode is only
for the wrapper's --published export, never a request to activate the n8n
workflow. Neither mode reads credential values or executes workflows.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections.abc import Mapping

# Support direct CLI execution without an installed Python package.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from scripts.n8n.render_parallel_shadow_workflow import (
    ShadowPreparationError,
    render_private_candidate,
    validate_internal_base_url,
)

MAX_BYTES = 2 * 1024 * 1024
EXPECTED_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
CALL = "Call LangGraph Shadow"
READ = "Read Correlated Evidence"
WEBHOOK = "Webhook - Parallel Shadow"
AUTH_NODES = {WEBHOOK, CALL, READ}
# Only a JSON-quoted literal followed by the approved dynamic route is accepted.
CALL_EXPRESSION = re.compile(
    r'^=\{\{\s*("(?:\\.|[^"\\])*")\s*\+\s*\$json\.target_path\s*\}\}$'
)


class BindingAuditError(ValueError):
    """Known, non-sensitive rejection code."""


def _reject(code: str) -> None:
    raise BindingAuditError(code)


def _credential_id(node: Mapping) -> str:
    creds = node.get("credentials")
    if not isinstance(creds, Mapping) or set(creds) != {"httpHeaderAuth"}:
        _reject("SHADOW_CREDENTIAL_REFERENCE_MISSING")
    credential = creds["httpHeaderAuth"]
    if not isinstance(credential, Mapping):
        _reject("SHADOW_CREDENTIAL_REFERENCE_MISSING")
    identity = credential.get("id")
    if not isinstance(identity, str) or not 1 <= len(identity) <= 128:
        _reject("SHADOW_CREDENTIAL_REFERENCE_MISSING")
    # Credential names are untrusted and never printed.
    if any(key not in {"id", "name"} for key in credential):
        _reject("SHADOW_CREDENTIAL_REFERENCE_UNEXPECTED_FIELD")
    return identity


def validate_export(
    raw: object, workflow_id: str, *, expect_active: bool = False,
) -> dict[str, object]:
    if not isinstance(workflow_id, str) or not EXPECTED_ID_RE.fullmatch(workflow_id):
        _reject("SHADOW_WORKFLOW_ID_INVALID")
    if isinstance(raw, list):
        if len(raw) != 1:
            _reject("SHADOW_EXPORT_NOT_SINGLE_WORKFLOW")
        raw = raw[0]
    if not isinstance(raw, Mapping) or raw.get("id") != workflow_id:
        _reject("SHADOW_WORKFLOW_ID_MISMATCH")
    if raw.get("isArchived") is True:
        _reject("SHADOW_WORKFLOW_ARCHIVED")
    # Never infer the state from an inactive template or from the mode
    # flag alone. Active and inactive audits have distinct strict contracts.
    if raw.get("active") is not expect_active:
        _reject(
            "SHADOW_WORKFLOW_NOT_ACTIVE"
            if expect_active else "SHADOW_WORKFLOW_NOT_INACTIVE"
        )
    nodes = raw.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 7 or any(not isinstance(n, Mapping) for n in nodes):
        _reject("SHADOW_NODE_SET_MISMATCH")
    by_name = {n.get("name"): n for n in nodes}
    if len(by_name) != 7 or CALL not in by_name:
        _reject("SHADOW_NODE_SET_MISMATCH")
    # n8n assigns new node IDs during import; require valid unique IDs, not
    # byte-for-byte equality with portable template IDs.
    node_ids = [n.get("id") for n in nodes]
    if (
        any(not isinstance(node_id, str) or not EXPECTED_ID_RE.fullmatch(node_id)
            for node_id in node_ids)
        or len(set(node_ids)) != len(node_ids)
    ):
        _reject("SHADOW_NODE_ID_INVALID")
    expression = by_name[CALL].get("parameters", {}).get("url")
    if not isinstance(expression, str):
        _reject("SHADOW_INTERNAL_URL_EXPRESSION_MISMATCH")
    match = CALL_EXPRESSION.fullmatch(expression)
    if not match:
        _reject("SHADOW_INTERNAL_URL_EXPRESSION_MISMATCH")
    try:
        base = json.loads(match.group(1))
        if validate_internal_base_url(base) != base:
            _reject("SHADOW_INTERNAL_URL_INVALID")
        expected = render_private_candidate(base)
    except (ValueError, ShadowPreparationError, TypeError):
        _reject("SHADOW_INTERNAL_URL_INVALID")
    expected_by_name = {n["name"]: n for n in expected["nodes"]}
    if set(by_name) != set(expected_by_name):
        _reject("SHADOW_NODE_SET_MISMATCH")
    if raw.get("connections") != expected["connections"]:
        _reject("SHADOW_TOPOLOGY_MISMATCH")
    if raw.get("pinData") not in ({}, None):
        _reject("SHADOW_PINNED_DATA_PRESENT")
    settings = raw.get("settings")
    if not isinstance(settings, Mapping) or any(
        settings.get(key) != value for key, value in expected["settings"].items()
    ):
        _reject("SHADOW_EXECUTION_PERSISTENCE_UNSAFE")
    for name, node in by_name.items():
        baseline = expected_by_name[name]
        if any(node.get(key) != baseline.get(key) for key in ("type", "typeVersion")):
            _reject("SHADOW_NODE_CONFIGURATION_DRIFT")
        parameters = node.get("parameters")
        if not isinstance(parameters, Mapping):
            _reject("SHADOW_NODE_CONFIGURATION_DRIFT")
        if name == READ:
            # n8n 2.x may omit its default GET method when serializing this
            # read-only HTTP node. Explicit non-GET methods are never allowed.
            if "method" not in parameters:
                parameters = {**parameters, "method": "GET"}
            elif parameters["method"] != "GET":
                _reject("SHADOW_READ_METHOD_NOT_GET")
        if parameters != baseline["parameters"]:
            _reject("SHADOW_NODE_CONFIGURATION_DRIFT")
        if any(node.get(flag) is True for flag in ("disabled", "continueOnFail", "alwaysOutputData", "executeOnce")):
            _reject("SHADOW_NODE_RUNTIME_FLAGS_UNSAFE")
        if name not in AUTH_NODES and "credentials" in node:
            _reject("SHADOW_UNEXPECTED_CREDENTIAL_REFERENCE")
    webhook_id = _credential_id(by_name[WEBHOOK])
    call_id = _credential_id(by_name[CALL])
    read_id = _credential_id(by_name[READ])
    if call_id != read_id or call_id == webhook_id:
        _reject("SHADOW_CREDENTIAL_BOUNDARY_MISMATCH")
    return {
        "contract": "n8n-parallel-shadow-g1-binding-audit-v1",
        "status": "pass",
        "read_only": True,
        "workflow_active": expect_active,
        "workflow_state_expectation": "active" if expect_active else "inactive",
        "node_count": 7,
        "webhook_header_auth_bound": True,
        "langgraph_header_auth_bound": True,
        "langgraph_http_nodes_share_credential": True,
        "webhook_credential_separate": True,
        "internal_url_private": True,
        "n8n_env_expression_required": False,
        "credentials_values_verified": False,
        "authenticated_http_verified": False,
        "shadow_execution_verified": False,
        "financial_parity_verified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", type=pathlib.Path, required=True)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument(
        "--expect-active", action="store_true",
        help="Validate an active published export (wrapper must use --published).",
    )
    args = parser.parse_args(argv)
    try:
        path = args.workflow
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
            _reject("SHADOW_EXPORT_SIZE_INVALID")
        raw = json.loads(path.read_text(encoding="utf-8"))
        result = validate_export(
            raw, args.workflow_id, expect_active=args.expect_active,
        )
    except BindingAuditError as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)}))
        return 2
    except (OSError, ValueError, UnicodeError, TypeError):
        print(json.dumps({"status": "rejected", "reason": "SHADOW_EXPORT_INVALID"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
