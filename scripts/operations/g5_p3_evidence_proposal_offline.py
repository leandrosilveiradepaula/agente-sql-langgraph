#!/usr/bin/env python3
"""Derive *unapproved* P3 candidate bindings from recovered G5 metadata.

All original source content and suggested bindings remain in encrypted, root-only
review packets. This is NOT a context builder/importer and never generates SQL.
Historical SQL-patterns cannot enter this process (excluded in sealed G5).
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys

from scripts.operations import g5_semantic_lineage_candidate as g5
from scripts.operations import g5_semantic_context_review_offline as sealed
from scripts.operations import g5_p3_semantic_crosswalk_offline as bridge

CONTRACT = "g5-p3-evidence-proposal-offline-v1"
MANIFEST_CONTRACT = "g5-p3-evidence-proposal-manifest-v1"
CATALOG = "ai_ducklake_table_catalog"  # structural catalog name, never a business mapping
ALIASES = "ai_ducklake_entity_aliases"
RULES = "ai_ducklake_agent_rules"
DRE = "ai_ducklake_dre_mapping"
NUMERIC_TYPES = frozenset(("numeric", "int2", "int4", "int8", "float4", "float8", "money"))
DATE_TYPES = frozenset(("date", "timestamp", "timestamptz", "time", "timetz"))
MAX_REVIEW_BYTES = 16 * 1024 * 1024


def decode_array(value: object) -> tuple[list, str]:
    """Only validate JSON structure. No SQL parsing or accounting inference."""
    if value is None:
        return [], "NOT_DECLARED"
    if not isinstance(value, str) or len(value) > 100_000:
        return [], "INVALID_SOURCE_JSON"
    try:
        parsed = json.loads(value)
    except ValueError:
        return [], "INVALID_SOURCE_JSON"
    if not isinstance(parsed, list) or len(parsed) > 1000:
        return [], "INVALID_SOURCE_JSON"
    return parsed, "SOURCE_ARRAY_DECLARED"


def candidate_columns(raw: object, allowed: dict[str, str], kinds: frozenset[str]) -> tuple[list[str], list[str], str]:
    parts, status = decode_array(raw)
    if status != "SOURCE_ARRAY_DECLARED":
        return [], [], status
    present, unavailable = [], []
    for entry in parts:
        if not isinstance(entry, str) or not g5.IDENT.fullmatch(entry):
            unavailable.append("UNSAFE_OR_NONIDENTIFIER")
        elif entry in allowed and allowed[entry] in kinds:
            present.append(entry)
        else:
            unavailable.append("COLUMN_OR_TYPE_UNRESOLVED")
    return sorted(set(present)), unavailable, status


def candidate_join(raw: object, table: str, physical: dict[str, dict[str, str]]) -> tuple[list[dict], list[str], str]:
    joins, status = decode_array(raw)
    if status != "SOURCE_ARRAY_DECLARED":
        return [], [], status
    candidates, blockers = [], []
    for join in joins:
        if not isinstance(join, dict) or not all(isinstance(join.get(k), str) for k in ("from_column", "to_table", "to_column")):
            blockers.append("JOIN_STRUCTURE_UNKNOWN")
            continue
        left, target, right = (join[k] for k in ("from_column", "to_table", "to_column"))
        if not all(g5.IDENT.fullmatch(x) for x in (left, target, right)):
            blockers.append("JOIN_IDENTIFIER_UNSAFE")
        elif (target not in physical or left not in physical[table]
              or right not in physical[target]
              or physical[table][left] != physical[target][right]):
            blockers.append("JOIN_NOT_PHYSICALLY_COMPATIBLE")
        else:
            candidates.append({
                "from_column": left, "to_table": target, "to_column": right,
                "type_compatible": True, "cardinality": None,
                "accounting_equivalence": "NOT_ATTESTED",
            })
    return candidates, blockers, status


def propose(packet: dict, crosswalk: dict, physical: dict[str, dict[str, str]],
            target_schema: str) -> tuple[dict, dict]:
    """Pure structural proposal. Never fill an approvable P3 review."""
    version = packet.get("origin", {}).get("source_version_sha256")
    if (not g5.HEX_SHA.fullmatch(version or "") or crosswalk.get("source_version_sha256") != version
            or crosswalk.get("contract") != bridge.CONTRACT
            or crosswalk.get("status") != "NOT_APPROVED_NOT_IMPORTABLE"
            or crosswalk.get("allowed_for_generation") is not False
            or crosswalk.get("historical_sql_patterns_included") is not False
            or crosswalk.get("can_import_into_semantic_catalog") is not False
            or crosswalk.get("financial_sql_executed") is not False
            or crosswalk.get("review_base", {}).get("candidate_version") is not None
            or not isinstance(physical, dict) or not physical
            or set(physical) != {t.get("table") for t in crosswalk.get("review_base", {}).get("tables", [])}):
        g5.deny("SOURCE_CROSSWALK_NOT_UNAPPROVED")
    collections = packet.get("collections", {})
    if not isinstance(collections, dict) or set(collections) != sealed.REVIEWED:
        g5.deny("SOURCE_COLLECTIONS_UNEXPECTED")
    known_ids = {(n, row["source_row_sha256"]) for n, rows in collections.items() for row in rows}
    links = crosswalk.get("reference_links")
    if (not isinstance(links, list) or len(links) != sum(len(v) for v in collections.values())
            or {(r.get("collection"), r.get("source_row_sha256")) for r in links} != known_ids):
        g5.deny("SOURCE_REFERENCE_LINKS_UNVERIFIED")
    scope = crosswalk["review_base"]
    if (scope.get("can_execute_financial_sql") is not False
            or scope.get("can_import_into_semantic_catalog") is not False
            or any(item.get(k) is not None for item in scope["tables"]
                   for k in ("grain", "primary_key", "key_columns", "metric_bindings", "date_bindings",
                             "join_bindings", "dimension_bindings", "dre_mappings", "business_evidence"))):
        g5.deny("P3_REVIEW_PREAPPROVAL_DETECTED")

    counters = Counter()
    linked = {name: [] for name in sorted(physical)}
    historical_evidence = {RULES: [], DRE: [], ALIASES: [], CATALOG: []}
    for name in sorted(collections):
        for row in collections[name]:
            raw = row["source_fields_unreviewed"]
            if not isinstance(raw, dict):
                g5.deny("SOURCE_RECORD_INVALID")
            row_sha = row["source_row_sha256"]
            historical_evidence[name].append({"source_row_sha256": row_sha, "source_fields_unreviewed": raw})
            if name == CATALOG:
                table, schema = raw.get("table_name"), raw.get("schema_name")
                if table not in physical or not isinstance(schema, str):
                    counters["catalog_outside_target"] += 1
                    continue
                cols = physical[table]
                primary_key = raw.get("primary_key")
                safe_pk = primary_key if isinstance(primary_key, str) and primary_key in cols else None
                keys, key_errors, key_status = candidate_columns(raw.get("key_columns"), cols, frozenset(cols.values()))
                metrics, metric_errors, metric_status = candidate_columns(raw.get("metric_columns"), cols, NUMERIC_TYPES)
                dates, date_errors, date_status = candidate_columns(raw.get("date_columns"), cols, DATE_TYPES)
                joins, join_errors, join_status = candidate_join(raw.get("join_rules"), table, physical)
                hint = {
                    "source_row_sha256": row_sha,
                    "source_schema": schema,
                    "identity_evidence": "SAME_SCHEMA_AND_TABLE" if schema == target_schema else "TABLE_NAME_ONLY_DIFFERENT_SCHEMA",
                    "source_primary_key_physical_candidate": safe_pk,
                    "source_key_columns_physical_candidates": keys,
                    "source_metric_columns_type_valid_candidates": metrics,
                    "source_date_columns_type_valid_candidates": dates,
                    "source_join_physical_candidates": joins,
                    "blocked_legacy_refs": {
                        "key_columns": len(key_errors), "metric_columns": len(metric_errors),
                        "date_columns": len(date_errors), "join_rules": len(join_errors),
                    },
                    "source_array_status": {
                        "key_columns": key_status, "metric_columns": metric_status,
                        "date_columns": date_status, "join_rules": join_status,
                    },
                    "metric_aggregation": None,
                    "metric_concept": None,
                    "metric_sign_convention": None,
                    "join_cardinality": None,
                    "grain_verified": False,
                    "financial_meaning_verified": False,
                    "approved": False,
                }
                linked[table].append(hint)
                counters["catalog_source_name_match"] += 1
                counters["metric_column_candidates"] += len(metrics)
                counters["date_column_candidates"] += len(dates)
                counters["join_physical_candidates"] += len(joins)
                counters["key_column_candidates"] += len(keys)
                counters["unresolved_legacy_fields"] += sum(hint["blocked_legacy_refs"].values())
            elif name == ALIASES:
                schema, table = g5.split_reference(raw.get("target_table"))
                col = raw.get("target_column")
                if table in physical and isinstance(col, str) and col in physical[table]:
                    linked[table].append({
                        "source_row_sha256": row_sha,
                        "kind": "SOURCE_ENTITY_ALIAS_EXPLICIT_PHYSICAL_COLUMN",
                        "source_schema": schema,
                        "source_column": col,
                        "physical_column_name_present": True,
                        "accounting_equivalence": "NOT_ATTESTED",
                        "approved": False,
                    })
                    counters["alias_column_name_match"] += 1
                else:
                    counters["alias_unmapped"] += 1
            elif name == RULES:
                counters["historical_rules_review_only"] += 1
            elif name == DRE:
                counters["historical_dre_review_only"] += 1
    record_count = sum(len(rows) for rows in collections.values())
    result = {
        "contract": CONTRACT,
        "status": "SOURCE_EVIDENCE_ENCRYPTED_UNAPPROVED",
        "source_version_sha256": version,
        "target_schema": target_schema,
        "target_tables": sorted(physical),
        "p3_review_draft_unchanged": scope,
        "historical_definitions_to_review": historical_evidence,
        "source_field_evidence_by_target_table": linked,
        "review_requirements": list(bridge.CHECKLIST),
        "historical_sql_patterns_included": False,
        "metric_aggregation_sign_evidence_verified": False,
        "business_mappings_approved": False,
        "can_import_into_semantic_catalog": False,
        "allowed_as_llm_or_generator_context": False,
        "can_execute_financial_sql": False,
        "financial_sql_executed": False,
    }
    summary = {
        "source_version_sha256": version,
        "source_records": record_count,
        "target_tables": len(physical),
        "classification_counts": dict(sorted(counters.items())),
        "financial_semantics_approved": False,
    }
    return result, summary


def decrypt_private_json(path: Path, ciphertext_sha: str, plaintext_sha: str,
                         password: str, max_bytes: int = MAX_REVIEW_BYTES) -> dict:
    if (g5.digest_private_file(path) != ciphertext_sha
            or not g5.HEX_SHA.fullmatch(plaintext_sha or "")):
        g5.deny("CIPHERTEXT_PROVENANCE_MISMATCH")
    proc = g5.decrypt_gpg(path, password)
    try:
        data = proc.stdout.read(max_bytes + 1)
        proc.stdout.close()
        if len(data) > max_bytes:
            g5.deny("ENCRYPTED_REVIEW_RESOURCE_LIMIT")
        if proc.wait(timeout=120) != 0 or g5.sha(data) != plaintext_sha:
            g5.deny("ENCRYPTED_REVIEW_PLAINTEXT_INVALID")
    finally:
        if proc.poll() is None:
            proc.kill(); proc.wait()
    try:
        value = json.loads(data)
    except (UnicodeError, ValueError):
        g5.deny("ENCRYPTED_REVIEW_JSON_INVALID")
    if not isinstance(value, dict):
        g5.deny("ENCRYPTED_REVIEW_JSON_INVALID")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--g5-manifest", required=True, type=Path)
    parser.add_argument("--crosswalk-manifest", required=True, type=Path)
    parser.add_argument("--audit-dir", required=True, type=Path)
    parser.add_argument("--policy", type=Path,
                        default=Path(__file__).with_name("g1_readonly_rollout.json"))
    args = parser.parse_args(argv)
    print("G5_EVIDENCE_MODE=PRIVATE_PROPOSALS_ONLY")
    try:
        g5.require_posix_io()
        if os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION", "false").strip().lower() in {"true", "1", "yes", "on"}:
            g5.deny("SQL_EXECUTION_FLAG_UNSAFE")
        from scripts.operations import p3_source_alignment_readonly as p3
        from scripts.operations import p3_semantic_mapping_review_readonly as mapping
        policy_data = args.policy.read_bytes()
        policy = p3.validate_policy(json.loads(policy_data))
        raw, p3_sha = g5.read_json_private(args.audit_dir / "physical-metadata.json", 3_000_000)
        context, physical, grants, identity = p3.verify_probe_snapshot(
            raw, policy, raw.get("context_version"))
        evaluation = p3.evaluate(policy, raw["context_version"], context, physical, grants, identity)
        if any(x in evaluation["blockers"] for x in ("ROLE_SCOPE_MISMATCH", "ROLE_WRITE_PRIVILEGE", "PHYSICAL_COLUMNS_MISSING")):
            g5.deny("P3_ROLE_SCOPE_NOT_ATTESTED")
        allowed = mapping.physical_inventory(policy, physical)
        template = mapping.create_review(policy, physical, raw["context_version"])
        g5_dir = args.g5_manifest.parent
        cross_dir = args.crosswalk_manifest.parent
        sealed.require_private_directory(g5_dir)
        sealed.require_private_directory(cross_dir)
        g5_manifest, g5_sha = g5.read_json_private(args.g5_manifest, 2_000_000)
        cross_manifest, _ = g5.read_json_private(args.crosswalk_manifest, 2_000_000)
        entries = bridge.require_source_manifest(g5_manifest, g5_dir, p3_sha)
        if (cross_manifest.get("contract") != "g5-p3-crosswalk-manifest-v1"
                or cross_manifest.get("status") != "UNAPPROVED_REVIEW_ONLY"
                or cross_manifest.get("p3_snapshot_sha256") != p3_sha
                or cross_manifest.get("source_manifest_sha256") != g5_sha
                or cross_manifest.get("source_sql_patterns_excluded") != g5_manifest["sql_pattern_rows_excluded"]
                or cross_manifest.get("candidate_for_generation") is not False
                or cross_manifest.get("can_import_into_semantic_catalog") is not False
                or cross_manifest.get("financial_sql_executed") is not False
                or cross_manifest.get("version_count") != len(entries)):
            g5.deny("CROSSWALK_MANIFEST_NOT_VERIFIED")
        cross_entries = cross_manifest.get("source_versions")
        if (not isinstance(cross_entries, list) or len(cross_entries) != len(entries)
                or any(not isinstance(x, dict) for x in cross_entries)
                or len(set(x.get("source_version_sha256") for x in cross_entries)) != len(entries)
                or any(not g5.HEX_SHA.fullmatch(x.get("source_version_sha256") or "") for x in cross_entries)):
            g5.deny("CROSSWALK_VERSIONS_INVALID")
        lookup = {r["source_version_sha256"]: r for r in cross_entries}
        if set(lookup) != {e["source_version_sha256"] for e in entries}:
            g5.deny("CROSSWALK_VERSION_MISMATCH")
        dest = args.g5_manifest.parent.parent / "g5-p3-evidence-proposals-unapproved-v1"
        if dest.exists() or dest.is_symlink() or not dest.is_absolute():
            g5.deny("OUTPUT_ALREADY_EXISTS_OR_UNSAFE")
        sealed.require_private_directory(dest.parent)
        if not sys.stdin.isatty():
            g5.deny("INTERACTIVE_TERMINAL_REQUIRED")
        import getpass
        password = getpass.getpass("Senha EXISTENTE do backup G5 (sem eco): ")
        if not (g5.MIN_PASSWORD <= len(password) <= 256 and all(33 <= ord(c) <= 126 for c in password)):
            g5.deny("PASSPHRASE_INVALID")
        proposals = []
        source_count = 0
        for item in entries:
            packet = bridge.open_verified_packet(g5_dir, item, password, g5_manifest)
            v = item["source_version_sha256"]
            cross = lookup[v]
            if (cross.get("file") != f"crosswalk-{v}.json.gpg"
                    or cross.get("source_row_count") != sum(item["row_counts"].values())):
                g5.deny("CROSSWALK_VERSION_SCOPE_INVALID")
            existing = decrypt_private_json(cross_dir / cross["file"], cross["ciphertext_sha256"],
                                            cross["plaintext_sha256"], password)
            expected, _ = bridge.assemble_crosswalk(packet, allowed, policy["schema"],
                                                      template, g5.sha(policy_data), p3_sha)
            if existing != expected:
                g5.deny("CROSSWALK_INDEPENDENT_RECONCILIATION_FAILED")
            candidate, summary = propose(packet, existing, allowed, policy["schema"])
            proposals.append((candidate, summary))
            source_count += summary["source_records"]
        if source_count != cross_manifest.get("source_record_count"):
            g5.deny("CROSSWALK_TOTAL_COVERAGE_MISMATCH")
        os.mkdir(dest, 0o700)
        try:
            items = []
            total = Counter()
            for packet, summary in proposals:
                ver = packet["source_version_sha256"]
                content = sealed.private_json(packet)
                f = dest / f"evidence-proposal-{ver}.json.gpg"
                digest = sealed.seal_gpg(f, content, password)
                sealed.verify_gpg(f, password, content)
                total.update(summary["classification_counts"])
                items.append({"source_version_sha256": ver, "file": f.name,
                              "plaintext_sha256": g5.sha(content), "ciphertext_sha256": digest,
                              "source_records": summary["source_records"],
                              "classification_counts": summary["classification_counts"]})
            manifest = {"contract": MANIFEST_CONTRACT,
                        "status": "UNAPPROVED_ENCRYPTED_EVIDENCE",
                        "source_manifest_sha256": g5_sha,
                        "crosswalk_manifest_sha256": g5.sha(g5.read_private(args.crosswalk_manifest, 2_000_000)),
                        "p3_snapshot_sha256": p3_sha,
                        "versions": items, "version_count": len(items),
                        "source_records": source_count,
                        "source_sql_patterns_excluded": g5_manifest["sql_pattern_rows_excluded"],
                        "can_import_into_semantic_catalog": False,
                        "approved_for_generation": False,
                        "financial_sql_executed": False}
            g5.private_write(dest / "manifest.json", manifest)
        except BaseException:
            for f in dest.iterdir():
                if f.is_file() and not f.is_symlink():
                    f.unlink()
            dest.rmdir()
            raise
        print("G5_EVIDENCE_RESULT=PASS")
        print("G5_EVIDENCE_SOURCE_VERSIONS=" + str(len(proposals)))
        print("G5_EVIDENCE_SOURCE_RECORDS=" + str(source_count))
        print("G5_EVIDENCE_SQL_PATTERNS_EXCLUDED=" + str(g5_manifest["sql_pattern_rows_excluded"]))
        for name in ("catalog_source_name_match", "metric_column_candidates", "date_column_candidates",
                     "join_physical_candidates", "alias_column_name_match", "unresolved_legacy_fields"):
            print("G5_EVIDENCE_" + name.upper() + "=" + str(total[name]))
        print("G5_EVIDENCE_APPROVED=false")
        print("G5_EVIDENCE_SQL_EXECUTED=false")
        print("G5_EVIDENCE_MANIFEST=" + str(dest / "manifest.json"))
        return 0
    except g5.Blocked as e:
        print("G5_EVIDENCE_RESULT=BLOCKED")
        print("G5_EVIDENCE_REASON=" + str(e))
        return 2
    except Exception:
        print("G5_EVIDENCE_RESULT=BLOCKED")
        print("G5_EVIDENCE_REASON=UNEXPECTED_ERROR")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())