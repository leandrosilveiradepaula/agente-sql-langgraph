#!/usr/bin/env python3
"""Classify reachable legacy PostgreSQL nodes from existing private G1/P3 proofs.

No Docker, network, SQL, decrypted credential export, n8n API or workflow write.
This is an *offline review draft*, NEVER an attestation of a live publication,
accounting approval, migration plan approval or cutover authorization.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping


class ReviewBlocked(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def deny(code: str) -> None:
    raise ReviewBlocked(code)


def _equal(proof: Mapping[str, str], key: str, expected: str) -> None:
    if proof.get(key) != expected:
        deny("EVIDENCE_INCOMPLETE_OR_DRIFTED")


def _safe_positive(value: Any, *, bound: int = 800) -> int:
    if type(value) is not int or value < 1 or value > bound:
        deny("POLICY_INVALID")
    return value


def _node_map(workflow: Mapping[str, Any]) -> tuple[dict[str, tuple[int, dict]], list[str]]:
    nodes = workflow.get("nodes")
    connections = workflow.get("connections")
    if (not isinstance(nodes, list) or not nodes or len(nodes) > 800
            or not isinstance(connections, dict)):
        deny("WORKFLOW_SHAPE_INVALID")
    names: dict[str, tuple[int, dict]] = {}
    triggers: list[str] = []
    seen_ids: set[str] = set()
    for ordinal, node in enumerate(nodes, 1):
        if not isinstance(node, dict):
            deny("WORKFLOW_SHAPE_INVALID")
        name, node_id, kind = node.get("name"), node.get("id"), node.get("type")
        if (not isinstance(name, str) or not 1 <= len(name) <= 200
                or not isinstance(node_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", node_id)
                or not isinstance(kind, str) or not kind or name in names
                or node_id in seen_ids):
            deny("WORKFLOW_SHAPE_INVALID")
        names[name] = (ordinal, node)
        seen_ids.add(node_id)
        if kind == "n8n-nodes-base.webhook" or kind.lower().endswith("trigger"):
            triggers.append(name)
    if not triggers:
        deny("WORKFLOW_SHAPE_INVALID")
    return names, triggers


def _reachable_postgres(workflow: Mapping[str, Any]) -> list[tuple[int, dict]]:
    """Over-approximate every trigger branch, including IF alternatives."""
    names, pending = _node_map(workflow)
    connections = workflow["connections"]
    visited: set[str] = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        if name not in names:
            deny("WORKFLOW_GRAPH_INVALID")
        visited.add(name)
        outputs = connections.get(name, {})
        if not isinstance(outputs, dict):
            deny("WORKFLOW_GRAPH_INVALID")
        for branches in outputs.values():
            if not isinstance(branches, list):
                deny("WORKFLOW_GRAPH_INVALID")
            for edges in branches:
                if edges is None:
                    continue
                if not isinstance(edges, list):
                    deny("WORKFLOW_GRAPH_INVALID")
                for edge in edges:
                    to = edge.get("node") if isinstance(edge, dict) else None
                    if not isinstance(to, str) or to not in names:
                        deny("WORKFLOW_GRAPH_INVALID")
                    pending.append(to)
    out: list[tuple[int, dict]] = []
    for name in visited:
        ordinal, node = names[name]
        if node["type"] != "n8n-nodes-base.postgres" or node.get("disabled") is True:
            continue
        cred = (node.get("credentials") or {}).get("postgres")
        if not isinstance(cred, dict) or not isinstance(cred.get("id"), str):
            deny("WORKFLOW_CREDENTIAL_UNVERIFIED")
        out.append((ordinal, node))
    return sorted(out, key=lambda row: row[0])


def review_existing_proofs(
    *, policy: Mapping[str, Any], snapshot: Mapping[str, Any],
    g1: Mapping[str, str], deps: Mapping[str, str],
) -> dict[str, Any]:
    """Create a *non-executable* decision draft using only prior evidence."""
    n8n = policy.get("n8n")
    if not isinstance(n8n, dict):
        deny("POLICY_INVALID")
    expected_count = _safe_positive(n8n.get("expected_node_count"))
    bound = n8n.get("binding_node_ids")
    if (not isinstance(bound, list) or len(bound) != 2 or len(set(bound)) != 2
            or not all(isinstance(x, str) and x for x in bound)):
        deny("POLICY_INVALID")
    workflow = snapshot.get("workflow")
    if not isinstance(workflow, dict) or workflow.get("id") != n8n.get("workflow_id"):
        deny("SNAPSHOT_WORKFLOW_INVALID")
    if len(workflow.get("nodes", [])) != expected_count:
        deny("SNAPSHOT_WORKFLOW_INVALID")
    old_id = n8n.get("old_credential_id")
    new_id = snapshot.get("credential_id")
    if (not isinstance(old_id, str) or not old_id or
            not isinstance(new_id, str) or not new_id or old_id == new_id or
            snapshot.get("old_credential_id") != old_id):
        deny("SNAPSHOT_CREDENTIAL_UNVERIFIED")

    for key, value in (
        ("G1_AUDIT_MODE", "LOCAL_CLI_READ_ONLY"),
        ("G1_WORKFLOW_CONTRACT", "PASS"),
        ("G1_CREDENTIAL", "ENCRYPTED_RECORD_MATCH"),
        ("G1_PUBLISHED_VERSION", "ACTIVE_MATCH"),
        ("G1_NODE_SET", "PASS"),
        ("G1_NODE_ORDER", "UNCHANGED"),
        ("G1_NEW_BINDINGS", str(len(bound))),
        ("G1_OLD_BINDINGS", "0"),
        ("G1_OTHER_BINDINGS", "0"),
        ("G1_UNAUTHORIZED_NODE_DRIFT", "0"),
        ("G1_FIELD_CONNECTIONS", "UNCHANGED"),
        ("SUPABASE_DEPENDENCY_AUDIT", "READ_ONLY"),
        ("SUPABASE_N8N_OFFICIAL_NODE_COUNT", str(expected_count)),
        ("SUPABASE_N8N_POSTGRES_CREDENTIAL_COUNT", "2"),
        ("SUPABASE_N8N_EXECUTION_ROLE_ATTESTED", "PASS"),
        ("SUPABASE_N8N_EXECUTION_CREDENTIAL_TARGET", "DEMO"),
        ("SUPABASE_SHADOW_REAL_SQL_EXECUTION_DISABLED", "PASS"),
        ("SUPABASE_N8N_REACHABLE_UNKNOWN_POSTGRES_NODES", "0"),
        ("SUPABASE_N8N_REACHABLE_OTHER_SUPABASE_UNVERIFIED_POSTGRES_NODES", "0"),
    ):
        proof = g1 if key.startswith("G1_") else deps
        _equal(proof, key, value)
    state = g1.get("G1_AUDIT_RESULT")
    if state not in {"STRICT_PASS", "N8N_248_NORMALIZED_PASS", "SETTINGS_DRIFT_REVIEW"}:
        deny("G1_NOT_ELIGIBLE_FOR_INVENTORY")
    if state == "SETTINGS_DRIFT_REVIEW":
        _equal(g1, "G1_SETTINGS_REVIEW_COUNT", "1")
        _equal(g1, "G1_SETTINGS_EQUIVALENCE", "REVIEW_REQUIRED")

    # G1 only replaced the two explicitly named executor bindings; the
    # previous snapshot can *already* contain other PostgreSQL credential
    # identities. The original code incorrectly required every reachable
    # PostgreSQL node to use old_id, although G1 never made that claim.
    # Reconstruct the after-PUT identity *only* for those two executor IDs.
    # Compare the resulting number of distinct credential references with
    # the independent P3 audit, including disabled/unreachable nodes.
    credential_ids_after_put: set[str] = set()
    for node in workflow["nodes"]:
        credentials = node.get("credentials") or {}
        if not isinstance(credentials, dict):
            deny("WORKFLOW_CREDENTIAL_UNVERIFIED")
        pg = credentials.get("postgres")
        if pg is None:
            if node["id"] in bound:
                deny("EXECUTOR_SNAPSHOT_CREDENTIAL_MISMATCH")
            continue
        cid = pg.get("id") if isinstance(pg, dict) else None
        if not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", cid):
            deny("WORKFLOW_CREDENTIAL_UNVERIFIED")
        if cid == new_id:
            # The replacement was created *after* the captured snapshot.
            deny("SNAPSHOT_CONTAINS_NEW_CREDENTIAL")
        if node["id"] in bound:
            if node.get("type") != "n8n-nodes-base.postgres" or cid != old_id:
                deny("EXECUTOR_SNAPSHOT_CREDENTIAL_MISMATCH")
            credential_ids_after_put.add(new_id)
        else:
            credential_ids_after_put.add(cid)
    try:
        observed_credential_count = int(deps["SUPABASE_N8N_POSTGRES_CREDENTIAL_COUNT"])
    except (TypeError, ValueError, KeyError):
        deny("EVIDENCE_INCOMPLETE_OR_DRIFTED")
    if len(credential_ids_after_put) != observed_credential_count:
        deny("P3_CREDENTIAL_TOPOLOGY_MISMATCH")

    postgres = _reachable_postgres(workflow)
    found_bindings: set[str] = set()
    rows: list[dict[str, Any]] = []
    counts = Counter()
    for ordinal, node in postgres:
        node_id = node["id"]
        expected_executor = node_id in bound
        if expected_executor:
            if node_id in found_bindings:
                deny("DUPLICATE_EXECUTOR")
            found_bindings.add(node_id)
        # P3 independently classified *all* reachable PostgreSQL nodes
        # as DEMO or SOURCE, with zero UNKNOWN/OTHER. Only the two executor
        # nodes have a separately attested DEMO credential and G1 attests
        # zero non-binding node drift. Thus the aggregate counts below must
        # agree exactly before marking a non-executor as SOURCE. Never infer
        # client/accounting semantics from that destination label.
        target = "DEMO" if expected_executor else "SOURCE"
        counts[target] += 1
        raw_operation = (node.get("parameters") or {}).get("operation")
        operation = raw_operation if isinstance(raw_operation, str) and raw_operation in {
            "executeQuery", "insert", "update", "upsert", "delete", "select"
        } else "UNKNOWN"
        rows.append({
            "snapshot_ordinal": ordinal,
            "node_id": node_id,
            "node_name": node["name"],
            "destination_at_p3_audit": target,
            "operation_class": operation,
            "role": "ATTESTED_FINANCIAL_EXECUTOR" if expected_executor else "LEGACY_DEPENDENCY_REVIEW",
            "business_purpose": None,
            "cutover_disposition": None,
            "replacement_dependency": None,
            "owner_approval_evidence": None,
        })
    if found_bindings != set(bound):
        deny("EXECUTOR_NOT_REACHABLE")
    if sum(counts.values()) != len(postgres):
        deny("CLASSIFICATION_INCOMPLETE")
    for key, target in (("SOURCE", "SOURCE"), ("DEMO", "DEMO")):
        observed = deps.get("SUPABASE_N8N_REACHABLE_" + key + "_POSTGRES_NODES")
        if observed != str(counts[target]):
            deny("P3_SOURCE_COUNT_MISMATCH")
    if counts["DEMO"] != len(bound):
        deny("P3_EXECUTOR_COUNT_MISMATCH")

    identity = {
        "workflow_id": n8n["workflow_id"],
        "node_count": expected_count,
        "snapshot_workflow_fingerprint": snapshot.get("fingerprint"),
        "g1_result": state,
    }
    # Do not echo raw workflow/secret payload; fingerprint is for review only.
    evidence_fingerprint = sha256(json.dumps(
        {"identity": identity, "deps": {
            k: deps[k] for k in sorted(deps) if k.startswith("SUPABASE_")
        }, "node_references": [(x["node_id"], x["destination_at_p3_audit"]) for x in rows]},
        sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return {
        "contract": "p3-reachable-postgres-decision-draft-v1",
        "status": "REVIEW_ONLY_NOT_A_CUTOVER_GATE",
        "provenance": "G1_PREPUT_SNAPSHOT_CORRELATED_WITH_P3_LOCAL_AUDIT",
        "published_attestation": "REQUIRES_SEPARATE_G1_RECONCILIATION",
        "classification_basis": "G1_EXACT_NONBINDING_NODES_AND_P3_COUNTS_ONLY",
        "post_put_credential_reference_count": len(credential_ids_after_put),
        "mapping_approved": False,
        "operational_cutover_authorized": False,
        "real_financial_sql_executed": False,
        "llm_calls": 0,
        "workflow": identity,
        "source_node_ordinals": [x["snapshot_ordinal"] for x in rows if x["destination_at_p3_audit"] == "SOURCE"],
        "demo_executor_ordinals": [x["snapshot_ordinal"] for x in rows if x["destination_at_p3_audit"] == "DEMO"],
        "source_node_count": counts["SOURCE"],
        "demo_executor_count": counts["DEMO"],
        "evidence_fingerprint": evidence_fingerprint,
        "shadow_evidence_target_at_p3_audit": deps.get("SUPABASE_SHADOW_EVIDENCE_TARGET", "UNKNOWN"),
        "node_review": rows,
    }


def _write_private_draft(path: Path, doc: Mapping[str, Any]) -> None:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        deny("PRIVATE_POSIX_REQUIRED")
    try:
        parent = path.parent.stat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid()
                or parent.st_mode & 0o077):
            deny("PRIVATE_DIRECTORY_REQUIRED")
        content = (json.dumps(doc, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")
        if len(content) > 300000:
            deny("PRIVATE_REPORT_TOO_LARGE")
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=False) as file:
                file.write(content)
        finally:
            os.close(fd)
    except ReviewBlocked:
        raise
    except OSError:
        deny("PRIVATE_REPORT_WRITE_BLOCKED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", required=True, type=Path)
    parser.add_argument("--policy", type=Path, default=Path(__file__).with_name("g1_readonly_rollout.json"))
    parser.add_argument("--snapshot", type=Path, default=Path.home() / ".local/state/agente-sql-langgraph/g1-readonly-snapshot.json")
    args = parser.parse_args(argv)
    try:
        from scripts.operations.g1_readonly_rollout import load_config, _load_verified_snapshot
        from scripts.operations.p3_source_alignment_readonly import read_private_proof
        config = load_config(args.policy)
        snapshot = _load_verified_snapshot(args.snapshot, config)
        proof_dir = args.audit_dir
        if proof_dir.is_symlink():
            deny("PRIVATE_DIRECTORY_REQUIRED")
        g1 = read_private_proof(proof_dir / "g1-proof.txt")
        deps = read_private_proof(proof_dir / "dependency-proof.txt")
        report = review_existing_proofs(policy=config.raw, snapshot=snapshot, g1=g1, deps=deps)
        _write_private_draft(proof_dir / "p3-source-node-review.json", report)
        print("P3_NODE_REVIEW=OFFLINE_DRAFT_CREATED")
        print("P3_REVIEW_SOURCE_NODE_COUNT=" + str(report["source_node_count"]))
        print("P3_REVIEW_DEMO_EXECUTOR_COUNT=" + str(report["demo_executor_count"]))
        print("P3_REVIEW_SOURCE_ORDINALS=" + ",".join(map(str, report["source_node_ordinals"])))
        print("P3_REVIEW_EXECUTOR_ORDINALS=" + ",".join(map(str, report["demo_executor_ordinals"])))
        print("P3_REVIEW_G1_STATUS=" + report["workflow"]["g1_result"])
        print("P3_REVIEW_CUTOVER_AUTHORIZED=false")
        print("P3_REVIEW_FINANCIAL_SQL_EXECUTED=false")
        print("P3_REVIEW_LLM_CALLS=0")
        return 0
    except ReviewBlocked as exc:
        print("P3_NODE_REVIEW=BLOCKED")
        print("P3_NODE_REVIEW_REASON=" + exc.code)
        return 2
    except Exception:
        # Snapshot import, SQL/provider/CLI errors can contain sensitive data.
        print("P3_NODE_REVIEW=BLOCKED")
        print("P3_NODE_REVIEW_REASON=PRIVATE_EVIDENCE_UNAVAILABLE")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
