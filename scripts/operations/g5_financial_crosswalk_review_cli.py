"""Read-only private CLI: match original G5 rows to independently approved context.

This command NEVER decrypts, connects to a database, calls an LLM, executes
SQL, writes a canonical context or signs its own accounting approval.
Prerequisites: local targeted G5 review has produced an owner-only plaintext
packet, an accountant has reviewed the complete private matrix, and a
different authority signed the exact row-version-context claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

from scripts.operations.g5_financial_crosswalk_review import (
    FinancialReviewBlocked, verified_review,
)
from scripts.operations.g5_targeted_financial_review_offline import (
    ReviewBlocked, select_verified_seal, verify_decrypted_packet,
)

_MAX_JSON = 8_000_000


def private_bytes(path: Path, limit: int = _MAX_JSON) -> bytes:
    if (
        not path.is_absolute()
        or path.is_symlink()
        or path.parent.is_symlink()
        or not path.is_file()
        or not path.parent.is_dir()
        or stat.S_IMODE(path.stat().st_mode) & 0o077
        or stat.S_IMODE(path.parent.stat().st_mode) & 0o077
    ):
        raise FinancialReviewBlocked("PRIVATE_FILE_PERMISSIONS_INVALID")
    handle = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        data = os.read(handle, limit + 1)
    finally:
        os.close(handle)
    if not 0 < len(data) <= limit:
        raise FinancialReviewBlocked("PRIVATE_FILE_SIZE_INVALID")
    return data


def private_json(path: Path) -> dict:
    try:
        result = json.loads(private_bytes(path))
    except (ValueError, UnicodeError, TypeError):
        raise FinancialReviewBlocked("PRIVATE_JSON_INVALID") from None
    if not isinstance(result, dict):
        raise FinancialReviewBlocked("PRIVATE_JSON_OBJECT_REQUIRED")
    return result


def verify_private_review(
    *,
    manifest_path: Path,
    source_version_sha256: str,
    packet_path: Path,
    n8n_binding_evidence_path: Path,
    review_path: Path,
    context_path: Path,
    approval_path: Path,
    verification_key_path: Path,
    p3_metadata_path: Path | None = None,
    remap_evidence_path: Path | None = None,
) -> dict:
    manifest = private_json(manifest_path)
    seal = select_verified_seal(manifest, source_version_sha256)
    legacy_evidence = private_json(n8n_binding_evidence_path)
    pinned = legacy_evidence.get("pinned_source_version_reconciliation")
    if (
        legacy_evidence.get("contract") != "legacy-semantic-static-coupling-audit-v1"
        or legacy_evidence.get("status") != "SOURCE_REVIEW_ONLY_NOT_FINANCIAL_EQUIVALENCE"
        or legacy_evidence.get("node_count") != 68
        or not isinstance(pinned, dict)
        or pinned.get("status") != "PINNED_VERSION_MATCHES_SEALED_G5"
        or pinned.get("pinned_version_hashes") != [source_version_sha256]
        or pinned.get("matching_source_version_sha256") != source_version_sha256
        or pinned.get("matching_manifest_row_counts") != seal["row_counts"]
        or pinned.get("accounting_definition_approved") is not False
        or pinned.get("source_plaintext_reviewed") is not False
    ):
        raise FinancialReviewBlocked("N8N_PUBLISHED_SOURCE_VERSION_NOT_BOUND")
    ciphertext = manifest_path.parent / seal["file"]
    if hashlib.sha256(private_bytes(ciphertext)).hexdigest() != seal["ciphertext_sha256"]:
        raise FinancialReviewBlocked("G5_CIPHERTEXT_SOURCE_CHANGED")
    content = private_bytes(packet_path)
    packet, integrity = verify_decrypted_packet(content, seal)
    if integrity.get("source_row_count") != sum(seal["row_counts"].values()):
        raise FinancialReviewBlocked("G5_RECORD_COUNT_DRIFT")
    key_bytes = private_bytes(verification_key_path, 1024)
    try:
        verification_key = bytes.fromhex(key_bytes.decode("ascii").strip())
    except (ValueError, UnicodeError):
        raise FinancialReviewBlocked("APPROVAL_VERIFICATION_KEY_INVALID") from None
    if len(verification_key) < 32:
        raise FinancialReviewBlocked("APPROVAL_VERIFICATION_KEY_INVALID")
    return verified_review(
        packet=packet,
        packet_sha256=integrity["packet_plaintext_sha256"],
        source_packet_bytes=content,
        trusted_seal=seal,
        review=private_json(review_path),
        raw_context=private_json(context_path),
        approval_receipt=private_json(approval_path),
        verifier_key=verification_key,
        p3_snapshot_bytes=(
            private_bytes(p3_metadata_path, 3_000_000)
            if p3_metadata_path is not None else None
        ),
        physical_remap_evidence=(
            private_json(remap_evidence_path)
            if remap_evidence_path is not None else None
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-version-sha256", required=True)
    parser.add_argument("--packet-file", type=Path, required=True)
    parser.add_argument("--n8n-binding-evidence", type=Path, required=True)
    parser.add_argument("--review-file", type=Path, required=True)
    parser.add_argument("--context-file", type=Path, required=True)
    parser.add_argument("--approval-file", type=Path, required=True)
    parser.add_argument("--verification-key-file", type=Path, required=True)
    parser.add_argument("--p3-metadata-file", type=Path)
    parser.add_argument("--physical-remap-evidence-file", type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_private_review(
            manifest_path=args.manifest,
            source_version_sha256=args.source_version_sha256,
            packet_path=args.packet_file,
            n8n_binding_evidence_path=args.n8n_binding_evidence,
            review_path=args.review_file,
            context_path=args.context_file,
            approval_path=args.approval_file,
            verification_key_path=args.verification_key_file,
            p3_metadata_path=args.p3_metadata_file,
            remap_evidence_path=args.physical_remap_evidence_file,
        )
    except (FinancialReviewBlocked, ReviewBlocked, OSError, ValueError):
        print("G5_FINANCIAL_MAPPING=BLOCKED")
        print("G5_ACCOUNTING_APPROVAL_VALIDATED=false")
        print("LANGGRAPH_CONTEXT_ACTIVATED=false")
        return 2
    print("G5_FINANCIAL_MAPPING=" + result["status"])
    print("G5_FINANCIAL_MAPPING_ROWS=" + str(result["reviewed_rows"]))
    print("G5_FINANCIAL_SOURCE_VERSION_SHA256=" + result["source_version_sha256"])
    print("G5_FINANCIAL_CONTEXT_FINGERPRINT=" + result["context_fingerprint"])
    print("LANGGRAPH_CONTEXT_ACTIVATED=false")
    print("SQL_EXECUTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
