#!/usr/bin/env python3
"""Build encrypted, version-isolated P3 review workbooks from sealed G5 evidence.

Offline, no database, SQL, network, LLM, generator, runtime or approvals.
Historical SQL patterns are never accepted. Physical name overlap is NOT
business equivalence; everything remains an unapproved review proposal.
"""
from __future__ import annotations

import argparse
from collections import Counter
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from scripts.operations import g5_semantic_lineage_candidate as g5
from scripts.operations import g5_semantic_context_review_offline as sealed

CONTRACT = "g5-p3-semantic-crosswalk-offline-v1"
REVIEWED = frozenset(sealed.REVIEWED)
MAX_PACKET_BYTES = 16 * 1024 * 1024
MAX_TOTAL_PACKET_BYTES = 128 * 1024 * 1024
MAX_MANIFEST_VERSIONS = 128
HEX = re.compile(r"^[0-9a-f]{64}$")
CHECKLIST = (
    "grain", "primary_key_uniqueness", "metric_aggregation_and_sign",
    "period_semantics", "dimension_meaning", "join_cardinality_and_fanout",
    "dre_mapping_if_applicable", "tenant_identity", "accounting_approval",
)


def ensure_hex(value: object) -> bool:
    return isinstance(value, str) and bool(HEX.fullmatch(value))


def require_source_manifest(manifest: dict, root: Path, p3_sha: str) -> list[dict]:
    if (manifest.get("contract") != "g5-private-source-review-manifest-v1"
            or manifest.get("status") != "ENCRYPTED_NOT_APPROVED"
            or manifest.get("p3_snapshot_sha256") != p3_sha
            or manifest.get("financial_sql_executed") is not False
            or manifest.get("context_activated") is not False
            or manifest.get("approved_for_generation") is not False
            or manifest.get("approved_for_import") is not False
            or not ensure_hex(manifest.get("source_archive_sha256"))
            or not ensure_hex(manifest.get("lineage_report_sha256"))
            or not ensure_hex(manifest.get("lineage_identifier_sha256"))):
        g5.deny("SOURCE_MANIFEST_NOT_UNAPPROVED_OR_P3_DRIFT")
    if (type(manifest.get("sql_pattern_rows_excluded")) is not int
            or manifest["sql_pattern_rows_excluded"] < 0):
        g5.deny("SOURCE_EVALUATION_COVERAGE_INVALID")
    entries = manifest.get("versions")
    if (not isinstance(entries, list) or not 1 <= len(entries) <= MAX_MANIFEST_VERSIONS):
        g5.deny("SOURCE_VERSION_MANIFEST_INVALID")
    seen = set()
    for item in entries:
        if not isinstance(item, dict):
            g5.deny("SOURCE_VERSION_MANIFEST_INVALID")
        version = item.get("source_version_sha256")
        if (not ensure_hex(version) or version in seen
                or item.get("file") != f"source-version-{version}.json.gpg"
                or not ensure_hex(item.get("ciphertext_sha256"))
                or not ensure_hex(item.get("plaintext_sha256"))
                or item.get("sealed_and_roundtrip_verified") is not True
                or not isinstance(item.get("row_counts"), dict)
                or set(item["row_counts"]) != REVIEWED
                or any(type(n) is not int or n < 0 for n in item["row_counts"].values())):
            g5.deny("SOURCE_VERSION_MANIFEST_INVALID")
        seen.add(version)
    if os.name != "posix" or not hasattr(os, "geteuid") or not hasattr(os, "O_NOFOLLOW"):
        g5.deny("PRIVATE_POSIX_REQUIRED")
    sealed.require_private_directory(root)
    return sorted(entries, key=lambda item: item["source_version_sha256"])


