"""Compile a HUMAN-completed G5/P3 worksheet into UNSIGNED review artifacts.

Never classifies business content, selects source tables, signs a receipt,
imports context, calls LLMs, queries a database or uses benchmark data.
Approved semantics must come from the independent reviewer's completed
private worksheet and a separately approved versioned tenant catalog.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.domain.context_normalizer import (
    ContextNormalizationError, normalize_context_snapshot,
)
from app.domain.context_validator import validate_context_snapshot
from scripts.operations.g5_financial_crosswalk_review import (
    DESTINATIONS, FinancialReviewBlocked, digest, draft, source_ids,
)
from scripts.operations.g5_financial_crosswalk_review_cli import (
    private_bytes, private_json,
)
from scripts.operations.g5_financial_review_worksheet_offline import (
    build_review_templates,
)
from scripts.operations.g5_physical_source_evidence import (
    original_physical_reference, physical_approval_claims,
)
from scripts.operations.g5_targeted_financial_review_offline import (
    ReviewBlocked, select_verified_seal, verify_decrypted_packet,
    write_private_once,
)
from app.domain.canonical_source_boundary import (
    CanonicalSourceBoundaryError, require_structural_patterns_only,
)


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def deny(reason: str) -> None:
    raise FinancialReviewBlocked(reason)


def _identity(value: object) -> bool:
    return isinstance(value, str) and bool(_ID.fullmatch(value))


def _canonical_context(context: Mapping, workbook: Mapping) -> dict:
    if (
        not isinstance(context, Mapping)
        or context.get("source_approval_status") != "APPROVED"
        or context.get("historical_evaluation_sql_excluded") is not True
        or not all(_identity(workbook.get(k)) for k in (
            "tenant_id", "semantic_agent_version", "reviewer_id", "prepared_by"
        ))
        or workbook["reviewer_id"] == workbook["prepared_by"]
        or context.get("tenant_id") != workbook["tenant_id"]
        or context.get("semantic_agent_version") != workbook["semantic_agent_version"]
    ):
        deny("G5_FINANCIAL_CONTEXT_NOT_APPROVED")
    try:
        require_structural_patterns_only(context)
        snapshot = normalize_context_snapshot(context)
        validated = validate_context_snapshot(snapshot)
    except (ContextNormalizationError, CanonicalSourceBoundaryError, ValueError, TypeError):
        deny("G5_FINANCIAL_CONTEXT_INVALID")
    if (
        validated.get("status") != "valid"
        or snapshot.get("fingerprint") != workbook.get("context_fingerprint")
    ):
        deny("G5_FINANCIAL_CONTEXT_FINGERPRINT_MISMATCH")
    return snapshot


def _review_financial_rows(workbook: Mapping, draft_rows: list, snapshot: Mapping) -> list:
    rows = workbook.get("financial_source_rows")
    if not isinstance(rows, list) or len(rows) != len(draft_rows):
        deny("G5_FINANCIAL_REVIEW_ROW_COVERAGE_INCOMPLETE")
    expected = {
        (row["collection"], row["source_row_sha256"]) for row in draft_rows
    }
    seen = set()
    results = []
    for item in rows:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"collection", "source_row_sha256", "classification", "destinations"}
        ):
            deny("G5_FINANCIAL_REVIEW_ROW_FORMAT_INVALID")
        key = (item["collection"], item["source_row_sha256"])
        if key not in expected or key in seen:
            deny("G5_FINANCIAL_REVIEW_ROW_UNKNOWN_OR_DUPLICATED")
        seen.add(key)
        cat, targets = item["classification"], item["destinations"]
        if (
            cat not in ("STRUCTURAL", "FORBIDDEN")
            or not isinstance(targets, list) or len(targets) > 24
            or (cat == "STRUCTURAL" and targets)
            or (cat == "FORBIDDEN" and not targets)
        ):
            deny("G5_FINANCIAL_REVIEW_PENDING_OR_UNMAPPED")
        used = set()
        for target in targets:
            if not isinstance(target, Mapping) or set(target) != {"collection", "index"}:
                deny("G5_FINANCIAL_REVIEW_TARGET_INVALID")
            bucket, index = target["collection"], target["index"]
            if (
                not isinstance(bucket, str) or bucket not in DESTINATIONS
                or type(index) is not int or index < 0
                or (bucket, index) in used
                or not isinstance(snapshot.get(bucket), list)
                or index >= len(snapshot[bucket])
            ):
                deny("G5_FINANCIAL_REVIEW_TARGET_NOT_CANONICAL")
            used.add((bucket, index))
        results.append(dict(item))
    if seen != expected:
        deny("G5_FINANCIAL_REVIEW_ROW_COVERAGE_INCOMPLETE")
    return sorted(results, key=lambda v: (v["collection"], v["source_row_sha256"]))


def compile_completed_review(
    *, packet: Mapping, packet_sha256: str, p3_bytes: bytes,
    filled_workbook: Mapping, filled_remap_draft: Mapping, approved_context: Mapping,
) -> tuple[dict, dict | None]:
    """Return two UNSIGNED candidate documents; never set approval flags."""
    financial_template = draft(packet, packet_sha256)
    workbook_template, remap_template = build_review_templates(
        packet=packet, packet_sha256=packet_sha256,
        financial_draft=financial_template, p3_bytes=p3_bytes,
    )
    if (
        not isinstance(filled_workbook, Mapping)
        or set(filled_workbook) != set(workbook_template)
        or any(filled_workbook[key] != workbook_template[key] for key in (
            "contract", "status", "source_version_sha256", "packet_plaintext_sha256",
            "p3_snapshot_sha256", "original_financial_row_count",
            "original_physical_binding_count", "independent_financial_signature_file",
            "approved_context_file", "accounting_approved", "context_activated",
            "benchmark_used", "financial_sql_executed"
        ))
        or not isinstance(filled_remap_draft, Mapping)
        or set(filled_remap_draft) != set(remap_template)
        or any(filled_remap_draft[key] != remap_template[key] for key in (
            "contract", "source_version_sha256", "packet_plaintext_sha256",
            "p3_snapshot_sha256"
        ))
    ):
        deny("G5_PRIVATE_REVIEW_WORKSHEET_PROVENANCE_CHANGED")
    snapshot = _canonical_context(approved_context, filled_workbook)
    rows = _review_financial_rows(
        filled_workbook, financial_template["rows"], snapshot,
    )
    review = {
        **financial_template,
        "tenant_id": filled_workbook["tenant_id"],
        "semantic_agent_version": filled_workbook["semantic_agent_version"],
        "context_fingerprint": snapshot["fingerprint"],
        "reviewer_id": filled_workbook["reviewer_id"],
        "rows": rows,
    }
    for field in ("tenant_id", "semantic_agent_version", "reviewer_id", "prepared_by"):
        if filled_remap_draft.get(field) != filled_workbook[field]:
            deny("G5_REMAP_REVIEW_IDENTITY_MISMATCH")
    decisions = filled_workbook.get("physical_binding_decisions")
    evidences = filled_remap_draft.get("remaps")
    template_decisions = workbook_template["physical_binding_decisions"]
    template_remaps = remap_template["remaps"]
    if (
        not isinstance(decisions, list) or len(decisions) != len(template_decisions)
        or not isinstance(evidences, list) or len(evidences) != len(template_remaps)
    ):
        deny("G5_PHYSICAL_WORKSHEET_COVERAGE_INCOMPLETE")
    expected_binding = {
        (row["collection"], row["source_row_sha256"]): row
        for row in template_decisions
    }
    expected_rationale = {
        (row["collection"], row["source_row_sha256"]): row
        for row in template_remaps
    }
    evidence_by_key = {}
    for row in evidences:
        if not isinstance(row, Mapping) or set(row) != set(template_remaps[0]):
            deny("G5_PHYSICAL_EVIDENCE_DRAFT_ROW_FORMAT_INVALID")
        key = (row["collection"], row["source_row_sha256"])
        if key not in expected_rationale or key in evidence_by_key:
            deny("G5_PHYSICAL_EVIDENCE_DRAFT_ROW_UNKNOWN_OR_DUPLICATED")
        baseline = expected_rationale[key]
        for original_key in (
            "collection", "source_row_sha256", "source_schema",
            "source_table", "source_column"
        ):
            if row[original_key] != baseline[original_key]:
                deny("G5_PHYSICAL_EVIDENCE_SOURCE_CHANGED")
        evidence_by_key[key] = row
    physical_decisions = []
    remaps = []
    hints = {
        (hint["collection"], hint["source_record_sha256"]): hint
        for hint in packet["physical_identifier_hints_unapproved"]
    }
    seen_decisions = set()
    for row in decisions:
        if not isinstance(row, Mapping) or set(row) != set(template_decisions[0]):
            deny("G5_PHYSICAL_WORKSHEET_DECISION_FORMAT_INVALID")
        key = (row["collection"], row["source_row_sha256"])
        if key not in expected_binding or key in seen_decisions:
            deny("G5_PHYSICAL_WORKSHEET_DECISION_UNKNOWN_OR_DUPLICATED")
        seen_decisions.add(key)
        baseline = expected_binding[key]
        for immutable in (
            "collection", "source_row_sha256", "matching_name_candidates_unapproved",
            "source_schema", "source_table", "source_column"
        ):
            if row[immutable] != baseline[immutable]:
                deny("G5_PHYSICAL_WORKSHEET_SOURCE_CHANGED")
        if row["physical_remap_evidence_sha256"] is not None:
            deny("G5_PHYSICAL_WORKSHEET_CANNOT_SELF_ATTEST_DIGEST")
        target = row["qualified_table"]
        column = row["target_column"]
        if not isinstance(target, str) or target.count(".") != 1:
            deny("G5_PHYSICAL_REVIEW_NOT_SELECTED")
        if not (column is None or isinstance(column, str)):
            deny("G5_PHYSICAL_REVIEW_COLUMN_INVALID")
        hint = hints[key]
        original_schema, original_table, original_column = original_physical_reference(
            packet, hint,
        )
        physical_schema, physical_table = target.split(".")
        remapped = (
            physical_table != original_table
            or (original_schema is not None and physical_schema != original_schema)
            or column != original_column
        )
        payload = evidence_by_key[key]
        if payload["qualified_table"] != target or payload["target_column"] != column:
            deny("G5_PHYSICAL_REVIEW_RATIONALE_TARGET_MISMATCH")
        entry = {
            "collection": key[0], "source_row_sha256": key[1],
            "qualified_table": target, "target_column": column,
        }
        if remapped:
            explanation = payload["review_rationale"]
            if not isinstance(explanation, str) or not explanation.strip():
                deny("G5_REMAP_JUSTIFICATION_REQUIRED")
            signed_row = dict(payload)
            entry["physical_remap_evidence_sha256"] = digest(signed_row)
            remaps.append(signed_row)
        elif payload["review_rationale"] not in (None, ""):
            deny("G5_UNNECESSARY_REMAP_JUSTIFICATION")
        physical_decisions.append(entry)
    if seen_decisions != set(expected_binding) or set(evidence_by_key) != set(expected_rationale):
        deny("G5_PHYSICAL_REVIEW_COVERAGE_INCOMPLETE")
    review["physical_binding_decisions"] = sorted(
        physical_decisions, key=lambda r: (r["collection"], r["source_row_sha256"]),
    )
    remap_document = None
    if remaps:
        remap_document = {
            "contract": "g5-physical-remap-review-evidence-v1",
            "source_version_sha256": packet["origin"]["source_version_sha256"],
            "packet_plaintext_sha256": packet_sha256,
            "p3_snapshot_sha256": packet["origin"]["p3_snapshot_sha256"],
            "tenant_id": review["tenant_id"],
            "semantic_agent_version": review["semantic_agent_version"],
            "prepared_by": filled_workbook["prepared_by"],
            "reviewer_id": review["reviewer_id"],
            "remaps": sorted(remaps, key=lambda r: (r["collection"], r["source_row_sha256"])),
        }
    physical_approval_claims(
        packet=packet, review=review, approved_catalog=snapshot["table_catalog"],
        p3_bytes=p3_bytes, remap_evidence=remap_document,
    )
    return review, remap_document


def compile_private(
    *, manifest_path: Path, source_version: str, packet_path: Path,
    p3_path: Path, completed_workbook_path: Path, completed_remap_path: Path,
    approved_context_path: Path, output_review_path: Path, output_evidence_path: Path | None,
) -> dict[str, int]:
    """Guard all files 0600/0700; write only verified UNSIGNED candidates."""
    if os.name != "posix":
        deny("G5_PRIVATE_REVIEW_POSIX_REQUIRED")
    seal = select_verified_seal(private_json(manifest_path), source_version)
    packet, integrity = verify_decrypted_packet(private_bytes(packet_path), seal)
    review, remap = compile_completed_review(
        packet=packet, packet_sha256=integrity["packet_plaintext_sha256"],
        p3_bytes=private_bytes(p3_path, 3_000_000),
        filled_workbook=private_json(completed_workbook_path),
        filled_remap_draft=private_json(completed_remap_path),
        approved_context=private_json(approved_context_path),
    )
    outputs = [output_review_path] + ([output_evidence_path] if remap else [])
    if remap and output_evidence_path is None:
        deny("G5_REMAP_PRIVATE_OUTPUT_PATH_REQUIRED")
    if len(set(outputs)) != len(outputs):
        deny("G5_PRIVATE_REVIEW_OUTPUT_PATH_COLLISION")
    for target in outputs:
        if (
            not target.is_absolute() or target.exists() or target.is_symlink()
            or target.parent != packet_path.parent
            or target.parent.stat().st_uid != os.geteuid()
            or stat.S_IMODE(target.parent.stat().st_mode) != 0o700
        ):
            deny("G5_REVIEW_OUTPUT_PATH_UNSAFE")
    prepared = [(output_review_path, review)]
    if remap is not None:
        prepared.append((output_evidence_path, remap))
    for target, payload in prepared:
        data = (json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()
        if not 0 < len(data) <= 8_000_000:
            deny("G5_REVIEW_OUTPUT_TOO_LARGE")
        write_private_once(target, data)
    return {"reviewed_rows": len(review["rows"]), "physical_rows": len(review["physical_binding_decisions"]), "remapped_rows": len(remap["remaps"]) if remap else 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "manifest", "source-version-sha256", "packet-file", "p3-file",
        "completed-workbook-file", "completed-remap-file", "approved-context-file",
        "output-review-file"
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--output-remap-evidence-file")
    args = parser.parse_args(argv)
    try:
        outcome = compile_private(
            manifest_path=Path(args.manifest),
            source_version=args.source_version_sha256,
            packet_path=Path(args.packet_file), p3_path=Path(args.p3_file),
            completed_workbook_path=Path(args.completed_workbook_file),
            completed_remap_path=Path(args.completed_remap_file),
            approved_context_path=Path(args.approved_context_file),
            output_review_path=Path(args.output_review_file),
            output_evidence_path=Path(args.output_remap_evidence_file) if args.output_remap_evidence_file else None,
        )
    except (FinancialReviewBlocked, ReviewBlocked, OSError, ValueError, TypeError):
        print("G5_REVIEW_CANDIDATE=BLOCKED")
        print("APPROVAL_SIGNED=false")
        print("CONTEXT_ACTIVATED=false")
        print("SQL_EXECUTED=false")
        return 2
    print("G5_REVIEW_CANDIDATE=UNSIGNED_NOT_ACTIVATED")
    for name, count in sorted(outcome.items()):
        print("G5_" + name.upper() + "=" + str(count))
    print("APPROVAL_SIGNED=false")
    print("CONTEXT_ACTIVATED=false")
    print("SQL_EXECUTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
