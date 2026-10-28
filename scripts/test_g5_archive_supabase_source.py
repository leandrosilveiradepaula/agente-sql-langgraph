"""G5 offline archive safety tests: no DB, GPG, Docker, or secrets."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SOURCE = Path(__file__).resolve().parent / "operations" / "g5_archive_supabase_source.py"
SPEC = importlib.util.spec_from_file_location("g5_archive_source", SOURCE)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

PROJECT = "nywxpvzhlpqjtcafpdfe"
FPR = "A" * 40


class ArchiveSourceSafetyTests(unittest.TestCase):
    def test_only_exact_public_key_fingerprint_accepted(self):
        for fpr in ("", "short", "x" * 40, "0" * 41, "A" * 39):
            with self.subTest(fpr=fpr), self.assertRaises(m.ArchiveBlocked):
                m.recipient_exists(fpr)

    def test_fingerprint_must_match_the_real_local_public_key(self):
        good = "pub::::::::::\nfpr:::::::::AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:\n"
        fake = "pub::::::::::\nfpr:::::::::BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB:\n"
        with patch.object(m.subprocess, "run", return_value=MagicMock(returncode=0, stdout=good)):
            self.assertTrue(m.recipient_exists(FPR))
        with patch.object(m.subprocess, "run", return_value=MagicMock(returncode=0, stdout=fake)):
            self.assertFalse(m.recipient_exists(FPR))

    def test_pg_connectivity_is_pinned_to_source_and_verified_tls(self):
        dsn = ("postgresql://postgres." + PROJECT +
               ":secret@aws-0-us-east-2.pooler.supabase.com:5432/postgres"
               "?sslmode=verify-full")
        env = m.pg_environment(dsn, PROJECT)
        self.assertEqual(env["PGDATABASE"], "postgres")
        self.assertEqual(env["PGUSER"], "postgres." + PROJECT)
        self.assertEqual(env["PGPASSWORD"], "secret")
        self.assertEqual(env["PGSSLMODE"], "verify-full")
        self.assertIn("default_transaction_read_only=on", env["PGOPTIONS"])
        self.assertNotIn(dsn, str({k: v for k, v in env.items() if k != "PGPASSWORD"}))
        with self.assertRaises(Exception):
            m.pg_environment(dsn, "cenhadslwxgykqtuobgc")
        with self.assertRaises(Exception):
            m.pg_environment(dsn.replace("verify-full", "require"), PROJECT)

    def test_unknown_connection_options_are_not_silently_accepted(self):
        dsn = ("postgresql://postgres." + PROJECT +
               ":secret@aws-0-us-east-2.pooler.supabase.com:5432/postgres"
               "?sslmode=verify-full&options=-c%20search_path%3Dpublic")
        with self.assertRaises(m.ArchiveBlocked):
            m.pg_environment(dsn, PROJECT)

    def test_gpg_producer_streams_without_plaintext_file_path(self):
        class FakeChild:
            def __init__(self, argv):
                self.argv = argv
                self.stdout = io.BytesIO(b"plain-for-test")
            def wait(self, timeout=None):
                return 0
            def poll(self):
                return 0
        calls = []
        def launch(argv, **kwargs):
            calls.append((argv, kwargs))
            return FakeChild(argv)
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "encrypted.partial"
            with patch.object(m.shutil, "which", side_effect=lambda n: "/usr/bin/" + n):
                with patch.object(m.subprocess, "Popen", side_effect=launch):
                    m.encrypted_capture(target, FPR, {"PGPASSWORD": "secret"})
            self.assertTrue(target.exists())
            self.assertIn("pg_dump", calls[0][0][0])
            self.assertIn("--format=custom", calls[0][0])
            self.assertNotIn("secret", str(calls[0][0]))
            self.assertIn("gpg", calls[1][0][0])
            self.assertIn("--encrypt", calls[1][0])
            self.assertNotIn("PGPASSWORD", calls[1][1]["env"])

    def test_capture_requires_local_typed_confirmation_before_prompt_or_dump(self):
        with patch.object(m, "private_directory"):
            with patch.object(m, "tools_available", return_value=True):
                with patch.object(m, "recipient_exists", return_value=True):
                    with patch.object(m.sys.stdin, "isatty", return_value=True):
                        with patch("builtins.input", return_value="not-authorized"):
                            with patch.object(m.getpass, "getpass") as ask:
                                with patch.object(m, "encrypted_capture") as dump:
                                    with self.assertRaises(m.ArchiveBlocked) as exc:
                                        m.capture(PROJECT, Path("/root/private"), FPR)
                                    self.assertEqual(str(exc.exception), "CAPTURE_NOT_AUTHORIZED")
                                    ask.assert_not_called()
                                    dump.assert_not_called()

    def test_integrity_receipt_verifies_only_encrypted_bytes_not_restore(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            filename = f"source-{PROJECT}-20261028T120000Z-1234567890abcdef.dump.gpg"
            (directory / filename).write_bytes(b"fake-ciphertext-for-integrity-test")
            size, digest = (len(b"fake-ciphertext-for-integrity-test"),
                            __import__("hashlib").sha256(b"fake-ciphertext-for-integrity-test").hexdigest())
            manifest = directory / (filename + ".manifest.json")
            receipt = {
                "version": 1, "project_ref": PROJECT,
                "captured_at": "20261028T120000Z",
                "archive_name": filename, "encrypted_sha256": digest,
                "encrypted_bytes": size, "format": "pg_dump_custom_openpgp",
                "restore_verified": False,
            }
            manifest.write_text(json.dumps(receipt))
            with patch.object(m, "private_directory"), patch.object(m, "check_private_file"):
                m.verify(PROJECT, directory, manifest)
                (directory / filename).write_bytes(b"tampered")
                with self.assertRaises(m.ArchiveBlocked) as exc:
                    m.verify(PROJECT, directory, manifest)
                self.assertEqual(str(exc.exception), "ENCRYPTED_ARCHIVE_DIGEST_MISMATCH")
            self.assertIs(receipt["restore_verified"], False)

    def test_manifest_cannot_claim_restore_success(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            filename = f"source-{PROJECT}-20261028T120000Z-1234567890abcdef.dump.gpg"
            (directory / filename).write_bytes(b"test")
            receipt = {
                "version": 1, "project_ref": PROJECT,
                "captured_at": "20261028T120000Z",
                "archive_name": filename, "encrypted_sha256": "f" * 64,
                "encrypted_bytes": 4, "format": "pg_dump_custom_openpgp",
                "restore_verified": True,
            }
            manifest = directory / (filename + ".manifest.json")
            manifest.write_text(json.dumps(receipt))
            with patch.object(m, "private_directory"), patch.object(m, "check_private_file"):
                with self.assertRaises(m.ArchiveBlocked) as exc:
                    m.verify(PROJECT, directory, manifest)
                self.assertEqual(str(exc.exception), "MANIFEST_INVALID")

    def test_no_raw_database_or_original_credentials_committed_to_git(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("ARCHIVE-SOURCE-READONLY", source)
        self.assertIn("default_transaction_read_only=on", source)
        self.assertIn("restore_verified", source)
        self.assertIn("subprocess.DEVNULL", source)
        self.assertNotIn("psql -f", source)
        self.assertNotIn("DROP DATABASE", source)


if __name__ == "__main__":
    unittest.main()
