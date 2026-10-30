"""Offline synthetic tests. Never read user files, use real GPG keys, or SQL."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts.operations.g5_semantic_lineage_candidate import (
    Blocked, CATALOGS, EVALUATION_ONLY, decode_copy_field, decrypt_gpg,
    digest_private_file, physical_shape, private_write, read_json_private,
    scan, select_reference, sha,
)


def fixture(schema="client_omega"):
    # Structurally different authorized physical schemas, no tenant-specific if.
    p3 = {
        "contract": "p3-metadata-snapshot-v1", "sql_executed": False,
        "llm_calls": 0, "physical": [
            [schema, "ledger_entries", "record_id", "text"],
            [schema, "ledger_entries", "amount_net", "numeric"],
            [schema, "ledger_entries", "date_field", "date"],
            [schema, "cost_centers", "record_id", "text"],
            [schema, "cost_centers", "label", "text"],
        ],
    }
    index, _ = physical_shape(p3)
    versions = ("knowledge-1", "knowledge-2")
    raw = [b'-- Historical pg_restore fixture\n', b'SET statement_timeout = 0;\n']
    counts = {}
    rowhashes = {}
    version_counts = {}
    for name in sorted(CATALOGS):
        columns = {
            "ai_ducklake_agent_rules": ("id", "agent_version", "is_active", "rule_content"),
            "ai_ducklake_dre_mapping": ("id", "agent_version", "sign_convention", "business_description"),
            "ai_ducklake_entity_aliases": ("id", "agent_version", "target_table", "target_column", "canonical_value"),
            "ai_ducklake_sql_patterns": ("id", "agent_version", "sql_pattern", "business_question_examples"),
            "ai_ducklake_table_catalog": ("id", "agent_version", "schema_name", "table_name", "primary_key"),
        }[name]
        raw.append((f'COPY public.{name} (' + ', '.join(columns) + ') FROM stdin;\n').encode('ascii'))
        h = hashlib.sha256()
        vc = {}
        for i, version in enumerate(versions):
            fields = {
                "ai_ducklake_agent_rules": [str(i), version, "t", "sensitive_rule_should_not_leak"],
                "ai_ducklake_dre_mapping": [str(i), version, "positive", "private_description_should_not_leak"],
                "ai_ducklake_entity_aliases": [str(i), version,
                    "source_schema.ledger_entries" if i == 0 else "ledger_entries",
                    "amount_net", "secret_account_should_not_leak"],
                "ai_ducklake_sql_patterns": [str(i), version, "select_private_sql_do_not_emit", "private_benchmark_do_not_emit"],
                "ai_ducklake_table_catalog": [str(i), version, "legacy", "ledger_entries",
                                              "record_id" if i == 0 else "missing_key"],
            }[name]
            line = ("\t".join(fields) + "\n").encode('ascii')
            raw.append(line)
            h.update(line)
            ver_hash = sha(version.encode('utf-8'))
            vc[ver_hash] = vc.get(ver_hash, 0) + 1
        counts[name] = len(versions)
        rowhashes[name] = h.hexdigest()
        version_counts[name] = vc
        raw.append(b'\\.\n')
    data = b''.join(raw)
    receipt = {
        "version": 1, "selected_collections": sorted(CATALOGS),
        "source_archive_sha256": "a" * 64,
        "sql_executed": False, "context_activated": False,
        "decrypted_bytes": len(data),
        "decrypted_sha256": sha(data), "row_counts": counts,
    }
    p3_sha = sha(json.dumps(p3).encode('utf-8'))
    cipher_sha = "b" * 64
    previous = {
        "contract": "g5-semantic-source-inventory-offline-v1",
        "source_archive_sha256": receipt["source_archive_sha256"],
        "recovered_ciphertext_sha256": cipher_sha,
        "p3_snapshot_sha256": p3_sha,
        "financial_sql_executed": False,
        "source_collections": [
            {"name": name, "rows": counts[name], "rows_sha256": rowhashes[name],
             "versions": [{"version_sha256": v, "rows": n} for v, n in vc.items()]}
            for name, vc in sorted(version_counts.items())
        ],
    }
    return data, receipt, previous, p3, index, p3_sha, cipher_sha


class LineageTests(unittest.TestCase):
    def test_two_materially_distinct_physical_contexts(self):
        for physical_schema in ("client_omega", "billing_epsilon"):
            with self.subTest(physical_schema=physical_schema):
                data, receipt, previous, _p3, index, p3_sha, cipher_sha = fixture(physical_schema)
                report, detail = scan(io.BytesIO(data), receipt, previous, index,
                                      p3_sha=p3_sha, cipher_sha=cipher_sha)
                self.assertEqual(report["source_row_count"], 10)
                self.assertEqual(report["source_collection_count"], 5)
                self.assertEqual(report["physical_evidence_counts"]["catalog_TABLE_NAME_ONLY"], 2)
                self.assertEqual(report["physical_evidence_counts"]["alias_TABLE_NAME_ONLY"], 2)
                self.assertEqual(report["physical_evidence_counts"]["alias_COLUMN_NAME_EXISTS"], 2)
                self.assertEqual(report["physical_evidence_counts"]["catalog_PRIMARY_KEY_COLUMNS_EXIST"], 1)
                self.assertEqual(report["physical_evidence_counts"]["catalog_PRIMARY_KEY_COLUMNS_MISSING"], 1)
                self.assertEqual(report["physical_evidence_counts"]["dre_sign_declared"], 2)
                self.assertTrue(report["historical_sql_patterns_evaluation_only"])
                self.assertFalse(report["mapped_context_approved"])
                self.assertFalse(detail["approved_for_context_activation"])
                self.assertEqual(len(detail["candidates"]), 4)
                self.assertEqual({v["version_sha256"] for v in report["version_scope"]},
                                 {sha(x.encode()) for x in ("knowledge-1", "knowledge-2")})
                serialized = json.dumps((report, detail))
                for secret in ("secret_account", "sensitive_rule", "private_benchmark", "select_private_sql"):
                    self.assertNotIn(secret, serialized)
                self.assertNotIn("knowledge-1", serialized)
                self.assertNotIn("knowledge-2", serialized)

    def test_version_count_drift_blocks(self):
        data, receipt, prior, _, index, fingerprint, cipher = fixture()
        prior["source_collections"][0]["versions"][0]["rows"] += 1
        with self.assertRaisesRegex(Blocked, "PRIOR_SOURCE_VERSION_MISMATCH"):
            scan(io.BytesIO(data), receipt, prior, index, p3_sha=fingerprint, cipher_sha=cipher)

    def test_content_digest_and_tampering_blocks(self):
        data, receipt, prior, _, index, fingerprint, cipher = fixture()
        with self.assertRaisesRegex(Blocked, "SOURCE_CONTENT_DIGEST_MISMATCH"):
            scan(io.BytesIO(data + b'--extra\n'), receipt, prior, index,
                 p3_sha=fingerprint, cipher_sha=cipher)
        with self.assertRaises(Blocked):
            scan(io.BytesIO(data.replace(b'\\.\n', b'', 1)), receipt, prior, index,
                 p3_sha=fingerprint, cipher_sha=cipher)
        self.assertEqual(EVALUATION_ONLY, "ai_ducklake_sql_patterns")

    def test_unqualified_name_and_ambiguity_not_approval(self):
        index = {"ledger_entries": {"client_a": {"id"}, "client_b": {"id"}}}
        self.assertEqual(select_reference(index, None, "ledger_entries")[0], "AMBIGUOUS_TABLE_NAME")
        self.assertEqual(select_reference(index, "client_a", "ledger_entries")[0], "EXACT_IDENTIFIER_ONLY")
        self.assertEqual(select_reference(index, "bad schema", "ledger_entries")[0], "REFERENCE_INVALID")
        self.assertEqual(select_reference(index, "client_a", "missing")[0], "NO_PHYSICAL_NAME_MATCH")

    def test_copy_escapes_and_null(self):
        self.assertIsNone(decode_copy_field(b'\\N'))
        self.assertEqual(decode_copy_field(b'a\\tb\\n'), 'a\tb\n')
        self.assertEqual(decode_copy_field(b'\\x41\\134'), 'A\\')
        with self.assertRaises(Blocked):
            decode_copy_field(b'\\x')

    def test_windows_private_file_operations_are_rejected(self):
        if os.name == "posix" and hasattr(os, "O_NOFOLLOW"):
            self.skipTest("Windows-only negative assertion")
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(Blocked, "PRIVATE_POSIX_REQUIRED"):
                private_write(Path(td) / "review.json", {"not_approved": True})
            with self.assertRaisesRegex(Blocked, "CIPHER_PATH_INVALID"):
                digest_private_file(Path(td) / "missing.gpg")

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"), "requires POSIX owner-only I/O")
    def test_private_output_exclusive_and_no_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            root.chmod(0o700)
            file = root / "review.json"
            private_write(file, {"not_approved": True})
            self.assertEqual(read_json_private(file)[0], {"not_approved": True})
            self.assertEqual(file.stat().st_mode & 0o077, 0)
            with self.assertRaises(FileExistsError):
                private_write(file, {"oops": True})
            link = root / "link.json"
            link.symlink_to(file)
            with self.assertRaises(Blocked):
                read_json_private(link)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW") and shutil.which("gpg"),
                         "requires POSIX private pipes and GPG")
    def test_synthetic_gpg_passphrase_pipe_only(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.gpg"
            password = "test-fixture-passphrase-generated-locally"
            payload = b'private_fixture_content_that_must_not_leak'
            # Test-only fixture: no real user data and no external network.
            p = subprocess.run([
                "gpg", "--batch", "--pinentry-mode", "loopback",
                "--passphrase", password, "--symmetric", "--cipher-algo", "AES256",
                "--output", str(path)], input=payload,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
            )
            self.assertEqual(p.returncode, 0)
            path.chmod(0o600)
            self.assertRegex(digest_private_file(path), r"^[a-f0-9]{64}$")
            p2 = decrypt_gpg(path, password)
            actual = p2.stdout.read()
            p2.stdout.close()
            self.assertEqual(p2.wait(timeout=20), 0)
            self.assertEqual(actual, payload)


if __name__ == "__main__":
    unittest.main()
