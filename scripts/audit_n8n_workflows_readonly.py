#!/usr/bin/env python3
"""Safe structural inventory of n8n workflow exports.

Never emits node parameters, code, SQL, URLs, credential references or raw
workflow JSON. This script is an operator-only audit tool, not LangGraph
business logic or a benchmark input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_NAME_LENGTH = 90
SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
URL = re.compile(r"(?i)\b(?:https?://|postgres(?:ql)?://|[a-z0-9]+://)\S+")
EMAIL = re.compile(r"(?i)\b[A-Z0-9_.+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
SECRET_LIKE = re.compile(
    r"(?i)\b(?:authorization|bearer|api[_ -]?key|secret|password|token)"
    r"\s*[:= ]\s*[^\s,;]+"
)
SENSITIVE_PARAM_KEYS = frozenset({
    "jsCode", "functionCode", "query", "sqlQuery",
    "conditions", "filters", "filter", "rules",
})


def safe_title(value: object) -> str:
    if not isinstance(value, str):
        return "[unnamed]"
    result = "".join(ch if ch.isprintable() else " " for ch in value)
    result = URL.sub("[url-redacted]", result)
    result = EMAIL.sub("[email-redacted]", result)
    result = SECRET_LIKE.sub("[secret-redacted]", result)
    result = result.strip()
    return result[:MAX_NAME_LENGTH] or "[unnamed]"


def safe_id(value: object) -> str:
    if isinstance(value, str) and SAFE_ID.fullmatch(value):
        return value
    return "[id-redacted]"


def parse_workflows(root: object) -> list[Mapping[str, Any]]:
    if isinstance(root, list):
        entries = root
    elif isinstance(root, Mapping):
        if isinstance(root.get("workflows"), list):
            entries = root["workflows"]
        elif isinstance(root.get("data"), list):
            entries = root["data"]
        elif isinstance(root.get("nodes"), list):
            entries = [root]
        else:
            raise ValueError("unrecognized export shape")
    else:
        raise ValueError("unrecognized export shape")
    if not all(isinstance(item, Mapping) for item in entries):
        raise ValueError("invalid workflow entry")
    return entries


def read_export(path: Path) -> list[Mapping[str, Any]]:
    if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("invalid export file")
    with path.open(encoding="utf-8") as stream:
        return parse_workflows(json.load(stream))


def node_type(node: Mapping[str, Any]) -> str:
    raw = node.get("type")
    if not isinstance(raw, str):
        return "unknown"
    return safe_title(raw)


def is_trigger(node: Mapping[str, Any]) -> bool:
    kind = node_type(node).casefold().split(".")[-1]
    return (
        kind.endswith("trigger")
        or kind in {"webhook", "form", "chat"}
        or "trigger" in kind
    )


def needs_review(node: Mapping[str, Any]) -> bool:
    parameters = node.get("parameters")
    if not isinstance(parameters, Mapping):
        return False
    if any(key in parameters for key in SENSITIVE_PARAM_KEYS):
        return True
    kind = node_type(node).casefold()
    return (
        kind.endswith(".code")
        or kind.endswith(".function")
        or kind.endswith(".if")
        or kind.endswith(".switch")
    )


def node_indices(workflow: Mapping[str, Any]) -> dict[str, int]:
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        return {}
    return {
        node["name"]: index
        for index, node in enumerate(nodes, 1)
        if isinstance(node, Mapping) and isinstance(node.get("name"), str)
    }


def edges(workflow: Mapping[str, Any]) -> list[tuple[int, int, int]]:
    connections = workflow.get("connections")
    if not isinstance(connections, Mapping):
        return []
    indices = node_indices(workflow)
    outgoing: set[tuple[int, int, int]] = set()
    for source, kinds in connections.items():
        if source not in indices or not isinstance(kinds, Mapping):
            continue
        for outputs in kinds.values():
            if not isinstance(outputs, list):
                continue
            for branch, links in enumerate(outputs):
                if not isinstance(links, list):
                    continue
                for link in links:
                    if not isinstance(link, Mapping):
                        continue
                    target = link.get("node")
                    if isinstance(target, str) and target in indices:
                        outgoing.add((indices[source], indices[target], branch))
    return sorted(outgoing)


def audit_summary(workflow: Mapping[str, Any]) -> str:
    nodes = workflow.get("nodes")
    nodes = nodes if isinstance(nodes, list) else []
    kinds = Counter(
        node_type(item) for item in nodes if isinstance(item, Mapping)
    )
    triggers = sum(is_trigger(item) for item in nodes if isinstance(item, Mapping))
    reviews = sum(needs_review(item) for item in nodes if isinstance(item, Mapping))
    active = "true" if workflow.get("active") is True else "false"
    return (
        f'WORKFLOW id={safe_id(workflow.get("id"))}'
        f' active={active} nodes={len(nodes)}'
        f' edges={len(edges(workflow))} triggers={triggers}'
        f' review_candidates={reviews}'
        f' name={json.dumps(safe_title(workflow.get("name")), ensure_ascii=False)}'
    )


def detailed_graph(workflow: Mapping[str, Any], *, max_nodes: int) -> None:
    nodes = workflow.get("nodes")
    nodes = nodes if isinstance(nodes, list) else []
    links = edges(workflow)
    print("GRAPH_WORKFLOW_ID=" + safe_id(workflow.get("id")))
    print("GRAPH_ACTIVE=" + ("true" if workflow.get("active") is True else "false"))
    print(f"GRAPH_NODES={len(nodes)}")
    print(f"GRAPH_EDGES={len(links)}")
    print("GRAPH_STRUCTURE_ONLY=true")
    # No actual Code/SQL/HTTP payload is ever logged.
    for index, node in enumerate(nodes[:max_nodes], start=1):
        if not isinstance(node, Mapping):
            continue
        targets = [
            f"{dst:03d}({branch})" for src, dst, branch in links
            if src == index
        ]
        print(
            f"NODE {index:03d}"
            f" type={node_type(node)}"
            f" trigger={'true' if is_trigger(node) else 'false'}"
            f" review={'true' if needs_review(node) else 'false'}"
            f" name={json.dumps(safe_title(node.get('name')), ensure_ascii=False)}"
            f" downstream={','.join(targets) if targets else 'none'}"
        )
    if len(nodes) > max_nodes:
        print(f"GRAPH_TRUNCATED={len(nodes) - max_nodes}")
    print("REVIEW_CLASSIFICATION=STRUCTURAL_TOPOLOGY_ONLY")
    print("INLINE_BUSINESS_RULES=UNCLASSIFIED_REVIEW_REQUIRED")
    print("OFFICIAL_INSERTION_POINT=NOT_YET_APPROVED")


def render(
    workflows: list[Mapping[str, Any]],
    *,
    matches: list[str],
    workflow_id: str | None,
    max_workflows: int,
    max_nodes: int,
) -> None:
    print("N8N_AUDIT_VERSION=1")
    print(f"N8N_WORKFLOWS_EXPORTED={len(workflows)}")
    print("N8N_EXPORT_PARAMETERS_REDACTED=true")
    if workflow_id is not None:
        selected = [item for item in workflows if item.get("id") == workflow_id]
    elif matches:
        lowered = [term.casefold() for term in matches if term.strip()]
        selected = [
            item for item in workflows
            if isinstance(item.get("name"), str)
            and any(term in item["name"].casefold() for term in lowered)
        ]
    else:
        selected = []

    selected = sorted(
        selected,
        key=lambda w: (w.get("active") is not True, str(w.get("name", "")).casefold()),
    )
    print(f"N8N_WORKFLOW_MATCHES={len(selected)}")
    for item in selected[:max_workflows]:
        print(audit_summary(item))
    if len(selected) > max_workflows:
        print(f"N8N_WORKFLOW_LIST_TRUNCATED={len(selected) - max_workflows}")
    if workflow_id is not None:
        if len(selected) == 1:
            detailed_graph(selected[0], max_nodes=max_nodes)
        elif not selected:
            print("N8N_WORKFLOW_ID_NOT_FOUND=true")
    elif len(selected) == 1:
        detailed_graph(selected[0], max_nodes=max_nodes)
    elif len(selected) > 1:
        print("N8N_OFFICIAL_SELECTION=REQUIRED_MULTIPLE_MATCHES")
    else:
        print("N8N_OFFICIAL_SELECTION=REQUIRED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sanitized n8n workflow structural audit")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--match", action="append", default=[])
    parser.add_argument("--workflow-id")
    parser.add_argument("--max-workflows", type=int, default=12)
    parser.add_argument("--max-nodes", type=int, default=90)
    args = parser.parse_args(argv)
    if not 1 <= args.max_workflows <= 50 or not 1 <= args.max_nodes <= 200:
        print("N8N_AUDIT_INVALID_LIMITS")
        return 2
    if args.workflow_id is not None and not SAFE_ID.fullmatch(args.workflow_id):
        print("N8N_AUDIT_INVALID_ID")
        return 2
    try:
        exported = read_export(args.input)
        render(
            exported,
            matches=args.match,
            workflow_id=args.workflow_id,
            max_workflows=args.max_workflows,
            max_nodes=args.max_nodes,
        )
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        # Deliberately never log untrusted export content or exception text.
        print("N8N_AUDIT_INPUT_INVALID")
        return 3
    print("N8N_AUDIT_READONLY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
