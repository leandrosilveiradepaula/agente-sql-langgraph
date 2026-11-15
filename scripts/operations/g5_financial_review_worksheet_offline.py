"""Generate private G5 financial/physical reviewer worksheets, never an approval.

Read the real G5 and P3 originals only after SHA/contract verification.
No business-specific rules, schema aliases, SQL, LLM or benchmark data.
The templates deliberately cannot pass the approval verifier until humans
individually review the rows, map to approved canonical context, and a
different authority signs the provenance-bound result.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path

from scripts.operations.g5_financial_crosswalk_review import (
    FinancialReviewBlocked, draft,
)
from scripts.operations.g5_financial_crosswalk_review_cli import private_bytes, private_json
from scripts.operations.g5_p3_original_physical_worklist import make_worklist
from scripts.operations.g5_targeted_financial_review_offline import (
    ReviewBlocked, select_verified_seal, verify_decrypted_packet,
    write_private_once,
)


def denied(code: str) -> None:
    raise FinancialReviewBlocked(code)


def build_review_templates(
    *, packet: dict, packet_sha256: str, financial_draft: dict,
    p3_bytes: bytes,
) -> tuple[dict, dict]:
    if financial_draft != draft(packet, packet_sha256):
        denied("G5_FINANCIAL_REVIEW_TEMPLATE_NOT_PRISTINE")
    worklist, counts = make_worklist(packet, p3_bytes)
    original = packet["origin"]
    source_version = original["source_version_sha256"]
    p3_sha = original["p3_snapshot_sha256"]
    physical = []
    evidence = []
    for row in worklist["physical_references"]:
        key = {
            "collection": row["collection"],
            "source_row_sha256": row["source_row_sha256"],
        }
        physical.append({
            **key,
            "qualified_table": None,
            "target_column": None,
            "physical_remap_evidence_sha256": None,
            "matching_name_candidates_unapproved":
                row["physical_options_not_selected"],
            "source_schema": row["legacy_schema"],
            "source_table": row["legacy_table"],
            "source_column": row["legacy_column"],
        })
        evidence.append({
            **key,
            "source_schema": row["legacy_schema"],
            "source_table": row["legacy_table"],
            "source_column": row["legacy_column"],
            "qualified_table": None,
            "target_column": None,
            "review_rationale": None,
        })
    workbook = {
        "contract": "g5-human-financial-review-worksheet-unapproved-v1",
        "status": "PRIVATE_REVIEW_PENDING_NO_APPROVAL",
        "source_version_sha256": source_version,
        "packet_plaintext_sha256": packet_sha256,
        "p3_snapshot_sha256": p3_sha,
        "original_financial_row_count": len(financial_draft["rows"]),
        "original_physical_binding_count": counts["original_hint_rows"],
        "tenant_id": None,
        "semantic_agent_version": None,
        "context_fingerprint": None,
        "reviewer_id": None,
        "prepared_by": None,
        "financial_source_rows": financial_draft["rows"],
        "physical_binding_decisions": physical,
        "approved_context_file": None,
        "independent_financial_signature_file": None,
        "accounting_approved": False,
        "context_activated": False,
        "benchmark_used": False,
        "financial_sql_executed": False,
    }
    remap = {
        # Intentionally a DIFFERENT contract, impossible for a verifier to accept.
        "contract": "g5-physical-remap-evidence-DRAFT-unapproved-v1",
        "source_version_sha256": source_version,
        "packet_plaintext_sha256": packet_sha256,
        "p3_snapshot_sha256": p3_sha,
        "tenant_id": None,
        "semantic_agent_version": None,
        "prepared_by": None,
        "reviewer_id": None,
        "remaps": evidence,
    }
    if (
        len(workbook["financial_source_rows"]) != sum(packet["row_counts"].values())
        or len(physical) != len(evidence)
        or len(physical) != len(packet["physical_identifier_hints_unapproved"])
    ):
        denied("G5_PRIVATE_REVIEW_WORKSHEET_COVERAGE_MISMATCH")
    return workbook, remap


def prepare(
    *, manifest: Path, source_version: str, packet_path: Path,
    p3_path: Path, financial_draft_path: Path, workbook_out: Path,
    remap_out: Path,
) -> dict[str, int]:
    if os.name != "posix":
        denied("G5_PRIVATE_REVIEW_POSIX_REQUIRED")
    seal = select_verified_seal(private_json(manifest), source_version)
    packet, integrity = verify_decrypted_packet(private_bytes(packet_path), seal)
    financial_draft = private_json(financial_draft_path)
    workbook, remap = build_review_templates(
        packet=packet,
        packet_sha256=integrity["packet_plaintext_sha256"],
        financial_draft=financial_draft,
        p3_bytes=private_bytes(p3_path, 3_000_000),
    )
    if workbook_out == remap_out:
        denied("G5_REVIEW_OUTPUT_PATH_COLLISION")
    for target in (workbook_out, remap_out):
        if (
            not target.is_absolute() or target.is_symlink() or target.exists()
            or target.parent != packet_path.parent
            or target.parent.stat().st_uid != os.geteuid()
            or stat.S_IMODE(target.parent.stat().st_mode) != 0o700
        ):
            denied("G5_REVIEW_PRIVATE_OUTPUT_REQUIRED")
    for target, payload in ((workbook_out, workbook), (remap_out, remap)):
        raw = (json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))+"\n").encode()
        if not 0 < len(raw) <= 8_000_000:
            denied("G5_REVIEW_OUTPUT_TOO_LARGE")
        write_private_once(target, raw)
    return {
        "original_source_rows": len(workbook["financial_source_rows"]),
        "original_physical_binding_rows": len(workbook["physical_binding_decisions"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "source-version-sha256", "packet-file",
                 "p3-file", "financial-draft-file", "output-workbook",
                 "output-remap-draft"):
        parser.add_argument("--"+name, required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare(
            manifest=Path(args.manifest),
            source_version=args.source_version_sha256,
            packet_path=Path(args.packet_file),
            p3_path=Path(args.p3_file),
            financial_draft_path=Path(args.financial_draft_file),
            workbook_out=Path(args.output_workbook),
            remap_out=Path(args.output_remap_draft),
        )
    except (OSError, ValueError, FinancialReviewBlocked, ReviewBlocked):
        print("G5_PRIVATE_REVIEW_WORKSHEETS=BLOCKED")
        print("SQL_EXECUTED=false")
        return 2
    print("G5_PRIVATE_REVIEW_WORKSHEETS=PASS")
    for key, val in sorted(result.items()):
        print("G5_"+key.upper()+"="+str(val))
    print("G5_FINANCIAL_APPROVAL=false")
    print("G5_GENERATOR_CONTEXT_USED=false")
    print("SQL_EXECUTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
