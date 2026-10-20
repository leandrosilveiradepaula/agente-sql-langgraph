from __future__ import annotations

"""Read-only, provider-neutral inventory of exported n8n workflow metadata.

This utility does NOT classify a customer-specific business rule automatically.
It creates a deterministic, minimal node-level evidence index to help a human
review actual workflow code without echoing prompts, credentials or SQL.

Input is an explicit local JSON export, not a live n8n API request.
"""

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


MAX_EXPORT_BYTES = 16 * 1024 * 1024
MAX_NODES = 2500
MAX_PARAM_BYTES = 4 * 1024 * 1024
# Human-readable names are deliberately NOT emitted: arbitrary workflow/node
# names can contain secrets that no heuristic regex can reliably recognize.
_ALLOWED_NODE_TYPE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


class WorkflowAuditError(ValueError):
    """Fail closed without including raw workflow export or exception text."""


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _safe_name(value: Any, *, index: int) -> str:
    """Never emit workflow-owned text; stable identity comes from ID hashes."""
    return f"node-{index + 1:03d}"

def load_workflow(path: Path) -> tuple[Mapping[str, Any], str]:
    """Read one explicit local export with strict size and shape controls."""
    try:
        if not path.is_file():
            raise WorkflowAuditError("WORKFLOW_FILE_NOT_FOUND")
        size = path.stat().st_size
        if size <= 0 or size > MAX_EXPORT_BYTES:
            raise WorkflowAuditError("WORKFLOW_FILE_SIZE_INVALID")
        raw = path.read_bytes()
        if len(raw) != size:
            raise WorkflowAuditError("WORKFLOW_FILE_CHANGED_DURING_READ")
        workflow = json.loads(raw)
    except WorkflowAuditError:
        raise
    except (OSError, ValueError, UnicodeError) as exc:
        raise WorkflowAuditError("WORKFLOW_READ_OR_JSON_INVALID") from exc
    # CLI can serialize one selected workflow as a singleton list.
    # Refuse multi-workflow bundles: the call must attest exactly one ID.
    if isinstance(workflow, list):
        if len(workflow) != 1 or not isinstance(workflow[0], dict):
            raise WorkflowAuditError("WORKFLOW_SINGLE_RECORD_REQUIRED")
        workflow = workflow[0]
    if not isinstance(workflow, dict):
        raise WorkflowAuditError("WORKFLOW_OBJECT_REQUIRED")
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES:
        raise WorkflowAuditError("WORKFLOW_NODES_INVALID")
    if not isinstance(workflow.get("connections", {}), Mapping):
        raise WorkflowAuditError("WORKFLOW_CONNECTIONS_INVALID")
    return workflow, _digest(raw)


def _node_identity(node: Mapping[str, Any]) -> str:
    raw_id = node.get("id")
    if isinstance(raw_id, str) and raw_id.strip():
        return "id:" + raw_id
    raw_name = node.get("name")
    if not isinstance(raw_name, str) or not raw_name:
        raise WorkflowAuditError("WORKFLOW_NODE_IDENTIFIER_MISSING")
    return "name:" + raw_name


