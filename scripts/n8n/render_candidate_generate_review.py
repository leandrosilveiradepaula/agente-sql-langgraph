"""Render an isolated, inactive candidate workflow for trusted private n8n routing.

This module only creates a local 0600 JSON. It does not import, publish,
activate, update credentials, generate SQL or call any network service.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

TEMPLATE = Path(__file__).with_name("candidate_generate_review_v1.workflow.json")
NODE = "Call LangGraph Generate"
PLACEHOLDER_PATH = "/v1/internal/sql-agent/generate"


def _private_base(value: str) -> str:
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        valid = (
            url.scheme == "http"
            and bool(host)
            and not url.username and not url.password
            and not url.path.rstrip("/") and not url.query and not url.fragment
        )
        if not valid or host in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
            if not address.is_private or address.is_loopback or address.is_link_local:
                raise ValueError
        except ValueError:
            if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,250}", host):
                raise ValueError("invalid host")
            if "." in host and not (
                host.endswith(".internal")
                or host.endswith(".docker")
                or host.endswith(".local")
            ):
                raise ValueError("public hostname forbidden")
        return value.rstrip("/")
    except Exception:
        raise ValueError("candidate_private_base_invalid") from None


def render(base: str) -> dict:
    doc = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    if doc.get("active") is not False or len(doc.get("nodes", [])) != 5:
        raise ValueError("candidate_template_invalid")
    matches = [n for n in doc["nodes"] if n.get("name") == NODE]
    if len(matches) != 1:
        raise ValueError("candidate_template_invalid")
    original = matches[0]["parameters"].get("url")
    if not isinstance(original, str) or "LANGGRAPH_SHADOW_INTERNAL_BASE_URL" not in original or PLACEHOLDER_PATH not in original:
        raise ValueError("candidate_template_invalid")
    matches[0]["parameters"]["url"] = f"={{{{ '{_private_base(base)}{PLACEHOLDER_PATH}' }}}}"
    if "credentials" in json.dumps(doc) or doc.get("pinData") != {}:
        raise ValueError("candidate_template_invalid")
    return doc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--internal-base-url")
    parser.add_argument("--output")
    parser.add_argument("--check-template", action="store_true")
    args = parser.parse_args()
    if args.check_template:
        doc = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        if doc.get("active") is not False or len(doc.get("nodes", [])) != 5:
            raise ValueError("candidate_template_invalid")
        print("G3_CANDIDATE_TEMPLATE=PASS")
        return 0
    if not args.internal_base_url or not args.output:
        parser.error("--internal-base-url and --output are required")
    doc = render(args.internal_base_url)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(args.output, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(doc, output, indent=2)
        output.write("\n")
    print("G3_PRIVATE_CANDIDATE_RENDERED=YES")
    print("G3_CANDIDATE_ACTIVE=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
