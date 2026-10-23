#!/usr/bin/env python3
"""Render the *inactive* n8n Shadow candidate for one authorized deployment.

This is an offline, configuration-only operation: no n8n API, database,
network, SQL, LLM, credential, or workflow import/activation. The checked-in
workflow remains a portable, immutable template. Only two HTTP Request URL
expressions are replaced in the generated *private* workflow JSON.

Never disable global n8n environment-variable isolation to deploy the Shadow.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import pathlib
import re
from urllib.parse import urlsplit


TEMPLATE = pathlib.Path(__file__).resolve().with_name(
    "parallel_langgraph_shadow_v1.workflow.json"
)
CALL_NODE = "Call LangGraph Shadow"
READ_NODE = "Read Correlated Evidence"
EXPECTED_HTTP_NODES = {CALL_NODE, READ_NODE}
EXPECTED_NODES = {
    "Webhook - Parallel Shadow",
    "Validate Shadow Envelope",
    "Acknowledge Shadow Receipt",
    CALL_NODE,
    "Validate LangGraph Response",
    READ_NODE,
    "Assert Shadow Evidence",
}
IPV4_ALLOWED = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)
IPV6_ALLOWED = ipaddress.ip_network("fc00::/7")
HOST_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,252}$")
# Explicitly internal cluster service domains, not public destinations.
CLUSTER_DNS = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,244}[.]svc[.]cluster[.]local$"
)


class ShadowPreparationError(ValueError):
    """Sanitized, non-secret workflow preparation rejection."""


def validate_internal_base_url(value: str) -> str:
    """Accept only a trusted private Docker/Kubernetes service base URL."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ShadowPreparationError("SHADOW_INTERNAL_URL_INVALID")
    if any(ord(char) < 33 or ord(char) == 127 for char in value):
        raise ShadowPreparationError("SHADOW_INTERNAL_URL_INVALID")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ""
        port = parsed.port  # Raises for invalid port values.
    except ValueError as exc:
        raise ShadowPreparationError("SHADOW_INTERNAL_URL_INVALID") from exc

    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ShadowPreparationError("SHADOW_INTERNAL_URL_INVALID")

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        name = hostname.casefold()
        if name in {"localhost", "host", "metadata", "host.docker.internal"}:
            raise ShadowPreparationError("SHADOW_INTERNAL_HOST_NOT_PRIVATE")
        # Reject numeric/hex IPv4 spellings that URL clients may coerce
        # into loopback or metadata addresses (for example 2130706433).
        if (name.isdecimal() or name.startswith("0x")):
            raise ShadowPreparationError("SHADOW_INTERNAL_HOST_NOT_PRIVATE")
        if not (HOST_LABEL.fullmatch(name) or CLUSTER_DNS.fullmatch(name)):
            raise ShadowPreparationError("SHADOW_INTERNAL_HOST_NOT_PRIVATE")
    else:
        allowed = (
            any(ip in net for net in IPV4_ALLOWED)
            if isinstance(ip, ipaddress.IPv4Address)
            else ip in IPV6_ALLOWED
        )
        if not allowed:
            raise ShadowPreparationError("SHADOW_INTERNAL_HOST_NOT_PRIVATE")

    return value.rstrip("/")