def _node_record(node: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    kind = node.get("type")
    if (
        not isinstance(kind, str)
        or not 1 <= len(kind) <= 180
        or any(char not in _ALLOWED_NODE_TYPE for char in kind)
    ):
        raise WorkflowAuditError("WORKFLOW_NODE_TYPE_INVALID")
    params = node.get("parameters", {})
    if not isinstance(params, Mapping):
        raise WorkflowAuditError("WORKFLOW_NODE_PARAMS_INVALID")
    canonical = _canonical(params)
    if len(canonical) > MAX_PARAM_BYTES:
        raise WorkflowAuditError("WORKFLOW_NODE_PARAMS_TOO_LARGE")
    code = params.get("jsCode", "")
    if code is None:
        code = ""
    if not isinstance(code, str):
        raise WorkflowAuditError("WORKFLOW_NODE_CODE_INVALID")

    review_flags: list[str] = []
    if code:
        review_flags.append("INLINE_CODE_REVIEW")
        if len(_JS_STRING.findall(code)) >= 12:
            review_flags.append("MANY_INLINE_STRING_LITERALS")
        if _SQL_SHAPE.search(code):
            review_flags.append("SQL_SHAPED_CODE_REVIEW")
    if any(
        isinstance(key, str)
        and ("prompt" in key.casefold() or "systemmessage" in key.casefold())
        for key in params
    ):
        review_flags.append("PROMPT_PARAMETER_REVIEW")
    if isinstance(params.get("query"), str) and params["query"].strip():
        review_flags.append("INLINE_QUERY_REVIEW")
    if kind.endswith(".httpRequest"):
        review_flags.append("EXTERNAL_REQUEST_REVIEW")

    name = _safe_name(node.get("name"), index=index)
    return {
        "index": index + 1,
        "name": name,
        "type": kind,
        "disabled_in_export": node.get("disabled") is True,
        "node_identity_sha256": _digest(_node_identity(node).encode("utf-8")),
        "parameters_sha256": _digest(canonical),
        "code_characters": len(code),
        "review_flags": review_flags,
    }


def summarize_workflow(
    workflow: Mapping[str, Any], source_sha256: str,
) -> dict[str, Any]:
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        raise WorkflowAuditError("WORKFLOW_NODES_INVALID")
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, Mapping):
            raise WorkflowAuditError("WORKFLOW_NODE_INVALID")
        identity = _node_identity(node)
        if identity in seen:
            raise WorkflowAuditError("WORKFLOW_NODE_IDENTIFIER_DUPLICATE")
        seen.add(identity)
        records.append(_node_record(node, index=index))

    counts = Counter(record["type"] for record in records)
    flags = Counter(
        flag for record in records for flag in record["review_flags"]
    )
    return {
        "contract": "n8n-workflow-evidence-index-v1",
        "read_only": True,
        "live_instance_verified": False,
        "workflow_export_sha256": source_sha256,
        "export_active_flag": workflow.get("active") is True,
        "node_count": len(records),
        "node_types": dict(sorted(counts.items())),
        "review_flags": dict(sorted(flags.items())),
        "nodes": records,
    }


def compare_exports(
    earlier: Mapping[str, Any], later: Mapping[str, Any],
) -> dict[str, Any]:
    old_nodes = earlier.get("nodes")
    new_nodes = later.get("nodes")
    if not isinstance(old_nodes, list) or not isinstance(new_nodes, list):
        raise WorkflowAuditError("WORKFLOW_COMPARISON_INVALID")
    old = {n["node_identity_sha256"]: n for n in old_nodes}
    new = {n["node_identity_sha256"]: n for n in new_nodes}
    if len(old) != len(old_nodes) or len(new) != len(new_nodes):
        raise WorkflowAuditError("WORKFLOW_COMPARISON_DUPLICATE_NODES")

    status: list[dict[str, Any]] = []
    for node in new_nodes:
        key = node["node_identity_sha256"]
        previous = old.get(key)
        changed = (
            previous is not None
            and (
                previous["parameters_sha256"] != node["parameters_sha256"]
                or previous["type"] != node["type"]
                or previous["disabled_in_export"] != node["disabled_in_export"]
            )
        )
        status.append({
            "index": node["index"],
            "name": node["name"],
            "status": (
                "added" if previous is None else
                "changed" if changed else "unchanged"
            ),
        })
    removed = [
        {"index": n["index"], "name": n["name"], "status": "removed"}
        for n in old_nodes if n["node_identity_sha256"] not in new
    ]
    all_changes = status + removed
    return {
        "baseline_export_sha256": earlier["workflow_export_sha256"],
        "candidate_export_sha256": later["workflow_export_sha256"],
        "unchanged": sum(x["status"] == "unchanged" for x in all_changes),
        "changed": sum(x["status"] == "changed" for x in all_changes),
        "added": sum(x["status"] == "added" for x in all_changes),
        "removed": sum(x["status"] == "removed" for x in all_changes),
        "nodes": all_changes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", type=Path, required=True)
    parser.add_argument("--compare-to", type=Path)
    args = parser.parse_args(argv)
    try:
        current, checksum = load_workflow(args.workflow)
        result = summarize_workflow(current, checksum)
        if args.compare_to is not None:
            baseline, baseline_sha = load_workflow(args.compare_to)
            result["comparison"] = compare_exports(
                summarize_workflow(baseline, baseline_sha), result,
            )
    except WorkflowAuditError as exc:
        # Only machine-defined codes, never source code, SQL or credentials.
        print(json.dumps({"status": "rejected", "reason": str(exc)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
