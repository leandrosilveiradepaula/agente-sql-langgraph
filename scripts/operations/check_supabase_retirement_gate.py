#!/usr/bin/env python3
"""Read-only Supabase retirement gate on *sanitized* consumer attestations.

No network, env secret reads, PostgreSQL connections or n8n modification.
Each consumer must be attested by a separately executed, real runtime check.
Never store DSNs, usernames, hosts, credentials or raw config in the input.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ALLOWED_DESTINATIONS = frozenset(("DEMO", "SOURCE", "OTHER", "UNKNOWN"))
ALLOWED_CONSUMERS = frozenset((
    "product_primary", "product_demo", "n8n_official",
    "n8n_shadow", "langgraph_shadow_evidence", "langgraph_semantic_context",
))
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,90}$")
SAFE_SHA = re.compile(r"^[0-9a-f]{40}$")
SAFE_TIME = re.compile(r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
# V2 deliberately rejects legacy V1 'archive_verified=True': a restore can
# succeed without durable off-host custody, tenant isolation or complete
# managed-platform recovery. Gate labels describe PLATFORM PROCESS only, never
# client-specific tables, aliases, financial metrics or semantic mappings.
TOP_KEYS = frozenset(("schema_version", "consumers", "gates"))
ITEM_KEYS = frozenset(("consumer", "destination", "verified_at",
                        "evidence_sha", "probe_id"))
GATE_KEYS = frozenset(("gate", "status", "verified_at",
                       "evidence_sha", "probe_id"))
REQUIRED_GATES = frozenset((
    "isolated_archive_restore", "offsite_ciphertext_custody",
    "managed_platform_scope", "identity_and_access",
    "tenant_isolation", "semantic_portability",
    "functional_financial_parity", "final_data_synchronization",
    "rollback", "observation", "human_retirement_approval",
))
SAFE_SHA256 = re.compile(r"^[0-9a-f]{64}$")

def analyze(data: object) -> tuple[str, list[str]]:
    """Fail closed, including when attestations are missing or malformed."""
    if not isinstance(data, dict):
        return "BLOCKED", ["INVALID_MANIFEST"]
    if data.get("schema_version") != 2 or type(data.get("schema_version")) is not int:
        return "BLOCKED", ["INVALID_VERSION"]
    if set(data) != TOP_KEYS:
        return "BLOCKED", ["INVALID_MANIFEST"]
    consumers = data.get("consumers")
    if not isinstance(consumers, list) or len(consumers) != len(ALLOWED_CONSUMERS):
        return "BLOCKED", ["INCOMPLETE_CONSUMERS"]
    seen: set[str] = set()
    blockers: list[str] = []
    for item in consumers:
        if not isinstance(item, dict) or set(item) != ITEM_KEYS:
            return "BLOCKED", ["INVALID_CONSUMER_RECORD"]
        name, destination = item["consumer"], item["destination"]
        if name not in ALLOWED_CONSUMERS or name in seen or destination not in ALLOWED_DESTINATIONS:
            return "BLOCKED", ["INVALID_CONSUMER_IDENTITY_OR_DESTINATION"]
        if (not isinstance(item["probe_id"], str) or
            not SAFE_ID.fullmatch(item["probe_id"]) or
            not isinstance(item["evidence_sha"], str) or
            not SAFE_SHA.fullmatch(item["evidence_sha"]) or
            not isinstance(item["verified_at"], str) or
            not SAFE_TIME.fullmatch(item["verified_at"])):
            return "BLOCKED", ["UNVERIFIED_CONSUMER"]
        seen.add(name)
        # OTHER is admissible only with a separate evidence attestation;
        # it may legitimately represent an independent external warehouse.
        if destination in ("SOURCE", "UNKNOWN"):
            blockers.append("CONSUMER_DEPENDS_ON_SOURCE_OR_UNKNOWN:" + name)
    if seen != ALLOWED_CONSUMERS:
        return "BLOCKED", ["MISSING_CONSUMER"]
    gates = data.get("gates")
    if not isinstance(gates, list) or len(gates) != len(REQUIRED_GATES):
        return "BLOCKED", ["INCOMPLETE_GATES"]
    seen_gates: set[str] = set()
    for record in gates:
        if not isinstance(record, dict) or set(record) != GATE_KEYS:
            return "BLOCKED", ["INVALID_GATE_RECORD"]
        gate = record.get("gate")
        if gate not in REQUIRED_GATES or gate in seen_gates:
            return "BLOCKED", ["INVALID_GATE_IDENTITY"]
        seen_gates.add(gate)
        status = record.get("status")
        if status == "PENDING":
            if any(record[k] is not None for k in (
                "verified_at", "evidence_sha", "probe_id",
            )):
                return "BLOCKED", ["INVALID_PENDING_GATE"]
            blockers.append("GATE_NOT_ATTESTED:" + gate)
        elif status == "PASS":
            if (not isinstance(record.get("verified_at"), str)
                    or not SAFE_TIME.fullmatch(record["verified_at"])
                    or not isinstance(record.get("evidence_sha"), str)
                    or not SAFE_SHA256.fullmatch(record["evidence_sha"])
                    or not isinstance(record.get("probe_id"), str)
                    or not SAFE_ID.fullmatch(record["probe_id"])):
                return "BLOCKED", ["UNVERIFIED_GATE_EVIDENCE:" + gate]
        else:
            return "BLOCKED", ["INVALID_GATE_STATUS"]
    if seen_gates != REQUIRED_GATES:
        return "BLOCKED", ["MISSING_GATE"]
    # A real human approval is STILL required before retirement. A manifest
    # claiming this field without proof is not an operational authorization.
    return ("READY" if not blockers else "BLOCKED"), sorted(blockers)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        # Hard ceiling prevents accidentally ingesting dumps or raw secrets.
        if args.manifest.stat().st_size > 16384:
            raise ValueError("FILE_TOO_LARGE")
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
        result, blockers = analyze(data)
    except (OSError, ValueError, UnicodeError):
        result, blockers = "BLOCKED", ["INVALID_OR_UNREADABLE_MANIFEST"]
    print("SUPABASE_RETIREMENT_GATE=" + result)
    for b in blockers:
        print("SUPABASE_RETIREMENT_BLOCKER=" + b)
    return 0 if result == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