def open_verified_packet(root: Path, item: dict, password: str,
                         manifest: dict) -> dict:
    """Decrypt one file in memory and prove it belongs to the G5 manifest."""
    path = root / item["file"]
    if g5.digest_private_file(path) != item["ciphertext_sha256"]:
        g5.deny("SOURCE_VERSION_CIPHERTEXT_MISMATCH")
    process = g5.decrypt_gpg(path, password)
    try:
        assert process.stdout is not None
        data = process.stdout.read(MAX_PACKET_BYTES + 1)
        process.stdout.close()
        if len(data) > MAX_PACKET_BYTES:
            g5.deny("SOURCE_VERSION_RESOURCE_LIMIT")
        if process.wait(timeout=120) != 0:
            g5.deny("SOURCE_VERSION_GPG_AUTH_FAILED")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    if g5.sha(data) != item["plaintext_sha256"]:
        g5.deny("SOURCE_VERSION_PLAINTEXT_MISMATCH")
    try:
        packet = json.loads(data)
    except (UnicodeError, ValueError):
        g5.deny("SOURCE_VERSION_JSON_INVALID")
    if not isinstance(packet, dict):
        g5.deny("SOURCE_VERSION_JSON_INVALID")
    origin = packet.get("origin")
    collections = packet.get("collections")
    if (packet.get("contract") != sealed.CONTRACT
            or packet.get("status") != "QUARANTINED_SOURCE_EVIDENCE_UNAPPROVED"
            or packet.get("tenant") is not None
            or packet.get("candidate_context_version") is not None
            or packet.get("can_import_into_semantic_catalog") is not False
            or packet.get("can_execute_financial_sql") is not False
            or packet.get("can_use_as_llm_or_planner_context") is not False
            or packet.get("financial_semantics_equivalence") != "NOT_ATTESTED"
            or packet.get("historical_sql_patterns_excluded") is not True
            or packet.get("source_business_rules_are_unreviewed") is not True
            or not isinstance(origin, dict)
            or origin.get("source_version_sha256") != item["source_version_sha256"]
            or origin.get("p3_snapshot_sha256") != manifest["p3_snapshot_sha256"]
            or origin.get("source_archive_sha256") != manifest["source_archive_sha256"]
            or not isinstance(collections, dict) or set(collections) != REVIEWED
            or packet.get("row_counts") != item["row_counts"]):
        g5.deny("SOURCE_VERSION_SCOPE_INVALID")
    for name, rows in collections.items():
        if not isinstance(rows, list) or len(rows) != item["row_counts"][name]:
            g5.deny("SOURCE_VERSION_ROWS_INVALID")
        fingerprints = set()
        for row in rows:
            if (not isinstance(row, dict)
                    or not ensure_hex(row.get("source_row_sha256"))
                    or not isinstance(row.get("source_fields_unreviewed"), dict)
                    or row["source_row_sha256"] in fingerprints):
                g5.deny("SOURCE_VERSION_ROWS_INVALID")
            fingerprints.add(row["source_row_sha256"])
    hints = packet.get("physical_identifier_hints_unapproved")
    if (not isinstance(hints, list) or any(not isinstance(h, dict)
                                           or h.get("accounting_equivalence") != "NOT_ATTESTED"
                                           or h.get("collection") not in REVIEWED
                                           for h in hints)):
        g5.deny("SOURCE_HINTS_INVALID")
    return packet


def classify_relation(ref: object, source_schema: object,
                      allowed: dict[str, dict[str, str]], target_schema: str,
                      target_column: object | None = None) -> tuple[str, str | None, str]:
    """Only literal structural identifiers. Never fuzzy-map or infer meaning."""
    if ref is None or ref == "":
        return "SEMANTIC_ONLY", None, "NO_PHYSICAL_COLUMN_DECLARED"
    if not isinstance(ref, str) or not g5.IDENT.fullmatch(ref):
        return "SOURCE_IDENTIFIER_UNSAFE", None, "NOT_EVALUATED"
    if ref not in allowed:
        return "OUTSIDE_AUTHORIZED_TARGET", None, "NOT_EVALUATED"
    if not isinstance(source_schema, str) or source_schema != target_schema:
        relation = "TARGET_TABLE_NAME_ONLY"
    else:
        relation = "TARGET_IDENTIFIER_EXACT"
    if target_column is None or target_column == "":
        column = "NO_PHYSICAL_COLUMN_DECLARED"
    elif not isinstance(target_column, str) or not g5.IDENT.fullmatch(target_column):
        column = "SOURCE_COLUMN_UNSAFE"
    elif target_column in allowed[ref]:
        column = "TARGET_COLUMN_NAME_PRESENT"
    else:
        column = "TARGET_COLUMN_NAME_MISSING"
    return relation, ref, column


