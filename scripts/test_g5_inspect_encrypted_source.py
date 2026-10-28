"""G5 encrypted archive inspection offline tests: synthetic data only."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock

SOURCE = Path(__file__).parent / "operations" / "g5_inspect_encrypted_source.py"
SPEC = importlib.util.spec_from_file_location("g5_inspect_encrypted_source", SOURCE)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
PROJECT = "nywxpvzhlpqjtcafpdfe"
PASS = "S" * 40  # Synthetic fixture, never use it for a real backup.


def make_ciphertext(path: Path, clear: bytes, password: str = PASS) -> None:
    """Create a synthetic symmetric fixture; never pass a password in argv."""
    reader, writer = os.pipe()
    try:
        proc = subprocess.Popen(
            [shutil.which("gpg"), "--batch", "--no-tty",
             "--pinentry-mode", "loopback", "--no-symkey-cache",
             "--passphrase-fd", str(reader), "--cipher-algo", "AES256",
             "--symmetric", "--output", str(path)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, pass_fds=(reader,),
        )
        os.close(reader)
        reader = None
        os.write(writer, password.encode("ascii") + b"\n")
        os.close(writer)
        writer = None
        proc.communicate(clear, timeout=30)
        if proc.returncode != 0:
            raise RuntimeError("synthetic GPG fixture failed")
    finally:
        for fd in (reader, writer):
            if fd is not None:
                os.close(fd)


class G5InspectTests(unittest.TestCase):
    def test_pg_restore_requires_version_17(self):
        with patch.object(m.shutil, "which", return_value="/usr/bin/pg_restore"):
            for version in ("16.15", "invalid"):
                with self.subTest(version=version):
                    with patch.object(m.subprocess, "run", return_value=MagicMock(
                        returncode=0, stdout="pg_restore (PostgreSQL) " + version)):
                        with self.assertRaises(m.ArchiveBlocked) as e:
                            m.pg_restore_binary()
                        self.assertEqual(str(e.exception), "PG_RESTORE_VERSION_UNSUPPORTED")
            with patch.object(m.subprocess, "run", return_value=MagicMock(
                returncode=0, stdout="pg_restore (PostgreSQL) 17.11 (Ubuntu)")):
                self.assertEqual(m.pg_restore_binary(), "/usr/bin/pg_restore")

    def test_manifest_checked_before_password_prompt_or_decryption(self):
        import sys
        with patch.object(sys, "argv", [
            "g5_inspect", "--manifest", "/private/nonexistent",
            "--source-project-ref", PROJECT,
        ]):
            with patch.object(m, "validated_archive",
                              side_effect=m.ArchiveBlocked("MANIFEST_INVALID")):
                with patch.object(m.getpass, "getpass") as secret:
                    with patch.object(m, "decrypt_and_check_toc") as decrypt:
                        with contextlib.redirect_stdout(io.StringIO()) as printed:
                            self.assertEqual(m.main(), 2)
                        secret.assert_not_called()
                        decrypt.assert_not_called()
                        self.assertNotIn("nonexistent", printed.getvalue())

    def test_reject_other_project_ref_and_tampered_encrypted_bytes(self):
        from scripts.operations import g5_archive_supabase_source as g5
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / f"source-{PROJECT}-20261028T145054Z-1557baa82308af9b.dump.gpg"
            archive.write_bytes(b"not encrypted test bytes")
            receipt = {
                "version": 1, "project_ref": PROJECT,
                "captured_at": "20261028T145054Z", "archive_name": archive.name,
                "format": "pg_dump_custom_openpgp_symmetric", "restore_verified": False,
                "encrypted_bytes": archive.stat().st_size,
                "encrypted_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            }
            manifest = root / (archive.name + ".manifest.json")
            manifest.write_text(json.dumps(receipt), encoding="utf-8")
            with patch.object(g5, "private_directory"), patch.object(g5, "check_private_file"):
                with self.assertRaises(m.ArchiveBlocked):
                    m.validated_archive(manifest, "cenhadslwxgykqtuobgc", root)
                self.assertEqual(m.validated_archive(manifest, PROJECT, root), archive)
                archive.write_bytes(b"tampered")
                with self.assertRaises(m.ArchiveBlocked):
                    m.validated_archive(manifest, PROJECT, root)

    @unittest.skipUnless(os.name == "posix" and shutil.which("gpg"), "Requires Linux GPG")
    def test_real_symmetric_gpg_roundtrip_and_fake_pg_restore_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            encrypted = root / "sample.dump.gpg"
            # Large fixture: GPG must be fully drained even when TOC parser exits.
            fake_clear = b"PGDMP" + b"SYNTHETIC_DEMO_DATA_ONLY" * 50000
            make_ciphertext(encrypted, fake_clear)
            fake_restore = root / "pg_restore_fixture"
            fake_restore.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "head = sys.stdin.buffer.read(5)\n"
                "if head != b'PGDMP': sys.exit(3)\n"
                "sys.stdout.write('; list of archive entries\\n'"
                "+'1; 0 0 TABLE public SENSITIVE_TABLE_NAME fake-owner\\n'"
                "+'2; 0 0 TABLE DATA public ANOTHER_PRIVATE_NAME fake-owner\\n')\n",
                encoding="ascii",
            )
            fake_restore.chmod(0o700)
            with patch.dict(os.environ, {"GNUPGHOME": str(root / "gnupg")}):
                (root / "gnupg").mkdir(mode=0o700)
                with contextlib.redirect_stdout(io.StringIO()) as captured:
                    size, entries = m.decrypt_and_check_toc(encrypted, PASS, str(fake_restore))
            self.assertEqual(size, len(fake_clear))
            self.assertEqual(entries, 2)
            self.assertNotIn("SENSITIVE_TABLE_NAME", captured.getvalue())
            self.assertNotIn("ANOTHER_PRIVATE_NAME", captured.getvalue())
            self.assertEqual(captured.getvalue(), "")
            with patch.dict(os.environ, {"GNUPGHOME": str(root / "gnupg")}):
                with self.assertRaises(m.ArchiveBlocked) as err:
                    m.decrypt_and_check_toc(encrypted, "W" * 40, str(fake_restore))
            self.assertEqual(str(err.exception), "GPG_DECRYPTION_FAILED")

    def test_toc_is_counted_without_names_or_sql(self):
        output = io.BytesIO(
            b"; metadata from dump\n"
            b"1; 0 0 TABLE public confidential_companies role\n"
            b"2; 0 0 FUNCTION public sensitive_function role\n"
            b"; private comment\n"
        )
        counts = [0]
        m.read_toc_counts(output, counts)
        self.assertEqual(counts[0], 2)

    def test_inspect_cli_emits_only_safe_codes_and_cannot_restore(self):
        import sys
        manifest = Path("/root/private/fixture.manifest.json")
        with patch.object(sys, "argv", [
            "g5_inspect", "--manifest", str(manifest),
            "--source-project-ref", PROJECT,
        ]):
            with patch.object(m, "validated_archive",
                              return_value=Path("/root/private/fixture.gpg")):
                with patch.object(m, "pg_restore_binary", return_value="/usr/bin/pg_restore"):
                    with patch.object(m.sys.stdin, "isatty", return_value=True):
                        with patch.object(m.getpass, "getpass", return_value=PASS):
                            with patch.object(m, "decrypt_and_check_toc",
                                              return_value=(100, 13)) as inspected:
                                with contextlib.redirect_stdout(io.StringIO()) as output:
                                    self.assertEqual(m.main(), 0)
            self.assertIn("G5_ARCHIVE_DECRYPTION=PASS", output.getvalue())
            self.assertIn("G5_PG_RESTORE_TOC_ENTRIES=13", output.getvalue())
            self.assertIn("G5_RESTORE_TEST=NOT_PERFORMED", output.getvalue())
            self.assertNotIn("G5_RESTORE_TEST=PASS", output.getvalue())
            inspected.assert_called_once()


if __name__ == "__main__":
    unittest.main()