def load_validated_template(path: pathlib.Path = TEMPLATE) -> dict:
    try:
        workflow = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeError) as exc:
        raise ShadowPreparationError("SHADOW_TEMPLATE_INVALID") from exc
    if (
        not isinstance(workflow, dict)
        or workflow.get("active") is not False
        or "id" in workflow
        or workflow.get("pinData") != {}
        or not isinstance(workflow.get("nodes"), list)
        or len(workflow["nodes"]) != len(EXPECTED_NODES)
    ):
        raise ShadowPreparationError("SHADOW_TEMPLATE_UNSAFE")
    nodes = workflow["nodes"]
    if {n.get("name") for n in nodes if isinstance(n, dict)} != EXPECTED_NODES:
        raise ShadowPreparationError("SHADOW_TEMPLATE_UNSAFE")
    if any("credentials" in n for n in nodes):
        raise ShadowPreparationError("SHADOW_TEMPLATE_CREDENTIALS_FORBIDDEN")
    http_nodes = {n["name"]: n for n in nodes if n.get("type") == "n8n-nodes-base.httpRequest"}
    if set(http_nodes) != EXPECTED_HTTP_NODES:
        raise ShadowPreparationError("SHADOW_TEMPLATE_UNSAFE")
    if any(
        n.get("parameters", {}).get("genericAuthType") != "httpHeaderAuth"
        or n.get("parameters", {}).get("authentication") != "genericCredentialType"
        or "$env.LANGGRAPH_SHADOW_INTERNAL_BASE_URL" not in
        n.get("parameters", {}).get("url", "")
        for n in http_nodes.values()
    ):
        raise ShadowPreparationError("SHADOW_TEMPLATE_UNSAFE")
    webhook = next(n for n in nodes if n["name"] == "Webhook - Parallel Shadow")
    if (
        webhook.get("parameters", {}).get("path") != "langgraph-shadow-parallel-v1"
        or webhook.get("parameters", {}).get("authentication") != "headerAuth"
    ):
        raise ShadowPreparationError("SHADOW_TEMPLATE_UNSAFE")
    if any(
        n["type"] not in {
            "n8n-nodes-base.webhook",
            "n8n-nodes-base.code",
            "n8n-nodes-base.respondToWebhook",
            "n8n-nodes-base.httpRequest",
        }
        for n in nodes
    ):
        raise ShadowPreparationError("SHADOW_TEMPLATE_UNSAFE")
    settings = workflow.get("settings") or {}
    if (
        settings.get("saveDataSuccessExecution") != "none"
        or settings.get("saveDataErrorExecution") != "none"
    ):
        raise ShadowPreparationError("SHADOW_TEMPLATE_UNSAFE")
    return workflow


def render_private_candidate(internal_base_url: str) -> dict:
    """Return an inactive n8n JSON object, leaving TEMPLATE untouched."""
    base = validate_internal_base_url(internal_base_url)
    workflow = load_validated_template()
    base_js = json.dumps(base, ensure_ascii=True)
    for node in workflow["nodes"]:
        if node["name"] == CALL_NODE:
            node["parameters"]["url"] = (
                "={{ " + base_js + " + $json.target_path }}"
            )
        elif node["name"] == READ_NODE:
            node["parameters"]["url"] = (
                "={{ " + base_js
                + " + '/v1/internal/agent-runs/'"
                + " + encodeURIComponent($json.agent_run_id)"
                + " + '/shadow-runs?run_id='"
                + " + encodeURIComponent($json.run_id)"
                + " + '&limit=10' }}"
            )

    result = json.dumps(workflow, ensure_ascii=False, separators=(",", ":"))
    if "$env" in result or "N8N_BLOCK_ENV_ACCESS_IN_NODE" in result:
        raise ShadowPreparationError("SHADOW_RENDERING_UNSAFE")
    if workflow["active"] is not False or "id" in workflow:
        raise ShadowPreparationError("SHADOW_RENDERING_UNSAFE")
    return workflow


def write_private_candidate(workflow: dict, output: pathlib.Path) -> None:
    """Create a fresh 0600 file; never overwrite a workflow or a symlink."""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    if output.suffix.casefold() != ".json":
        raise ShadowPreparationError("SHADOW_OUTPUT_MUST_BE_JSON")
    try:
        fd = os.open(output, flags, 0o600)
    except OSError as exc:
        raise ShadowPreparationError("SHADOW_OUTPUT_CANNOT_CREATE") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(workflow, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except BaseException:
        try:
            output.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-template", action="store_true",
        help="Validate only the Git-tracked candidate; no file created.",
    )
    parser.add_argument(
        "--internal-base-url", default=None,
        help="Trusted private Docker/Kubernetes URL, not a secret. "
             "Alternatively set SHADOW_INTERNAL_BASE_URL only in this shell.",
    )
    parser.add_argument(
        "--output", type=pathlib.Path,
        help="New private JSON file to prepare (never overwritten).",
    )
    args = parser.parse_args()
    try:
        load_validated_template()
        if args.check_template:
            print("SHADOW_TEMPLATE=PASS active=false secrets_embedded=false")
            return 0
        base = args.internal_base_url or os.environ.get("SHADOW_INTERNAL_BASE_URL")
        if not base or args.output is None:
            parser.error("rendering requires --output and --internal-base-url")
        workflow = render_private_candidate(base)
        write_private_candidate(workflow, args.output)
    except ShadowPreparationError as exc:
        print("SHADOW_RENDER=FAIL reason=" + str(exc))
        return 2

    print("SHADOW_RENDER=PASS active=false")
    print("N8N_ENV_EXPRESSIONS_REQUIRED=false")
    print("CREDENTIALS_EMBEDDED=false")
    print("N8N_WORKFLOW_IMPORTED=false")
    print("N8N_WORKFLOW_ACTIVATED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
