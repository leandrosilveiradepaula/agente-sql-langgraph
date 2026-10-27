#!/usr/bin/env python3
"""G1 read-only forensics after a n8n credential-rebinding PUT.

Reads the private pre-PUT snapshot, encrypted credential metadata and the
stored workflow via n8n 2.4.8 local CLI. No n8n API key, HTTP requests,
PostgreSQL connection, export file, workflow write, or secret output.
A STRICT_PASS confirms database-stored bindings and the current active
version; it is not an approval to execute financial SQL.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from g1_partial_reconcile_readonly import find_n8n_container
from g1_readonly_rollout import (
    RolloutError,
    _load_verified_snapshot,
    _node_for_comparison,
    load_config,
    read_n8n_runtime_version,
    validate_workflow,
)

FIELDS = ("name", "connections", "settings", "staticData",
          "pinData", "meta", "tags")
MAX_EXPORT_CHARS = 18_000_000


def parse_single_cli_export(stdout: str, *, expected_id: str, kind: str) -> dict[str, Any]:
    """Parse one expected record from noisy CLI output, never echoing it.

    We deliberately require exactly one matching root JSON array. Any
    ambiguity in the external CLI format fails closed rather than treating
    an empty/failed read as a successful authorization.
    """
    if not isinstance(stdout, str) or not stdout or len(stdout) > MAX_EXPORT_CHARS:
        raise RolloutError("saida CLI ausente ou fora do limite")
    if kind not in ("workflow", "credential"):
        raise RolloutError("tipo de inventario invalido")
    decoder = json.JSONDecoder()
    matches: list[dict[str, Any]] = []
    for candidate in re.finditer(r"\[\s*\{", stdout):
        try:
            decoded, _end = decoder.raw_decode(stdout[candidate.start():])
        except (ValueError, TypeError):
            continue
        if not isinstance(decoded, list) or len(decoded) != 1:
            continue
        record = decoded[0]
        if not isinstance(record, dict) or record.get("id") != expected_id:
            continue
        if kind == "workflow":
            if not isinstance(record.get("nodes"), list) or not isinstance(record.get("name"), str):
                continue
        elif not (isinstance(record.get("name"), str)
                  and isinstance(record.get("type"), str)
                  and isinstance(record.get("data"), str)):
            continue
        matches.append(record)
    if len(matches) != 1:
        raise RolloutError("exportacao CLI com identidade/formato nao verificavel")
    return matches[0]


def export_one(container: str, kind: str, record_id: str) -> dict[str, Any]:
    """n8n's encrypted/local, read-only export; keep all bytes in memory."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", record_id):
        raise RolloutError("identificador CLI invalido")
    if kind not in ("workflow", "credential"):
        raise RolloutError("tipo CLI nao autorizado")
    cmd = [
        "docker", "exec", "-u", "node", container,
        "n8n", "export:workflow" if kind == "workflow" else "export:credentials",
        "--id=" + record_id,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=75,
        )
    except (OSError, subprocess.SubprocessError):
        raise RolloutError("inventario CLI read-only indisponivel") from None
    return parse_single_cli_export(result.stdout, expected_id=record_id, kind=kind)


