"""Private G5/P3 crosswalk contract tests on invented, materially distinct schemas."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import unittest.mock

from scripts.operations import g5_semantic_lineage_candidate as g5
from scripts.operations import g5_semantic_context_review_offline as sealed
from scripts.operations import g5_p3_semantic_crosswalk_offline as cross

# Existing G5 synthetic fixtures are intentionally constructed without production data.
from scripts.test_g5_semantic_lineage_candidate import fixture


def create_packets(schema="accounts_alpha"):
    data, receipt, prior, p3, index, p3_sha, cipher_sha = fixture(schema)
    collector = sealed.VersionedCollector()
    lineage, hints = g5.scan(io.BytesIO(data), receipt, prior, index,
                             p3_sha=p3_sha, cipher_sha=cipher_sha,
                             on_semantic_record=collector.accept)
    return collector.packages(receipt=receipt, lineage=lineage,
                              hints=hints, p3_sha=p3_sha), p3_sha


def draft(schema, tables):
    return {
        "contract": "p3-semantic-mapping-review-v1",
        "status": "UNAPPROVED_DRAFT",
        "candidate_version": None, "organization_id": None, "review_evidence": None,
        "intent_definitions": None, "entity_aliases": None, "business_rules": None,
        "can_import_into_semantic_catalog": False, "can_execute_financial_sql": False,
        "tables": [{
            "schema": schema, "table": name,
            "columns": [{"name": col, "postgres_type": kind} for col, kind in sorted(cols.items())],
            "grain": None, "primary_key": None, "key_columns": None,
            "metric_bindings": None, "dimension_bindings": None,
            "date_bindings": None, "join_bindings": None, "dre_mappings": None,
            "business_evidence": None,
        } for name, cols in sorted(tables.items())],
    }


class CrosswalkTests(unittest.TestCase):
    def test_two_different_clients_same_code_no_business_inference(self):
        for schema, allowed in (
            ("operations_alpha", {"ledger_entries": {"record_id": "text", "amount_net": "numeric"},
                                  "cost_centers": {"label": "text"}}),
            ("billing_beta", {"ledger_entries": {"record_id": "uuid", "amount_net": "float8"},
                              "region_codes": {"code": "text"}}),
        ):
            with self.subTest(schema=schema):
                packets, p3sha = create_packets("source_history")
                reviews = [cross.assemble_crosswalk(p, allowed, schema, draft(schema, allowed),
                                                    "a" * 64, p3sha) for p in packets]
                self.assertEqual(len(reviews), 2)
                self.assertTrue(all(s["source_row_count"] == 4 for _, s in reviews))
                self.assertTrue(all(r["allowed_for_generation"] is False for r, _ in reviews))
                self.assertTrue(all(r["financial_sql_executed"] is False for r, _ in reviews))
                self.assertTrue(all(r["historical_sql_patterns_included"] is False for r, _ in reviews))
                self.assertTrue(all(r["review_base"]["candidate_version"] is None for r, _ in reviews))
                self.assertTrue(all(t["metric_bindings"] is None for r, _ in reviews for t in r["review_base"]["tables"]))
                self.assertNotEqual(reviews[0][0]["source_version_sha256"], reviews[1][0]["source_version_sha256"])
                # The crosswalk never contains complete historical business prose.
                data = json.dumps(reviews)
                for historical in ("sensitive_rule_should_not_leak", "private_description_should_not_leak",
                                   "select_private_sql_do_not_emit", "private_benchmark_do_not_emit"):
                    self.assertNotIn(historical, data)

    def test_different_table_names_block_silent_mapping(self):
        allowed = {"invoices": {"total": "numeric"}}
        p = create_packets()[0][0]
        review, summary = cross.assemble_crosswalk(p, allowed, "other_schema",
                                                  draft("other_schema", allowed), "b" * 64,
                                                  "a" * 64)
        self.assertEqual(summary["matched_target_table_count"], 0)
        self.assertTrue(any(r["identifier_relation"] == "OUTSIDE_AUTHORIZED_TARGET" for r in review["reference_links"]))
        self.assertFalse(review["can_import_into_semantic_catalog"])

    def test_corrupted_template_and_preapproval_are_blocked(self):
        packet = create_packets()[0][0]
        allowed = {"ledger_entries": {"amount_net": "numeric"}}
        d = draft("target_schema", allowed)
        d["tables"][0]["metric_bindings"] = [{"column": "amount_net"}]
        with self.assertRaisesRegex(g5.Blocked, "P3_DRAFT_NOT_UNREVIEWED"):
            cross.assemble_crosswalk(packet, allowed, "target_schema", d, "a" * 64, "b" * 64)
        d = draft("target_schema", allowed)
        d["organization_id"] = "unverified-tenant"
        with self.assertRaisesRegex(g5.Blocked, "P3_DRAFT_NOT_UNREVIEWED"):
            cross.assemble_crosswalk(packet, allowed, "target_schema", d, "a" * 64, "b" * 64)

    def test_windows_cli_fails_closed_before_accessing_private_files(self):
        if os.name == "posix" and hasattr(os, "O_NOFOLLOW"):
            self.skipTest("Windows-only contract")
        with unittest.mock.patch("builtins.print") as printer:
            rc = cross.main(["--g5-manifest", "missing.json", "--audit-dir", "missing"])
        self.assertEqual(rc, 2)
        self.assertTrue(any("G5_CROSSWALK_REASON=PRIVATE_POSIX_REQUIRED" in call.args[0]
                            for call in printer.call_args_list if call.args))

    def test_identifier_collision_absence_and_composite_key(self):
        allowed = {"documents": {"id": "text", "amount": "numeric"}}
        self.assertEqual(cross.classify_relation("documents", "old_schema", allowed, "new_schema", "amount"),
                         ("TARGET_TABLE_NAME_ONLY", "documents", "TARGET_COLUMN_NAME_PRESENT"))
        self.assertEqual(cross.classify_relation("documents", "new_schema", allowed, "new_schema", "unknown")[2],
                         "TARGET_COLUMN_NAME_MISSING")
        self.assertEqual(cross.classify_relation("nonexistent", "new_schema", allowed, "new_schema")[0],
                         "OUTSIDE_AUTHORIZED_TARGET")
        self.assertEqual(cross.classify_relation("documents;DROP", "new_schema", allowed, "new_schema")[0],
                         "SOURCE_IDENTIFIER_UNSAFE")
        self.assertEqual(cross.classify_relation(None, None, allowed, "new_schema")[0], "SEMANTIC_ONLY")

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid") and hasattr(os, "O_NOFOLLOW"),
                         "requires POSIX private filesystem")
    def test_private_manifest_prevents_overwrite_and_tampering(self):
        packets, p3sha = create_packets()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.chmod(0o700)
            entries = []
            for packet in packets:
                ver = packet["origin"]["source_version_sha256"]
                entries.append({
                    "source_version_sha256": ver,
                    "file": f"source-version-{ver}.json.gpg",
                    "ciphertext_sha256": "c" * 64,
                    "plaintext_sha256": "d" * 64,
                    "row_counts": packet["row_counts"],
                    "sealed_and_roundtrip_verified": True,
                })
            manifest = {
                "contract": "g5-private-source-review-manifest-v1",
                "status": "ENCRYPTED_NOT_APPROVED",
                "p3_snapshot_sha256": p3sha,
                "financial_sql_executed": False,
                "context_activated": False,
                "approved_for_generation": False,
                "approved_for_import": False,
                "source_archive_sha256": "a" * 64,
                "lineage_report_sha256": "b" * 64,
                "lineage_identifier_sha256": "c" * 64,
                "sql_pattern_rows_excluded": 2,
                "versions": entries,
            }
            self.assertEqual(len(cross.require_source_manifest(manifest, root, p3sha)), 2)
            manifest["approved_for_generation"] = True
            with self.assertRaisesRegex(g5.Blocked, "SOURCE_MANIFEST_NOT_UNAPPROVED_OR_P3_DRIFT"):
                cross.require_source_manifest(manifest, root, p3sha)
            manifest["approved_for_generation"] = False
            manifest["versions"][1]["source_version_sha256"] = manifest["versions"][0]["source_version_sha256"]
            with self.assertRaisesRegex(g5.Blocked, "SOURCE_VERSION_MANIFEST_INVALID"):
                cross.require_source_manifest(manifest, root, p3sha)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW") and shutil.which("gpg"),
                         "requires POSIX private GPG")
    def test_real_synthetic_gpg_packet_verification_and_missing_row_block(self):
        packets, p3sha = create_packets()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.chmod(0o700)
            passphrase = "test-" + "local-fixture-generated-passphrase-123456"
            packet = packets[0]
            raw = sealed.private_json(packet)
            h = packet["origin"]["source_version_sha256"]
            file = root / f"source-version-{h}.json.gpg"
            sha = sealed.seal_gpg(file, raw, passphrase)
            receipt = {"p3_snapshot_sha256": p3sha,
                       "source_archive_sha256": packet["origin"]["source_archive_sha256"]}
            entry = {"source_version_sha256": h, "file": file.name,
                     "ciphertext_sha256": sha, "plaintext_sha256": hashlib.sha256(raw).hexdigest(),
                     "row_counts": packet["row_counts"], "sealed_and_roundtrip_verified": True}
            fetched = cross.open_verified_packet(root, entry, passphrase, receipt)
            self.assertEqual(fetched, packet)
            broken = dict(entry)
            broken["plaintext_sha256"] = "a" * 64
            with self.assertRaisesRegex(g5.Blocked, "SOURCE_VERSION_PLAINTEXT_MISMATCH"):
                cross.open_verified_packet(root, broken, passphrase, receipt)
            file.write_bytes(file.read_bytes() + b"corrupted")
            with self.assertRaisesRegex(g5.Blocked, "SOURCE_VERSION_CIPHERTEXT_MISMATCH"):
                cross.open_verified_packet(root, entry, passphrase, receipt)


if __name__ == "__main__":
    unittest.main()