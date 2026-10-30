"""Fail-closed synthetic end-to-end G5 archival-to-private-review tests."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.operations import g5_semantic_lineage_candidate as lineage
from scripts.operations import g5_semantic_context_review_offline as reviewed
from scripts.test_g5_semantic_lineage_candidate import fixture


class SourceReviewTests(unittest.TestCase):
    def historical_fixture(self, schema="accounting_alpha"):
        data, receipt, prior, p3, index, p3_sha, cipher_sha = fixture(schema)
        collector = reviewed.VersionedCollector()
        report, hints = lineage.scan(io.BytesIO(data), receipt, prior, index,
                                     p3_sha=p3_sha, cipher_sha=cipher_sha,
                                     on_semantic_record=collector.accept)
        return data, receipt, prior, p3, p3_sha, report, hints, collector

    def test_source_rules_recovered_but_never_approved(self):
        for schema in ("accounting_alpha", "billing_beta"):
            with self.subTest(schema=schema):
                _, receipt, _, _, p3_sha, report, hints, collector = self.historical_fixture(schema)
                packets = collector.packages(receipt=receipt, lineage=report, hints=hints, p3_sha=p3_sha)
                self.assertEqual(len(packets), 2)
                self.assertEqual(sum(sum(p["row_counts"].values()) for p in packets), 8)
                self.assertTrue(all(p["can_use_as_llm_or_planner_context"] is False for p in packets))
                self.assertTrue(all(p["can_execute_financial_sql"] is False for p in packets))
                self.assertTrue(all(p["tenant"] is None for p in packets))
                self.assertTrue(all(p["historical_sql_patterns_excluded"] for p in packets))
                self.assertTrue(all(len(p["physical_identifier_hints_unapproved"]) == 2 for p in packets))
                private_text = json.dumps(packets)
                self.assertIn("sensitive_rule_should_not_leak", private_text)
                self.assertIn("private_description_should_not_leak", private_text)
                for secret in ("select_private_sql_do_not_emit", "private_benchmark_do_not_emit"):
                    self.assertNotIn(secret, private_text)
                self.assertIn("knowledge-1", private_text)  # in encrypted packet ONLY
                self.assertNotIn("knowledge-1", json.dumps(report))

    def test_empty_or_unrecognized_version_fails_closed(self):
        _, receipt, _, _, p3_sha, report, hints, collector = self.historical_fixture()
        candidate = collector.records[next(iter(collector.records))]
        candidate["ai_ducklake_agent_rules"].clear()
        with self.assertRaisesRegex(lineage.Blocked, "CONTEXT_VERSION_ROWS_DO_NOT_MATCH_LINEAGE"):
            collector.packages(receipt=receipt, lineage=report, hints=hints, p3_sha=p3_sha)

    def test_unverified_technical_hint_ref_fails(self):
        _, receipt, _, _, p3_sha, report, hints, collector = self.historical_fixture()
        hints["candidates"][0]["source_record_sha256"] = "0" * 64
        with self.assertRaisesRegex(lineage.Blocked, "UNVERIFIED_CANDIDATE_REFERENCE"):
            collector.packages(receipt=receipt, lineage=report, hints=hints, p3_sha=p3_sha)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"), "requires POSIX private files")
    def test_tampered_reconciled_report_fails(self):
        data, receipt, prior, p3, p3_sha, report, hints, collector = self.historical_fixture()
        report["source_row_count"] += 1
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); root.chmod(0o700)
            cipher = root / "raw.sql.gpg"
            cipher.write_bytes(b"synthetic")
            cipher.chmod(0o600)
            receipt["output_sha256"] = lineage.digest_private_file(cipher)
            # Tampered lineage cannot agree with independent SOURCE re-scan.
            inventory = prior
            original_hash = receipt["output_sha256"]
            index, _ = lineage.physical_shape(p3)
            rereport, _ = lineage.scan(io.BytesIO(data), receipt, inventory, index,
                                      p3_sha=p3_sha, cipher_sha="b" * 64)
            self.assertNotEqual(rereport, report)
            self.assertNotEqual(original_hash, "b" * 64)

    def test_exclusion_at_callback_boundary(self):
        data, receipt, prior, p3, p3_sha, report, hints, collector = self.historical_fixture()
        self.assertEqual(sum(len(r) for table in collector.records.values() for r in table.values()), 8)
        with self.assertRaisesRegex(lineage.Blocked, "EVALUATION_ROW_REACHED_CONTEXT_COLLECTOR"):
            collector.accept(lineage.EVALUATION_ONLY, "a" * 64, {"agent_version": b"bad"}, b"bad\n")

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW") and shutil.which("gpg"),
                         "requires POSIX private files and GPG")
    def test_encryption_roundtrip_and_manifest_never_leak(self):
        _, receipt, _, _, p3_sha, report, hints, collector = self.historical_fixture()
        packets = collector.packages(receipt=receipt, lineage=report, hints=hints, p3_sha=p3_sha)
        password = "test-fixture-passphrase-generated-locally"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); root.chmod(0o700)
            manifest = {"versions": []}
            for packet in packets:
                original = reviewed.private_json(packet)
                path = root / (packet["origin"]["source_version_sha256"] + ".gpg")
                digest = reviewed.seal_gpg(path, original, password)
                reviewed.verify_gpg(path, password, original)
                self.assertEqual(digest, lineage.digest_private_file(path))
                self.assertEqual(path.stat().st_mode & 0o077, 0)
                self.assertNotIn(b"sensitive_rule_should_not_leak", path.read_bytes())
                manifest["versions"].append({"sha": digest, "rows": packet["row_counts"]})
                with self.assertRaises(FileExistsError):
                    reviewed.seal_gpg(path, original, password)
            manifest_str = json.dumps(manifest)
            self.assertNotIn("sensitive_rule", manifest_str)
            self.assertNotIn("select_private_sql", manifest_str)
            self.assertNotIn("knowledge-1", manifest_str)


if __name__ == "__main__":
    unittest.main()
