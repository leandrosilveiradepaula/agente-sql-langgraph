"""G5 read-only extension compatibility audit: synthetic data only."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SOURCE = Path(__file__).parent / "operations" / "g5_extension_compatibility_readonly.py"
SPEC = importlib.util.spec_from_file_location("g5_extension_compatibility_readonly", SOURCE)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
PROJECT = "nywxpvzhlpqjtcafpdfe"
FAKE_PASS = "F" * 40
SHA = "sha256:" + "a" * 64


class ExtensionAuditTests(unittest.TestCase):
    def test_extension_toc_parser_retains_only_strict_extension_identifiers(self):
        lines = io.BytesIO(
            b"; private archive header\n"
            b"1; 3079 1200 EXTENSION - pgcrypto owner\n"
            b"2; 3079 1300 EXTENSION - supabase_vault owner\n"
            b"3; 3079 1301 EXTENSION - uuid-ossp owner\n"
            b"4; 1259 1000 TABLE public PRIVATE_CUSTOMER_DATA owner\n"
            b"5; 0 0 COMMENT - EXTENSION pgcrypto owner\n"
        )
        from scripts.operations.g5_inspect_encrypted_source import read_toc_counts
        counts, extensions, invalid = [0], set(), [False]
        read_toc_counts(lines, counts, extensions, invalid)
        self.assertEqual(counts, [5])
        self.assertEqual(extensions, {"pgcrypto", "supabase_vault", "uuid-ossp"})
        self.assertFalse(invalid[0])
        self.assertNotIn("PRIVATE_CUSTOMER_DATA", repr(extensions))
        bad = io.BytesIO(
            b'1; 3079 1300 EXTENSION - "SENSITIVE_NAME" owner\n'
        )
        counts, extensions, invalid = [0], set(), [False]
        read_toc_counts(bad, counts, extensions, invalid)
        self.assertEqual(counts, [1])
        self.assertTrue(invalid[0])

    def test_image_reference_allowlist_is_structural(self):
        for ok in ("postgres:17", "supabase/postgres:17.6.1.136"):
            self.assertIsNotNone(m.IMAGE_REF.fullmatch(ok))
        for rejected in (
            "postgres:latest", "supabase/postgres:15.1.1.1",
            "example.com/attacker/postgres:17", "postgres:17 && whoami",
            "postgres:17\n", "supabase/postgres:17.6.1.136:evil",
        ):
            self.assertIsNone(m.IMAGE_REF.fullmatch(rejected))
        with patch.object(m, "docker_query", return_value=MagicMock(
            returncode=0, stdout=(SHA + "\n").encode(),
        )) as query:
            self.assertEqual(m.cached_image_id(["docker"], "postgres:17"), SHA)
            query.assert_called_once_with(
                ["docker"], ["image", "inspect", "--format", "{{.Id}}", "postgres:17"],
            )
        with patch.object(m, "docker_query") as query:
            with self.assertRaises(m.ArchiveBlocked):
                m.cached_image_id(["docker"], "malicious:17")
            query.assert_not_called()

    def test_image_metadata_probe_has_no_network_mount_privilege_db_or_secrets(self):
        result = MagicMock(
            returncode=0, stdout=b"pgcrypto\nsupabase_vault\nuuid-ossp\n",
        )
        with patch.object(m, "docker_query", return_value=result) as query:
            available = m.available_control_files(["docker"], SHA)
        self.assertEqual(available, {"pgcrypto", "supabase_vault", "uuid-ossp"})
        argv = query.call_args.args[1]
        self.assertIn("--network=none", argv)
        self.assertIn("--pull=never", argv)
        self.assertIn("--read-only", argv)
        self.assertIn("--user=65534:65534", argv)
        self.assertIn("--cap-drop=ALL", argv)
        self.assertIn("--security-opt=no-new-privileges", argv)
        self.assertIn("--log-driver=none", argv)
        self.assertIn("--entrypoint=/bin/sh", argv)
        self.assertIn(SHA, argv)
        self.assertNotIn("postgres:17", argv)
        self.assertFalse(any(value in argv for value in (
            "-p", "-P", "--publish", "-v", "--volume", "--mount",
            "--privileged", "--network=host",
        )))
        self.assertNotIn("DATABASE_URL", str(argv))
        self.assertNotIn("PGPASSWORD", str(argv))
        self.assertNotIn("/root/.local/share", str(argv))

    def test_invalid_control_file_output_fails_without_echoing_names(self):
        for out in (
            b"", b"pgcrypto\n PRIVATE_DSN\n",
            b"pgcrypto\nsecret;id\n",
            b"pgcrypto\nsome.file\n",
            b"p" * 32769,
            b"pgcrypto\n\xff\n",
        ):
            with self.subTest(output_length=len(out)):
                with patch.object(m, "docker_query", return_value=MagicMock(
                    returncode=0, stdout=out,
                )):
                    with self.assertRaises(m.ArchiveBlocked) as error:
                        m.available_control_files(["docker"], SHA)
                    self.assertEqual(str(error.exception),
                                     "IMAGE_EXTENSION_PROBE_INVALID")
                    self.assertNotIn("PRIVATE_DSN", str(error.exception))

    def test_missing_extensions_is_generic_not_business_hardcode(self):
        requirements = {"supabase_vault", "pgcrypto", "uuid-ossp"}
        vanilla = {"pgcrypto", "uuid-ossp", "plpgsql"}
        supabase = vanilla | {"supabase_vault"}
        self.assertEqual(m.compare_extensions(requirements, vanilla),
                         ("supabase_vault",))
        self.assertEqual(m.compare_extensions(requirements, supabase), ())
        with self.assertRaises(m.ArchiveBlocked):
            m.compare_extensions(set(), vanilla)
        with self.assertRaises(m.ArchiveBlocked):
            m.compare_extensions({"invalid;SQL"}, vanilla)

    def test_cli_checks_images_before_requesting_backup_password(self):
        import sys
        args = ["audit.py", "--manifest", "/private/synthetic.json",
                "--source-project-ref", PROJECT,
                "--image-ref", "supabase/postgres:17.6.1.136"]
        with patch.object(sys, "argv", args):
            with patch.object(m, "validated_archive", return_value=Path("/private/archive.gpg")):
                with patch.object(m, "docker_executable", return_value=["docker"]):
                    with patch.object(m, "cached_image_id",
                                      side_effect=m.ArchiveBlocked("POSTGRES17_IMAGE_NOT_CACHED")):
                        with patch.object(m.getpass, "getpass") as getpass:
                            with contextlib.redirect_stdout(io.StringIO()) as output:
                                self.assertEqual(m.main(), 2)
                            getpass.assert_not_called()
                            self.assertIn("POSTGRES17_IMAGE_NOT_CACHED", output.getvalue())

    def test_cli_compares_two_candidates_without_real_restore(self):
        import sys
        args = ["audit.py", "--manifest", "/private/synthetic.json",
                "--source-project-ref", PROJECT,
                "--image-ref", "postgres:17",
                "--image-ref", "supabase/postgres:17.6.1.136"]
        def inventory(_archive, _password, _binary, *, extensions):
            extensions.update({"pgcrypto", "supabase_vault", "uuid-ossp"})
            return 25905751, 811
        with patch.object(sys, "argv", args):
            with patch.object(m, "validated_archive", return_value=Path("/private/archive.gpg")):
                with patch.object(m, "docker_executable", return_value=["docker"]):
                    with patch.object(m, "cached_image_id", return_value=SHA):
                        with patch.object(m, "available_control_files", side_effect=[
                            {"pgcrypto", "plpgsql", "uuid-ossp"},
                            {"pgcrypto", "plpgsql", "uuid-ossp", "supabase_vault"},
                        ]):
                            with patch.object(m, "pg_restore_binary",
                                              return_value="pg_restore"):
                                with patch.object(m.sys.stdin, "isatty",
                                                  return_value=True):
                                    with patch.object(m.getpass, "getpass",
                                                      return_value=FAKE_PASS):
                                        with patch.object(m, "decrypt_and_check_toc",
                                                          side_effect=inventory) as decrypt:
                                            with contextlib.redirect_stdout(io.StringIO()) as printed:
                                                self.assertEqual(m.main(), 0)
        content = printed.getvalue()
        self.assertIn("G5_ARCHIVE_EXTENSION_COUNT=3", content)
        self.assertIn("G5_IMAGE_1_MISSING=supabase_vault", content)
        self.assertIn("G5_IMAGE_2_MISSING_COUNT=0", content)
        self.assertIn("G5_IMAGE_2_EXTENSION_COVERAGE=FILES_PRESENT_NOT_RESTORE_PROOF", content)
        self.assertIn("G5_RESTORE_TEST=NOT_PERFORMED", content)
        self.assertNotIn(FAKE_PASS, content)
        self.assertNotIn("G5_RESTORE_TEST=PASS", content)
        decrypt.assert_called_once()

    @unittest.skipUnless(os.name == "posix" and shutil.which("gpg"), "Linux GPG only")
    def test_real_gpg_and_fake_pg_restore_inventory_never_leaks_table_names(self):
        from scripts.test_g5_inspect_encrypted_source import make_ciphertext
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            encrypted = root / "fixture.gpg"
            make_ciphertext(encrypted, b"PGDMP" + b"TEST_ONLY" * 15000, password=FAKE_PASS)
            fixture = root / "pg_restore_fixture"
            fixture.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "if sys.stdin.buffer.read(5) != b'PGDMP': sys.exit(2)\n"
                "sys.stdout.write('1; 3079 1000 EXTENSION - pgcrypto owner\\n'"
                "+'2; 3079 1001 EXTENSION - supabase_vault owner\\n'"
                "+'3; 1259 1002 TABLE public PRIVATE_CUSTOMER_DATA owner\\n')\n",
                encoding="ascii",
            )
            fixture.chmod(0o700)
            (root / "gnupg").mkdir(mode=0o700)
            inventory: set[str] = set()
            with patch.dict(os.environ, {"GNUPGHOME": str(root / "gnupg")}):
                with contextlib.redirect_stdout(io.StringIO()) as printed:
                    bytes_read, items = m.decrypt_and_check_toc(
                        encrypted, FAKE_PASS, str(fixture), extensions=inventory,
                    )
            # The encryption fixture helper uses its own synthetic password.
            # A wrong passphrase is detected instead of hiding an error.
            self.assertEqual(items, 3)
            self.assertEqual(inventory, {"pgcrypto", "supabase_vault"})
            self.assertGreater(bytes_read, 100)
            self.assertEqual(printed.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