def node_map(workflow: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    source = workflow.get("nodes")
    if not isinstance(source, list) or not source:
        raise RolloutError("lista de nos nao verificavel")
    nodes: dict[str, dict[str, Any]] = {}
    for raw_node in source:
        if not isinstance(raw_node, dict) or not isinstance(raw_node.get("id"), str):
            raise RolloutError("estrutura de no nao verificavel")
        node_id = raw_node["id"]
        if node_id in nodes:
            raise RolloutError("identidade de no duplicada")
        nodes[node_id] = _node_for_comparison(raw_node)
    return nodes


def field_state(before: Mapping[str, Any], after: Mapping[str, Any],
                key: str) -> str:
    if key not in before and key not in after:
        return "BOTH_ABSENT"
    if key not in before:
        return "ADDED"
    if key not in after:
        return "REMOVED"
    return "UNCHANGED" if before[key] == after[key] else "CHANGED"


def evaluate(snapshot: Mapping[str, Any], stored: Mapping[str, Any],
             credential: Mapping[str, Any], config: Any) -> dict[str, str]:
    """Pure, conservative comparison. A changed nonbinding field is a gate."""
    original = snapshot["workflow"]
    new_id, new_name = snapshot["credential_id"], snapshot["credential_name"]
    if (credential.get("id"), credential.get("name"), credential.get("type")) != (
        new_id, new_name, config.n8n["credential_type"]
    ):
        raise RolloutError("credencial exportada diverge do snapshot")

    before = node_map(original)
    after = node_map(stored)
    if set(before) != set(after):
        raise RolloutError("identidade/conjunto de nos divergente")
    original_order = [node["id"] for node in original["nodes"]]
    stored_order = [node["id"] for node in stored["nodes"]]

    ids = set(config.n8n["binding_node_ids"])
    if not ids.issubset(before):
        raise RolloutError("nos G1 ausentes do snapshot")

    counts = {"NEW": 0, "OLD": 0, "OTHER": 0}
    unauthorized_node_drift = 0
    for node_id, old_node in before.items():
        expected = copy.deepcopy(old_node)
        actual = after[node_id]
        if node_id in ids:
            old_cred = expected.get("credentials", {}).get("postgres")
            current_cred = actual.get("credentials", {}).get("postgres")
            if not isinstance(old_cred, dict) or not isinstance(current_cred, dict):
                counts["OTHER"] += 1
                unauthorized_node_drift += 1
                continue
            if current_cred == {"id": new_id, "name": new_name}:
                counts["NEW"] += 1
            elif current_cred == {
                "id": config.n8n["old_credential_id"],
                "name": config.n8n.get("old_credential_name", "Postgres account 2"),
            }:
                counts["OLD"] += 1
            else:
                counts["OTHER"] += 1
            expected["credentials"]["postgres"] = current_cred
        if expected != actual:
            unauthorized_node_drift += 1

    field_results = {field: field_state(original, stored, field) for field in FIELDS}
    other_fields_match = all(
        v in ("UNCHANGED", "BOTH_ABSENT") for v in field_results.values()
    )
    try:
        validate_workflow(stored, config, require_old_bindings=False)
        workflow_contract = "PASS"
    except RolloutError:
        workflow_contract = "REVIEW_REQUIRED"
    version = (
        "ACTIVE_MATCH" if stored.get("active") is True
        and bool(stored.get("versionId"))
        and stored.get("versionId") == stored.get("activeVersionId")
        else "REVIEW_REQUIRED"
    )
    result = {
        "G1_AUDIT_MODE": "LOCAL_CLI_READ_ONLY",
        "G1_SNAPSHOT": "VALID",
        "G1_CREDENTIAL": "ENCRYPTED_RECORD_MATCH",
        "G1_WORKFLOW_CONTRACT": workflow_contract,
        "G1_PUBLISHED_VERSION": version,
        "G1_NODE_SET": "PASS",
        "G1_NODE_ORDER": "UNCHANGED" if original_order == stored_order else "CHANGED",
        "G1_NEW_BINDINGS": str(counts["NEW"]),
        "G1_OLD_BINDINGS": str(counts["OLD"]),
        "G1_OTHER_BINDINGS": str(counts["OTHER"]),
        "G1_UNAUTHORIZED_NODE_DRIFT": str(unauthorized_node_drift),
    }
    for field, state in field_results.items():
        result["G1_FIELD_" + field.upper()] = state
    if (
        workflow_contract == "PASS" and version == "ACTIVE_MATCH"
        and result["G1_NODE_ORDER"] == "UNCHANGED"
        and counts == {"NEW": 2, "OLD": 0, "OTHER": 0}
        and unauthorized_node_drift == 0 and other_fields_match
    ):
        result["G1_AUDIT_RESULT"] = "STRICT_PASS"
    elif counts["NEW"] != 2 or counts["OLD"] or counts["OTHER"]:
        result["G1_AUDIT_RESULT"] = "BINDINGS_REVIEW_REQUIRED"
    elif workflow_contract != "PASS" or version != "ACTIVE_MATCH" \
            or unauthorized_node_drift != 0 or result["G1_NODE_ORDER"] != "UNCHANGED":
        result["G1_AUDIT_RESULT"] = "STRUCTURAL_REVIEW_REQUIRED"
    else:
        result["G1_AUDIT_RESULT"] = "NONBINDING_FIELD_DRIFT_REVIEW"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path,
        default=Path(__file__).with_name("g1_readonly_rollout.json"),
    )
    parser.add_argument(
        "--snapshot", type=Path,
        default=Path.home() /
        ".local/state/agente-sql-langgraph/g1-readonly-snapshot.json",
    )
    parser.add_argument("--n8n-container", default="")
    args = parser.parse_args(argv)
    print("G1_AUDIT_MODE=LOCAL_CLI_READ_ONLY")
    config = load_config(args.config)
    snapshot = _load_verified_snapshot(args.snapshot, config)
    container = find_n8n_container(args.n8n_container)
    read_n8n_runtime_version(config, container)
    # No HTTP client, n8n API key, admin DB DSN or SQL request anywhere.
    credential = export_one(container, "credential", snapshot["credential_id"])
    stored = export_one(container, "workflow", config.n8n["workflow_id"])
    result = evaluate(snapshot, stored, credential, config)
    for key, value in result.items():
        if key != "G1_AUDIT_MODE":
            print(key + "=" + value)
    return 0 if result["G1_AUDIT_RESULT"] == "STRICT_PASS" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RolloutError as exc:
        print("G1_AUDIT_RESULT=BLOCKED_READ_ONLY")
        print("ERROR=" + str(exc), file=sys.stderr)
        raise SystemExit(2)
    except Exception:
        print("G1_AUDIT_RESULT=BLOCKED_READ_ONLY")
        print("ERROR=DIAGNOSTICO_NAO_VERIFICAVEL", file=sys.stderr)
        raise SystemExit(2)
