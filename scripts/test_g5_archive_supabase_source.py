"""G5 offline archive safety tests: no DB, GPG, Docker, or secrets."""
from __future__ import annotations

import importlib.util
import io
import json
import os
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


    def test_plan_never_reads_dsn_or_captures(self):
        import sys
        with patch.object(sys, "argv", [
            "g5_archive_supabase_source.py", "--plan", "--source-project-ref", PROJECT,
        ]):
            with patch.object(m, "tools_available", return_value=True):
                with patch.object(m.getpass, "getpass") as credentials:
                    with patch.object(m, "encrypted_capture") as dump:
                        self.assertEqual(m.main(), 0)
                        credentials.assert_not_called()
                        dump.assert_not_called()

    def test_capture_writes_only_encrypted_artifact_and_integrity_receipt(self):
        dsn = ("postgresql://postgres." + PROJECT +
               ":secret@aws-0-us-east-2.pooler.supabase.com:5432/postgres"
               "?sslmode=verify-full")
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            def fake_encrypted_capture(path, recipient, env):
                self.assertEqual(recipient, FPR)
                self.assertEqual(env["PGPASSWORD"], "secret")
                path.write_bytes(b"simulated-encrypted-bytes")
            with patch.object(m, "private_directory"), patch.object(m, "check_private_file"):
                with patch.object(m, "tools_available", return_value=True):
                    with patch.object(m, "recipient_exists", return_value=True):
                        with patch.object(m.sys.stdin, "isatty", return_value=True):
                            with patch("builtins.input", return_value="ARCHIVE-SOURCE-READONLY"):
                                with patch.object(m.getpass, "getpass", return_value=dsn):
                                    with patch.object(m, "encrypted_capture", side_effect=fake_encrypted_capture):
                                        receipt = m.capture(PROJECT, directory, FPR)
                data = json.loads(receipt.read_text())
                self.assertEqual(data["project_ref"], PROJECT)
                self.assertEqual(data["format"], "pg_dump_custom_openpgp")
                self.assertIs(data["restore_verified"], False)
                self.assertFalse(list(directory.glob("*.partial")))
                self.assertEqual((directory / data["archive_name"]).read_bytes(), b"simulated-encrypted-bytes")
                m.verify(PROJECT, directory, receipt)

    def test_failed_capture_never_leaves_a_final_archive(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            def fail_after_partial(path, *args):
                path.write_bytes(b"partial-ciphertext")
                raise m.ArchiveBlocked("ENCRYPTED_DUMP_FAILED")
            with patch.object(m, "private_directory"), patch.object(m, "tools_available", return_value=True):
                with patch.object(m, "recipient_exists", return_value=True):
                    with patch.object(m.sys.stdin, "isatty", return_value=True):
                        with patch("builtins.input", return_value="ARCHIVE-SOURCE-READONLY"):
                            with patch.object(m.getpass, "getpass", return_value="fake-dsn"):
                                with patch.object(m, "pg_environment", return_value={"PGPASSWORD": "secret"}):
                                    with patch.object(m, "encrypted_capture", side_effect=fail_after_partial):
                                        with self.assertRaises(m.ArchiveBlocked):
                                            m.capture(PROJECT, directory, FPR)
            self.assertEqual(list(directory.iterdir()), [])


    def test_collision_never_deletes_a_preexisting_archive(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            prior = []
            def collide(src, dst, *, follow_symlinks=False):
                existing = Path(dst)
                existing.write_bytes(b"previous-archive-must-survive")
                prior.append(existing)
                raise FileExistsError("simulated filename collision")
            def fake_dump(path, *args):
                path.write_bytes(b"encrypted-new-contents")
            with patch.object(m, "private_directory"), patch.object(m, "check_private_file"):
                with patch.object(m, "tools_available", return_value=True):
                    with patch.object(m, "recipient_exists", return_value=True):
                        with patch.object(m.sys.stdin, "isatty", return_value=True):
                            with patch("builtins.input", return_value="ARCHIVE-SOURCE-READONLY"):
                                with patch.object(m.getpass, "getpass", return_value="not-used"):
                                    with patch.object(m, "pg_environment", return_value={}):
                                        with patch.object(m, "encrypted_capture", side_effect=fake_dump):
                                            with patch.object(m.os, "link", side_effect=collide):
                                                with self.assertRaises(FileExistsError):
                                                    m.capture(PROJECT, directory, FPR)
            self.assertEqual(len(prior), 1)
            self.assertEqual(prior[0].read_bytes(), b"previous-archive-must-survive")
            self.assertEqual(len(list(directory.iterdir())), 1)


    def test_password_only_mode_needs_no_gpg_public_key(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            def fake_symmetric_dump(path, recipient, env, *, passphrase=None):
                self.assertIsNone(recipient)
                self.assertEqual(passphrase, "x" * 40)
                self.assertEqual(env["PGPASSWORD"], "db-secret")
                path.write_bytes(b"gpg-symmetric-test-ciphertext")
            with patch.object(m, "private_directory"), patch.object(m, "check_private_file"):
                with patch.object(m, "tools_available", return_value=True):
                    with patch.object(m, "recipient_exists") as key_lookup:
                        with patch.object(m.sys.stdin, "isatty", return_value=True):
                            with patch("builtins.input", return_value="ARCHIVE-SOURCE-READONLY"):
                                with patch.object(m.getpass, "getpass", side_effect=[
                                    "x" * 40, "x" * 40, "db-admin-dsn",
                                ]):
                                    with patch.object(m, "pg_environment", return_value={"PGPASSWORD": "db-secret"}):
                                        with patch.object(m, "encrypted_capture", side_effect=fake_symmetric_dump):
                                            receipt = m.capture(PROJECT, directory)
                        key_lookup.assert_not_called()
                metadata = json.loads(receipt.read_text())
                self.assertEqual(metadata["format"], "pg_dump_custom_openpgp_symmetric")
                self.assertIs(metadata["restore_verified"], False)
                m.verify(PROJECT, directory, receipt)

    def test_password_mismatch_and_weak_password_abort_before_db(self):
        for proposed in (
            ("x" * 31, "x" * 31),
            ("x" * 40, "y" * 40),
            ("a" * 31 + "\n", "a" * 31 + "\n"),
            ("☂" * 40, "☂" * 40),
        ):
            with self.subTest(proposed=proposed):
                with patch.object(m, "private_directory"), patch.object(m, "tools_available", return_value=True):
                    with patch.object(m.sys.stdin, "isatty", return_value=True):
                        with patch("builtins.input", return_value="ARCHIVE-SOURCE-READONLY"):
                            with patch.object(m.getpass, "getpass", side_effect=list(proposed)) as secret_prompt:
                                with patch.object(m, "pg_environment") as db:
                                    with self.assertRaises(m.ArchiveBlocked):
                                        m.capture(PROJECT, Path("/private"))
                                    db.assert_not_called()
                                    self.assertLessEqual(secret_prompt.call_count, 2)

    @unittest.skipUnless(os.name == "posix", "POSIX-only encrypted stream smoke")
    def test_symmetrical_gpg_secrets_only_in_anonymous_fd(self):
        """Real GPG roundtrip with synthetic bytes and a fake pg_dump binary."""
        gpg_binary = m.shutil.which("gpg")
        if not gpg_binary:
            self.skipTest("GPG unavailable on this runner")
        phrase = "Q" * 40  # Synthetic fixture, not a real backup password
        expected = b"OFFLINE_SYNTHETIC_TEST_DATA_ONLY\n"
        real_popen = m.subprocess.Popen
        gpg_invocations = []

        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            pg_dump = directory / "fake_pg_dump"
            pg_dump.write_text(
                "#!/bin/sh\nprintf 'OFFLINE_SYNTHETIC_TEST_DATA_ONLY\\n'\n",
                encoding="ascii",
            )
            pg_dump.chmod(0o700)
            homedir = directory / "gnupg"
            homedir.mkdir(mode=0o700)
            output = directory / "synthetic.gpg"
            def observer(argv, **kwargs):
                if argv[0] == gpg_binary:
                    gpg_invocations.append((argv, kwargs))
                return real_popen(argv, **kwargs)
            with patch.dict(os.environ, {"GNUPGHOME": str(homedir)}):
                with patch.object(m.shutil, "which", side_effect=lambda n:
                                  str(pg_dump) if n == "pg_dump" else gpg_binary if n == "gpg" else None):
                    with patch.object(m.subprocess, "Popen", side_effect=observer):
                        m.encrypted_capture(
                            output, None,
                            {"PATH": os.environ.get("PATH", ""), "PGPASSWORD": "fake-sql-password"},
                            passphrase=phrase,
                        )
                self.assertNotEqual(output.read_bytes(), expected)
                self.assertEqual(len(gpg_invocations), 1)
                args, options = gpg_invocations[0]
                self.assertIn("--symmetric", args)
                self.assertIn("--passphrase-fd", args)
                self.assertIn("AES256", args)
                self.assertEqual(len(options["pass_fds"]), 1)
                self.assertNotIn(phrase, str(args))
                self.assertNotIn(phrase, str(options["env"]))
                self.assertNotIn("PGPASSWORD", options["env"])
                # Decrypt fixture in a separate process with an anonymous FD.
                reader, writer = os.pipe()
                try:
                    decrypt = real_popen(
                        [gpg_binary, "--batch", "--no-tty", "--pinentry-mode",
                         "loopback", "--no-symkey-cache", "--passphrase-fd",
                         str(reader), "--decrypt", str(output)],
                        stdout=m.subprocess.PIPE, stderr=m.subprocess.DEVNULL,
                        pass_fds=(reader,),
                        env={k: os.environ[k] for k in
                             ("HOME", "PATH", "GNUPGHOME") if k in os.environ},
                    )
                    os.close(reader)
                    reader = None
                    os.write(writer, phrase.encode("ascii") + b"\n")
                    os.close(writer)
                    writer = None
                    clear, _ = decrypt.communicate(timeout=30)
                    self.assertEqual(decrypt.returncode, 0)
                    self.assertEqual(clear, expected)
                finally:
                    if reader is not None:
                        os.close(reader)
                    if writer is not None:
                        os.close(writer)

    def test_unusable_encryption_mode_blocked_before_disk_write(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "should-not-exist.gpg"
            with self.assertRaises(m.ArchiveBlocked):
                m.encrypted_capture(path, None, {})
            with self.assertRaises(m.ArchiveBlocked):
                m.encrypted_capture(path, FPR, {}, passphrase="x" * 40)
            self.assertFalse(path.exists())


    def test_pg_dump_version_probe_blocks_16_and_accepts_17(self):
        with patch.object(m.shutil, "which", side_effect=lambda n: "/usr/bin/" + n):
            with patch.object(m.subprocess, "run") as proc:
                proc.return_value = MagicMock(
                    returncode=0, stdout="pg_dump (PostgreSQL) 16.15\n"
                )
                self.assertFalse(m.tools_available())
                proc.return_value = MagicMock(
                    returncode=0, stdout="pg_dump (PostgreSQL) 17.11 (Ubuntu)\n"
                )
                self.assertTrue(m.tools_available())
                proc.return_value = MagicMock(returncode=1, stdout="")
                self.assertFalse(m.tools_available())

    def test_plan_reports_missing_incompatible_pg_dump(self):
        import sys
        with patch.object(sys, "argv", [
            "g5_archive_supabase_source.py", "--plan", "--source-project-ref", PROJECT,
        ]):
            with patch.object(m, "tools_available", return_value=False):
                with patch.object(m.getpass, "getpass") as no_credentials:
                    self.assertEqual(m.main(), 2)
                    no_credentials.assert_not_called()


    def test_safe_postgres_errors_never_echo_connection_or_secret(self):
        fixtures = {
            "SOURCE_AUTHENTICATION_FAILED":
                "pg_dump: error: password authentication failed for user postgres.private-password",
            "SOURCE_TLS_VERIFICATION_FAILED":
                "pg_dump: error: SSL error: certificate verify failed for hostname SECRET-HOST",
            "SOURCE_CLIENT_VERSION_MISMATCH":
                "pg_dump: error: aborting because of server version mismatch",
            "SOURCE_CONNECTION_POOL_EXHAUSTED":
                "pg_dump: error: too many clients already",
            "SOURCE_DNS_FAILED":
                "pg_dump: error: could not translate host name SECRET-HOST to address",
            "SOURCE_NETWORK_FAILED":
                "pg_dump: error: connection refused to PRIVATE-ENDPOINT",
            "SOURCE_ACCESS_DENIED":
                "pg_dump: error: permission denied for table PRIVATE-FINANCIAL-TABLE",
            "SOURCE_LOCK_TIMEOUT":
                "pg_dump: error: canceling statement due to lock timeout",
            "SOURCE_QUERY_FAILED":
                "pg_dump: error: query failed: SELECT * FROM SECRET-TABLE",
        }
        for category, secret_line in fixtures.items():
            with self.subTest(category=category):
                result = m.classify_pg_dump_error(secret_line.encode())
                self.assertEqual(result, category)
                self.assertIn(result, m.PG_DUMP_ERROR_ORDER)
                self.assertNotIn("PRIVATE", result)
                self.assertNotIn("SECRET", result)
        self.assertIsNone(m.classify_pg_dump_error("unrecognized private DSN secret"))
        observed = set()
        m.observe_pg_dump_stderr(io.BytesIO(
            b"pg_dump: error: permission denied for table confidential\n"
            b"pg_dump: error: query failed: SELECT confidential\n"
        ), observed)
        self.assertEqual(observed, {"SOURCE_ACCESS_DENIED", "SOURCE_QUERY_FAILED"})

    @unittest.skipUnless(os.name == "posix", "Linux-only actual pipeline failure proof")
    def test_failed_pg_dump_is_sanitized_even_with_real_gpg(self):
        """Run real GPG, simulated failing pg_dump, no database/network/secret logs."""
        gpg_binary = m.shutil.which("gpg")
        if not gpg_binary:
            self.skipTest("GPG unavailable on this runner")
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            fake = directory / "failing_pg_dump"
            fake.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' 'pg_dump: error: password authentication failed "
                "for user FAKE_PRIVATE_ID_AND_PASSWORD' >&2\n"
                "exit 1\n", encoding="ascii",
            )
            fake.chmod(0o700)
            homedir = directory / "gnupg"
            homedir.mkdir(mode=0o700)
            encrypted = directory / "incomplete.gpg"
            with patch.dict(os.environ, {"GNUPGHOME": str(homedir)}):
                with patch.object(m.shutil, "which", side_effect=lambda name:
                                  str(fake) if name == "pg_dump"
                                  else gpg_binary if name == "gpg" else None):
                    with self.assertRaises(m.ArchiveBlocked) as error:
                        m.encrypted_capture(
                            encrypted, None,
                            {"PATH": os.environ.get("PATH", ""),
                             "PGPASSWORD": "SYNTHETIC_PASSWORD_MUST_NOT_LEAK"},
                            passphrase="a" * 40,
                        )
            self.assertEqual(str(error.exception), "SOURCE_AUTHENTICATION_FAILED")
            self.assertNotIn("FAKE_PRIVATE_ID_AND_PASSWORD", str(error.exception))
            self.assertNotIn("SYNTHETIC_PASSWORD_MUST_NOT_LEAK", str(error.exception))

    @unittest.skipUnless(os.name == "posix", "Linux-only pipeline exit code proof")
    def test_failed_gpg_is_distinct_from_failed_pg_dump(self):
        """No DB/GPG server: both executables are isolated fake fixtures."""
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            fake_pg_dump = directory / "good_pg_dump"
            fake_gpg = directory / "broken_gpg"
            fake_pg_dump.write_text("#!/bin/sh\nprintf 'fixture-test\\n'\n", encoding="ascii")
            fake_gpg.write_text("#!/bin/sh\nexit 2\n", encoding="ascii")
            fake_pg_dump.chmod(0o700)
            fake_gpg.chmod(0o700)
            with patch.object(m.shutil, "which", side_effect=lambda name:
                              str(fake_pg_dump) if name == "pg_dump" else str(fake_gpg)):
                with self.assertRaises(m.ArchiveBlocked) as error:
                    m.encrypted_capture(
                        directory / "incomplete.gpg", None,
                        {"PATH": os.environ.get("PATH", "")},
                        passphrase="a" * 40,
                    )
            self.assertEqual(str(error.exception), "GPG_ENCRYPTION_FAILED")


    def test_capture_cli_verifies_integrity_before_claiming_success(self):
        import sys
        manifest = Path("/root/private/synthetic.dump.gpg.manifest.json")
        args = ["g5_archive_supabase_source.py", "--capture",
                "--source-project-ref", PROJECT]
        with patch.object(sys, "argv", args):
            with patch.object(m, "capture", return_value=manifest) as make:
                with patch.object(m, "verify") as proof:
                    self.assertEqual(m.main(), 0)
                    make.assert_called_once()
                    proof.assert_called_once_with(
                        PROJECT, m.ARCHIVE_DIR, manifest
                    )

    def test_failed_post_capture_integrity_check_does_not_report_success(self):
        import sys
        import contextlib
        buffer = io.StringIO()
        manifest = Path("/root/private/synthetic.dump.gpg.manifest.json")
        args = ["g5_archive_supabase_source.py", "--capture",
                "--source-project-ref", PROJECT]
        with patch.object(sys, "argv", args):
            with patch.object(m, "capture", return_value=manifest):
                with patch.object(m, "verify",
                                  side_effect=m.ArchiveBlocked("ENCRYPTED_ARCHIVE_DIGEST_MISMATCH")):
                    with contextlib.redirect_stdout(buffer):
                        self.assertEqual(m.main(), 2)
        text = buffer.getvalue()
        self.assertIn("G5_ARCHIVE_RESULT=BLOCKED", text)
        self.assertNotIn("G5_ARCHIVE_RESULT=ENCRYPTED_CAPTURED", text)
        self.assertNotIn("G5_ARCHIVE_MANIFEST=", text)
        self.assertIn("G5_ARCHIVE_ERROR=ENCRYPTED_ARCHIVE_DIGEST_MISMATCH", text)


if __name__ == "__main__":
    unittest.main()
