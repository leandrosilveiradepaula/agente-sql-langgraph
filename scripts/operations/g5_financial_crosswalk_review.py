"""Offline G5 row-to-catalog review: no inference, LLM, SQL, import or activation."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any

from app.domain.context_normalizer import (
    ContextNormalizationError, normalize_context_snapshot,
)
from app.domain.context_validator import validate_context_snapshot
from app.domain.canonical_source_boundary import (
    CanonicalSourceBoundaryError, require_structural_patterns_only,
)

SHA = re.compile(r"^[0-9a-f]{64}$")
IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
DESTINATIONS = frozenset({
    "rules", "entities", "dre_mappings", "table_catalog",
    "metric_source_compositions",
})


class FinancialReviewBlocked(ValueError):
    """Missing independently verified business meaning or physical lineage."""


def deny(code: str) -> None:
    raise FinancialReviewBlocked(code)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("ascii")).hexdigest()


def source_ids(packet: Mapping[str, Any]) -> set[tuple[str, str]]:
    if not isinstance(packet, Mapping):
        deny("G5_PACKET_INVALID")
    origin = packet.get("origin")
    collections = packet.get("collections")
    if (
        not isinstance(origin, Mapping)
        or not isinstance(origin.get("source_version_sha256"), str)
        or not SHA.fullmatch(origin["source_version_sha256"])
        or packet.get("status") != "QUARANTINED_SOURCE_EVIDENCE_UNAPPROVED"
        or packet.get("financial_semantics_equivalence") != "NOT_ATTESTED"
        or packet.get("historical_sql_patterns_excluded") is not True
        or packet.get("can_import_into_semantic_catalog") is not False
        or packet.get("can_use_as_llm_or_planner_context") is not False
        or packet.get("can_execute_financial_sql") is not False
        or not isinstance(collections, Mapping) or not collections
        or not isinstance(packet.get("row_counts"), Mapping)
        or set(collections) != set(packet["row_counts"])
    ):
        deny("G5_QUARANTINE_OR_VERSION_UNVERIFIED")
    seen: set[str] = set()
    records: set[tuple[str, str]] = set()
    for collection, rows in collections.items():
        if (
            not isinstance(collection, str) or not 1 <= len(collection) <= 128
            or not isinstance(rows, list) or len(rows) != packet["row_counts"][collection]
        ):
            deny("G5_COLLECTION_INCOMPLETE")
        for row in rows:
            ref = row.get("source_row_sha256") if isinstance(row, Mapping) else None
            if not isinstance(ref, str) or not SHA.fullmatch(ref) or ref in seen:
                deny("G5_RECORD_PROVENANCE_INVALID")
            seen.add(ref)
            records.add((collection, ref))
            if len(records) > 50000:
                deny("G5_RECORD_LIMIT")
    if not records:
        deny("G5_EMPTY_REVIEW")
    return records


def draft(packet: Mapping[str, Any], packet_sha256: str) -> dict[str, Any]:
    """Private human-review queue of references ONLY, never source values."""
    if not isinstance(packet_sha256, str) or not SHA.fullmatch(packet_sha256):
        deny("G5_PACKET_SHA_INVALID")
    rows = source_ids(packet)
    return {
        "contract": "g5-financial-crosswalk-review-v1",
        "source_version_sha256": packet["origin"]["source_version_sha256"],
        "packet_plaintext_sha256": packet_sha256,
        "tenant_id": None,
        "semantic_agent_version": None,
        "context_fingerprint": None,
        "reviewer_id": None,
        "rows": [
            {"collection": c, "source_row_sha256": r,
             "classification": "UNRESOLVED", "destinations": []}
            for c, r in sorted(rows)
        ],
        "accounting_approved": False,
        "ready_for_generation": False,
        "benchmark_used": False,
        "financial_sql_executed": False,
    }


def verified_review(
    *,
    packet: Mapping[str, Any],
    packet_sha256: str,
    source_packet_bytes: bytes,
    trusted_seal: Mapping[str, Any],
    review: Mapping[str, Any],
    raw_context: Mapping[str, Any],
    approval_receipt: Mapping[str, Any] | None,
    verifier_key: bytes | None,
    p3_snapshot_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Require exact row coverage AND independent signed accounting decision.

    Success produces only a nonactivated migration candidate, not a runtime
    approval. The signer must be independent of the review author.
    """
    if (
        not isinstance(source_packet_bytes, bytes)
        or not 0 < len(source_packet_bytes) <= 8_000_000
        or not isinstance(trusted_seal, Mapping)
        or not isinstance(packet_sha256, str)
        or not SHA.fullmatch(packet_sha256)
        or hashlib.sha256(source_packet_bytes).hexdigest() != packet_sha256
        or trusted_seal.get("plaintext_sha256") != packet_sha256
        or trusted_seal.get("source_version_sha256") != (
            packet.get("origin", {}).get("source_version_sha256")
        )
        or trusted_seal.get("sealed_and_roundtrip_verified") is not True
    ):
        deny("G5_TRUSTED_SEAL_NOT_VERIFIED")
    try:
        if json.loads(source_packet_bytes) != packet:
            deny("G5_PACKET_CONTENT_CHANGED")
    except (ValueError, UnicodeError, TypeError):
        deny("G5_PACKET_CONTENT_INVALID")
    expected = source_ids(packet)
    template = draft(packet, packet_sha256)
    if (
        not isinstance(review, Mapping)
        or any(review.get(key) != template[key] for key in (
            "contract", "source_version_sha256", "packet_plaintext_sha256",
            "accounting_approved", "ready_for_generation",
            "benchmark_used", "financial_sql_executed",
        ))
        or not isinstance(review.get("rows"), list)
        or len(review["rows"]) != len(expected)
        or not isinstance(raw_context, Mapping)
    ):
        deny("G5_FINANCIAL_REVIEW_PROVENANCE_INVALID")
    tenant, version, reviewer = (
        review.get("tenant_id"),
        review.get("semantic_agent_version"),
        review.get("reviewer_id"),
    )
    if (
        not all(isinstance(v, str) and IDENTITY.fullmatch(v)
                for v in (tenant, version, reviewer))
        or raw_context.get("tenant_id") != tenant
        or raw_context.get("semantic_agent_version") != version
        or raw_context.get("source_approval_status") != "APPROVED"
        or raw_context.get("historical_evaluation_sql_excluded") is not True
    ):
        deny("G5_TENANT_CONTEXT_PROVENANCE_INVALID")
    try:
        require_structural_patterns_only(raw_context)
        snapshot = normalize_context_snapshot(raw_context)
        result = validate_context_snapshot(snapshot)
    except (ContextNormalizationError, CanonicalSourceBoundaryError, TypeError, ValueError):
        deny("G5_CONTEXT_STRUCTURE_INVALID")
    if (
        result.get("status") != "valid"
        or review.get("context_fingerprint") != snapshot["fingerprint"]
    ):
        deny("G5_CONTEXT_UNAPPROVED_OR_DRIFT")
    present: set[tuple[str, str]] = set()
    classified = {"STRUCTURAL": 0, "FORBIDDEN": 0}
    for item in review["rows"]:
        if not isinstance(item, Mapping) or set(item) != {
            "collection", "source_row_sha256", "classification", "destinations",
        }:
            deny("G5_REVIEW_ROW_INVALID")
        if (
            not isinstance(item.get("collection"), str)
            or not isinstance(item.get("source_row_sha256"), str)
        ):
            deny("G5_REVIEW_REFERENCE_INVALID")
        key = (item["collection"], item["source_row_sha256"])
        if key not in expected or key in present:
            deny("G5_ROW_COVERAGE_INVALID")
        present.add(key)
        category, targets = item["classification"], item["destinations"]
        if not isinstance(category, str) or category not in classified:
            deny("G5_UNRESOLVED_OR_TRANSITIONAL_BUSINESS")
        if (
            not isinstance(targets, list)
            or len(targets) > 24
            or (category == "STRUCTURAL" and targets)
            or (category == "FORBIDDEN" and not targets)
        ):
            deny("G5_BUSINESS_MAPPING_MISSING_OR_UNSAFE")
        unique: set[tuple[str, int]] = set()
        for target in targets:
            if not isinstance(target, Mapping) or set(target) != {"collection", "index"}:
                deny("G5_TARGET_NOT_CANONICAL")
            collection, index = target.get("collection"), target.get("index")
            if (
                not isinstance(collection, str)
                or collection not in DESTINATIONS
                or type(index) is not int or index < 0
                or (collection, index) in unique
                or not isinstance(snapshot.get(collection), list)
                or index >= len(snapshot[collection])
                or not isinstance(snapshot[collection][index], Mapping)
            ):
                deny("G5_TARGET_CONTEXT_NOT_BOUND")
            unique.add((collection, index))
        classified[category] += 1
    if present != expected:
        deny("G5_SOURCE_REVIEW_INCOMPLETE")
    # Real G5 source snapshots carry unapproved P3 hints, including
    # duplicate physical table names across schemas. An accountant's
    # approval cannot silently select a schema without independently
    # anchored physical metadata and explicit, signed source bindings.
    from scripts.operations.g5_physical_source_evidence import (
        physical_approval_claims,
    )
    physical_claims = physical_approval_claims(
        packet=packet, review=review,
        approved_catalog=snapshot["table_catalog"],
        p3_bytes=p3_snapshot_bytes,
    )
    row_hash = digest(sorted(
        review["rows"], key=lambda item: (item["collection"], item["source_row_sha256"]),
    ))
    claims = {
        "decision": "APPROVE_G5_FINANCIAL_CROSSWALK",
        "tenant_id": tenant,
        "semantic_agent_version": version,
        "reviewer_id": reviewer,
        "context_fingerprint": snapshot["fingerprint"],
        "source_version_sha256": packet["origin"]["source_version_sha256"],
        "packet_plaintext_sha256": packet_sha256,
        "review_rows_sha256": row_hash,
        **physical_claims,
    }
    if (
        not isinstance(approval_receipt, Mapping)
        or set(approval_receipt) != {"contract", "claims", "hmac_sha256"}
        or approval_receipt.get("contract") != "g5-independent-financial-approval-v1"
        or approval_receipt.get("claims") != claims
        or not isinstance(verifier_key, bytes) or len(verifier_key) < 32
        or not isinstance(approval_receipt.get("hmac_sha256"), str)
        or not SHA.fullmatch(approval_receipt["hmac_sha256"])
        or not hmac.compare_digest(
            hmac.new(
                verifier_key, digest(claims).encode("ascii"), hashlib.sha256,
            ).hexdigest(), approval_receipt["hmac_sha256"],
        )
    ):
        deny("G5_INDEPENDENT_APPROVAL_REQUIRED")
    return {
        "status": "G5_FINANCIAL_MAPPING_CANDIDATE_NOT_ACTIVATED",
        "source_version_sha256": claims["source_version_sha256"],
        "context_fingerprint": claims["context_fingerprint"],
        "review_rows_sha256": row_hash,
        "attestation_sha256": digest(approval_receipt),
        "reviewed_rows": len(present),
        "classifications": classified,
        "activation_authorized": False,
        "context_persisted": False,
        "financial_sql_executed": False,
        "benchmark_used": False,
        "raw_business_values_returned": False,
    }
