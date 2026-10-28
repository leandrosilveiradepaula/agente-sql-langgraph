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
TOP_KEYS = frozenset(("schema_version", "consumers", "archive_verified",
                       "rollback_verified", "observation_verified",
                       "retirement_explicitly_approved"))
ITEM_KEYS = frozenset(("consumer", "destination", "verified_at",
                        "evidence_sha", "probe_id"))

def analyze(data: object) -> tuple[str, list[str]]:
    """Fail closed, including when attestations are missing or malformed."""
    if not isinstance(data, dict) or set(data) != TOP_KEYS:
        return "BLOCKED", ["INVALID_MANIFEST"]
    if data.get("schema_version") != 1:
        return "BLOCKED", ["INVALID_VERSION"]
    for field in ("archive_verified", "rollback_verified",
                  "observation_verified", "retirement_explicitly_approved"):
        if type(data.get(field)) is not bool:
            return "BLOCKED", ["INVALID_ATTESTATION"]
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
    for field in ("archive_verified", "rollback_verified", "observation_verified",
                  "retirement_explicitly_approved"):
        if data[field] is not True:
            blockers.append("GATE_NOT_ATTESTED:" + field)
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