def assemble_crosswalk(packet: dict, allowed: dict[str, dict[str, str]],
                       target_schema: str, draft: dict, policy_sha: str,
                       snapshot_sha: str) -> tuple[dict, dict]:
    """Prepare an *encrypted-only* reviewer workbook; do not fill financial fields."""
    if (not g5.IDENT.fullmatch(target_schema)
            or not allowed or not all(g5.IDENT.fullmatch(k) for k in allowed)
            or draft.get("contract") != "p3-semantic-mapping-review-v1"
            or draft.get("status") != "UNAPPROVED_DRAFT"
            or draft.get("can_import_into_semantic_catalog") is not False
            or draft.get("can_execute_financial_sql") is not False
            or set(row["table"] for row in draft.get("tables", [])) != set(allowed)
            or any(row.get("schema") != target_schema for row in draft["tables"])):
        g5.deny("P3_REVIEW_TARGET_INVALID")
    if (draft.get("candidate_version") is not None
            or draft.get("organization_id") is not None
            or draft.get("review_evidence") is not None
            or any(draft.get(k) is not None for k in ("intent_definitions", "entity_aliases", "business_rules"))):
        g5.deny("P3_DRAFT_NOT_UNREVIEWED")
    for row in draft["tables"]:
        if any(row.get(k) is not None for k in (
            "grain", "primary_key", "key_columns", "metric_bindings",
            "dimension_bindings", "date_bindings", "join_bindings",
            "dre_mappings", "business_evidence")):
            g5.deny("P3_DRAFT_NOT_UNREVIEWED")
    rows = packet["collections"]
    references = []
    categories = Counter()
    matched = Counter()
    for name in sorted(REVIEWED):
        for source in rows[name]:
            fields = source["source_fields_unreviewed"]
            source_row = source["source_row_sha256"]
            if name == "ai_ducklake_entity_aliases":
                raw_ref = fields.get("target_table")
                raw_schema, raw_table = g5.split_reference(raw_ref)
                relation, target, col = classify_relation(
                    raw_table, raw_schema, allowed, target_schema, fields.get("target_column"))
            elif name == "ai_ducklake_table_catalog":
                relation, target, col = classify_relation(
                    fields.get("table_name"), fields.get("schema_name"), allowed,
                    target_schema, fields.get("primary_key"))
            elif name == "ai_ducklake_agent_rules":
                relation, target, col = "REQUIRES_RULE_REVIEW", None, "NOT_APPLICABLE"
            else:
                relation, target, col = "REQUIRES_DRE_REVIEW", None, "NOT_APPLICABLE"
            categories[f"{name}/{relation}/{col}"] += 1
            if target is not None:
                matched[target] += 1
            references.append({
                "collection": name, "source_row_sha256": source_row,
                "source_version_sha256": packet["origin"]["source_version_sha256"],
                "candidate_target_table": target,
                "identifier_relation": relation, "column_relation": col,
                "accounting_equivalence": "NOT_ATTESTED",
            })
    # Never treat a name match as an approved context binding.
    result = {
        "contract": CONTRACT,
        "status": "NOT_APPROVED_NOT_IMPORTABLE",
        "source_version_sha256": packet["origin"]["source_version_sha256"],
        "p3_snapshot_sha256": snapshot_sha,
        "p3_policy_sha256": policy_sha,
        "source_version_packet_plaintext_sha256": g5.sha(sealed.private_json(packet)),
        "review_base": draft,
        "reference_links": references,
        "review_requirements": list(CHECKLIST),
        "all_financial_meanings_require_independent_evidence": True,
        "source_rules_remain_encrypted_in_original_packet": True,
        "historical_sql_patterns_included": False,
        "allowed_for_llm_context": False,
        "allowed_for_generation": False,
        "can_import_into_semantic_catalog": False,
        "can_execute_financial_sql": False,
        "financial_sql_executed": False,
        "llm_calls": 0,
    }
    summary = {
        "source_version_sha256": packet["origin"]["source_version_sha256"],
        "source_row_count": len(references),
        "classification_counts": dict(sorted(categories.items())),
        "matched_target_table_count": len(matched),
        "requires_independent_accounting_approval": True,
        "ready_for_generation": False,
    }
    return result, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--g5-manifest", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--policy", type=Path,
                        default=Path(__file__).with_name("g1_readonly_rollout.json"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    print("G5_CROSSWALK_MODE=OFFLINE_PRIVATE_ONLY")
    try:
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "geteuid"):
            g5.deny("PRIVATE_POSIX_REQUIRED")
        if os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") == "true":
            g5.deny("FINANCIAL_EXECUTION_FLAG_UNSAFE")
        from scripts.operations import p3_source_alignment_readonly as p3
        from scripts.operations import p3_semantic_mapping_review_readonly as mapping
        if args.audit_dir.is_symlink():
            g5.deny("P3_PRIVATE_DIRECTORY_REQUIRED")
        policy_data = args.policy.read_bytes()
        policy = p3.validate_policy(json.loads(policy_data))
        raw, p3_sha = g5.read_json_private(args.audit_dir / "physical-metadata.json", 3_000_000)
        context, physical, grants, identity = p3.verify_probe_snapshot(
            raw, policy, raw.get("context_version"))
        evaluation = p3.evaluate(policy, raw["context_version"],
                                 context, physical, grants, identity)
        if any(b in evaluation["blockers"] for b in (
            "ROLE_SCOPE_MISMATCH", "ROLE_WRITE_PRIVILEGE", "PHYSICAL_COLUMNS_MISSING")):
            g5.deny("P3_READER_PRIVILEGES_NOT_VERIFIED")
        allowed = mapping.physical_inventory(policy, physical)
        draft = mapping.create_review(policy, physical, raw["context_version"])
        root = args.g5_manifest.parent
        sealed.require_private_directory(root)
        manifest, manifest_sha = g5.read_json_private(args.g5_manifest, 2_000_000)
        entries = require_source_manifest(manifest, root, p3_sha)
        dest = args.output_dir or root.parent / "g5-p3-crosswalk-unapproved-v1"
        if (not dest.is_absolute() or dest.exists() or dest.is_symlink()
                or dest.parent != root.parent):
            g5.deny("TARGET_OUTPUT_UNSAFE_OR_EXISTS")
        sealed.require_private_directory(dest.parent)
        if not sys.stdin.isatty():
            g5.deny("INTERACTIVE_TERMINAL_REQUIRED")
        password = getpass("Senha EXISTENTE do backup G5 (sem eco): ")
        if not (g5.MIN_PASSWORD <= len(password) <= 256
                and all(33 <= ord(ch) <= 126 for ch in password)):
            g5.deny("SOURCE_PASSPHRASE_INVALID")
        # Validate every version completely before writing any output.
        validated = [open_verified_packet(root, e, password, manifest) for e in entries]
        if sum(sum(e["row_counts"].values()) for e in entries) != sum(
                sum(len(v["collections"][k]) for k in REVIEWED) for v in validated):
            g5.deny("SOURCE_VERSION_COVERAGE_MISMATCH")
        if sum(len(sealed.private_json(v)) for v in validated) > MAX_TOTAL_PACKET_BYTES:
            g5.deny("SOURCE_TOTAL_RESOURCE_LIMIT")
        os.mkdir(dest, 0o700)
        try:
            reports = []
            for packet in validated:
                review, summary = assemble_crosswalk(packet, allowed,
                            policy["schema"], draft, g5.sha(policy_data), p3_sha)
                version_sha = packet["origin"]["source_version_sha256"]
                name = f"crosswalk-{version_sha}.json.gpg"
                path = dest / name
                plain = sealed.private_json(review)
                ciphertext_sha = sealed.seal_gpg(path, plain, password)
                sealed.verify_gpg(path, password, plain)
                reports.append({
                    **summary,
                    "file": name,
                    "ciphertext_sha256": ciphertext_sha,
                    "plaintext_sha256": g5.sha(plain),
                })
            output_manifest = {
                "contract": "g5-p3-crosswalk-manifest-v1",
                "status": "UNAPPROVED_REVIEW_ONLY",
                "p3_snapshot_sha256": p3_sha,
                "source_manifest_sha256": manifest_sha,
                "source_versions": reports,
                "version_count": len(reports),
                "source_record_count": sum(x["source_row_count"] for x in reports),
                "reviewed_target_relation_count": len(allowed),
                "source_sql_patterns_excluded": manifest["sql_pattern_rows_excluded"],
                "candidate_for_generation": False,
                "can_import_into_semantic_catalog": False,
                "financial_sql_executed": False,
                "llm_calls": 0,
            }
            g5.private_write(dest / "manifest.json", output_manifest)
        except BaseException:
            for item in dest.iterdir():
                if item.is_file() and not item.is_symlink():
                    item.unlink()
            dest.rmdir()
            raise
        print("G5_CROSSWALK_RESULT=PASS")
        print("G5_CROSSWALK_VERSIONS=" + str(len(reports)))
        print("G5_CROSSWALK_SOURCE_ROWS=" + str(output_manifest["source_record_count"]))
        print("G5_CROSSWALK_TARGET_TABLES=" + str(len(allowed)))
        print("G5_CROSSWALK_EVALUATION_SQL_EXCLUDED=" + str(manifest["sql_pattern_rows_excluded"]))
        print("G5_CROSSWALK_APPROVED=false")
        print("G5_CROSSWALK_SQL_EXECUTED=false")
        print("G5_CROSSWALK_MANIFEST=" + str(dest / "manifest.json"))
        return 0
    except g5.Blocked as error:
        print("G5_CROSSWALK_RESULT=BLOCKED")
        print("G5_CROSSWALK_REASON=" + str(error))
        return 2
    except Exception:
        print("G5_CROSSWALK_RESULT=BLOCKED")
        print("G5_CROSSWALK_REASON=UNEXPECTED_ERROR")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())